"""Mirage engine API (CONTRACTS.md §5 control plane, §11 data plane).

Run: `uv run uvicorn engine.api.server:app --port 8000`. OpenAPI at /openapi.json.
Data plane routes that act on a run need `Authorization: Bearer <run_token>`.
shortcut: live mode only; MIRAGE_MODE=replay (fixtures) comes next.
"""

import asyncio
import os

from fastapi import FastAPI, Header, HTTPException, Request
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
from engine.detection.rules import POLICY
from engine.gateway import gate
from engine.store import events

app = FastAPI(title="Mirage engine", version="0.1.0")
if os.getenv("MIRAGE_MODE", "live") != "live":
    print("MIRAGE_MODE=replay is not implemented yet: serving live mode.")


def _run(run_id) -> gate.LiveRun:
    if run_id not in gate.runs:
        raise HTTPException(404, f"Unknown run {run_id}")
    return gate.runs[run_id]


def _authed(run_id, authorization) -> gate.LiveRun:
    run = _run(run_id)
    if authorization != f"Bearer {run.token}":
        raise HTTPException(401, "Missing or wrong run token")
    return run


# --- data plane: SDK -> engine ------------------------------------------------------------


@app.post("/agents")
def register_agent(spec: AgentSpec) -> AgentSpec:
    gate.agents[spec.name] = spec
    return spec


@app.post("/runs")
def start_run(body: RunStart) -> RunStarted:
    if body.agent not in gate.agents:
        raise HTTPException(404, f"Agent {body.agent} is not registered (POST /agents)")
    if gate.STOP.is_set():
        raise HTTPException(409, "Global STOP is on")
    run = gate.LiveRun(id=gate.next_id("run"), agent=body.agent, task=body.task)
    gate.runs[run.id] = run
    gate.set_status(run, "running", "sdk", "Run started.")
    events.emit("run.started", {"task": run.task}, run_id=run.id)
    return RunStarted(run_id=run.id, run_token=run.token)


@app.post("/runs/{run_id}/model-calls", status_code=204)
def record_model_call(run_id: str, body: ModelCall, authorization: str = Header("")):
    _authed(run_id, authorization).model_calls.append(body.model_dump())


@app.post("/gateway/check")
def check(body: ToolCheck, authorization: str = Header("")) -> GateDecision:
    return gate.check(_authed(body.run_id, authorization), body.tool, body.args)


@app.post("/runs/{run_id}/tool-results", status_code=204)
def record_tool_result(run_id: str, body: ToolResult, authorization: str = Header("")):
    run = _authed(run_id, authorization)
    gate.record_result(run, body.call_id, body.tool, body.result, body.error)


@app.get("/runs/{run_id}/wait")
def wait(run_id: str, timeout: float = 25, authorization: str = Header("")) -> WaitResult:
    run = _authed(run_id, authorization)  # sync route: runs in the threadpool, may block
    run.resume.wait(min(timeout, 60))
    status = "halted" if run.status == "completed" else run.status
    return WaitResult(status=status if status != "queued" else "running")


@app.post("/runs/{run_id}/complete")
def complete_run(run_id: str, authorization: str = Header("")) -> Run:
    run = _authed(run_id, authorization)
    if run.status == "running":
        gate.set_status(run, "completed", "sdk", "Task finished.")
    return run.model()


# --- control plane: web + MCP -> engine --------------------------------------------------


@app.get("/runs")
def list_runs() -> list[Run]:
    return [r.model() for r in gate.runs.values()]


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> Run:
    return _run(run_id).model()


@app.get("/events")
def list_events(after: int = 0) -> list[Event]:
    return events.read(after)


@app.get("/stream")
async def stream(request: Request, after: int = 0):
    after = int(request.headers.get("last-event-id", after))

    async def gen():
        nonlocal after
        while not await request.is_disconnected():
            for event in events.read(after):
                after = event.seq
                yield {"id": str(event.seq), "data": event.model_dump_json()}
            await asyncio.sleep(0.25)

    return EventSourceResponse(gen())


@app.get("/incidents")
def list_incidents() -> list[Incident]:
    return list(gate.incidents.values())


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> Incident:
    if incident_id not in gate.incidents:
        raise HTTPException(404, f"Unknown incident {incident_id}")
    return gate.incidents[incident_id]


@app.get("/policies")
def policies() -> dict:
    return {"canary": POLICY["canary"],
            "agents": {name: spec.model_dump() for name, spec in gate.agents.items()}}


@app.post("/stop")
def stop(body: HumanRequest) -> list[Run]:
    gate.global_stop(body.actor, body.reason)
    return list_runs()


def _act(run_id, body, action, allowed_from):
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
    return _act(run_id, body, "unfreeze", ("frozen",))


@app.post("/runs/{run_id}/kill")
def kill(run_id: str, body: HumanRequest) -> Run:
    return _act(run_id, body, "kill", ("running", "frozen"))


@app.post("/demo/reset", status_code=204)
def demo_reset():
    gate.reset()
    events.reset()
