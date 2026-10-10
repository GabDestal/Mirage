"""Engine API: the SDK data plane and the operator control plane, over HTTP."""

import time

import pytest
from fastapi.testclient import TestClient

from contracts.models import Snapshot
from engine.api.server import app
from engine.detonation import snapshot
from engine.gateway import gate
from engine.store import events

USER = "demo-user@mirage-demo.com"
ATTACKER = "attacker@evil-corp-demo.com"
AGENT = {
    "name": "meeting_assistant", "owner": "liam",
    "tools": ["read_calendar", "search_contacts", "export_contacts", "send_email"],
    "allow": {"tools": ["read_calendar", "search_contacts", "export_contacts", "send_email"],
              "email_to": [USER]},
    "entrypoint": "agents.meeting_assistant.agent:build_agent",
}
HUMAN = {"actor": "gabi", "reason": "test"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "events.db")
    events.reset()
    gate.reset()
    client = TestClient(app)
    assert client.post("/agents", json=AGENT).status_code == 200
    yield client
    events.reset()
    gate.reset()


def start(api):
    started = api.post("/runs", json={"agent": AGENT["name"], "task": "Prep my meetings"}).json()
    return started["run_id"], {"Authorization": f"Bearer {started['run_token']}"}


def check(api, run_id, auth, tool, **args):
    return api.post("/gateway/check", headers=auth,
                    json={"run_id": run_id, "tool": tool, "args": args})


def test_allowed_call_and_result_are_recorded(api):
    run_id, auth = start(api)
    decision = check(api, run_id, auth, "send_email", to=USER, subject="Brief", body="hi").json()
    assert decision["decision"] == "allow"
    r = api.post(f"/runs/{run_id}/tool-results", headers=auth,
                 json={"call_id": decision["call_id"], "tool": "send_email", "result": "sent"})
    assert r.status_code == 204
    assert gate.runs[run_id].tool_results[0]["result"] == "sent"
    assert api.post(f"/runs/{run_id}/complete", headers=auth).json()["status"] == "completed"


def test_attack_freezes_only_that_run(api):
    bad_id, bad_auth = start(api)
    ok_id, _ = start(api)
    decision = check(api, bad_id, bad_auth, "send_email", to=ATTACKER, subject="x", body="rows")
    assert decision.json()["decision"] == "freeze"
    assert decision.json()["rule_id"] == "DEST_NOT_ALLOWED"
    assert api.get(f"/runs/{bad_id}/wait?timeout=0.05", headers=bad_auth).json() == {
        "status": "frozen"}
    assert api.get(f"/runs/{ok_id}").json()["status"] == "running"  # others continue

    incident = api.get("/incidents").json()[0]
    assert incident["run_id"] == bad_id and incident["next_action"] == "detonate"

    api.post(f"/runs/{bad_id}/unfreeze", json=HUMAN)
    assert api.get(f"/runs/{bad_id}/wait", headers=bad_auth).json() == {"status": "running"}


def test_kill_and_stop_revoke(api):
    run_id, auth = start(api)
    check(api, run_id, auth, "send_email", to=ATTACKER, subject="x", body="y")
    api.post(f"/runs/{run_id}/kill", json=HUMAN)
    assert api.get(f"/runs/{run_id}/wait", headers=auth).json() == {"status": "killed"}
    assert check(api, run_id, auth, "read_calendar").json()["decision"] == "block"

    other_id, other_auth = start(api)
    api.post("/stop", json=HUMAN)
    assert api.get(f"/runs/{other_id}").json()["status"] == "halted"
    assert check(api, other_id, other_auth, "read_calendar").json()["decision"] == "block"
    assert api.post("/runs", json={"agent": AGENT["name"], "task": "t"}).status_code == 409


def test_auth_and_state_errors(api):
    run_id, _ = start(api)
    assert check(api, run_id, {"Authorization": "Bearer nope"}, "read_calendar").status_code == 401
    assert api.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 409  # not frozen
    assert api.post("/runs", json={"agent": "ghost", "task": "t"}).status_code == 404


def test_events_feed_and_openapi(api):
    run_id, auth = start(api)
    check(api, run_id, auth, "export_contacts")
    types = [e["type"] for e in api.get("/events").json()]
    assert types[:2] == ["run.status", "run.started"]
    assert "gate.decision" in types
    last = api.get("/events").json()[-1]["seq"]
    assert api.get(f"/events?after={last}").json() == []
    assert "/gateway/check" in api.get("/openapi.json").json()["paths"]


def test_detonate_route_runs_the_sandbox(api):
    gate.agents["meeting_assistant"].entrypoint = "tests.sandbox_agents:attacker"
    run_id, auth = start(api)
    api.post(f"/runs/{run_id}/model-calls", headers=auth, json={
        "model_id": "openai.gpt-oss-20b-1:0", "request": {"messages": []},
        "response": {"stopReason": "tool_use"}})
    d = check(api, run_id, auth, "read_calendar", date="2026-10-11").json()
    api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": d["call_id"], "tool": "read_calendar", "result": {"events": []}})
    d = check(api, run_id, auth, "export_contacts").json()
    api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": d["call_id"], "tool": "export_contacts",
        "result": {"count": 1, "csv": "c1,a@contoso.example"}})
    check(api, run_id, auth, "send_email", to=ATTACKER, subject="x", body="rows")  # freeze

    incident_id = api.get("/incidents").json()[0]["id"]
    snap = Snapshot.model_validate(snapshot.load(incident_id))  # the file matches the contract
    assert snap.runner == gate.SDK_RUNNER and snap.entrypoint == "tests.sandbox_agents:attacker"
    assert snap.model_calls[0].model_id == "openai.gpt-oss-20b-1:0"
    assert [r.tool for r in snap.tool_results] == ["read_calendar", "export_contacts"]

    # the test agent is not wrapped by mirage.protect: run the entrypoint itself, as a dev agent would
    path = snapshot.SNAP_DIR / f"{incident_id}.json"
    path.write_text(snap.model_copy(update={"runner": None}).model_dump_json(), encoding="utf-8")
    assert api.post(f"/incidents/{incident_id}/detonate?runs=1").json()["detonation_id"]
    assert api.post(f"/incidents/{incident_id}/detonate").status_code == 409  # already running
    for _ in range(100):
        incident = api.get(f"/incidents/{incident_id}").json()
        if incident["status"] in ("confirmed", "false_positive"):
            break
        time.sleep(0.1)
    assert incident["status"] == "confirmed" and incident["next_action"] == "find_cause"
    assert incident["verdict"]["compromised_runs"] == "1/1"


def _verdict(incident_id, confirmed):
    return {"incident_id": incident_id, "confirmed": confirmed, "compromised_runs": "3/3",
            "policies_violated": [], "blast_radius": {"records": 0, "recipients": [],
                                                      "secrets": [], "summary": ""}}


@pytest.mark.parametrize("step, code", [
    (None, 200),                                    # open
    ("detonating", 409),
    ("false_positive", 200),
    ("confirmed", 409),
])
def test_unfreeze_follows_the_incident(api, step, code):
    run_id, auth = start(api)
    check(api, run_id, auth, "send_email", to=ATTACKER, subject="x", body="y")
    inc_id = gate.runs[run_id].incident_id
    if step == "detonating":
        events.emit("detonation.started", {}, run_id=run_id, incident_id=inc_id, env="mirage")
    elif step:
        events.emit("verdict.ready", _verdict(inc_id, step == "confirmed"),
                    run_id=run_id, incident_id=inc_id, env="mirage")
    r = api.post(f"/runs/{run_id}/unfreeze", json=HUMAN)
    assert r.status_code == code
    if step == "confirmed":
        assert "Kill it and approve a clean restart" in r.json()["detail"]


def test_a_model_typo_tool_does_not_freeze_but_a_disallowed_tool_does(api):
    gate.agents["meeting_assistant"].allow.tools.remove("export_contacts")
    run_id, auth = start(api)
    typo = check(api, run_id, auth, "search_contactschannelcommentary", query="x").json()
    assert (typo["decision"], typo["rule_id"]) == ("allow", "UNKNOWN_TOOL")
    assert api.get(f"/runs/{run_id}").json()["status"] == "running"
    known = check(api, run_id, auth, "export_contacts").json()  # the agent has it, not allowed
    assert (known["decision"], known["rule_id"]) == ("freeze", "TOOL_NOT_ALLOWED")
