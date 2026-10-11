"""The gate: every production tool call is checked before it runs.

`check(run, tool, args)` decides and returns at once (used by the HTTP data plane: the SDK then
waits on `GET /runs/{id}/wait` while frozen). `execute` is the in-process path of the dev harness:
check, wait while frozen, then run the tool.

Order: global STOP, run status, layer 1 hard rules, layer 2. A rule hit freezes only that run.
Escalation: an agent that keeps reaching for tools it does not have (probing for a way around)
is frozen at the MIRAGE_ESCALATE_AFTER-th attempt (default 2), with an incident. A human
unfreezes it (the blocked call then runs) or kills it. The agent never holds credentials.
Incidents live only in the event log (engine/api/state.py folds them). Live runs and agents
are in memory: a run's thread and its freeze lock belong to the process that runs it.
"""

import builtins
import copy
import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from contracts.models import AgentSpec, AutomaticClearance, GateDecision, HumanAction, Run
from engine.config import MODE
from engine.detection import decision_model
from engine.detection.rules import POLICY, hard_rule
from engine.detonation import jobs, snapshot
from engine.dev import tools  # shortcut: in-process tool dispatch, dev harness only
from engine.store import events
from engine.store.events import emit

STOP = threading.Event()  # global STOP: halts every run
SDK_RUNNER = "mirage.sandbox:run"  # sandbox runner for agents registered through the SDK
agents: dict[str, AgentSpec] = {}
runs: dict[str, "LiveRun"] = {}

PREFIX = {"run": "run", "call": "call", "incident": "inc"}
_last = dict.fromkeys(PREFIX, 0)
_id_lock = threading.Lock()


def next_id(kind):
    """Next id, after both this process's last one and the highest in the shared log."""
    with _id_lock:
        _last[kind] = max(_last[kind], events.max_number(PREFIX[kind])) + 1
        return f"{PREFIX[kind]}_{_last[kind]:03d}"


@dataclass
class LiveRun:
    id: str
    agent: str
    task: str
    status: str = "queued"
    incident_id: str | None = None
    tool_calls: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    model_calls: list = field(default_factory=list)  # snapshot material
    tool_results: list = field(default_factory=list)  # snapshot material
    calls: dict = field(default_factory=dict)  # checked call identity and admission/result state
    containment_generation: int = 0
    medium_call_id: str | None = None
    revoked_by_reset: bool = False  # fences pending checks after incident ids are reused
    check_lock: Any = field(default_factory=threading.Lock)  # serialize this run only
    resume: threading.Event = field(default_factory=threading.Event)  # set = not frozen
    # how to rebuild the agent in a detonation (set by the agent at start)
    entrypoint: str = ""
    system: str = ""
    model_id: str = ""
    legit: dict = field(default_factory=dict)  # "legit task completed" check: {tool, to}
    admitted_spec: AgentSpec | None = None
    policy: dict = field(init=False)
    restarted_from: str | None = None  # a clean restart of this run, approved by a human
    probes: list = field(default_factory=list)  # tools it asked for and does not have
    # dev harness only
    user_name: str = ""
    user_email: str = ""
    calendar: str = ""
    services: Any = None
    messages: list = field(default_factory=list)
    status_reason: str | None = None

    def __post_init__(self):
        self.admitted_spec = copy.deepcopy(self.admitted_spec or agents.get(self.agent))
        self.policy = copy.deepcopy(_policy_from_spec(self.agent, self.admitted_spec))
        if self.admitted_spec is not None:
            self.legit = copy.deepcopy(self.admitted_spec.legit)

    def model(self) -> Run:
        return Run(id=self.id, agent=self.agent, env="prod", task=self.task, status=self.status,
                   started_at=self.started_at, ended_at=self.ended_at,
                   incident_id=self.incident_id, tool_calls=self.tool_calls,
                   restarted_from=self.restarted_from, status_reason=self.status_reason)


def reset():
    with jobs.lock:
        for run in runs.values():
            run.revoked_by_reset = True
            run.status = "halted"
            run.resume.set()
        STOP.clear()
        agents.clear()
        runs.clear()
        _last.update(dict.fromkeys(PREFIX, 0))


def policy_for(agent):
    """Registered agents bring their own allowlist (AgentSpec); others use policies.yaml."""
    return _policy_from_spec(agent, agents.get(agent))


def _policy_from_spec(agent, spec):
    if spec is None:
        return POLICY
    return {"canary": POLICY["canary"], "agents": {agent: {"tools": spec.allow.tools}},
            "destinations": {"email_domains": spec.allow.email_to,
                             "url_domains": spec.allow.url_hosts},
            "known_tools": spec.tools}  # every tool the agent has, allowed or not


def is_known(policy, tool):
    """False only when the agent declared its tools and this is not one of them."""
    return "known_tools" not in policy or tool in policy["known_tools"]


def is_probe(policy, tool):
    """An unknown tool that is not a garbled known one (gpt-oss glues junk onto real names)."""
    return not any(name in tool for name in policy.get("known_tools", []))


def _apply_status(run, to, reason):
    previous = run.status
    if to in ("frozen", "completed", "failed", "killed", "halted"):
        run.containment_generation += 1
        for call in run.calls.values():
            if call["state"] == "held":
                call["state"] = "revoked"
    run.status = to
    run.status_reason = reason
    if to in ("completed", "failed", "killed", "halted"):
        run.ended_at = datetime.now(UTC)
    if to == "frozen":
        run.resume.clear()
    else:
        run.resume.set()
    return previous


def _emit_status(run, previous, to, actor, reason, expected_epoch=None):
    emit("run.status", {"from": previous, "to": to, "actor": actor, "reason": reason},
         run_id=run.id, incident_id=run.incident_id, expected_epoch=expected_epoch)


def set_status(run, to, actor, reason, *, expected_epoch=None):
    if to == "running":
        _emit_status(run, run.status, to, actor, reason, expected_epoch)
        if expected_epoch is not None and events.read_batch()[0] != expected_epoch:
            raise events.StaleEpoch("Recovery evidence belongs to a replaced stream")
        # Install release authority after durable evidence, before waking any waiter.
        for call in run.calls.values():
            if call["state"] == "held" and call["generation"] == run.containment_generation:
                call["released"] = True
        _apply_status(run, to, reason)
    else:
        previous = _apply_status(run, to, reason)
        _emit_status(run, previous, to, actor, reason, expected_epoch)


def clearance(run, incident_id, call, status, reason, epoch=None):
    evidence = AutomaticClearance(status=status, reason=reason)
    emit("agent.message", {"role": "system", "text": f"Automatic clearance {status}.",
         "automatic_clearance": evidence.model_dump()}, run_id=run.id,
         incident_id=incident_id, env="mirage", expected_epoch=epoch)
    call["automatic_status"] = status


def _human(actor, action, target, reason):
    emit("human.action", HumanAction(actor=actor, action=action, target=target, reason=reason,
                                     ts=datetime.now(UTC)).model_dump(mode="json"))


def _control(run_id, to, action, actor, reason, call_id=None):
    with jobs.lock:
        run = runs[run_id]
        allowed = ("frozen",) if to == "running" else ("running", "frozen")
        if (run.status not in allowed or run.revoked_by_reset
                or (to == "running" and STOP.is_set())):
            raise ValueError(f"Cannot {action} a run that is {run.status} or revoked.")
        medium = run.calls.get(run.medium_call_id)
        if to == "running" and medium and not medium.get("released"):
            raise CallAuthorityError("Medium suspicion requires conclusive initial sandbox clearance.")
        if action == "approve":
            raise CallAuthorityError("Live medium approvals have been replaced by sandbox clearance.")
        if action in ("approve", "reject"):
            pending = [cid for cid, call in run.calls.items()
                       if call["state"] == "held" and not call["released"]
                       and call["generation"] == run.containment_generation
                       and call["rule_id"] == "NEEDS_APPROVAL"]
            if len(pending) != 1 or (call_id is not None and call_id != pending[0]):
                raise CallAuthorityError("The original call is no longer waiting for approval.")
        if to == "running":
            _human(actor, action, run_id, reason)
            set_status(run, to, actor, reason)
        else:
            previous = _apply_status(run, to, reason)
            try:
                _human(actor, action, run_id, reason)
            finally:
                _emit_status(run, previous, to, actor, reason)


def freeze(run_id, actor, reason):
    _control(run_id, "frozen", "freeze", actor, reason)


def unfreeze(run_id, actor, reason):
    _control(run_id, "running", "unfreeze", actor, reason)


def approve(run_id, actor, reason, call_id=None):
    """Approval queue: the held call runs (like unfreeze), logged as an approval."""
    _control(run_id, "running", "approve", actor, reason, call_id)


def reject(run_id, actor, reason, call_id=None):
    """Approval queue: the held call never runs and the run ends (like kill)."""
    _control(run_id, "killed", "reject", actor, reason, call_id)


def kill(run_id, actor, reason):
    _control(run_id, "killed", "kill", actor, reason)


def global_stop(actor, reason):
    with jobs.lock:
        _global_stop(actor, reason)


def _global_stop(actor, reason):
    STOP.set()
    halted = []
    for run in runs.values():
        if run.status in ("queued", "running", "frozen"):
            halted.append((run, _apply_status(run, "halted", reason)))
    # Revoke every run first; attempt all evidence writes and still report their failure.
    try:
        _human(actor, "global_stop", "all", reason)
    finally:
        try:
            emit("global.stop", {"actor": actor, "reason": reason})
        finally:
            failure = None
            for run, previous in halted:
                try:
                    _emit_status(run, previous, "halted", actor, reason)
                except Exception as error:  # noqa: BLE001 - finish diagnostics, then fail
                    if failure is None:
                        failure = error
            if failure is not None:
                raise failure


def lift_stop(actor, reason):
    """Halted runs stay halted: resume relaunches them (POST /runs/{id}/resume, /resume-all)."""
    with jobs.lock:
        _human(actor, "lift_stop", "all", reason)
        emit("global.stop_lifted", {"actor": actor, "reason": reason})
        STOP.clear()


def check(run, tool, args) -> GateDecision:
    with run.check_lock:
        return _check(run, tool, args)


def _check(run, tool, args) -> GateDecision:
    with jobs.lock:
        if run.revoked_by_reset:
            return GateDecision(call_id=next_id("call"), tool=tool, args=args, decision="block",
                                layer="hard_rule", rule_id="RUN_REVOKED",
                                explanation="Run was revoked by demo reset.")
        call_id = next_id("call")
        run.tool_calls += 1
        generation = run.containment_generation
        call = run.calls[call_id] = {"tool": tool, "args": copy.deepcopy(args),
                                    "token": run.token, "state": "revoked",
                                    "generation": generation, "was_held": False}
        emit("tool.requested", {"call_id": call_id, "tool": tool, "args": args}, run_id=run.id)
        policy = run.policy
        evaluate = not STOP.is_set() and run.status not in (
            "frozen", "killed", "halted", "completed", "failed") and is_known(policy, tool)

    # A slow decision must not hold up healthy runs, STOP, or reset. Recheck authority below.
    hit = hard_rule(run.agent, tool, args, policy) if evaluate else None
    judged = None  # layer 2: only outbound calls the hard rules allowed
    if evaluate and not hit:
        judged = decision_model.judge(run.agent, run.task, tool, args)
        if judged and "policy_id" in judged and not judged["review"]:
            hit = (None, judged["explanation"])
    review = judged if judged and judged.get("review") else None
    with jobs.lock:
        if STOP.is_set() or run.status in ("killed", "halted", "completed", "failed"):
            hit = None
            decision, rule = "block", ("RUN_REVOKED", f"Run is {run.status}; access is revoked.")
        elif run.status == "frozen":
            hit = None
            decision, rule = "block", ("RUN_FROZEN", "Run is frozen; no new call may run.")
        elif generation != run.containment_generation:
            hit = None
            decision, rule = "block", ("RUN_REVOKED", "Containment changed during this check.")
        elif not is_known(policy, tool):
            hit = None
            decision, rule = "block", ("UNKNOWN_TOOL",
                                       f"{tool} is not registered; execution is blocked.")
            if is_probe(policy, tool):
                run.probes.append(tool)
                if len(run.probes) >= int(os.getenv("MIRAGE_ESCALATE_AFTER", "2")):
                    hit = ("ESCALATION", (f"Escalation: {len(run.probes)} attempts to use tools "
                                          f"this agent does not have ({', '.join(run.probes)}). "
                                          f"It looks for a way around its permissions."))
                    decision, rule = "freeze", hit
        elif not evaluate:
            decision, rule = "block", ("RUN_FROZEN", "This call was not evaluated while frozen.")
        elif hit:
            decision, rule = "freeze", hit
        elif review:
            decision, rule = "freeze", ("SANDBOX_REVIEW", (f"Checking in Mirage "
                                        f"({review['policy_id']}, p={review['p']}): "
                                        f"{review['explanation']}"))
        else:
            decision, rule = "allow", (None, "No rule matched." + (
                f" Layer 2 unavailable: {judged['unavailable']}" if judged else ""))

        held = decision == "freeze" and rule[0] == "SANDBOX_REVIEW"
        by_model = bool((hit or held) and judged and "policy_id" in judged)
        gate = GateDecision(call_id=call_id, tool=tool, args=args, decision=decision,
                            layer="decision_model" if by_model else "hard_rule",
                            rule_id=rule[0], explanation=rule[1],
                            policy_id=judged["policy_id"] if by_model else None,
                            p=judged["p"] if by_model else None)
        if hit or held:
            run.incident_id = next_id("incident")
            run.medium_call_id = call_id if held else None
        # Reset revokes the old run while a decision is pending; don't write its old ids into
        # the new log. STOP/kill on an existing run still get their normal decision evidence.
        if run.revoked_by_reset:
            return gate
        # Containment is authority, not evidence: a failed write must never leave it running.
        if hit or held:
            set_status(run, "frozen", "gate", rule[1])
        emit("gate.decision", gate.model_dump(mode="json"), run_id=run.id,
             incident_id=run.incident_id if hit or held else None)
        if decision == "allow" and is_known(policy, tool):
            call["state"] = "admitted"
        elif decision == "freeze":
            # Probe escalation contains the run, but an unregistered callback cannot be released.
            call.update(state="held" if is_known(policy, tool) else "revoked",
                        generation=run.containment_generation, was_held=True,
                        released=False, rule_id=rule[0])
        if hit or held:
            spec = run.admitted_spec
            try:
                snap = snapshot.save(run, run.incident_id, policy,
                                     entrypoint=spec.entrypoint if spec else "",
                                     runner=SDK_RUNNER if spec else None)
            except Exception as error:  # noqa: BLE001 - containment survives persistence failure
                emit("incident.opened", {"incident_id": run.incident_id,
                                         "trigger_call_id": call_id},
                     run_id=run.id, incident_id=run.incident_id)
                if held:
                    clearance(run, run.incident_id, call, "inconclusive", "snapshot_failed")
                emit("detonation.failed", {"incident_id": run.incident_id, "detonation_id": "",
                     "error": f"Snapshot persistence failed ({type(error).__name__}); "
                              "production remains frozen. Repair the snapshot before retrying."},
                     run_id=run.id, incident_id=run.incident_id, env="mirage")
                return gate
            emit("incident.opened", {"incident_id": run.incident_id, "trigger_call_id": call_id,
                                     "inputs": [i.model_dump() for i in snapshot.inputs(snap)]},
                 run_id=run.id, incident_id=run.incident_id)
            if held:
                clearance(run, run.incident_id, call, "checking", "initial_baseline")
            if MODE == "live":
                jobs.automatic(run.incident_id, run)
        return gate


def error_type(error):
    """Retain a known category only; provider text and custom names may contain credentials."""
    name = error.partition(":")[0].strip() if isinstance(error, str) else ""
    kind = getattr(builtins, name, None)
    if name in {"ClientError", "HTTPStatusError", "ValidationError", "ExecutionError"} or (
            isinstance(kind, type) and issubclass(kind, BaseException)):
        return name
    return "ExecutionError"


class CallAuthorityError(ValueError):
    """A call has no remaining admission or result authority for this run."""


def _wait_status(run, call_id):
    if call_id is not None:
        call = run.calls.get(call_id)
        if (run.revoked_by_reset or not call or call["token"] != run.token
                or call["state"] != "held"
                or call["generation"] != run.containment_generation or STOP.is_set()):
            raise CallAuthorityError("This held call is unknown, revoked, or already admitted.")
        if run.status == "running" and call["released"]:
            call["state"] = "admitted"
            return "running"
        if run.status != "frozen":
            raise CallAuthorityError("This held call has no approved release.")
    elif run.status == "running" and any(
            call["was_held"] and call["state"] in ("held", "revoked")
            for call in run.calls.values()):
        raise CallAuthorityError("The original checked call_id is required to claim this release.")
    return "halted" if run.status == "completed" else (
        "running" if run.status == "queued" else run.status)


def wait(run, call_id=None, timeout=25):
    """Status-only legacy polling, or one atomic admission of the original held call."""
    with jobs.lock:
        status = _wait_status(run, call_id)
    if status == "frozen":
        run.resume.wait(timeout)
        with jobs.lock:
            status = _wait_status(run, call_id)
    return status


def record_result(run, call_id, tool, result, error=None):
    with jobs.lock:
        call = run.calls.get(call_id)
        if (run.revoked_by_reset or not call or call["tool"] != tool
                or call["token"] != run.token or call["state"] not in ("admitted", "consumed")):
            raise CallAuthorityError("This call is not admitted for this run and tool.")
        if error is not None:
            error, result = error_type(error), None
        recorded = {"call_id": call_id, "tool": tool, "args": call["args"],
                    "result": result, "error": error}
        if call["state"] == "consumed":
            if (json.dumps(call["result"], sort_keys=True, default=str)
                    != json.dumps(recorded, sort_keys=True, default=str)):
                raise CallAuthorityError("This call already recorded a different result.")
            return
        emit("tool.result", {"call_id": call_id, "tool": tool, "result": result, "error": error},
             run_id=run.id)
        call["state"], call["result"] = "consumed", copy.deepcopy(recorded)
        run.tool_results.append(call["result"])


def execute(run, tool, args):
    """Dev harness path: check, wait while frozen, run the tool in-process."""
    gate = check(run, tool, args)
    if gate.decision == "freeze":
        try:
            wait(run, gate.call_id, timeout=None)  # only this run's thread waits
        except CallAuthorityError:
            return {"error": "Access revoked by Mirage."}
    if gate.decision == "block" or run.status != "running":
        return {"error": "Access revoked by Mirage."}
    try:
        result = tools.dispatch(run, tool, args)
    except Exception as e:  # noqa: BLE001 - bad arguments from the model: report, keep the run
        result = {"error": f"{type(e).__name__}: {e}"}
    record_result(run, gate.call_id, tool, result, result.get("error"))
    return result
