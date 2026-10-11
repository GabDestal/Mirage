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
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from sse_starlette.sse import EventSourceResponse

# Load dotenv before engine modules capture paths or settings.
from engine.config import MODE  # isort: skip

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
    ResumeAll,
    ResumeSkip,
    Run,
    RunCompletion,
    RunStart,
    RunStarted,
    RuntimeInfo,
    ServiceView,
    ToolCheck,
    ToolResult,
    WaitResult,
)
from engine import bisect as engine_bisect
from engine import handoff as engine_handoff
from engine.api import recovery, repair, services
from engine.api.replay import Replay
from engine.api.rules import router as rules_router
from engine.api.state import fold
from engine.detection.rules import POLICY
from engine.detonation import jobs, sandbox, snapshot
from engine.gateway import gate
from engine.store import events

FIXTURES = Path(__file__).parents[2] / "contracts" / "fixtures"


def _fixture():
    if os.getenv("MIRAGE_FIXTURE"):
        return os.environ["MIRAGE_FIXTURE"]
    if os.getenv("MIRAGE_REPLAY_MANAGED") == "1":
        return FIXTURES / "fleet_demo_4agents.jsonl"
    demo = FIXTURES / "calendar_demo.jsonl"  # Liam's recorded demo, once it exists
    return demo if demo.exists() else FIXTURES / "sample_demo.jsonl"


PUBLIC = os.getenv("MIRAGE_PUBLIC") == "1"  # exposed (tunnel): fix checks need the incident token
REPLAY = (Replay(_fixture(), float(os.getenv("MIRAGE_REPLAY_SPEED", "1")),
                 managed=os.getenv("MIRAGE_REPLAY_MANAGED") == "1")
          if MODE == "replay" else None)

INSTANCE_ID = uuid4().hex
_live_epoch = None
_replay_epoch = uuid4().hex


def _revision():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=FIXTURES.parents[1], stderr=subprocess.DEVNULL,
                                       text=True, timeout=2).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


REVISION = _revision()  # loaded once; a later checkout change is not this process's provenance


def _event_batch(after=0):
    global _live_epoch
    with jobs.lock:
        if REPLAY:
            with REPLAY.lock:
                visible = REPLAY.visible()
                epoch = _replay_epoch
                last_seq = visible[-1].seq if visible else 0
                batch = [event for event in visible if event.seq > after]
        else:
            epoch, last_seq, batch = events.read_batch(after)
            if _live_epoch is not None and epoch != _live_epoch:
                jobs.discard_stale(epoch)
                gate.reset()  # old in-memory tokens/owners cannot control a replacement log
                restore()
                epoch, last_seq, batch = events.read_batch(after)
            _live_epoch = epoch
        info = RuntimeInfo(engine_mode=MODE, instance_id=INSTANCE_ID,
                           stream_epoch=f"{INSTANCE_ID}:{epoch}", last_seq=last_seq,
                           revision=REVISION, owned_run_ids=[] if REPLAY else sorted(gate.runs))
        return info, batch


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
    jobs.restore()
    repair.restore()


@asynccontextmanager
async def lifespan(app):
    if not REPLAY:
        _event_batch()
        restore()
        jobs.start()
    yield
    if not REPLAY:
        jobs.shutdown()
        _stop_demo_agents()  # a normal shutdown does not leave the live demo fleet running


app = FastAPI(title="Mirage engine", version="0.1.0", lifespan=lifespan)
app.include_router(rules_router)


def live_only():
    if REPLAY:
        raise HTTPException(409, "Replay mode: the data plane is off (MIRAGE_MODE=live to run agents)")


app.include_router(repair.router(live_only))
app.include_router(recovery.router(live_only))


def _run(run_id) -> gate.LiveRun:
    _event_batch()
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
    return REPLAY.state() if REPLAY else fold(_event_batch()[1])


# --- data plane: SDK -> engine ------------------------------------------------------------

data_plane = {"dependencies": [Depends(live_only)]}


@app.post("/agents", **data_plane)
def register_agent(spec: AgentSpec) -> AgentSpec:
    with jobs.lock:
        _event_batch()
        gate.agents[spec.name] = spec
        events.emit("agent.registered", spec.model_dump(mode="json"))  # survives an engine restart
        return spec


@app.post("/runs", **data_plane)
def start_run(body: RunStart) -> RunStarted:
    with jobs.lock:
        _event_batch()
        spec = gate.agents.get(body.agent)
        if spec is None:
            raise HTTPException(404, f"Agent {body.agent} is not registered (POST /agents)")
        if gate.STOP.is_set():
            raise HTTPException(409, "Global STOP is on")
        queued = [r for r in gate.runs.values()
                  if r.agent == body.agent and r.task == body.task and r.status == "queued"
                  and r.restarted_from is not None
                  and (body.restarted_from is None or r.restarted_from == body.restarted_from)]
        if len(queued) > 1:
            raise HTTPException(409, "Ambiguous clean restart: specify the original run")
        if queued:
            run = queued[0]
            if spec != run.admitted_spec:
                raise HTTPException(409, "Registration changed since this clean restart was approved")
            recovery.require_claim(run)
            gate.set_status(run, "running", "sdk", f"Clean restart of {run.restarted_from}.")
            return RunStarted(run_id=run.id, run_token=run.token,
                              rule_revision=run.policy.get("rule_revision"))
        if body.restarted_from is not None:
            raise HTTPException(409, "No matching approved clean restart is queued")
        run = gate.LiveRun(id=gate.next_id("run"), agent=body.agent, task=body.task,
                           admitted_spec=spec)
        gate.runs[run.id] = run
        gate.set_status(run, "running", "sdk", "Run started.")
        events.emit("run.started", {"task": run.task, "agent": run.agent,
                                    "restarted_from": run.restarted_from,
                                    "rule_revision": run.policy.get("rule_revision")}, run_id=run.id)
        return RunStarted(run_id=run.id, run_token=run.token,
                          rule_revision=run.policy.get("rule_revision"))


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
    try:
        gate.record_result(run, body.call_id, body.tool, body.result, body.error)
    except gate.CallAuthorityError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/runs/{run_id}/wait", **data_plane)
def wait(run_id: str, timeout: float = 25, authorization: str = Header(""),
         call_id: str | None = Query(None, description="Original checked call held for a human.")) -> WaitResult:
    """Poll status; a bound call_id claims only that call's approved release, once."""
    run = _authed(run_id, authorization)  # sync route: runs in the threadpool, may block
    try:
        return WaitResult(status=gate.wait(run, call_id, min(timeout, 60)))
    except gate.CallAuthorityError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/runs/{run_id}/complete", **data_plane)
def complete_run(run_id: str, authorization: str = Header(""),
                 body: RunCompletion | None = None) -> Run:
    with jobs.lock:
        run = _authed(run_id, authorization)
        if run.status == "running":
            error = body.error if body else None
            if error is not None:
                gate.set_status(run, "failed", "sdk", f"Run failed: {gate.error_type(error)}.")
            else:
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


@app.get("/runtime")
def runtime_info() -> RuntimeInfo:
    return _event_batch()[0]


@app.get("/events", responses={200: {"headers": {
    "X-Mirage-Stream-Epoch": {"schema": {"type": "string"}}}}})
def list_events(after: int = 0, response: Response = None) -> list[Event]:
    info, batch = _event_batch(after)
    if response is not None:
        response.headers["X-Mirage-Stream-Epoch"] = info.stream_epoch
    return batch


@app.get("/stream")
async def stream(request: Request, after: int = 0):
    after = int(request.headers.get("last-event-id", after))

    async def gen():
        nonlocal after
        previous = None
        while not await request.is_disconnected():
            info, batch = _event_batch(after)
            if after > info.last_seq or (previous and previous.stream_epoch != info.stream_epoch):
                after = 0
                info, batch = _event_batch()
            if info != previous:
                yield {"event": "runtime", "data": info.model_dump_json()}
                previous = info
            for event in batch:
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
    if not REPLAY:
        return []  # medium suspicion has an incident; legacy dialogs cannot release it
    runs = _state()[0]
    pending = {}
    for e in list_events():
        p = e.payload
        if e.type == "gate.decision" and p.get("rule_id") == "NEEDS_APPROVAL":
            pending[e.run_id] = Approval(call_id=p["call_id"], run_id=e.run_id,
                                         agent=runs[e.run_id].agent if e.run_id in runs else "",
                                         tool=p["tool"], args=p["args"], policy_id=p.get("policy_id"),
                                         p=p.get("p"), explanation=p["explanation"], ts=e.ts)
    return [a for r, a in pending.items()
            if r in runs and runs[r].status == "frozen" and not runs[r].incident_id]


@app.get("/approvals")
def approvals() -> list[Approval]:
    """Legacy recorded approvals. Live medium suspicion uses automatic sandbox clearance."""
    return sorted(_pending_approvals(), key=lambda a: a.ts)


def _decide(call_id, body, action):
    with jobs.lock:
        held = next((a for a in _pending_approvals() if a.call_id == call_id), None)
        if not held:
            raise HTTPException(404, f"No call {call_id} is waiting for approval")
        if REPLAY:
            _recorded_control(action)
            REPLAY.advance()
            return get_run(held.run_id)
        if held.run_id not in gate.runs:
            raise HTTPException(409, f"Run {held.run_id} is owned by another process (no live control)")
        try:
            getattr(gate, action)(held.run_id, body.actor, body.reason, call_id)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
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
    if REPLAY and REPLAY.managed:
        specs = {}
        for e in REPLAY.recorded:
            if e.type == "agent.registered":
                specs[e.payload["name"]] = {**e.payload, "entrypoint": ""}
            elif e.type == "run.started" and e.env == "prod":
                name = e.payload["agent"]
                tools = sorted({x.payload["tool"] for x in REPLAY.recorded
                                if x.run_id == e.run_id and x.type == "tool.requested"})
                destinations = sorted({x.payload["args"]["to"] for x in REPLAY.recorded
                                       if x.run_id == e.run_id and x.type == "gate.decision"
                                       and x.payload["decision"] == "allow"
                                       and "to" in x.payload["args"]})
                specs.setdefault(name, AgentSpec(name=name, owner="recorded-demo", tools=tools,
                                                allow={"tools": tools, "email_to": destinations},
                                                entrypoint="").model_dump())
        return {"canary": POLICY["canary"], "agents": specs}
    return {"canary": POLICY["canary"],
            "agents": {name: spec.model_dump() for name, spec in gate.agents.items()}}


@app.post("/stop")
def stop(body: HumanRequest) -> list[Run]:
    if REPLAY:
        if REPLAY.managed:
            _recorded_stop(body)
        else:
            REPLAY.advance()
    else:
        with jobs.lock:
            _event_batch()
            gate.global_stop(body.actor, body.reason)
            _stop_resumed_agents()
    return list_runs()


@app.post("/stop/lift", status_code=204)
def lift_stop(body: HumanRequest):
    """Lift Stop all. Halted runs stay halted (the dashboard uses /resume-all instead)."""
    if REPLAY:
        if REPLAY.managed:
            _recorded_stop(body, lift=True)
        else:
            REPLAY.advance()
    else:
        gate.lift_stop(body.actor, body.reason)


def _compromised(inc):
    """Detonation confirmed (or is past confirming) that the run is compromised."""
    return inc and (inc.status not in ("open", "false_positive")
                    or (inc.verdict and inc.verdict.confirmed))


def _recorded_control(action, run_id=None):
    if REPLAY and REPLAY.managed:
        if run_id is not None:
            get_run(run_id)
        raise HTTPException(409, f"Recorded demo: {action} is unsupported; no live run is controlled. "
                                 "Use /demo/reset to restart the recording.")


def _recorded_stop(body, *, lift=False):
    try:
        REPLAY.pause(body, lift=lift)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


def _act(run_id, body, action, allowed_from):
    if REPLAY:
        _recorded_control(action, run_id)
        REPLAY.advance()
        return get_run(run_id)
    if run_id not in gate.runs and run_id in _state()[0]:
        raise HTTPException(409, f"Run {run_id} is owned by another process (no live control)")
    run = _run(run_id)
    if run.status not in allowed_from:
        raise HTTPException(409, f"Cannot {action} a run that is {run.status}")
    try:
        getattr(gate, action)(run_id, body.actor, body.reason)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return run.model()


@app.post("/runs/{run_id}/freeze")
def freeze(run_id: str, body: HumanRequest) -> Run:
    return _act(run_id, body, "freeze", ("running",))


@app.post("/runs/{run_id}/unfreeze")
def unfreeze(run_id: str, body: HumanRequest) -> Run:
    with jobs.lock:
        if not REPLAY or REPLAY.managed:
            runs, incidents = _state()
            inc = incidents.get(runs[run_id].incident_id) if run_id in runs else None
            if inc and inc.automatic_clearance and inc.automatic_clearance.status != "cleared":
                raise HTTPException(409, "Medium suspicion requires conclusive initial sandbox clearance.")
            if inc and (inc.status == "detonating" or (not REPLAY and jobs.running(inc.id))):
                raise HTTPException(409, "Cannot unfreeze: detonation is running. Wait for the verdict.")
            cleared_medium = (inc and inc.status == "closed" and inc.automatic_clearance
                              and inc.automatic_clearance.status == "cleared"
                              and inc.verdict and not inc.verdict.confirmed)
            if _compromised(inc) and not cleared_medium:
                raise HTTPException(409, "Cannot unfreeze: detonation confirmed this run is compromised. "
                                         "Kill it and approve a clean restart.")
        return _act(run_id, body, "unfreeze", ("frozen",))


@app.post("/runs/{run_id}/restart")
def restart(run_id: str, body: HumanRequest, request: Request) -> Run:
    """A human approves one clean restart of a killed, halted or failed run. It is created
    `queued` with `restarted_from`, and the engine launches the agent from its entrypoint (as
    resume does); its matching agent/task/spec SDK start claims the run once. Without an
    entrypoint it stays queued for the agent's owner."""
    if REPLAY:
        _recorded_control("restart", run_id)
        REPLAY.advance()
        return get_run(run_id)
    with jobs.lock:
        old = get_run(run_id)
        if old.status not in ("killed", "halted", "failed"):
            raise HTTPException(409, f"Cannot restart a run that is {old.status}: kill it first")
        if gate.STOP.is_set():
            raise HTTPException(409, "Global STOP is on")
        _restart_available(old)
        if not _compromised(_state()[1].get(old.incident_id)):
            return _launch(old, body, request, "approve_restart")
        # Compromised: only the prepared verified rollout; its trusted recovery launcher claims it.
        recovery.require_prepared(old, gate.agents.get(old.agent))
        new = _queue_restart(old, body, "approve_restart")
        recovery.approved(old, new, body)
        return get_run(new.id)


def _restart_available(old):
    if any(run.restarted_from == old.id for run in _state()[0].values()):
        raise HTTPException(409, "A clean restart has already been approved for this run")


def _queue_restart(old, body, action, note=None):
    _restart_available(old)
    events.emit("human.action", {"actor": body.actor, "action": action,
                                 "target": old.id, "reason": body.reason,
                                 "ts": datetime.now(UTC).isoformat()})
    spec = gate.agents.get(old.agent)
    run = gate.LiveRun(id=gate.next_id("run"), agent=old.agent, task=old.task,
                       restarted_from=old.id, admitted_spec=spec)
    gate.runs[run.id] = run
    events.emit("run.started", {"task": run.task, "agent": run.agent, "restarted_from": old.id,
                                "status": "queued", "rule_revision": run.policy.get("rule_revision"),
                                **({"note": note} if note else {})},
                run_id=run.id)
    return run


_popen_agent = subprocess.Popen  # starts a resumed or restarted agent (tests swap it)

# Rebuilds the agent from its entrypoint ("module:factory") and runs the task from the start.
RESUME_RUNNER = ("import importlib, sys; m, _, f = sys.argv[1].partition(':'); "
                 "getattr(importlib.import_module(m), f)().invoke({'messages': [('user', sys.argv[2])]})")


@app.post("/runs/{run_id}/resume")
def resume(run_id: str, body: HumanRequest, request: Request) -> Run:
    """Resume a halted run after Stop all: a clean restart the engine launches itself. The agent
    restarts its task from the beginning; the old run stays halted and every call is gated."""
    if REPLAY:
        _recorded_control("resume", run_id)
        REPLAY.advance()
        return get_run(run_id)
    with jobs.lock:  # Stop all cannot land between the checks and the launch
        old = get_run(run_id)
        if old.status != "halted":
            raise HTTPException(409, f"Cannot resume a run that is {old.status}: only halted runs resume")
        _resume_block(old)
        if gate.STOP.is_set():
            gate.lift_stop(body.actor, body.reason)
        return _launch(old, body, request, "resume")


def _resume_block(old):
    _restart_available(old)
    if _compromised(_state()[1].get(old.incident_id)):
        raise HTTPException(409, "Detonation confirmed this run is compromised. "
                                 "Fix it, then approve a clean restart.")


def _launch(old, body, request, action):
    """Queue the successor run, then start the agent from its entrypoint to claim it."""
    spec = gate.agents.get(old.agent)
    if not (spec and spec.entrypoint):
        note = "No entrypoint recorded: the agent's owner must start it; it takes over this run."
        return get_run(_queue_restart(old, body, action, note).id)
    run = _queue_restart(old, body, action)
    env = {**os.environ, "MIRAGE_URL": str(request.base_url).rstrip("/")}
    _demo["resumed"].append(_popen_agent(
        [sys.executable, "-c", RESUME_RUNNER, spec.entrypoint, old.task],
        cwd=FIXTURES.parents[1], env=env))
    return get_run(run.id)


@app.post("/resume-all")
def resume_all(body: HumanRequest, request: Request) -> ResumeAll:
    """Lift Stop all (if on) and resume every halted run that has no restart yet. Compromised
    runs stay halted and come back in `skipped`. Managed replay only resumes its paused clock."""
    if REPLAY:
        if REPLAY.managed:
            _recorded_stop(body, lift=True)
        else:
            REPLAY.advance()
        return ResumeAll(resumed=[], skipped=[])
    with jobs.lock:
        if gate.STOP.is_set():
            gate.lift_stop(body.actor, body.reason)
        runs = list_runs()
        restarted = {r.restarted_from for r in runs}
        resumed, skipped = [], []
        for old in runs:
            if old.status != "halted" or old.id in restarted:
                continue
            try:
                _resume_block(old)
            except HTTPException as e:
                skipped.append(ResumeSkip(run_id=old.id, reason=e.detail))
                continue
            resumed.append(_launch(old, body, request, "resume"))
        return ResumeAll(resumed=resumed, skipped=skipped)


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


def _incident_step(incident_id, step, body=None, *, pr_url=None, runs=None) -> dict:
    """detonate / bisect / handoff / verify. Replay: play the next segment, return its head."""
    if not REPLAY:
        raise HTTPException(501, f"{step} is not built yet in live mode")
    get_incident(incident_id)
    if REPLAY.managed:
        try:
            return REPLAY.advance_for(incident_id, step, body, pr_url=pr_url, runs=runs)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
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
def detonate(incident_id: str, runs: int = Query(3, ge=1, le=10),
             body: HumanRequest | None = None) -> dict:
    """Explicit retry/operator replay; initial incident detonation is automatic at freeze."""
    if REPLAY:
        return _incident_step(incident_id, "detonate", body)
    with jobs.lock:
        get_incident(incident_id)
        det_id = _schedule(incident_id, lambda det_id: sandbox.detonate(
            incident_id, runs, detonation_id=det_id, emit_started=False), runs=runs, body=body)
        return {"detonation_id": det_id}


@app.post("/incidents/{incident_id}/bisect")
def bisect(incident_id: str, runs: int = Query(2, ge=1, le=10),
           body: HumanRequest | None = None) -> dict:
    """Live: remove one input at a time in the background; rows come as bisection.step events."""
    if REPLAY:
        return _incident_step(incident_id, "bisect", body, runs=runs)
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
        return _incident_step(incident_id, "handoff", body)
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
    if REPLAY:
        if not REPLAY.managed:
            raise HTTPException(409, "Replay mode: reporting a real PR is unsupported")
        return _incident_step(incident_id, "pr", pr_url=body.url)
    return engine_handoff.pr_opened(incident_id, body.url)


@app.post("/incidents/{incident_id}/verify")
def verify(incident_id: str, runs: int = Query(3, ge=1, le=10),
           authorization: str = Header(""), body: HumanRequest | None = None) -> dict:
    """Live: check a fix in the background (current agent code + policy, from scratch).
    The result comes as fix.verified {attack_blocked, legit_task_completed, passed}."""
    if REPLAY:
        return _incident_step(incident_id, "verify", body, runs=runs)
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
    global _replay_epoch
    if REPLAY:
        if REPLAY.managed and body and body.scenario != "calendar":
            raise HTTPException(409, "Recorded demo supports only the calendar scenario")
        with REPLAY.lock:
            REPLAY.restart()
            _replay_epoch = uuid4().hex
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
    global _replay_epoch
    if REPLAY:
        with REPLAY.lock:
            REPLAY.restart()
            _replay_epoch = uuid4().hex
        return
    _reset_live()
