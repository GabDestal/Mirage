"""Mirage engine API (CONTRACTS.md §5 control plane, §11 data plane).

Run: `uv run uvicorn engine.api.server:app --port 8000`. OpenAPI at /openapi.json.
`MIRAGE_MODE=live` runs the engine. `MIRAGE_MODE=replay` plays a fixture through the same routes
(MIRAGE_FIXTURE, MIRAGE_REPLAY_SPEED: 1 = real time, 10 = 10x, inf = instant): POST actions move the replay forward; the SDK routes
answer 409. Data plane routes that act on a run need `Authorization: Bearer <run_token>`.
"""

import asyncio
import os
import threading
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from contracts.models import (
    AgentSpec,
    Event,
    GateDecision,
    HumanRequest,
    Incident,
    ModelCall,
    Run,
    RunStart,
    RunStarted,
    ToolCheck,
    ToolResult,
    WaitResult,
)
from engine.api.replay import Replay
from engine.api.state import fold
from engine.detection.rules import POLICY
from engine.detonation import sandbox
from engine.gateway import gate
from engine.store import events

FIXTURES = Path(__file__).parents[2] / "contracts" / "fixtures"


def _fixture():
    if os.getenv("MIRAGE_FIXTURE"):
        return os.environ["MIRAGE_FIXTURE"]
    demo = FIXTURES / "calendar_demo.jsonl"  # Liam's recorded demo, once it exists
    return demo if demo.exists() else FIXTURES / "sample_demo.jsonl"


MODE = os.getenv("MIRAGE_MODE", "live")
REPLAY = (Replay(_fixture(), float(os.getenv("MIRAGE_REPLAY_SPEED", "1")))
          if MODE == "replay" else None)

app = FastAPI(title="Mirage engine", version="0.1.0")


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
    return spec


@app.post("/runs", **data_plane)
def start_run(body: RunStart) -> RunStarted:
    if body.agent not in gate.agents:
        raise HTTPException(404, f"Agent {body.agent} is not registered (POST /agents)")
    if gate.STOP.is_set():
        raise HTTPException(409, "Global STOP is on")
    run = gate.LiveRun(id=gate.next_id("run"), agent=body.agent, task=body.task)
    gate.runs[run.id] = run
    gate.set_status(run, "running", "sdk", "Run started.")
    events.emit("run.started", {"task": run.task, "agent": run.agent}, run_id=run.id)
    return RunStarted(run_id=run.id, run_token=run.token)


@app.post("/runs/{run_id}/model-calls", status_code=204, **data_plane)
def record_model_call(run_id: str, body: ModelCall, authorization: str = Header("")):
    _authed(run_id, authorization).model_calls.append(body.model_dump())


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
    return list_runs()


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
    if not REPLAY:
        runs, incidents = _state()
        inc = incidents.get(runs[run_id].incident_id) if run_id in runs else None
        if inc and inc.status == "detonating":
            raise HTTPException(409, "Cannot unfreeze: detonation is running. Wait for the verdict.")
        if inc and (inc.status not in ("open", "false_positive")
                    or (inc.verdict and inc.verdict.confirmed)):
            raise HTTPException(409, "Cannot unfreeze: detonation confirmed this run is compromised. "
                                     "Kill it and approve a clean restart.")
    return _act(run_id, body, "unfreeze", ("frozen",))


@app.post("/runs/{run_id}/kill")
def kill(run_id: str, body: HumanRequest) -> Run:
    return _act(run_id, body, "kill", ("running", "frozen"))


def _incident_step(incident_id, step) -> dict:
    """detonate / bisect / handoff / verify. Replay: play the next segment, return its head."""
    if not REPLAY:
        raise HTTPException(501, f"{step} is not built yet in live mode")
    get_incident(incident_id)
    head = REPLAY.advance()
    return head.payload if head else {}


_detonating = set()  # incident ids with a detonation running in this API process


@app.post("/incidents/{incident_id}/detonate")
def detonate(incident_id: str, runs: int = 3) -> dict:
    """Live: replay the frozen run in the sandbox in the background; results come as events.
    Works for incidents frozen by any process: the snapshot is read from disk."""
    if REPLAY:
        return _incident_step(incident_id, "detonate")
    get_incident(incident_id)
    if incident_id in _detonating:
        raise HTTPException(409, "A detonation is already running for this incident")
    _detonating.add(incident_id)
    detonation_id = f"det_{incident_id.removeprefix('inc_')}_{int(time.time())}"

    def work():
        try:
            sandbox.detonate(incident_id, runs, detonation_id=detonation_id)
        except Exception as e:  # noqa: BLE001 - keep the API up; the operator can retry
            events.emit("detonation.failed", {"incident_id": incident_id,
                                              "detonation_id": detonation_id,
                                              "error": f"{type(e).__name__}: {e}"},
                        incident_id=incident_id, env="mirage")
        finally:
            _detonating.discard(incident_id)

    threading.Thread(target=work, daemon=True).start()
    return {"detonation_id": detonation_id}


@app.post("/incidents/{incident_id}/bisect")
def bisect(incident_id: str) -> dict:
    return _incident_step(incident_id, "bisect")


@app.post("/incidents/{incident_id}/handoff")
def handoff(incident_id: str) -> dict:
    return _incident_step(incident_id, "handoff")


@app.post("/incidents/{incident_id}/verify")
def verify(incident_id: str) -> dict:
    return _incident_step(incident_id, "verify")


@app.post("/demo/start", status_code=204)
def demo_start():
    if not REPLAY:
        raise HTTPException(501, "Live demo start is not built yet: run agents/run_demo.py")
    REPLAY.restart()


@app.post("/demo/reset", status_code=204)
def demo_reset():
    if REPLAY:
        REPLAY.restart()
        return
    gate.reset()
    events.reset()
