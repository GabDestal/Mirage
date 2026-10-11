"""Human rule lifecycle and immutable admission authority over HTTP."""

import copy
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.detonation import sandbox, snapshot
from engine.gateway import gate
from engine.store import events

USER = "user@synthetic.example"
OTHER = "other@synthetic.example"
SPEC = {"name": "meeting_assistant", "owner": "synthetic-operator",
        "tools": ["read_calendar", "send_email", "fetch_url", "crm_export"],
        "allow": {"tools": ["read_calendar", "send_email", "fetch_url"],
                  "email_to": [USER, OTHER], "url_hosts": ["synthetic.example"]},
        "entrypoint": "tests.sandbox_agents:ignores_invite",
        "legit": {"tool": "send_email", "to": USER}}
HUMAN = {"actor": "synthetic-operator", "reason": "Limit the prepared brief to its named recipient"}
DRAFT = {"agent": SPEC["name"], "allow": {"tools": ["read_calendar", "send_email", "fetch_url"],
                                         "email_to": [USER]}}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(server, "PUBLIC", False)
    gate.reset()
    with TestClient(server.app) as client:
        assert client.post("/agents", json=SPEC).status_code == 200
        yield client
    gate.reset()


def start(api, task="Prepare a brief", **extra):
    response = api.post("/runs", json={"agent": SPEC["name"], "task": task, **extra})
    assert response.status_code == 200, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['run_token']}"}


def check(api, started, auth, recipient):
    response = api.post("/gateway/check", headers=auth, json={
        "run_id": started["run_id"], "tool": "send_email", "args": {"to": recipient}})
    assert response.status_code == 200, response.text
    return response.json()


def test_digest_draft_preview_explicit_activation_and_reload(api):
    old, _ = start(api)
    before = events.read()[-1].seq
    created = api.post("/rules", json=DRAFT)
    assert created.status_code == 200, created.text
    rule = created.json()
    version = rule["version"]
    assert len(version) == 64 and rule["status"] == "draft"
    reordered = copy.deepcopy(DRAFT)
    reordered["allow"]["tools"] = list(reversed(DRAFT["allow"]["tools"])) + ["send_email"]
    reordered["allow"]["email_to"] = [USER.upper(), USER]
    assert api.post("/rules", json=reordered).json() == rule
    assert api.get("/rules").json() == [rule]
    assert api.get(f"/rules/{version}").json() == rule
    assert api.get("/rules?offset=1").json() == []
    assert api.get("/rules?agent=unregistered").json() == []
    assert api.get("/rules/agents").json() == [SPEC]
    after_draft = events.read()[-1].seq
    assert after_draft == before + 1
    assert gate.policy_for(SPEC["name"]).get("rule_revision") is None
    preview = api.post(f"/rules/{version}/preview", json={}).json()
    assert preview["authoritative"] is True
    assert preview["decision"] is None and USER in preview["summary"]
    assert preview["effective_allow"]["url_hosts"] == ["synthetic.example"]
    for recipient, decision in ((USER, "allow"), (OTHER, "freeze")):
        result = api.post(f"/rules/{version}/preview", json={
            "tool": "send_email", "args": {"to": recipient}}).json()
        assert result["decision"]["decision"] == decision
    unknown = api.post(f"/rules/{version}/preview", json={"tool": "imaginary_tool"}).json()
    assert unknown["decision"]["rule_id"] == "UNKNOWN_TOOL"
    assert events.read()[-1].seq == after_draft
    assert gate.runs[old["run_id"]].tool_calls == 0
    active = api.post(f"/rules/{version}/activate", json=HUMAN)
    assert active.status_code == 200 and active.json()["status"] == "active"
    audit = [e for e in events.read() if e.type == "human.action"][-1]
    assert audit.payload["action"] == "activate_rule"
    assert (audit.payload["actor"], audit.payload["reason"]) == (HUMAN["actor"], HUMAN["reason"])
    last = events.read()[-1].seq
    assert api.post(f"/rules/{version}/activate", json=HUMAN).json() == active.json()
    assert events.read()[-1].seq == last
    gate.reset()
    server.restore()
    assert api.get(f"/rules/{version}").json() == active.json()
    assert gate.policy_for(SPEC["name"])["rule_revision"] == version


def test_old_new_and_approved_queued_restart_pin_separate_policy_copies(api, monkeypatch):
    old, old_auth = start(api, "Old running task")
    source, _ = start(api, "Queued task")
    assert api.post(f"/runs/{source['run_id']}/kill", json=HUMAN).status_code == 200
    queued = api.post(f"/runs/{source['run_id']}/restart", json=HUMAN).json()
    assert queued["status"] == "queued" and queued["rule_revision"] is None
    version = api.post("/rules", json=DRAFT).json()["version"]
    assert api.post(f"/rules/{version}/activate", json=HUMAN).status_code == 200
    assert check(api, old, old_auth, OTHER)["decision"] == "allow"
    claimed, claim_auth = start(api, "Queued task", restarted_from=source["run_id"])
    assert claimed["run_id"] == queued["id"] and claimed["rule_revision"] is None
    assert check(api, claimed, claim_auth, OTHER)["decision"] == "allow"
    fresh, fresh_auth = start(api, "New task")
    assert fresh["rule_revision"] == version
    assert api.get(f"/runs/{fresh['run_id']}").json()["rule_revision"] == version
    assert check(api, fresh, fresh_auth, USER)["decision"] == "allow"
    assert check(api, fresh, fresh_auth, OTHER)["rule_id"] == "DEST_NOT_ALLOWED"
    incident = gate.runs[fresh["run_id"]].incident_id
    frozen = snapshot.load(incident)
    assert frozen["policy"]["rule_revision"] == version
    assert frozen["policy"] == gate.runs[fresh["run_id"]].policy
    # Activate another valid restriction; freeze-time authority still refuses the old violation.
    second = copy.deepcopy(DRAFT)
    second["allow"]["email_to"] = [USER, OTHER]
    next_version = api.post("/rules", json=second).json()["version"]
    assert api.post(f"/rules/{next_version}/activate", json=HUMAN).status_code == 200
    assert api.get(f"/rules/{version}").json()["status"] == "superseded"
    assert snapshot.load(incident) == frozen

    def attempted_effect(_snap, *, current_spec=None):
        return [{"step": 1, "tool": "send_email", "args": {"to": OTHER}}], None

    monkeypatch.setattr(sandbox, "run_once", attempted_effect)
    monkeypatch.setattr(sandbox.time, "sleep", lambda _: None)
    _, _, result = sandbox.detonate(incident, 1, verify=True)
    assert not result.passed and result.attack_blocked == "0/1"
    assert result.policy_revisions == sorted([version, next_version])
    proof = [e for e in events.read() if e.type == "fix.verified"][-1]
    assert proof.payload["policy_revisions"] == result.policy_revisions
    assert result.effects[0].violates == ["P1", "P5"]


@pytest.mark.parametrize("payload", [
    {**DRAFT, "rule_revision": "caller-revision"},
    {**DRAFT, "allow": {"tools": ["crm_export"], "email_to": [USER]}},
    {**DRAFT, "allow": {"tools": ["made_up_tool"], "email_to": [USER]}},
    {**DRAFT, "allow": {"tools": ["send_email"], "email_to": ["outside@attacker.example"]}},
    {**DRAFT, "allow": {"tools": ["send_email"], "email_to": ["*@synthetic.example"]}},
    {**DRAFT, "allow": {"tools": ["send_email"], "email_to": [USER],
                       "url_hosts": ["attacker.example"]}},
])
def test_http_rejects_broadening_and_caller_authority_without_events(api, payload):
    before = events.read()[-1].seq
    assert api.post("/rules", json=payload).status_code == 422
    assert api.get("/rules").json() == []
    assert events.read()[-1].seq == before
    assert api.post("/runs", json={"agent": SPEC["name"], "task": "brief",
                                    "rule_revision": "caller-revision"}).status_code == 422


def test_activation_has_human_authority_and_revalidates_registration(api, monkeypatch):
    version = api.post("/rules", json=DRAFT).json()["version"]
    endpoint = f"/rules/{version}/activate"
    for body in ({}, {"actor": "", "reason": "why"}, {"actor": "human", "reason": " "}):
        assert api.post(endpoint, json=body).status_code == 422
    monkeypatch.setattr(server, "PUBLIC", True)
    assert api.post(endpoint, json=HUMAN).status_code == 403
    assert api.post("/rules", json=DRAFT).status_code == 403
    monkeypatch.setattr(server, "PUBLIC", False)
    tighter = copy.deepcopy(SPEC)
    tighter["allow"]["email_to"] = [OTHER]
    assert api.post("/agents", json=tighter).status_code == 200
    assert api.post(endpoint, json=HUMAN).status_code == 422
    assert api.get(f"/rules/{version}").json()["status"] == "draft"
    assert not [e for e in events.read() if e.type == "rule.activated"]


def test_verification_pins_its_start_rule_across_mid_proof_activation(api, monkeypatch):
    first = api.post("/rules", json=DRAFT).json()["version"]
    assert api.post(f"/rules/{first}/activate", json=HUMAN).status_code == 200
    started, auth = start(api)
    assert check(api, started, auth, OTHER)["decision"] == "freeze"
    incident = gate.runs[started["run_id"]].incident_id
    next_draft = copy.deepcopy(DRAFT)
    next_draft["allow"]["email_to"] = [OTHER]
    later = api.post("/rules", json=next_draft).json()["version"]
    observed = []

    def clean_effect(snap, *, current_spec=None):
        observed.append(snap["_verification_policy"]["rule_revision"])
        if len(observed) == 1:
            assert api.post(f"/rules/{later}/activate", json=HUMAN).status_code == 200
        if current_spec is not None:
            current_spec.update(copy.deepcopy(SPEC))
        return [{"step": 1, "tool": "send_email", "args": {
            "to": USER, "subject": "Synthetic brief", "body": "Prepared brief"}}], None

    monkeypatch.setenv("MIRAGE_PARALLEL", "1")
    monkeypatch.setattr(sandbox, "run_once", clean_effect)
    monkeypatch.setattr(sandbox.time, "sleep", lambda _: None)
    _, _, result = sandbox.detonate(incident, 2, verify=True)
    assert result.passed and result.policy_revisions == [first]
    assert observed == [first, first]
    assert gate.policy_for(SPEC["name"])["rule_revision"] == later


@contextmanager
def isolated_engine(tmp_path):
    """A real socket and owned subprocess; never touch the user's running engine."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"AWS_BEARER_TOKEN_BEDROCK", "MIRAGE_PUBLIC"}}
        environment.update(MIRAGE_MODE="live", MIRAGE_LAYER2="0", MIRAGE_JUDGE="0",
                           MIRAGE_DB=str(tmp_path / "http.db"),
                           MIRAGE_SNAPSHOTS=str(tmp_path / "snapshots"))
        with (tmp_path / "server.log").open("w") as log:
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "engine.api.server:app",
                                        "--fd", str(listener.fileno()), "--log-level", "error"],
                                       pass_fds=(listener.fileno(),), env=environment,
                                       cwd=Path(__file__).parents[1], stdout=log, stderr=log)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
                    for _ in range(100):
                        assert process.poll() is None, (tmp_path / "server.log").read_text()
                        try:
                            if client.get("/runtime").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.05)
                    else:
                        pytest.fail("Owned isolated engine did not become ready")
                    yield client
            finally:
                process.terminate()
                process.wait(timeout=10)


def test_real_http_rule_lifecycle_survives_owned_engine_process_restart(tmp_path):
    with isolated_engine(tmp_path) as client:
        assert client.post("/agents", json=SPEC).status_code == 200
        rule = client.post("/rules", json=DRAFT)
        assert rule.status_code == 200, rule.text
        version = rule.json()["version"]
        assert client.get(f"/rules/{version}").json()["status"] == "draft"
        assert client.post(f"/rules/{version}/preview").json()["authoritative"] is True
        assert client.post(f"/rules/{version}/activate", json=HUMAN).status_code == 200
    with isolated_engine(tmp_path) as client:
        assert client.get("/rules").json()[0]["status"] == "active"
        started, auth = start(client)
        assert started["rule_revision"] == version
        assert check(client, started, auth, USER)["decision"] == "allow"
        assert check(client, started, auth, OTHER)["decision"] == "freeze"
