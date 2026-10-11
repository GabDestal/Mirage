"""Layer 2 (decision model) and the deterministic bulk-export rule. The model is faked."""

import json

import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.detection import decision_model
from engine.detection.rules import POLICY, hard_rule
from engine.gateway import gate
from tests.test_api import AGENT, check, start

CONTACTS = " ".join(f"c{i}@contoso-demo.com" for i in range(8))
NAMES = "Ben Okafor, Grace Li, Alice Martin, Chloe Dubois, David Kim, Emma Rossi"


def fake_model(monkeypatch, answer):
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        if isinstance(answer, Exception):
            raise answer
        return {"output": {"message": {"content": [{"text": json.dumps(answer)}]}}}

    monkeypatch.setenv("MIRAGE_LAYER2", "1")
    monkeypatch.setattr(decision_model, "_converse", converse)
    return calls


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    client = TestClient(server.app)
    spec = {**AGENT, "allow": {**AGENT["allow"], "email_to": ["*@contoso-demo.com", "demo-user@mirage-demo.com"]}}
    client.post("/agents", json=spec)
    return client


def test_bulk_records_is_a_deterministic_p4_even_to_an_allowed_domain():
    policy = {**POLICY, "agents": {"a": {"tools": ["send_email"]}},
              "destinations": {"email_domains": ["*@contoso-demo.com"], "url_domains": []}}
    leak = {"to": "partners@contoso-demo.com", "body": CONTACTS}
    assert hard_rule("a", "send_email", leak, policy)[0] == "BULK_RECORDS"
    brief = {"to": "partners@contoso-demo.com", "body": " ".join(CONTACTS.split()[:4])}
    assert hard_rule("a", "send_email", brief, policy) is None  # a brief with a few attendees


def test_the_model_freezes_what_the_rules_allow(api, monkeypatch):
    calls = fake_model(monkeypatch, {"violates": True, "policy_id": "P4", "p": 0.97,
                                     "reason": "The body lists the customers by name."})
    run_id, auth = start(api)
    d = check(api, run_id, auth, "send_email", to="partners@contoso-demo.com", subject="x", body=NAMES).json()
    assert (d["decision"], d["layer"], d["policy_id"], d["p"]) == ("freeze", "decision_model", "P4", 0.97)
    assert api.get("/incidents").json()[0]["trigger"]["layer"] == "decision_model"
    assert "<call>" in calls[0]["messages"][0]["content"][0]["text"]  # args fenced as data


def test_below_threshold_reads_and_outages_are_allowed(api, monkeypatch):
    calls = fake_model(monkeypatch, {"violates": True, "policy_id": "P5", "p": 0.3, "reason": "unsure"})
    run_id, auth = start(api)
    assert check(api, run_id, auth, "send_email", to="ben@contoso-demo.com", subject="Hi",
                 body="Thanks for the call.").json()["decision"] == "allow"
    check(api, run_id, auth, "read_calendar", date="2026-10-11")
    assert len(calls) == 1  # the read was not sent to the model

    fake_model(monkeypatch, TimeoutError("Bedrock timed out"))
    d = check(api, run_id, auth, "send_email", to="ben@contoso-demo.com", subject="Hi", body="x").json()
    assert d["decision"] == "allow" and "Layer 2 unavailable: TimeoutError" in d["explanation"]


def test_a_bulk_export_effect_is_a_p4_violation_in_the_verdict():
    from engine.detonation import sandbox
    snap = {"agent": "a", "policy": {**POLICY, "agents": {"a": {"tools": ["send_email"]}},
            "destinations": {"email_domains": ["*@contoso-demo.com"], "url_domains": []}}}
    effect = {"tool": "send_email", "args": {"to": "partners@contoso-demo.com", "body": CONTACTS}}
    assert sandbox.violations(snap, effect, [snap["policy"]]) == ["P4"]


def test_medium_risk_opens_incident_and_cannot_use_legacy_human_approval(api, monkeypatch):
    from engine.store import events
    fake_model(monkeypatch, {"violates": True, "policy_id": "P5", "p": 0.55,
                             "reason": "A recipient the user did not name."})
    run_id, auth = start(api)
    d = check(api, run_id, auth, "send_email", to="ben@contoso-demo.com", subject="Hi", body="x").json()
    assert (d["decision"], d["rule_id"], d["layer"], d["p"]) == ("freeze", "SANDBOX_REVIEW", "decision_model", 0.55)
    assert api.get(f"/runs/{run_id}").json()["status"] == "frozen"
    (incident,) = api.get("/incidents").json()
    assert incident["trigger"]["call_id"] == d["call_id"]
    assert incident["automatic_clearance"]["status"] == "checking"
    assert api.get("/approvals").json() == []
    assert api.post(f"/approvals/{d['call_id']}/approve", json={"actor": "a", "reason": "b"}).status_code == 404

    human = {"actor": "gabi", "reason": "unknown recipient"}
    assert api.post(f"/runs/{run_id}/unfreeze", json=human).status_code == 409
    assert api.post(f"/runs/{run_id}/kill", json=human).json()["status"] == "killed"
    actions = [e.payload["action"] for e in events.read() if e.type == "human.action"]
    assert actions == ["kill"]
