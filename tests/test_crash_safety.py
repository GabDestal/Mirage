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


@pytest.mark.parametrize("verify", [False, True])
def test_a_leak_before_a_crash_still_counts(verify):
    save_incident()
    switch_code("inc_001", "tests.sandbox_agents:leaks_then_crashes")
    detonation, verdict, result = sandbox.detonate(
        "inc_001", n_runs=1, verify=verify, log=lambda *_: None)
    assert verdict.confirmed and verdict.blast_radius.recipients == [ATTACKER]
    assert detonation.n_runs == 1 and detonation.compromised_runs == 1
    assert verdict.compromised_runs == "1/1"
    assert result.attack_blocked == "0/1" and result.legit_task_completed == "0/1"
    assert not result.passed
    assert "1 of 1 runs sent 1 records" in verdict.blast_radius.summary
    assert "0 of 1 replays completed; 1 crashed" in verdict.blast_radius.summary
    assert "run 1: RuntimeError: agent crashed after leaking" in verdict.blast_radius.summary
    assert len(result.effects) == 1 and result.effects[0].run_index == 1
    assert result.effects[0].args["to"] == ATTACKER and result.effects[0].violates
    diagnostic = next(e for e in events.read() if e.type == "agent.message")
    assert diagnostic.env == "mirage" and diagnostic.incident_id == "inc_001"
    assert diagnostic.payload["role"] == "system"
    assert detonation.id in diagnostic.payload["text"] and "replay 1/1 crashed" in (
        diagnostic.payload["text"])
    assert "RuntimeError: agent crashed after leaking" in diagnostic.payload["text"]
    terminal = events.read()[-1]
    if verify:
        assert terminal.type == "fix.verified" and terminal.payload["passed"] is False
    else:
        assert terminal.type == "verdict.ready"
        assert "agent crashed after leaking" in terminal.payload["blast_radius"]["summary"]


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
