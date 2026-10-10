"""Clean restart: a human approves, the new run waits queued, the agent's next start takes it."""

import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, check, start


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    client = TestClient(server.app)
    client.post("/agents", json=AGENT)
    return client


def test_approved_restart_is_taken_over_by_the_agents_next_start(api):
    run_id, auth = start(api)
    check(api, run_id, auth, "send_email", to=ATTACKER, subject="x", body="rows")  # frozen
    assert api.post(f"/runs/{run_id}/restart", json=HUMAN).status_code == 409  # kill first
    api.post(f"/runs/{run_id}/kill", json=HUMAN)

    new = api.post(f"/runs/{run_id}/restart", json=HUMAN).json()
    assert new["status"] == "queued" and new["restarted_from"] == run_id
    assert new["id"] != run_id
    assert any(e.type == "human.action" and e.payload["action"] == "approve_restart"
               for e in events.read())

    started = api.post("/runs", json={"agent": AGENT["name"], "task": "Prep my meetings"}).json()
    assert started["run_id"] == new["id"]  # the SDK's next start took the queued run
    run = api.get(f"/runs/{new['id']}").json()
    assert run["status"] == "running" and run["restarted_from"] == run_id


def test_ids_continue_from_the_log_across_processes(api):
    # run_005 was killed by another process (only its events are here)
    events.emit("run.started", {"task": "Prep", "agent": AGENT["name"]}, run_id="run_005")
    events.emit("run.status", {"from": "running", "to": "killed", "actor": "x", "reason": "x"},
                run_id="run_005")
    new = api.post("/runs/run_005/restart", json=HUMAN).json()
    assert new["id"] == "run_006" and new["restarted_from"] == "run_005"
