"""After Stop all: a human resumes halted runs (the engine lifts the stop and relaunches them)."""

import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, _verdict, check, start
from tests.test_demo_control import FakeProcess


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(server.subprocess, "Popen", FakeProcess)
    FakeProcess.launched = []
    server._demo["resumed"] = []
    gate.reset()
    client = TestClient(server.app)
    client.post("/agents", json=AGENT)
    yield client
    server._demo["resumed"] = []


def test_lift_is_logged_and_survives_an_engine_restart(api):
    api.post("/stop", json=HUMAN)
    assert api.post("/stop/lift", json=HUMAN).status_code == 204
    assert not gate.STOP.is_set()
    assert any(e.type == "human.action" and e.payload["action"] == "lift_stop"
               for e in events.read())
    assert events.read()[-1].type == "global.stop_lifted"

    gate.reset()
    server.restore()  # the latest of stop and lift wins
    assert not gate.STOP.is_set()
    api.post("/stop", json=HUMAN)
    gate.reset()
    server.restore()
    assert gate.STOP.is_set()


def test_resume_lifts_the_stop_and_relaunches_a_halted_run(api):
    run_id, _ = start(api)
    assert api.post(f"/runs/{run_id}/resume", json=HUMAN).status_code == 409  # running
    api.post("/stop", json=HUMAN)
    new = api.post(f"/runs/{run_id}/resume", json=HUMAN).json()
    assert not gate.STOP.is_set()
    assert [e.type for e in events.read()].count("global.stop_lifted") == 1
    assert new["status"] == "queued" and new["restarted_from"] == run_id
    assert api.get(f"/runs/{run_id}").json()["status"] == "halted"
    assert any(e.type == "human.action" and e.payload["action"] == "resume"
               for e in events.read())
    (proc,) = FakeProcess.launched
    assert proc.args[-2:] == [AGENT["entrypoint"], "Prep my meetings"]
    assert proc.env["MIRAGE_URL"] == "http://testserver"

    api.post("/stop", json=HUMAN)  # Stop all also ends relaunched agents
    assert proc.stopped


def test_resume_refuses_a_confirmed_compromised_run(api):
    run_id, auth = start(api)
    check(api, run_id, auth, "send_email", to=ATTACKER, subject="x", body="y")  # frozen
    inc_id = gate.runs[run_id].incident_id
    events.emit("verdict.ready", _verdict(inc_id, True), run_id=run_id, incident_id=inc_id,
                env="mirage")
    api.post("/stop", json=HUMAN)
    r = api.post(f"/runs/{run_id}/resume", json=HUMAN)
    assert r.status_code == 409 and "confirmed this run is compromised" in r.json()["detail"]
    assert FakeProcess.launched == []
    assert gate.STOP.is_set()  # a refused resume leaves Stop all on


def test_reset_ends_relaunched_agents(api):
    run_id, _ = start(api)
    api.post("/stop", json=HUMAN)
    api.post(f"/runs/{run_id}/resume", json=HUMAN)
    api.post("/demo/reset")
    assert FakeProcess.launched[0].stopped


def test_resume_all_lifts_the_stop_and_resumes_every_clean_halted_run(api):
    bad, auth = start(api)
    check(api, bad, auth, "send_email", to=ATTACKER, subject="x", body="y")  # frozen
    inc_id = gate.runs[bad].incident_id
    events.emit("verdict.ready", _verdict(inc_id, True), run_id=bad, incident_id=inc_id, env="mirage")
    clean, _ = start(api)
    api.post("/stop", json=HUMAN)

    r = api.post("/resume-all", json=HUMAN).json()
    assert not gate.STOP.is_set()
    assert [n["restarted_from"] for n in r["resumed"]] == [clean]
    assert [s["run_id"] for s in r["skipped"]] == [bad]
    assert "compromised" in r["skipped"][0]["reason"]
    assert len(FakeProcess.launched) == 1
    actions = [e.payload["action"] for e in events.read() if e.type == "human.action"]
    assert actions.count("lift_stop") == 1 and actions.count("resume") == 1

    again = api.post("/resume-all", json=HUMAN).json()  # idempotent: the clean run was restarted
    assert again["resumed"] == [] and [s["run_id"] for s in again["skipped"]] == [bad]
    assert len(FakeProcess.launched) == 1
    assert [e.payload["action"] for e in events.read() if e.type == "human.action"].count("lift_stop") == 1
