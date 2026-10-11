"""Automatic medium clearance through real HTTP and protected SDK callbacks, offline."""

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from mirage import core

from engine.api import server
from engine.detection import decision_model
from engine.detonation import jobs, sandbox, snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, HUMAN, USER, check, start
from tests.test_auto_detonation import idle

AUTOMATIC = jobs.automatic
ARGS = {"to": USER, "subject": "Meeting brief", "body": "Renewal call at 09:00."}
LEGIT = {"required": [{"tool": "send_email", "args": {"to": USER},
                       "nonempty": ["subject", "body"],
                       "contains": {"body": ["Renewal call", "09:00"]}}]}


@pytest.fixture
def model(monkeypatch):
    """Mock only the provider boundary; retain parsing, thresholds and fenced call data."""
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        if kwargs["modelId"] == "synthetic-gate":
            answer = {"violates": True, "policy_id": "P5", "p": 0.55,
                      "reason": "Synthetic medium suspicion."}
        else:
            assert kwargs["modelId"] == "synthetic-stronger-judge"
            answer = {"violates": False, "policy_id": None, "p": 0,
                      "reason": "The exact held brief fits the admitted task."}
        return {"output": {"message": {"content": [{"text": json.dumps(answer)}]}}}

    monkeypatch.setenv("MIRAGE_LAYER2", "1")
    monkeypatch.setenv("BEDROCK_GATE_MODEL_ID", "synthetic-gate")
    monkeypatch.setenv("BEDROCK_JUDGE_MODEL_ID", "synthetic-stronger-judge")
    monkeypatch.setattr(decision_model, "_converse", converse)
    return calls


@pytest.fixture
def api(monkeypatch, model):
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(gate, "MODE", "live")
    monkeypatch.setattr(jobs, "automatic", AUTOMATIC)
    monkeypatch.setenv("MIRAGE_PARALLEL", "1")
    monkeypatch.setattr(sandbox, "load_dotenv", lambda: None)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    gate.reset()
    with TestClient(server.app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(core, "_http", client)
        monkeypatch.setattr(core, "_sandbox", None)
        assert client.post("/agents", json={**AGENT, "legit": LEGIT}).status_code == 200
        yield client
    gate.reset()


def protected(run_id, auth, effects):
    run = {"id": run_id, "token": auth["Authorization"].removeprefix("Bearer ")}
    token = core._run.set(run)
    try:
        return core.tool("send_email", ARGS, lambda: effects.append(copy.deepcopy(ARGS))
                         or {"status": "sent"})
    finally:
        core._run.reset(token)


def test_medium_freeze_persists_snapshot_and_queues_three_baselines(api, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def held(incident_id, n_runs, **kwargs):
        snap = snapshot.load(incident_id)
        run = gate.runs[snap["run_id"]]
        assert run.status == "frozen" and not run.resume.is_set()
        calls.append((incident_id, n_runs, kwargs))
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(sandbox, "detonate", held)
    run_id, auth = start(api)
    try:
        decision = check(api, run_id, auth, "send_email", **ARGS).json()
        assert decision["decision"] == "freeze" and decision["p"] == 0.55
        incident_id = gate.runs[run_id].incident_id
        assert incident_id is not None, "medium freeze needs a persisted incident, not an approval"
        assert entered.wait(2)
        snap = snapshot.load(incident_id)
        assert snap["run_id"] == run_id and snap["legit"] == LEGIT
        assert calls[0][1] == 3
        assert not calls[0][2].get("verify") and not calls[0][2].get("removed_input_id")
        incident = api.get(f"/incidents/{incident_id}").json()
        assert incident["status"] == "detonating"
        assert incident["automatic_clearance"]["status"] == "checking"
        assert incident["sandbox_job"]["n_runs"] == 3
        assert api.get("/approvals").json() == []
        assert api.post(f"/approvals/{decision['call_id']}/approve", json=HUMAN).status_code == 404
        assert api.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 409
        assert not any(event.type == "human.action" for event in events.read())
    finally:
        release.set()
        jobs.shutdown()


def test_safe_medium_resumes_original_protected_effect_once_without_human(api, monkeypatch,
                                                                       model):
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
    replays, effects = [], []
    original_wait = core._wait

    def observed_wait(*args, **kwargs):
        waiting.set()
        return original_wait(*args, **kwargs)

    def replay(snap, **kwargs):
        replays.append(copy.deepcopy(snap))
        entered.set()
        assert release.wait(10)
        return [{"step": 1, "tool": "send_email", "args": copy.deepcopy(ARGS)}], None

    monkeypatch.setattr(core, "_wait", observed_wait)
    monkeypatch.setattr(sandbox, "run_once", replay)
    run_id, auth = start(api)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(protected, run_id, auth, effects)
        try:
            assert waiting.wait(2)
            assert effects == [] and gate.runs[run_id].status == "frozen"
            incident_id = gate.runs[run_id].incident_id
            assert incident_id is not None, "medium call never reached automatic sandbox proof"
            assert entered.wait(2)
            release.set()
            assert pending.result(10) == {"status": "sent"}
            idle(incident_id)
            assert len(replays) == 3 and effects == [ARGS]
            assert gate.runs[run_id].status == "running"
            assert len(gate.runs[run_id].tool_results) == 1
            incident = api.get(f"/incidents/{incident_id}").json()
            assert incident["automatic_clearance"]["status"] == "cleared"
            assert incident["verdict"]["confirmed"] is False
            assert any(call["modelId"] == "synthetic-stronger-judge" for call in model)
            assert not any(event.type == "human.action" for event in events.read())
        finally:
            release.set()
            if gate.runs[run_id].status in ("running", "frozen"):
                api.post(f"/runs/{run_id}/kill", json=HUMAN)
