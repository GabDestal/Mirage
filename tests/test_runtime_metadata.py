"""Runtime ownership and durable proof jobs, with synthetic work and isolated stores."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.detonation import jobs
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, check, start

REPO = Path(__file__).parents[1]
PRIVATE_MARKER = "SYNTHETIC_PRIVATE_PROVIDER_ARGUMENT_9471"


class DeferredPool:
    """Reserve real jobs deterministically before their executor starts."""

    def __init__(self):
        self.work = []

    def submit(self, work):
        future = Future()
        self.work.append((work, future))
        return future

    def run_next(self):
        work, future = self.work.pop(0)
        if future.set_running_or_notify_cancel():
            future.set_result(work())

    def shutdown(self, **kwargs):
        for _, future in self.work:
            future.cancel()


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    with TestClient(server.app) as client:
        assert client.post("/agents", json=AGENT).status_code == 200
        yield client
    gate.reset()


@pytest.fixture
def deferred(monkeypatch):
    pool = DeferredPool()
    monkeypatch.setattr(jobs, "_pool", pool)
    yield pool
    jobs.shutdown()


def freeze(api):
    run_id, auth = start(api)
    assert check(api, run_id, auth, "send_email", to=ATTACKER).json()["decision"] == "freeze"
    return run_id, gate.runs[run_id].incident_id


def runtime(api):
    response = api.get("/runtime")
    assert response.status_code == 200, "Runtime truth must be exposed independently of history"
    body = response.json()
    assert set(body) == {"engine_mode", "instance_id", "stream_epoch", "last_seq",
                         "revision", "owned_run_ids"}
    assert body["instance_id"] and body["stream_epoch"]
    return body


def public_job(api, incident_id):
    body = api.get(f"/incidents/{incident_id}").json()
    assert "sandbox_job" in body, "Incident must expose structured queue/execution state"
    assert body["sandbox_job"] is not None
    return body["sandbox_job"]


def child(code, tmp_path, *, mode="live", git_available=True):
    # No inherited credentials or dotenv; every data path is a synthetic temporary path.
    env = {"PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(REPO),
           "MIRAGE_MODE": mode, "MIRAGE_LAYER2": "0", "MIRAGE_JUDGE": "0",
           "MIRAGE_DB": str(events.DB_PATH), "MIRAGE_SNAPSHOTS": str(tmp_path / "snapshots"),
           "MIRAGE_TOKENS": str(tmp_path / "tokens.json"),
           "MIRAGE_REPLAY_SPEED": "inf", "PATH": os.defpath if git_available else ""}
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def first_frame(last_event_id):
    async def read():
        async def connected():
            return False

        request = SimpleNamespace(headers={"last-event-id": str(last_event_id)},
                                  is_disconnected=connected)
        response = await server.stream(request)
        try:
            return await asyncio.wait_for(anext(response.body_iterator), timeout=1)
        finally:
            await response.body_iterator.aclose()

    return asyncio.run(read())


def test_runtime_reports_current_owners_separately_from_external_history(api):
    owned, _ = start(api)
    events.emit("run.started", {"agent": "external", "task": "Synthetic external task"},
                run_id="run_external")
    body = runtime(api)
    assert body["engine_mode"] == "live"
    assert body["owned_run_ids"] == [owned]
    assert body["last_seq"] == events.read()[-1].seq
    assert api.get("/runs/run_external").json()["status"] == "running"
    assert api.post("/runs/run_external/freeze", json=HUMAN).status_code == 409
    assert body["revision"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def test_no_job_is_null_and_legacy_fixture_still_folds(api):
    _, incident_id = freeze(api)
    body = api.get(f"/incidents/{incident_id}").json()
    assert "sandbox_job" in body and body["sandbox_job"] is None
    recorded = server.Replay(server.FIXTURES / "sample_demo.jsonl", float("inf"))
    recorded.restart()
    assert all(inc.sandbox_job is None for inc in recorded.state()[1].values())


@pytest.mark.parametrize("purpose", ["detonate", "bisect", "verify"])
def test_job_is_visible_when_reserved_then_running_and_completed(api, deferred, purpose):
    run_id, incident_id = freeze(api)
    seen = []

    def work(_):
        seen.append(public_job(api, incident_id))

    job_id = jobs.submit(incident_id, work, purpose=purpose, n_runs=2)
    queued = public_job(api, incident_id)
    assert queued == {"id": job_id, "purpose": purpose, "status": "queued",
                      "n_runs": 2, "error": None}
    assert seen == [] and jobs.running(incident_id)
    deferred.run_next()
    assert seen == [{**queued, "status": "running"}]
    completed = public_job(api, incident_id)
    assert completed == {**queued, "status": "completed"}
    assert server.fold(events.read())[1][incident_id].sandbox_job.model_dump() == completed
    assert not jobs.running(incident_id)
    assert gate.runs[run_id].status == "frozen" and not gate.runs[run_id].resume.is_set()
    persisted = [e.payload["sandbox_job"]["status"] for e in events.read()
                 if e.incident_id == incident_id and "sandbox_job" in e.payload]
    assert persisted == ["queued", "running", "completed"]


@pytest.mark.parametrize("purpose", ["detonate", "bisect", "verify"])
def test_failure_is_durable_and_never_exposes_private_exception(api, deferred, purpose):
    run_id, incident_id = freeze(api)

    def fail(_):
        raise RuntimeError(PRIVATE_MARKER)

    jobs.submit(incident_id, fail, purpose=purpose, n_runs=2)
    deferred.run_next()
    # Check raw public events before the new projection, to prove the real exposure on main.
    assert PRIVATE_MARKER not in api.get("/events").text
    failed = public_job(api, incident_id)
    assert failed["status"] == "failed" and failed["purpose"] == purpose
    assert failed["error"] and len(failed["error"]) < 80
    assert PRIVATE_MARKER not in api.get("/incidents").text
    assert PRIVATE_MARKER not in json.dumps(first_frame(0))
    assert gate.runs[run_id].status == "frozen" and not gate.runs[run_id].resume.is_set()
    assert not jobs.running(incident_id)
    assert any(e.payload.get("sandbox_job") == failed for e in events.read())
    assert server.fold(events.read())[1][incident_id].sandbox_job.model_dump() == failed


def test_executor_failure_is_publicly_sanitized_and_releases_reservation(api, monkeypatch):
    _, incident_id = freeze(api)

    class BrokenPool:
        def submit(self, work):
            raise RuntimeError(PRIVATE_MARKER)

        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(jobs, "_pool", BrokenPool())
    response = api.post(f"/incidents/{incident_id}/detonate", json=HUMAN)
    assert response.status_code == 503
    assert PRIVATE_MARKER not in response.text + api.get("/events").text
    assert public_job(api, incident_id)["status"] == "failed"
    assert not jobs.running(incident_id)


def test_reset_is_excluded_while_active_and_changes_epoch_only_when_accepted(api):
    _, incident_id = freeze(api)
    entered, release = threading.Event(), threading.Event()

    def work(_):
        entered.set()
        assert release.wait(5)

    before = runtime(api)
    jobs.submit(incident_id, work)
    try:
        assert entered.wait(2)
        assert api.post("/demo/reset").status_code == 409
        assert runtime(api)["stream_epoch"] == before["stream_epoch"]
        assert public_job(api, incident_id)["status"] == "running"
    finally:
        release.set()
        jobs.shutdown()
    assert api.post("/demo/reset").status_code == 204
    after = runtime(api)
    assert after["instance_id"] == before["instance_id"]
    assert after["stream_epoch"] != before["stream_epoch"]
    assert after["last_seq"] == 0 and after["owned_run_ids"] == []


def test_external_lower_sequence_reset_changes_epoch_and_recovers_events(api, tmp_path):
    old_run, _ = start(api)
    for index in range(8):
        events.emit("agent.message", {"text": f"Old synthetic event {index}"})
    before = runtime(api)
    assert before["owned_run_ids"] == [old_run]
    child('''
import json
from engine.store import events
events.reset()
event = events.emit("agent.message", {"text": "Fresh synthetic generation"})
print(json.dumps(event.model_dump(mode="json")))
''', tmp_path)
    stale = api.get(f"/events?after={before['last_seq']}")
    epoch = stale.headers.get("X-Mirage-Stream-Epoch")
    assert epoch and epoch != before["stream_epoch"]
    after = runtime(api)
    assert after["instance_id"] == before["instance_id"]
    assert after["stream_epoch"] == epoch and after["last_seq"] == 1
    assert after["owned_run_ids"] == []
    fresh = api.get("/events")
    assert fresh.headers["X-Mirage-Stream-Epoch"] == epoch
    assert [e["payload"]["text"] for e in fresh.json()] == ["Fresh synthetic generation"]


def test_sse_first_frame_is_named_runtime_even_when_business_events_exist(api):
    frame = first_frame(0)
    assert frame.get("event") == "runtime", "Business history cannot establish live ownership"
    assert "id" not in frame
    assert json.loads(frame["data"]) == runtime(api)


def test_sse_reconnect_starts_with_runtime_before_stale_cursor_filtering(api):
    before = runtime(api)
    assert api.post("/demo/reset").status_code == 204
    frame = first_frame(before["last_seq"] + 1000)
    assert frame.get("event") == "runtime", "Reconnect must publish runtime before event filtering"
    assert "id" not in frame  # runtime frames must not overwrite the business event cursor
    body = json.loads(frame["data"])
    assert body == runtime(api)
    assert body["stream_epoch"] != before["stream_epoch"]


@pytest.mark.parametrize("status", ["queued", "running"])
def test_new_process_restore_retains_history_without_owners_or_live_jobs(
        api, deferred, tmp_path, status):
    run_id, incident_id = freeze(api)
    job_id = jobs.submit(incident_id, lambda _: pytest.fail("Restored work must never execute"))
    if status == "running":
        events.emit("detonation.started", {"incident_id": incident_id,
                    "detonation_id": job_id, "purpose": "detonate", "n_runs": 3,
                    "sandbox_job": {"id": job_id, "purpose": "detonate", "status": status,
                                    "n_runs": 3, "error": None}},
                    incident_id=incident_id, env="mirage")
    before = runtime(api)
    restored = child(f'''
import json
from fastapi.testclient import TestClient
from engine.api import server
from engine.detonation import sandbox
from engine.gateway import gate
def forbidden(*args, **kwargs):
    raise AssertionError("Restore must never automatically replay")
sandbox.detonate = forbidden
with TestClient(server.app) as api:
    print(json.dumps({{
        "runtime": api.get("/runtime").json(),
        "run": api.get("/runs/{run_id}").json(),
        "incident": api.get("/incidents/{incident_id}").json(),
        "control": api.post("/runs/{run_id}/unfreeze", json={HUMAN!r}).status_code,
        "owners": list(gate.runs),
    }}))
''', tmp_path)
    body = restored["runtime"]
    assert body["instance_id"] != before["instance_id"]
    assert body["stream_epoch"] != before["stream_epoch"]
    assert body["owned_run_ids"] == restored["owners"] == []
    assert restored["run"]["status"] == "frozen"
    job = restored["incident"]["sandbox_job"]
    assert job["status"] == "failed" and job["error"] == "interrupted"
    assert restored["control"] == 409


def test_absent_git_provenance_is_null(tmp_path):
    body = child('''
import json
from fastapi.testclient import TestClient
from engine.api import server
with TestClient(server.app) as api:
    response = api.get("/runtime")
    assert response.status_code == 200
    print(response.text)
''', tmp_path, git_available=False)
    assert body["revision"] is None


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_runtime_mode_is_the_immutable_startup_mode(tmp_path, mode):
    body = child('''
import json
import os
from fastapi.testclient import TestClient
from engine.api import server
from engine.config import MODE
from engine.gateway import gate
os.environ["MIRAGE_MODE"] = "replay" if MODE == "live" else "live"
with TestClient(server.app) as api:
    response = api.get("/runtime")
    assert response.status_code == 200
    print(json.dumps({"runtime": api.get("/runtime").json(), "gate_mode": gate.MODE,
                      "replay": server.REPLAY is not None}))
''', tmp_path, mode=mode)
    assert body["runtime"]["engine_mode"] == body["gate_mode"] == mode
    assert body["replay"] is (mode == "replay")
