"""The gate: every production tool call is checked before it runs.

`check(run, tool, args)` decides and returns at once (used by the HTTP data plane: the SDK then
waits on `GET /runs/{id}/wait` while frozen). `execute` is the in-process path of the dev harness:
check, wait while frozen, then run the tool.

Order: global STOP, run status, layer 1 hard rules. A rule hit freezes only that run. A human
unfreezes it (the blocked call then runs) or kills it. The agent never holds credentials.
shortcut: runs, agents and incidents live in memory; the event log is the durable record.
"""

import itertools
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from contracts.models import AgentSpec, GateDecision, HumanAction, Incident, Run
from engine.detection.rules import POLICY, hard_rule
from engine.detonation import snapshot
from engine.dev import tools  # shortcut: in-process tool dispatch, dev harness only
from engine.store.events import emit

STOP = threading.Event()  # global STOP: halts every run
SDK_RUNNER = "mirage_sdk.sandbox:run"  # sandbox runner for agents registered through the SDK
agents: dict[str, AgentSpec] = {}
runs: dict[str, "LiveRun"] = {}
incidents: dict[str, Incident] = {}

PREFIX = {"run": "run", "call": "call", "incident": "inc"}
_ids = {k: itertools.count(1) for k in PREFIX}


def next_id(kind):
    return f"{PREFIX[kind]}_{next(_ids[kind]):03d}"


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
    resume: threading.Event = field(default_factory=threading.Event)  # set = not frozen
    # how to rebuild the agent in a detonation (set by the agent at start)
    entrypoint: str = ""
    system: str = ""
    model_id: str = ""
    legit: dict = field(default_factory=dict)  # "legit task completed" check: {tool, to}
    # dev harness only
    user_name: str = ""
    user_email: str = ""
    calendar: str = ""
    services: Any = None
    messages: list = field(default_factory=list)

    def model(self) -> Run:
        return Run(id=self.id, agent=self.agent, env="prod", task=self.task, status=self.status,
                   started_at=self.started_at, ended_at=self.ended_at,
                   incident_id=self.incident_id, tool_calls=self.tool_calls)


def reset():
    STOP.clear()
    agents.clear()
    runs.clear()
    incidents.clear()
    _ids.update({k: itertools.count(1) for k in PREFIX})


def policy_for(agent):
    """Registered agents bring their own allowlist (AgentSpec); others use policies.yaml."""
    spec = agents.get(agent)
    if spec is None:
        return POLICY
    return {"canary": POLICY["canary"], "agents": {agent: {"tools": spec.allow.tools}},
            "destinations": {"email_domains": spec.allow.email_to,
                             "url_domains": spec.allow.url_hosts}}


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


def kill(run_id, actor, reason):
    _human(actor, "kill", run_id, reason)
    set_status(runs[run_id], "killed", actor, reason)


def global_stop(actor, reason):
    STOP.set()
    _human(actor, "global_stop", "all", reason)
    emit("global.stop", {"actor": actor, "reason": reason})
    for run in runs.values():
        if run.status in ("queued", "running", "frozen"):
            set_status(run, "halted", actor, reason)


def check(run, tool, args) -> GateDecision:
    call_id = next_id("call")
    run.tool_calls += 1
    run.calls[call_id] = {"tool": tool, "args": args}
    emit("tool.requested", {"call_id": call_id, "tool": tool, "args": args}, run_id=run.id)

    hit = None
    if STOP.is_set() or run.status in ("killed", "halted", "completed"):
        decision, rule = "block", ("RUN_REVOKED", f"Run is {run.status}; access is revoked.")
    elif run.status == "frozen":
        decision, rule = "freeze", ("RUN_FROZEN", "Run is frozen; waiting for a human.")
    elif hit := hard_rule(run.agent, tool, args, policy_for(run.agent)):
        decision, rule = "freeze", hit
    else:
        decision, rule = "allow", (None, "No rule matched.")

    gate = GateDecision(call_id=call_id, tool=tool, args=args, decision=decision,
                        layer="hard_rule", rule_id=rule[0], explanation=rule[1])
    if hit:
        run.incident_id = next_id("incident")
    emit("gate.decision", gate.model_dump(mode="json"), run_id=run.id,
         incident_id=run.incident_id if hit else None)
    if hit:
        spec = agents.get(run.agent)
        snap = snapshot.save(run, run.incident_id, policy_for(run.agent),  # freeze = snapshot
                             entrypoint=spec.entrypoint if spec else "",
                             runner=SDK_RUNNER if spec else None)
        incidents[run.incident_id] = Incident(
            id=run.incident_id, run_id=run.id, status="open", opened_at=datetime.now(UTC),
            trigger=gate, snapshot_id=snap["id"], inputs=snapshot.inputs(snap))
        emit("incident.opened", {"incident_id": run.incident_id, "trigger_call_id": call_id,
                                 "inputs": [i.model_dump() for i in snapshot.inputs(snap)]},
             run_id=run.id, incident_id=run.incident_id)
        set_status(run, "frozen", "gate", rule[1])
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
