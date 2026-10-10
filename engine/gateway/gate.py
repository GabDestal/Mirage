"""The gate: every production tool call is checked before it runs.

`check(run, tool, args)` decides and returns at once (used by the HTTP data plane: the SDK then
waits on `GET /runs/{id}/wait` while frozen). `execute` is the in-process path of the dev harness:
check, wait while frozen, then run the tool.

Order: global STOP, run status, layer 1 hard rules. A rule hit freezes only that run. A human
unfreezes it (the blocked call then runs) or kills it. The agent never holds credentials.
Incidents live only in the event log (engine/api/state.py folds them). Live runs and agents
are in memory: a run's thread and its freeze lock belong to the process that runs it.
"""

import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from contracts.models import AgentSpec, GateDecision, HumanAction, Run
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
    calls: dict = field(default_factory=dict)  # call_id -> {tool, args}, to pair results
    revoked_by_reset: bool = False  # fences pending checks after incident ids are reused
    check_lock: Any = field(default_factory=threading.Lock)  # serialize this run only
    resume: threading.Event = field(default_factory=threading.Event)  # set = not frozen
    # how to rebuild the agent in a detonation (set by the agent at start)
    entrypoint: str = ""
    system: str = ""
    model_id: str = ""
    legit: dict = field(default_factory=dict)  # "legit task completed" check: {tool, to}
    restarted_from: str | None = None  # a clean restart of this run, approved by a human
    # dev harness only
    user_name: str = ""
    user_email: str = ""
    calendar: str = ""
    services: Any = None
    messages: list = field(default_factory=list)

    def model(self) -> Run:
        return Run(id=self.id, agent=self.agent, env="prod", task=self.task, status=self.status,
                   started_at=self.started_at, ended_at=self.ended_at,
                   incident_id=self.incident_id, tool_calls=self.tool_calls,
                   restarted_from=self.restarted_from)


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
    spec = agents.get(agent)
    if spec is None:
        return POLICY
    return {"canary": POLICY["canary"], "agents": {agent: {"tools": spec.allow.tools}},
            "destinations": {"email_domains": spec.allow.email_to,
                             "url_domains": spec.allow.url_hosts},
            "known_tools": spec.tools}  # every tool the agent has, allowed or not


def is_known(policy, tool):
    """False only when the agent declared its tools and this is not one of them."""
    return "known_tools" not in policy or tool in policy["known_tools"]


def set_status(run, to, actor, reason):
    emit("run.status", {"from": run.status, "to": to, "actor": actor, "reason": reason},
         run_id=run.id, incident_id=run.incident_id)
    run.status = to
    if to in ("completed", "killed", "halted"):
        run.ended_at = datetime.now(UTC)
    if to == "frozen":
        run.resume.clear()
    else:
        run.resume.set()


def _human(actor, action, target, reason):
    emit("human.action", HumanAction(actor=actor, action=action, target=target, reason=reason,
                                     ts=datetime.now(UTC)).model_dump(mode="json"))


def freeze(run_id, actor, reason):
    _human(actor, "freeze", run_id, reason)
    set_status(runs[run_id], "frozen", actor, reason)


def unfreeze(run_id, actor, reason):
    _human(actor, "unfreeze", run_id, reason)
    set_status(runs[run_id], "running", actor, reason)


def approve(run_id, actor, reason):
    """Approval queue: the held call runs (like unfreeze), logged as an approval."""
    _human(actor, "approve", run_id, reason)
    set_status(runs[run_id], "running", actor, reason)


def reject(run_id, actor, reason):
    """Approval queue: the held call never runs and the run ends (like kill)."""
    _human(actor, "reject", run_id, reason)
    set_status(runs[run_id], "killed", actor, reason)


def kill(run_id, actor, reason):
    _human(actor, "kill", run_id, reason)
    set_status(runs[run_id], "killed", actor, reason)


def global_stop(actor, reason):
    with jobs.lock:
        _global_stop(actor, reason)


def _global_stop(actor, reason):
    STOP.set()
    _human(actor, "global_stop", "all", reason)
    emit("global.stop", {"actor": actor, "reason": reason})
    for run in runs.values():
        if run.status in ("queued", "running", "frozen"):
            set_status(run, "halted", actor, reason)


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
        run.calls[call_id] = {"tool": tool, "args": args}
        emit("tool.requested", {"call_id": call_id, "tool": tool, "args": args}, run_id=run.id)
        policy = policy_for(run.agent)
        evaluate = not STOP.is_set() and run.status not in (
            "frozen", "killed", "halted", "completed") and is_known(policy, tool)

    # A slow decision must not hold up healthy runs, STOP, or reset. Recheck authority below.
    hit = hard_rule(run.agent, tool, args, policy) if evaluate else None
    judged = None  # layer 2: only outbound calls the hard rules allowed
    if evaluate and not hit:
        judged = decision_model.judge(run.agent, run.task, tool, args)
        if judged and "policy_id" in judged and not judged["review"]:
            hit = (None, judged["explanation"])
    review = judged if judged and judged.get("review") else None  # medium risk: ask a human
    with jobs.lock:
        if STOP.is_set() or run.status in ("killed", "halted", "completed"):
            hit = None
            decision, rule = "block", ("RUN_REVOKED", f"Run is {run.status}; access is revoked.")
        elif run.status == "frozen":
            hit = None
            decision, rule = "freeze", ("RUN_FROZEN", "Run is frozen; waiting for a human.")
        elif not is_known(policy, tool):
            hit = None
            decision, rule = "allow", ("UNKNOWN_TOOL",
                                       f"{tool} is not one of the agent's tools; nothing can run.")
        elif not evaluate:
            # A human may have released a freeze while this check was in flight. Keep this
            # call held; the SDK's wait observes the release without bypassing a new check.
            decision, rule = "freeze", ("RUN_FROZEN", "Run was frozen; waiting for a human.")
        elif hit:
            decision, rule = "freeze", hit
        elif review:  # held like a freeze (the SDK waits), but no incident: a human decides
            decision, rule = "freeze", ("NEEDS_APPROVAL", (f"Waiting for a human to approve "
                                        f"({review['policy_id']}, p={review['p']}): "
                                        f"{review['explanation']}"))
        else:
            decision, rule = "allow", (None, "No rule matched." + (
                f" Layer 2 unavailable: {judged['unavailable']}" if judged else ""))

        held = decision == "freeze" and rule[0] == "NEEDS_APPROVAL"
        by_model = bool((hit or held) and judged and "policy_id" in judged)
        gate = GateDecision(call_id=call_id, tool=tool, args=args, decision=decision,
                            layer="decision_model" if by_model else "hard_rule",
                            rule_id=rule[0], explanation=rule[1],
                            policy_id=judged["policy_id"] if by_model else None,
                            p=judged["p"] if by_model else None)
        if hit:
            run.incident_id = next_id("incident")
        # Reset revokes the old run while a decision is pending; don't write its old ids into
        # the new log. STOP/kill on an existing run still get their normal decision evidence.
        if run.revoked_by_reset:
            return gate
        emit("gate.decision", gate.model_dump(mode="json"), run_id=run.id,
             incident_id=run.incident_id if hit else None)
        if held:
            set_status(run, "frozen", "gate", rule[1])
        if hit:
            spec = agents.get(run.agent)
            snap = snapshot.save(run, run.incident_id, policy,
                                 entrypoint=spec.entrypoint if spec else "",
                                 runner=SDK_RUNNER if spec else None)
            emit("incident.opened", {"incident_id": run.incident_id, "trigger_call_id": call_id,
                                     "inputs": [i.model_dump() for i in snapshot.inputs(snap)]},
                 run_id=run.id, incident_id=run.incident_id)
            set_status(run, "frozen", "gate", rule[1])
            if os.getenv("MIRAGE_MODE", "live") != "replay":
                jobs.automatic(run.incident_id, run)
        return gate


def record_result(run, call_id, tool, result, error=None):
    args = run.calls.get(call_id, {}).get("args", {})
    run.tool_results.append({"call_id": call_id, "tool": tool, "args": args, "result": result,
                             "error": error})
    emit("tool.result", {"call_id": call_id, "tool": tool, "result": result, "error": error},
         run_id=run.id)


def execute(run, tool, args):
    """Dev harness path: check, wait while frozen, run the tool in-process."""
    gate = check(run, tool, args)
    if gate.decision == "freeze":
        run.resume.wait()  # only this run's thread waits; a human decides
    if gate.decision == "block" or run.status != "running":
        return {"error": "Access revoked by Mirage."}
    try:
        result = tools.dispatch(run, tool, args)
    except Exception as e:  # noqa: BLE001 - bad arguments from the model: report, keep the run
        result = {"error": f"{type(e).__name__}: {e}"}
    record_result(run, gate.call_id, tool, result, result.get("error"))
    return result
