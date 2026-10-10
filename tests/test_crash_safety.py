"""A replay that crashed proves nothing: it must never turn into a "false positive"."""

import time

import pytest
from fastapi.testclient import TestClient

from engine import cli
from engine.api import server
from engine.detonation import sandbox
from engine.gateway import gate
from engine.store import events
from tests.test_bisect import ATTACKER, save_incident
from tests.test_verify import switch_code


def test_every_replay_crashing_gives_no_verdict():
    save_incident()
    switch_code("inc_001", "agents.run_demo_fleet:start_worker")  # the bug found live
    with pytest.raises(sandbox.DetonationError, match="crashed"):
        sandbox.detonate("inc_001", n_runs=2, log=lambda *_: None)
    assert not any(e.type == "verdict.ready" for e in events.read())
    assert cli.main(["detonate", "--incident", "inc_001", "--runs", "1", "--from-freeze"]) == 2


def test_a_leak_before_a_crash_still_counts():
    save_incident()
    switch_code("inc_001", "tests.sandbox_agents:leaks_then_crashes")
    _, verdict, _ = sandbox.detonate("inc_001", n_runs=1, log=lambda *_: None)
    assert verdict.confirmed and verdict.blast_radius.recipients == [ATTACKER]


def test_the_api_reports_a_failed_detonation_not_a_false_positive(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    save_incident("inc_003")
    switch_code("inc_003", "agents.run_demo_fleet:start_worker")
    events.emit("run.started", {"task": "t", "agent": "assistant"}, run_id="run_002")
    events.emit("gate.decision", {"call_id": "c9", "tool": "send_email", "args": {"to": ATTACKER},
                                  "decision": "freeze", "layer": "hard_rule",
                                  "rule_id": "DEST_NOT_ALLOWED", "explanation": "x"},
                run_id="run_002")
    events.emit("incident.opened", {"incident_id": "inc_003", "trigger_call_id": "c9"},
                run_id="run_002", incident_id="inc_003")
    api = TestClient(server.app)
    api.post("/incidents/inc_003/detonate?runs=1")
    for _ in range(600):  # up to 60 s
        if any(e.type == "detonation.failed" for e in events.read()):
            break
        time.sleep(0.1)
    failed = next(e for e in events.read() if e.type == "detonation.failed")
    assert "crashed" in failed.payload["error"] and "start_worker" in failed.payload["error"]
    incident = api.get("/incidents/inc_003").json()
    assert incident["status"] == "open" and incident["verdict"] is None  # retry, not "false alarm"
    assert incident["next_action"] == "detonate"
