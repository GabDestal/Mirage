"""Who triggered what is logged; registrations and STOP survive an engine restart; *@domain."""

import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.detection.rules import POLICY, hard_rule
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, HUMAN
from tests.test_bisect import ATTACKER, save_incident


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    return TestClient(server.app)


def test_wildcard_domains_in_an_allowlist():
    policy = {**POLICY, "destinations": {"email_domains": ["*@contoso-demo.com"],
                                         "url_domains": []}}
    assert hard_rule("assistant", "send_email", {"to": "ben@contoso-demo.com"}, policy) is None
    assert hard_rule("assistant", "send_email", {"to": ATTACKER}, policy)[0] == "DEST_NOT_ALLOWED"


def test_who_triggered_detonate_find_cause_and_verify_is_logged(api, monkeypatch):
    from engine.detonation import jobs

    save_incident("inc_005")
    events.emit("run.started", {"task": "t", "agent": "assistant"}, run_id="run_002")
    events.emit("gate.decision", {"call_id": "c9", "tool": "send_email", "args": {"to": ATTACKER},
                                  "decision": "freeze", "layer": "hard_rule",
                                  "rule_id": "DEST_NOT_ALLOWED", "explanation": "x"},
                run_id="run_002")
    events.emit("incident.opened", {"incident_id": "inc_005", "trigger_call_id": "c9"},
                run_id="run_002", incident_id="inc_005")
    events.emit("verdict.ready", {"incident_id": "inc_005", "confirmed": True,
                                  "compromised_runs": "3/3", "policies_violated": [],
                                  "blast_radius": {"records": 0, "recipients": [], "secrets": [],
                                                   "summary": ""}},
                incident_id="inc_005", env="mirage")
    monkeypatch.setattr(server.sandbox, "detonate", lambda *a, **k: None)  # no real sandbox
    monkeypatch.setattr(server.engine_bisect, "bisect", lambda *a, **k: None)

    assert api.post("/incidents/inc_005/detonate", json={
        "actor": "gabi via UI", "reason": "check it"}).status_code == 200
    jobs._pool.submit(lambda: None).result(timeout=5)
    assert api.post("/incidents/inc_005/bisect", json=HUMAN).status_code == 200
    jobs._pool.submit(lambda: None).result(timeout=5)
    assert api.post("/incidents/inc_005/verify").status_code == 200  # MCP without a body
    jobs._pool.submit(lambda: None).result(timeout=5)
    audit = [(e.payload["actor"], e.payload["action"]) for e in events.read()
             if e.type == "human.action"]
    assert audit == [("gabi via UI", "detonate"), ("gabi", "find_cause"), ("unknown", "verify")]


def test_registrations_and_stop_survive_an_engine_restart(api):
    api.post("/agents", json=AGENT)
    api.post("/stop", json=HUMAN)
    gate.reset()  # what a restart loses: everything in memory
    assert not gate.agents and not gate.STOP.is_set()

    server.restore()  # what the engine does at startup
    assert AGENT["name"] in gate.agents and gate.STOP.is_set()
    assert api.post("/runs", json={"agent": AGENT["name"], "task": "t"}).status_code == 409
