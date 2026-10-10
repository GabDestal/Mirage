"""The gate: every production tool call goes through `execute(run, tool, args)`.

Order: global STOP, run status, layer 1 hard rules. A rule hit freezes the run: its thread
waits at the blocked call until a human unfreezes it (the call then runs) or kills it.
Other runs have their own lock and continue. The agent never holds credentials.
"""

import itertools
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from contracts.models import GateDecision, HumanAction
from engine.detection.rules import hard_rule
from engine.dev import (
    tools,  # shortcut: in-process tool dispatch until the SDK data plane (§11) replaces it
)
from engine.store.events import emit

STOP = threading.Event()  # global STOP: halts every run
runs: dict[str, "LiveRun"] = {}

_call_ids = itertools.count(1)
_incident_ids = itertools.count(1)


@dataclass
class LiveRun:
    id: str
    agent: str
    task: str
    user_name: str
    user_email: str
    calendar: str
    services: Any  # production adapters (fakes until the real keys arrive)
    status: str = "queued"
    incident_id: str | None = None
    tool_calls: int = 0
    messages: list = field(default_factory=list)  # full agent context, for the snapshot
    resume: threading.Event = field(default_factory=threading.Event)


def set_status(run, to, actor, reason):
    emit("run.status", {"from": run.status, "to": to, "actor": actor, "reason": reason},
         run_id=run.id, incident_id=run.incident_id)
    run.status = to


def _human(actor, action, target, reason):
    emit("human.action", HumanAction(actor=actor, action=action, target=target, reason=reason,
                                     ts=datetime.now(UTC)).model_dump(mode="json"))


def unfreeze(run_id, actor, reason):
    run = runs[run_id]
    _human(actor, "unfreeze", run_id, reason)
    set_status(run, "running", actor, reason)
    run.resume.set()


def kill(run_id, actor, reason):
    run = runs[run_id]
    _human(actor, "kill", run_id, reason)
    set_status(run, "killed", actor, reason)
    run.resume.set()


def global_stop(actor, reason):
    STOP.set()
    _human(actor, "global_stop", "all", reason)
    emit("global.stop", {"actor": actor, "reason": reason})
    for run in runs.values():
        if run.status in ("queued", "running", "frozen"):
            set_status(run, "halted", actor, reason)
            run.resume.set()


def execute(run, tool, args):
    call_id = f"call_{next(_call_ids):03d}"
    run.tool_calls += 1
    emit("tool.requested", {"call_id": call_id, "tool": tool, "args": args}, run_id=run.id)

    def decide(decision, rule_id, explanation):
        gate = GateDecision(call_id=call_id, tool=tool, args=args, decision=decision,
                            layer="hard_rule", rule_id=rule_id, explanation=explanation)
        emit("gate.decision", gate.model_dump(mode="json"), run_id=run.id,
             incident_id=run.incident_id)

    if STOP.is_set() or run.status != "running":
        decide("block", "RUN_REVOKED", f"Run is {run.status}; access is revoked.")
        return {"error": "Access revoked by Mirage."}

    hit = hard_rule(run.agent, tool, args)
    if hit:
        run.incident_id = f"inc_{next(_incident_ids):03d}"
        decide("freeze", *hit)
        emit("incident.opened", {"incident_id": run.incident_id, "trigger_call_id": call_id},
             run_id=run.id, incident_id=run.incident_id)
        set_status(run, "frozen", "gate", hit[1])
        run.resume.wait()  # only this run's thread waits; a human decides
        if run.status != "running":
            return {"error": "Access revoked by Mirage."}
    else:
        decide("allow", None, "No rule matched.")

    try:
        result = tools.dispatch(run, tool, args)
    except Exception as e:  # noqa: BLE001 - bad arguments from the model: report back, do not crash the run
        result = {"error": f"{type(e).__name__}: {e}"}
    emit("tool.result", {"call_id": call_id, "tool": tool, "result": result,
                         "error": result.get("error")}, run_id=run.id)
    return result
