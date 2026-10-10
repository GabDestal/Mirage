"""Mirage engine API (CONTRACTS.md §5 control plane, §11 data plane).

Run: `uv run uvicorn engine.api.server:app --port 8000`. OpenAPI at /openapi.json.
`MIRAGE_MODE=live` runs the engine. `MIRAGE_MODE=replay` plays a fixture through the same routes
(MIRAGE_FIXTURE, MIRAGE_REPLAY_SPEED: 1 = real time, 10 = 10x, inf = instant): POST actions move the replay forward; the SDK routes
answer 409. Data plane routes that act on a run need `Authorization: Bearer <run_token>`.
"""

import asyncio
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from contracts.models import (
    AgentSpec,
    Approval,
    DemoStart,
    Event,
    GateDecision,
    HumanRequest,
    Incident,
    ModelCall,
    PullRequest,
    Run,
    RunStart,
    RunStarted,
    ServiceView,
    ToolCheck,
    ToolResult,
    WaitResult,
)
from engine import bisect as engine_bisect
from engine import handoff as engine_handoff
from engine.api import services
from engine.api.replay import Replay
from engine.api.state import fold
from engine.detection.rules import POLICY
from engine.detonation import jobs, sandbox, snapshot
from engine.gateway import gate
from engine.store import events

FIXTURES = Path(__file__).parents[2] / "contracts" / "fixtures"


def _fixture():
    if os.getenv("MIRAGE_FIXTURE"):
        return os.environ["MIRAGE_FIXTURE"]
    demo = FIXTURES / "calendar_demo.jsonl"  # Liam's recorded demo, once it exists
    return demo if demo.exists() else FIXTURES / "sample_demo.jsonl"


MODE = os.getenv("MIRAGE_MODE", "live")
PUBLIC = os.getenv("MIRAGE_PUBLIC") == "1"  # exposed (tunnel): fix checks need the incident token
REPLAY = (Replay(_fixture(), float(os.getenv("MIRAGE_REPLAY_SPEED", "1")))
          if MODE == "replay" else None)

def restore():
    """After an engine restart: agent registrations and a global STOP come back from the log.
    The latest of Stop all and its lift wins."""
    for e in events.read():
        if e.type == "agent.registered":
            gate.agents[e.payload["name"]] = AgentSpec.model_validate(e.payload)
        elif e.type == "global.stop":
            gate.STOP.set()
        elif e.type == "global.stop_lifted":
            gate.STOP.clear()


@asynccontextmanager
async def lifespan(app):
    if not REPLAY:
        restore()
        jobs.start()
    yield
    if not REPLAY:
        jobs.shutdown()
    _stop_demo_agents()  # a normal shutdown (Ctrl+C) does not leave the demo fleet running


app = FastAPI(title="Mirage engine", version="0.1.0", lifespan=lifespan)


def live_only():
    if REPLAY:
        raise HTTPException(409, "Replay mode: the data plane is off (MIRAGE_MODE=live to run agents)")


def _run(run_id) -> gate.LiveRun:
    if run_id not in gate.runs:
        raise HTTPException(404, f"Unknown run {run_id}")
    return gate.runs[run_id]


def _authed(run_id, authorization) -> gate.LiveRun:
    run = _run(run_id)
    if authorization != f"Bearer {run.token}":
        raise HTTPException(401, "Missing or wrong run token")
    return run


def _state():
    """(runs, incidents) as contract models, in either mode."""
    return REPLAY.state() if REPLAY else fold(events.read())


# --- data plane: SDK -> engine ------------------------------------------------------------

data_plane = {"dependencies": [Depends(live_only)]}


@app.post("/agents", **data_plane)
def register_agent(spec: AgentSpec) -> AgentSpec:
    gate.agents[spec.name] = spec
    events.emit("agent.registered", spec.model_dump(mode="json"))  # survives an engine restart
    return spec


@app.post("/runs", **data_plane)
def start_run(body: RunStart) -> RunStarted:
    if body.agent not in gate.agents:
        raise HTTPException(404, f"Agent {body.agent} is not registered (POST /agents)")
    if gate.STOP.is_set():
        raise HTTPException(409, "Global STOP is on")
    queued = next((r for r in gate.runs.values()
                   if r.agent == body.agent and r.status == "queued"), None)
    if queued:  # an approved clean restart: this run takes it over
        gate.set_status(queued, "running", "sdk", f"Clean restart of {queued.restarted_from}.")
        return RunStarted(run_id=queued.id, run_token=queued.token)
    run = gate.LiveRun(id=gate.next_id("run"), agent=body.agent, task=body.task,
                       restarted_from=body.restarted_from)
    gate.runs[run.id] = run
    gate.set_status(run, "running", "sdk", "Run started.")
    events.emit("run.started", {"task": run.task, "agent": run.agent,
                                "restarted_from": run.restarted_from}, run_id=run.id)
    return RunStarted(run_id=run.id, run_token=run.token)


@app.post("/runs/{run_id}/model-calls", status_code=204, **data_plane)
def record_model_call(run_id: str, body: ModelCall, authorization: str = Header("")):
    run = _authed(run_id, authorization)
    run.model_calls.append(body.model_dump())
    run.model_id = run.model_id or body.model_id


@app.post("/gateway/check", **data_plane)
def check(body: ToolCheck, authorization: str = Header("")) -> GateDecision:
    return gate.check(_authed(body.run_id, authorization), body.tool, body.args)


@app.post("/runs/{run_id}/tool-results", status_code=204, **data_plane)
def record_tool_result(run_id: str, body: ToolResult, authorization: str = Header("")):
    run = _authed(run_id, authorization)
    gate.record_result(run, body.call_id, body.tool, body.result, body.error)


@app.get("/runs/{run_id}/wait", **data_plane)
def wait(run_id: str, timeout: float = 25, authorization: str = Header("")) -> WaitResult:
    run = _authed(run_id, authorization)  # sync route: runs in the threadpool, may block
    run.resume.wait(min(timeout, 60))
    status = "halted" if run.status == "completed" else run.status
    return WaitResult(status=status if status != "queued" else "running")


@app.post("/runs/{run_id}/complete", **data_plane)
def complete_run(run_id: str, authorization: str = Header("")) -> Run:
    run = _authed(run_id, authorization)
    if run.status == "running":
        gate.set_status(run, "completed", "sdk", "Task finished.")
    return run.model()


# --- control plane: web + MCP -> engine --------------------------------------------------


@app.get("/runs")
def list_runs() -> list[Run]:
    return list(_state()[0].values())


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> Run:
    runs = _state()[0]
    if run_id not in runs:
        raise HTTPException(404, f"Unknown run {run_id}")
    return runs[run_id]


@app.get("/events")
def list_events(after: int = 0) -> list[Event]:
    return REPLAY.visible(after) if REPLAY else events.read(after)


@app.get("/stream")
async def stream(request: Request, after: int = 0):
    after = int(request.headers.get("last-event-id", after))

    async def gen():
        nonlocal after
        while not await request.is_disconnected():
            for event in list_events(after):
                after = event.seq
                yield {"id": str(event.seq), "data": event.model_dump_json()}
            await asyncio.sleep(0.25)

    return EventSourceResponse(gen())


@app.get("/incidents")
def list_incidents() -> list[Incident]:
    return list(_state()[1].values())


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> Incident:
    incidents = _state()[1]
    if incident_id not in incidents:
        raise HTTPException(404, f"Unknown incident {incident_id}")
    return incidents[incident_id]


@app.get("/services/{service}")
def service_view(service: Literal["outbox", "calendar", "crm"],
                 env: Literal["prod", "mirage"] = "prod") -> ServiceView:
    """The outbox / calendar / CRM panels, prod or Mirage, folded from the event log."""
    return services.view(list_events(), service, env)


def _pending_approvals():
    runs = _state()[0]
    pending = {}
    for e in list_events():
        p = e.payload
        if e.type == "gate.decision" and p.get("rule_id") == "NEEDS_APPROVAL":
            pending[e.run_id] = Approval(call_id=p["call_id"], run_id=e.run_id,
                                         agent=runs[e.run_id].agent if e.run_id in runs else "",
                                         tool=p["tool"], args=p["args"], policy_id=p.get("policy_id"),
                                         p=p.get("p"), explanation=p["explanation"], ts=e.ts)
    return [a for r, a in pending.items()  # still held: frozen, and not an incident
            if r in runs and runs[r].status == "frozen" and not runs[r].incident_id]


@app.get("/approvals")
def approvals() -> list[Approval]:
    """Calls layer 2 held for a human (medium risk). Oldest first."""
    return sorted(_pending_approvals(), key=lambda a: a.ts)


def _decide(call_id, body, action):
    held = next((a for a in _pending_approvals() if a.call_id == call_id), None)
    if not held:
        raise HTTPException(404, f"No call {call_id} is waiting for approval")
    if REPLAY:
        REPLAY.advance()
        return get_run(held.run_id)
    if held.run_id not in gate.runs:
        raise HTTPException(409, f"Run {held.run_id} is owned by another process (no live control)")
    getattr(gate, action)(held.run_id, body.actor, body.reason)
    return gate.runs[held.run_id].model()


@app.post("/approvals/{call_id}/approve")
def approve(call_id: str, body: HumanRequest) -> Run:
    """The held call runs."""
    return _decide(call_id, body, "approve")


@app.post("/approvals/{call_id}/reject")
def reject(call_id: str, body: HumanRequest) -> Run:
    """The held call never runs and the run ends; a human can approve a clean restart."""
    return _decide(call_id, body, "reject")


@app.get("/policies")
def policies() -> dict:
    return {"canary": POLICY["canary"],
            "agents": {name: spec.model_dump() for name, spec in gate.agents.items()}}


@app.post("/stop")
def stop(body: HumanRequest) -> list[Run]:
    if REPLAY:
        REPLAY.advance()
    else:
        gate.global_stop(body.actor, body.reason)
        _stop_resumed_agents()
    return list_runs()


@app.post("/stop/lift", status_code=204)
def lift_stop(body: HumanRequest):
    """Lift Stop all. Halted runs stay halted until a human resumes each one."""
    if REPLAY:
        REPLAY.advance()
    else:
        gate.lift_stop(body.actor, body.reason)


def _compromised(inc):
    """Detonation confirmed (or is past confirming) that the run is compromised."""
    return inc and (inc.status not in ("open", "false_positive")
                    or (inc.verdict and inc.verdict.confirmed))


def _act(run_id, body, action, allowed_from):
    if REPLAY:
        REPLAY.advance()
        return get_run(run_id)
    if run_id not in gate.runs and run_id in _state()[0]:
        raise HTTPException(409, f"Run {run_id} is owned by another process (no live control)")
    run = _run(run_id)
    if run.status not in allowed_from:
        raise HTTPException(409, f"Cannot {action} a run that is {run.status}")
    getattr(gate, action)(run_id, body.actor, body.reason)
    return run.model()


@app.post("/runs/{run_id}/freeze")
def freeze(run_id: str, body: HumanRequest) -> Run:
    return _act(run_id, body, "freeze", ("running",))


@app.post("/runs/{run_id}/unfreeze")
def unfreeze(run_id: str, body: HumanRequest) -> Run:
    with jobs.lock:
        if not REPLAY:
            runs, incidents = _state()
            inc = incidents.get(runs[run_id].incident_id) if run_id in runs else None
            if inc and (inc.status == "detonating" or jobs.running(inc.id)):
                raise HTTPException(409, "Cannot unfreeze: detonation is running. Wait for the verdict.")
            if _compromised(inc):
                raise HTTPException(409, "Cannot unfreeze: detonation confirmed this run is compromised. "
                                         "Kill it and approve a clean restart.")
        return _act(run_id, body, "unfreeze", ("frozen",))


@app.post("/runs/{run_id}/restart")
def restart(run_id: str, body: HumanRequest) -> Run:
    """A human approves a clean restart of a killed or halted run. The new run is created
    `queued` with `restarted_from`; the agent's next start (SDK `POST /runs`) takes it over.
    The engine does not launch it (resume does)."""
    if REPLAY:
        REPLAY.advance()
        return get_run(run_id)
    old = get_run(run_id)
    if old.status not in ("killed", "halted"):
        raise HTTPException(409, f"Cannot restart a run that is {old.status}: kill it first")
    if gate.STOP.is_set():
        raise HTTPException(409, "Global STOP is on")
    return get_run(_queue_restart(old, body, "approve_restart").id)


def _queue_restart(old, body, action, note=None):
    events.emit("human.action", {"actor": body.actor, "action": action,
                                 "target": old.id, "reason": body.reason,
                                 "ts": datetime.now(UTC).isoformat()})
    run = gate.LiveRun(id=gate.next_id("run"), agent=old.agent, task=old.task,
                       restarted_from=old.id)
    gate.runs[run.id] = run
    events.emit("run.started", {"task": run.task, "agent": run.agent, "restarted_from": old.id,
                                "status": "queued", **({"note": note} if note else {})},
                run_id=run.id)
    return run


# Rebuilds the agent from its entrypoint ("module:factory") and runs the task from the start.
RESUME_RUNNER = ("import importlib, sys; m, _, f = sys.argv[1].partition(':'); "
                 "getattr(importlib.import_module(m), f)().invoke({'messages': [('user', sys.argv[2])]})")


@app.post("/runs/{run_id}/resume")
def resume(run_id: str, body: HumanRequest, request: Request) -> Run:
    """Resume a halted run after Stop all: a clean restart the engine launches itself. The agent
    restarts its task from the beginning; the old run stays halted and every call is gated."""
    if REPLAY:
        REPLAY.advance()
        return get_run(run_id)
    with jobs.lock:  # Stop all cannot land between the checks and the launch
        old = get_run(run_id)
        if old.status != "halted":
            raise HTTPException(409, f"Cannot resume a run that is {old.status}: only halted runs resume")
        if gate.STOP.is_set():
            raise HTTPException(409, "Lift Stop all first")
        if _compromised(_state()[1].get(old.incident_id)):
            raise HTTPException(409, "Detonation confirmed this run is compromised. "
                                     "Fix it, then approve a clean restart.")
        spec = gate.agents.get(old.agent)
        if not (spec and spec.entrypoint):
            note = "No entrypoint recorded: the agent's owner must start it; it takes over this run."
            return get_run(_queue_restart(old, body, "resume", note).id)
        run = _queue_restart(old, body, "resume")
        env = {**os.environ, "MIRAGE_URL": str(request.base_url).rstrip("/")}
        _demo["resumed"].append(subprocess.Popen(
            [sys.executable, "-c", RESUME_RUNNER, spec.entrypoint, old.task],
            cwd=FIXTURES.parents[1], env=env))
        return get_run(run.id)


@app.post("/runs/{run_id}/kill")
def kill(run_id: str, body: HumanRequest) -> Run:
    return _act(run_id, body, "kill", ("running", "frozen"))


def _audit(action, incident_id, body):
    """Log who triggered a detonation, a bisection or a fix check (AGENTS.md: every human
    decision is logged). Callers that send no body are logged as "unknown"."""
    events.emit("human.action", {"actor": body.actor if body else "unknown", "action": action,
                                 "target": incident_id,
                                 "reason": body.reason if body else "(no reason given)",
                                 "ts": datetime.now(UTC).isoformat()})


def _incident_step(incident_id, step) -> dict:
    """detonate / bisect / handoff / verify. Replay: play the next segment, return its head."""
    if not REPLAY:
        raise HTTPException(501, f"{step} is not built yet in live mode")
    get_incident(incident_id)
    head = REPLAY.advance()
    return head.payload if head else {}


def _schedule(incident_id, work, *, purpose="detonate", runs=3, body=None):
    try:
        return jobs.submit(incident_id, work, purpose=purpose, n_runs=runs,
                           audit=lambda: _audit("find_cause" if purpose == "bisect" else purpose,
                                                incident_id, body))
    except jobs.Busy as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        raise HTTPException(503, "Sandbox scheduling failed; retry explicitly") from error


@app.post("/incidents/{incident_id}/detonate")
def detonate(incident_id: str, runs: int = 3, body: HumanRequest | None = None) -> dict:
    """Explicit retry/operator replay; initial incident detonation is automatic at freeze."""
    if REPLAY:
        return _incident_step(incident_id, "detonate")
    with jobs.lock:
        get_incident(incident_id)
        det_id = _schedule(incident_id, lambda det_id: sandbox.detonate(
            incident_id, runs, detonation_id=det_id, emit_started=False), runs=runs, body=body)
        return {"detonation_id": det_id}


@app.post("/incidents/{incident_id}/bisect")
def bisect(incident_id: str, runs: int = 2, body: HumanRequest | None = None) -> dict:
    """Live: remove one input at a time in the background; rows come as bisection.step events."""
    if REPLAY:
        return _incident_step(incident_id, "bisect")
    with jobs.lock:
        incident = get_incident(incident_id)
        if not (incident.verdict and incident.verdict.confirmed):
            raise HTTPException(409, "Detonate first: bisection needs a confirmed compromise")
        _schedule(incident_id, lambda _: engine_bisect.bisect(incident_id, runs),
                  purpose="bisect", runs=runs, body=body)
        return {"incident_id": incident_id, "status": "bisecting"}


@app.post("/incidents/{incident_id}/handoff")
def handoff(incident_id: str, body: HumanRequest | None = None) -> dict:
    """Live: the prompt + report for a coding agent, and a token for this incident only.
    Returns {prompt, claude_code_url, codex_url, mirage_token, report}. The token is never logged."""
    if REPLAY:
        return _incident_step(incident_id, "handoff")
    incident = get_incident(incident_id)
    if not (incident.verdict and incident.verdict.confirmed):
        raise HTTPException(409, "Detonate first: a handoff needs a confirmed compromise")
    if body:
        events.emit("human.action", {"actor": body.actor, "action": "handoff",
                                     "target": incident_id, "reason": body.reason,
                                     "ts": datetime.now(UTC).isoformat()})
    return engine_handoff.create(incident)


@app.post("/incidents/{incident_id}/pr")
def pr_opened(incident_id: str, body: PullRequest) -> dict:
    """The coding agent (or a human) reports the fix PR. Emits pr.opened."""
    get_incident(incident_id)
    return engine_handoff.pr_opened(incident_id, body.url)


@app.post("/incidents/{incident_id}/verify")
def verify(incident_id: str, runs: int = 3, authorization: str = Header(""), body: HumanRequest | None = None) -> dict:
    """Live: check a fix in the background (current agent code + policy, from scratch).
    The result comes as fix.verified {attack_blocked, legit_task_completed, passed}."""
    if REPLAY:
        return _incident_step(incident_id, "verify")
    with jobs.lock:
        get_incident(incident_id)
        if PUBLIC and not engine_handoff.token_ok(incident_id, authorization):
            raise HTTPException(401, "This API is public: send the incident's mirage_token")
        _schedule(incident_id, lambda det_id: sandbox.detonate(
            incident_id, runs, verify=True, detonation_id=det_id, emit_started=False),
            purpose="verify", runs=runs, body=body)
        return {"incident_id": incident_id, "status": "verifying"}


DEMO_RUNNER = ["-m", "agents.run_demo_fleet"]  # Liam's fleet: 4 agents, one gets poisoned
_demo = {"proc": None, "resumed": []}  # the agents processes /demo/start and resume launched


def _terminate(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _stop_resumed_agents():
    procs, _demo["resumed"] = _demo["resumed"], []
    for proc in procs:
        _terminate(proc)


def _stop_demo_agents():
    proc, _demo["proc"] = _demo["proc"], None
    _terminate(proc)
    _stop_resumed_agents()


def _reset_live():
    """A clean slate: stop the demo agents, forget runs and agents, lift STOP, clear the log,
    the snapshots and the handoff tokens."""
    try:
        with jobs.resetting():
            _stop_demo_agents()
            gate.reset()
            events.reset()
            for file in snapshot.SNAP_DIR.glob("*.json"):
                file.unlink()
            engine_handoff.TOKENS.unlink(missing_ok=True)
    except jobs.Busy as error:
        raise HTTPException(409, str(error)) from error


@app.post("/demo/start", status_code=204)
def demo_start(request: Request, body: DemoStart | None = None):
    """Live: reset, then launch the story's agents as their own process, pointed at this engine
    (they join through the SDK like any customer agent). Replay: restart the recording."""
    if REPLAY:
        REPLAY.restart()
        return
    scenario = body.scenario if body else "calendar"
    if scenario != "calendar":
        raise HTTPException(501, f"Scenario {scenario} is not built yet (only calendar)")
    _reset_live()
    env = {**os.environ, "MIRAGE_URL": str(request.base_url).rstrip("/")}
    _demo["proc"] = subprocess.Popen([sys.executable, *DEMO_RUNNER], cwd=FIXTURES.parents[1],
                                     env=env)


@app.post("/demo/reset", status_code=204)
def demo_reset():
    if REPLAY:
        REPLAY.restart()
        return
    _reset_live()
