"""Durable exposure job HTTP seams without providers or user services."""

import copy
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from contracts.models import ExposureJob
from engine.api import exposure as api
from engine.detonation import jobs, snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_exposure import setup  # noqa: F401 - shared real-jail fixture


@pytest.fixture
def client(setup, tmp_path, monkeypatch):  # noqa: F811 - imported pytest fixture
    source, _, entry = setup
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "exposure.db")
    monkeypatch.setattr(snapshot, "SNAP_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(gate, "agents", {})
    monkeypatch.setattr(gate, "STOP", threading.Event())
    monkeypatch.setattr(jobs, "_pending", {})
    snapshot.SNAP_DIR.mkdir()
    (snapshot.SNAP_DIR / "inc_original.json").write_text(json.dumps(source))
    manifest = tmp_path / "candidates.json"
    manifest.write_text(json.dumps([entry, {"agent_name": "invoice", "role": "invoice",
                                          "tools": ["list_invoices", "send_email"]}]))
    monkeypatch.setenv("MIRAGE_EXPOSURE_CANDIDATES", str(manifest))
    incident = SimpleNamespace(cause_input_id="in_01")
    app = FastAPI()
    app.include_router(api.create_router(lambda incident_id: incident))
    with TestClient(app) as http:
        yield http, incident, entry


def request(client, names=None, **extra):
    http, _, entry = client
    return http.post("/incidents/inc_original/exposure-jobs", json={
        "agent_names": names or [entry["agent_name"], "invoice"],
        "actor": "synthetic operator", "reason": "Assess the sibling", **extra})


def test_create_get_list_and_original_recording_unchanged(client):
    http, _, _ = client
    source = (snapshot.SNAP_DIR / "inc_original.json").read_bytes()
    candidate_response = http.get("/incidents/inc_original/exposure-candidates")
    assert candidate_response.status_code == 200
    assert [c["status"] for c in candidate_response.json()] == ["unassessed", "not_applicable"]
    created = request(client)
    assert created.status_code == 202, created.text
    queued = ExposureJob.model_validate(created.json())
    assert queued.status == "queued" and queued.results == []
    result = http.get(f"/exposure-jobs/{queued.id}")
    assert result.status_code == 200, result.text
    job = ExposureJob.model_validate(result.json())
    deadline = time.monotonic() + 10
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
        result = http.get(f"/exposure-jobs/{queued.id}")
        job = ExposureJob.model_validate(result.json())
    assert job.status == "completed"
    assert [r.status for r in job.results] == ["vulnerable", "not_applicable"]
    assert job.results[0].replay_kind == "scripted"
    assert http.get("/exposure-jobs?incident_id=inc_original").json() == [result.json()]
    assert http.get("/exposure-jobs?incident_id=other").json() == []
    assert http.get("/exposure-jobs/absent").status_code == 404
    assert source == (snapshot.SNAP_DIR / "inc_original.json").read_bytes()
    assert all(e.type in ("agent.message", "human.action") for e in events.read())
    assert any(e.payload.get("actor") == "synthetic operator" for e in events.read())


@pytest.mark.parametrize("names,extra", [(["unknown"], {}), (["invoice", "invoice"], {}),
                                        ([" "], {}), (["invoice"], {"code_root": "/tmp"}),
                                        (["invoice"], {"snapshot_path": "/tmp"})])
def test_paths_unknown_names_and_duplicate_names_fail_before_scheduling(client, names, extra):
    response = request(client, names, **extra)
    assert response.status_code == 422
    assert events.read() == []


def test_missing_causal_input_and_stop_refuse_replay(client):
    _, incident, _ = client
    incident.cause_input_id = None
    assert request(client).status_code == 409
    incident.cause_input_id = "in_01"
    gate.STOP.set()
    assert request(client).status_code == 409
    assert events.read() == []


def test_orphan_job_fails_interrupted_without_running(client, monkeypatch):
    http, _, _ = client
    job = ExposureJob(id="exposure_orphan", incident_id="inc_original",
                      agent_names=["invoice"], status="running")
    api._save(job, events.read_batch()[0])
    monkeypatch.setattr(api.exposure, "evaluate", lambda *a: pytest.fail("Orphan resumed"))
    response = http.get("/exposure-jobs/exposure_orphan")
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "interrupted"


def test_old_epoch_work_cannot_write_into_reset_namespace(client, monkeypatch):
    _, _, entry = client
    epoch = events.read_batch()[0]
    job = ExposureJob(id="exposure_old", incident_id="inc_original",
                      agent_names=[entry["agent_name"]], status="queued")
    source = json.loads((snapshot.SNAP_DIR / "inc_original.json").read_text())
    events.reset()
    monkeypatch.setattr(api.exposure, "evaluate", lambda *a: pytest.fail("Stale work replayed"))
    with pytest.raises(events.StaleEpoch):
        api._work(copy.deepcopy(job), source, "in_01", [entry], epoch)
    assert events.read() == []


def test_wire_fixture_validates_without_fabricating_provenance():
    path = Path(__file__).parents[1] / "contracts/fixtures/exposure_demo.json"
    job = ExposureJob.model_validate_json(path.read_text())
    assert [r.status for r in job.results] == ["vulnerable", "not_applicable", "could_not_evaluate"]
    assert job.results[0].replay_kind == "scripted" and job.results[0].code_revision is None


def test_replay_router_never_executes_or_reads_live_receipts(client, monkeypatch):
    _, incident, _ = client
    response = request(client)
    assert response.status_code == 202
    job_id = response.json()["id"]
    app = FastAPI()
    app.include_router(api.create_router(lambda _: incident, replay=True))
    with TestClient(app) as recorded:
        assert recorded.get("/exposure-jobs").json() == []
        assert recorded.get(f"/exposure-jobs/{job_id}").status_code == 404
        assert recorded.get("/incidents/inc_original/exposure-candidates").json() == []
        assert recorded.post("/incidents/inc_original/exposure-jobs", json={
            "agent_names": ["invoice"], "actor": "operator", "reason": "test"}).status_code == 409


def test_exposure_shares_queue_and_reset_exclusion_with_other_incidents(client, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def hold(_):
        started.set()
        assert release.wait(5)
    jobs.submit("inc_other", hold)
    assert started.wait(2)
    calls = []
    original = api.exposure.evaluate
    monkeypatch.setattr(api.exposure, "evaluate", lambda *args: calls.append(args) or original(*args))
    try:
        created = request(client)
        assert created.status_code == 202 and created.json()["status"] == "queued"
        assert calls == []
        # The gateway's shared lock remains available while the other sandbox is running.
        assert jobs.lock.acquire(blocking=False)
        jobs.lock.release()
        with pytest.raises(jobs.Busy), jobs.resetting():
            pytest.fail("Reset entered during active sandbox work")
    finally:
        release.set()
    jobs.shutdown()
    history = events.read()
    own = [e for e in history if e.incident_id == "inc_original"]
    assert not any("sandbox_job" in e.payload or e.type.startswith("detonation.") for e in own)
    final = client[0].get(f"/exposure-jobs/{created.json()['id']}").json()
    assert final["status"] in ("completed", "failed")
    if final["status"] == "failed":
        assert final["error"] == "interrupted"
