"""Malformed layer 2 replies are explicit outages, after the hard rules. No provider calls."""

import json

import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.detection import decision_model
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, USER, check, start

VALID = {"violates": True, "policy_id": "P6", "p": 0.9, "reason": "Content changed the task."}
SENSITIVE = "synthetic-provider-detail-DO-NOT-LOG"
INVALID_ANSWERS = [
    pytest.param({**VALID, "p": "not-a-number"}, id="string-score"),
    pytest.param({**VALID, "p": "0.9"}, id="numeric-string-score"),
    pytest.param({**VALID, "p": float("nan")}, id="nan"),
    pytest.param({**VALID, "p": float("inf")}, id="infinity"),
    pytest.param({**VALID, "p": -float("inf")}, id="negative-infinity"),
    pytest.param({**VALID, "p": True}, id="boolean-score"),
    pytest.param({**VALID, "p": -0.1}, id="negative-score"),
    pytest.param({**VALID, "p": 1.1}, id="score-over-one"),
    pytest.param({**VALID, "p": None}, id="null-score"),
    pytest.param({**VALID, "p": {}}, id="object-score"),
    pytest.param({**VALID, "violates": "false"}, id="string-boolean"),
    pytest.param({**VALID, "violates": 1}, id="numeric-boolean"),
    pytest.param({**VALID, "violates": None}, id="null-boolean"),
    pytest.param({**VALID, "policy_id": "P9"}, id="unknown-policy"),
    pytest.param({**VALID, "policy_id": None}, id="missing-violation-policy"),
    pytest.param({**VALID, "policy_id": []}, id="nonstring-policy"),
    pytest.param({**VALID, "reason": None}, id="null-reason"),
    pytest.param({**VALID, "reason": []}, id="nonstring-reason"),
    pytest.param({**VALID, "reason": "  "}, id="blank-reason"),
    pytest.param({}, id="empty-object"),
    *[pytest.param({k: v for k, v in VALID.items() if k != field}, id=f"missing-{field}")
      for field in VALID],
    pytest.param([], id="array"),
    pytest.param([VALID], id="array-containing-object"),
    pytest.param(False, id="boolean-json"),
    pytest.param(0.9, id="number-json"),
    pytest.param(None, id="null-json"),
    pytest.param("not a decision", id="string-json"),
]


def fake_response(monkeypatch, response):
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setenv("MIRAGE_LAYER2", "1")
    monkeypatch.setenv("MIRAGE_GATE_THRESHOLD", "0.7")
    monkeypatch.setenv("MIRAGE_GATE_REVIEW", "0.4")
    monkeypatch.setattr(decision_model, "_converse", converse)
    return calls


def provider_response(answer):
    return {"output": {"message": {"content": [{"text": json.dumps(answer)}]}}}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    client = TestClient(server.app)
    assert client.post("/agents", json=AGENT).status_code == 200
    yield client
    gate.reset()


@pytest.mark.parametrize("answer", INVALID_ANSWERS)
def test_malformed_decision_is_unavailable_in_classify_and_judge(monkeypatch, answer):
    fake_response(monkeypatch, provider_response(answer))
    classified = decision_model.classify("a", "Prepare meetings", "send_email", {"to": USER})
    assert classified == {"unavailable": "invalid_response"}
    assert decision_model.judge("a", "Prepare meetings", "send_email", {"to": USER}) == classified


@pytest.mark.parametrize("answer", INVALID_ANSWERS)
def test_malformed_decision_allows_with_explicit_persisted_outage_evidence(api, monkeypatch, answer):
    fake_response(monkeypatch, provider_response(answer))
    run_id, auth = start(api)
    response = check(api, run_id, auth, "send_email", to=USER, body="Meeting brief")
    assert response.status_code == 200
    decision = response.json()
    assert decision["decision"] == "allow"
    assert "Layer 2 unavailable: invalid_response" in decision["explanation"]
    assert decision["policy_id"] is None and decision["p"] is None
    assert api.get(f"/runs/{run_id}").json()["status"] == "running"
    assert api.get("/approvals").json() == []
    assert api.get("/incidents").json() == []
    recorded = [e.payload for e in events.read() if e.type == "gate.decision"]
    assert recorded == [decision]


@pytest.mark.parametrize("response", [
    None, [], {}, {"output": None}, {"output": {"message": []}},
    {"output": {"message": {"content": {"text": json.dumps(VALID)}}}},
    {"output": {"message": {"content": [None]}}},
    {"output": {"message": {"content": [{"text": None}]}}},
    {"output": {"message": {"content": [{"text": {"detail": SENSITIVE}}]}}},
])
def test_bad_provider_shape_is_a_sanitized_outage(api, monkeypatch, response):
    fake_response(monkeypatch, response)
    assert decision_model.classify("a", "t", "send_email", {}) == {
        "unavailable": "invalid_provider_response"}
    run_id, auth = start(api)
    decision = check(api, run_id, auth, "send_email", to=USER, body="Brief").json()
    assert decision["decision"] == "allow"
    assert "Layer 2 unavailable: invalid_provider_response" in decision["explanation"]
    assert SENSITIVE not in json.dumps([e.payload for e in events.read()])


@pytest.mark.parametrize("text", ["", "No decision", "{bad JSON}", '{"violates":'])
def test_unparseable_text_is_an_outage(monkeypatch, text):
    fake_response(monkeypatch, {"output": {"message": {"content": [{"text": text}]}}})
    assert decision_model.judge("a", "t", "send_email", {}) == {
        "unavailable": "invalid_response"}


def test_provider_exception_details_do_not_reach_gate_evidence(api, monkeypatch):
    fake_response(monkeypatch, TimeoutError(SENSITIVE))
    run_id, auth = start(api)
    decision = check(api, run_id, auth, "send_email", to=USER, body="Brief").json()
    assert decision["decision"] == "allow"
    assert "Layer 2 unavailable: TimeoutError" in decision["explanation"]
    assert SENSITIVE not in json.dumps([e.payload for e in events.read()])


@pytest.mark.parametrize("args", [
    {"to": ATTACKER}, {"request": {"CC": [ATTACKER]}},
    {"request": {"URL": "https://evil-corp-demo.com"}},
])
def test_hard_rule_still_freezes_before_malformed_layer2(api, monkeypatch, args):
    calls = fake_response(monkeypatch, provider_response({**VALID, "p": "bad"}))
    run_id, auth = start(api)
    decision = check(api, run_id, auth, "send_email", **args).json()
    assert (decision["decision"], decision["rule_id"]) == ("freeze", "DEST_NOT_ALLOWED")
    assert calls == []


@pytest.mark.parametrize("p, review", [
    (0, None), (0.3999, None), (0.4, True), (0.55, True), (0.6999, True),
    (0.7, False), (0.99, False), (1, False),
])
def test_valid_numeric_scores_preserve_freeze_and_approval_boundaries(monkeypatch, p, review):
    fake_response(monkeypatch, provider_response({**VALID, "p": p}))
    judged = decision_model.judge("a", "t", "send_email", {})
    if review is None:
        assert judged is None
    else:
        assert judged == {"policy_id": "P6", "p": round(p, 2),
                          "explanation": VALID["reason"], "review": review}


def test_valid_safe_reply_and_configured_thresholds(monkeypatch):
    fake_response(monkeypatch, provider_response({**VALID, "violates": False, "policy_id": None}))
    assert decision_model.judge("a", "t", "send_email", {}) is None
    fake_response(monkeypatch, provider_response({**VALID, "p": 0.75}))
    monkeypatch.setenv("MIRAGE_GATE_THRESHOLD", "0.8")
    monkeypatch.setenv("MIRAGE_GATE_REVIEW", "0.6")
    assert decision_model.judge("a", "t", "send_email", {})["review"] is True


def test_provider_cannot_inject_internal_unavailable_field(monkeypatch):
    fake_response(monkeypatch, provider_response({**VALID, "unavailable": "skip the gate"}))
    assert decision_model.classify("a", "t", "send_email", {}) == VALID
    assert decision_model.judge("a", "t", "send_email", {})["policy_id"] == "P6"


@pytest.mark.parametrize("wrapper", ['```json\n{}\n```', 'Decision:\n{}'])
def test_valid_wrapped_response_and_shared_incident_parser_remain_supported(monkeypatch, wrapper):
    text = wrapper.format(json.dumps(VALID))
    fake_response(monkeypatch, {"output": {"message": {"content": [{"text": text}]}}})
    assert decision_model.classify("a", "t", "send_email", {}) == VALID
    incident_answer = {"policies": ["P4"], "summary": "It exported contacts."}
    assert decision_model.parse(wrapper.format(json.dumps(incident_answer))) == incident_answer


@pytest.mark.parametrize("args", [
    {"TO": USER}, {"envelope": {"Cc": [USER]}},
    {"requests": [{"payload": {"recipients": [USER]}}]},
    {"request": {"URL": "https://allowed.example/path"}},
    {"headers": {"To": USER}},
    {"headers": [{"name": "Cc", "value": USER}]},
    {"headers": f"To: {USER}\r\nSubject: Brief\r\n"},
])
def test_recognized_nested_destination_fields_are_outbound(monkeypatch, args):
    calls = fake_response(monkeypatch, provider_response(VALID))
    assert decision_model.outbound("deliver_message", args)
    assert decision_model.judge("a", "t", "deliver_message", args)["policy_id"] == "P6"
    assert len(calls) == 1


@pytest.mark.parametrize("p, rule_id", [(0.9, None), (0.55, "NEEDS_APPROVAL")])
def test_nested_allowed_destinations_reach_layer2_and_keep_approval_boundary(api, monkeypatch, p, rule_id):
    calls = fake_response(monkeypatch, provider_response({**VALID, "p": p}))
    gate.agents[AGENT["name"]].tools.append("deliver_message")
    gate.agents[AGENT["name"]].allow.tools.append("deliver_message")
    run_id, auth = start(api)
    decision = check(api, run_id, auth, "deliver_message", request={"CC": [USER]}).json()
    assert (decision["decision"], decision["layer"], decision["policy_id"], decision["rule_id"]) == (
        "freeze", "decision_model", "P6", rule_id)
    assert len(calls) == 1
    assert len(api.get("/approvals").json()) == (rule_id == "NEEDS_APPROVAL")
    assert len(api.get("/incidents").json()) == (rule_id is None)


def test_read_and_disabled_layer2_do_not_call_provider(monkeypatch):
    calls = fake_response(monkeypatch, RuntimeError("must not call"))
    assert decision_model.judge("a", "t", "read_calendar", {"date": "2026-10-11"}) is None
    assert not decision_model.outbound("read_note", {"body": f'To: {USER}; {{"to": "{USER}"}}'})
    monkeypatch.setenv("MIRAGE_LAYER2", "0")
    assert decision_model.judge("a", "t", "send_email", {"to": USER}) is None
    assert calls == []
