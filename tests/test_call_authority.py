"""Synthetic authority races through the SDK's protected callbacks; no provider calls."""

import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from mirage import core

from engine.api import server
from engine.detonation import snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, USER, check, start


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    with TestClient(server.app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(core, "_http", client)
        monkeypatch.setattr(core, "_sandbox", None)
        assert client.post("/agents", json={**AGENT, "entrypoint": ""}).status_code == 200
        yield client
    gate.reset()



def handle(run_id, auth):
    return {"id": run_id, "token": auth["Authorization"].removeprefix("Bearer ")}



def protected(run, to, effects, callback=None):
    token = core._run.set(run)
    try:
        return core.tool("send_email", {"to": to, "body": "Synthetic brief"},
                         callback or (lambda: effects.append(to) or {"status": "sent"}))
    except (core.Blocked, httpx.HTTPStatusError):
        return "blocked"
    finally:
        core._run.reset(token)



def test_approval_releases_only_the_original_checked_call(api, monkeypatch):
    run_id, auth = start(api)
    safe_wait, unsafe_checked = threading.Event(), threading.Event()
    safe_effects, unsafe_effects = [], []
    original_wait, original_post = core._wait, core._post

    def observed_wait(run, *args, **kwargs):
        safe_wait.set()
        return original_wait(run, *args, **kwargs)

    def observed_post(path, body=None, run=None):
        result = original_post(path, body, run)
        if path == "/gateway/check" and body.args.get("to") == ATTACKER:
            unsafe_checked.set()
        return result

    monkeypatch.setattr(core, "_wait", observed_wait)
    monkeypatch.setattr(core, "_post", observed_post)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        safe = pool.submit(protected, handle(run_id, auth), USER, safe_effects)
        try:
            assert safe_wait.wait(2)
            (approval,) = api.get("/approvals").json()
            unsafe = pool.submit(protected, handle(run_id, auth), ATTACKER, unsafe_effects)
            assert unsafe_checked.wait(2)
            assert safe_effects == unsafe_effects == []
            assert api.post(f"/approvals/{approval['call_id']}/approve",
                            json=HUMAN).status_code == 200
            assert safe.result(3) == {"status": "sent"}
            unsafe.result(3)
        finally:
            if gate.runs[run_id].status in ("running", "frozen"):
                api.post(f"/runs/{run_id}/kill", json=HUMAN)
    assert safe_effects == [USER]
    assert unsafe_effects == []



@pytest.mark.parametrize("mismatch", ["call", "run", "tool", "token"])
def test_result_identity_binds_token_run_original_call_and_tool(api, mismatch):
    run_id, auth = start(api)
    other_id, other_auth = start(api)
    admitted = check(api, run_id, auth, "read_calendar").json()
    target, headers = run_id, auth
    payload = {"call_id": admitted["call_id"], "tool": "read_calendar", "result": []}
    if mismatch == "call":
        payload["call_id"] = "call_missing"
    elif mismatch == "run":
        target, headers = other_id, other_auth
    elif mismatch == "tool":
        payload["tool"] = "search_contacts"
    else:
        headers = other_auth
    response = api.post(f"/runs/{target}/tool-results", headers=headers, json=payload)
    assert response.status_code == (401 if mismatch == "token" else 409)
    assert gate.runs[target].tool_results == []
    assert not any(e.type == "tool.result" for e in events.read())



@pytest.mark.parametrize("kind", ["incident", "approval"])
def test_result_cannot_acknowledge_a_call_still_held_for_a_human(api, monkeypatch, kind):
    run_id, auth = start(api)
    if kind == "approval":
        monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
            "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
    held = check(api, run_id, auth, "send_email", to=USER if kind == "approval" else ATTACKER).json()
    response = api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": held["call_id"], "tool": "send_email", "result": {"status": "sent"}})
    assert response.status_code == 409
    assert gate.runs[run_id].tool_results == []



def test_duplicate_result_is_idempotent_and_conflicting_replay_is_rejected(api):
    run_id, auth = start(api)
    admitted = check(api, run_id, auth, "read_calendar").json()
    payload = {"call_id": admitted["call_id"], "tool": "read_calendar", "result": []}
    path = f"/runs/{run_id}/tool-results"
    assert api.post(path, headers=auth, json=payload).status_code == 204
    assert api.post(path, headers=auth, json=payload).status_code == 204
    assert api.post(path, headers=auth, json={**payload, "result": ["changed"]}
                    ).status_code == 409
    assert len(gate.runs[run_id].tool_results) == 1
    assert len([e for e in events.read() if e.type == "tool.result"]) == 1



def test_original_admitted_result_can_arrive_after_manual_freeze(api):
    run_id, auth = start(api)
    admitted = check(api, run_id, auth, "read_calendar").json()
    assert api.post(f"/runs/{run_id}/freeze", json=HUMAN).status_code == 200
    response = api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": admitted["call_id"], "tool": "read_calendar", "result": []})
    assert response.status_code == 204
    assert gate.runs[run_id].status == "frozen"
    assert len(gate.runs[run_id].tool_results) == 1



def test_approved_call_does_not_reappear_after_later_manual_freeze(api, monkeypatch):
    run_id, auth = start(api)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"}
        if args[2] == "send_email" else None)
    held = check(api, run_id, auth, "send_email", to=USER).json()
    path = f"/approvals/{held['call_id']}/approve"
    assert api.post(path, json=HUMAN).status_code == 200
    assert api.post(f"/runs/{run_id}/freeze", json=HUMAN).status_code == 200
    assert api.get("/approvals").json() == []
    assert api.post(path, json=HUMAN).status_code in (404, 409)
    assert gate.runs[run_id].status == "frozen"



def test_reject_revokes_only_the_original_run_and_old_approval_stays_rejected(api, monkeypatch):
    run_id, auth = start(api)
    healthy_id, healthy_auth = start(api)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"}
        if args[2] == "send_email" else None)
    held = check(api, run_id, auth, "send_email", to=USER).json()
    assert api.post(f"/approvals/{held['call_id']}/reject", json=HUMAN).status_code == 200
    assert api.post(f"/approvals/{held['call_id']}/approve", json=HUMAN).status_code in (404, 409)
    assert gate.runs[healthy_id].status == "running"
    assert check(api, run_id, auth, "read_calendar").json()["decision"] == "block"
    assert check(api, healthy_id, healthy_auth, "read_calendar").json()["decision"] == "allow"


def test_already_frozen_checks_block_without_policy_evaluation(api, monkeypatch):
    run_id, auth = start(api)
    assert check(api, run_id, auth, "send_email", to=ATTACKER).json()["decision"] == "freeze"
    original_incident = gate.runs[run_id].incident_id

    def unexpected_evaluation(*args):
        pytest.fail("An already-frozen call must not evaluate policy or gain release authority")

    monkeypatch.setattr(gate, "hard_rule", unexpected_evaluation)
    monkeypatch.setattr(gate.decision_model, "judge", unexpected_evaluation)
    extra = check(api, run_id, auth, "send_email", to=USER).json()
    assert extra["decision"] == "block" and extra["rule_id"] == "RUN_FROZEN"
    assert gate.runs[run_id].incident_id == original_incident
    assert len([e for e in events.read() if e.type == "incident.opened"]) == 1


@pytest.mark.parametrize("release_action", ["approve", "unfreeze"])
def test_delayed_original_sdk_wait_cannot_revive_after_later_control_epoch(
        api, monkeypatch, release_action):
    run_id, auth = start(api)
    entered, release = threading.Event(), threading.Event()
    effects = []
    original_wait = core._wait

    def delayed_wait(run, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_wait(run, *args, **kwargs)

    monkeypatch.setattr(core, "_wait", delayed_wait)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
    with ThreadPoolExecutor(max_workers=1) as pool:
        callback = pool.submit(protected, handle(run_id, auth), USER, effects)
        try:
            assert entered.wait(2)
            (approval,) = api.get("/approvals").json()
            path = (f"/approvals/{approval['call_id']}/approve" if release_action == "approve"
                    else f"/runs/{run_id}/unfreeze")
            assert api.post(path, json=HUMAN).status_code == 200
            assert api.post(f"/runs/{run_id}/freeze", json=HUMAN).status_code == 200
            assert api.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 200
        finally:
            if gate.runs[run_id].status == "frozen":
                api.post(f"/runs/{run_id}/kill", json=HUMAN)
            release.set()
        assert callback.result(3) == "blocked"
    assert effects == []
    assert gate.runs[run_id].status == "running"
    assert gate.runs[run_id].tool_results == []


@pytest.mark.parametrize("control", ["freeze", "kill", "stop"])
def test_admitted_sdk_callback_can_acknowledge_after_containment(api, control):
    run_id, auth = start(api)
    entered, release = threading.Event(), threading.Event()
    effects = []

    def in_flight():
        entered.set()
        assert release.wait(5)
        effects.append(USER)
        return {"status": "sent"}

    with ThreadPoolExecutor(max_workers=1) as pool:
        callback = pool.submit(protected, handle(run_id, auth), USER, effects, in_flight)
        try:
            assert entered.wait(2)
            path = "/stop" if control == "stop" else f"/runs/{run_id}/{control}"
            assert api.post(path, json=HUMAN).status_code == 200
            assert check(api, run_id, auth, "send_email", to=USER).json()["decision"] == "block"
        finally:
            release.set()
        assert callback.result(3) == {"status": "sent"}
    assert effects == [USER]
    assert gate.runs[run_id].status == {"freeze": "frozen", "kill": "killed", "stop": "halted"}[
        control]
    assert len(gate.runs[run_id].tool_results) == 1
    assert len([e for e in events.read() if e.type == "tool.result"]) == 1


def test_rejected_result_never_enters_a_later_snapshot(api):
    run_id, auth = start(api)
    response = api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": "call_missing", "tool": "read_calendar",
        "result": [{"title": "Forged input", "description": "Synthetic forged instruction"}]})
    assert check(api, run_id, auth, "send_email", to=ATTACKER).json()["decision"] == "freeze"
    saved = snapshot.load(gate.runs[run_id].incident_id)
    assert saved["tool_results"] == []
    assert [i["id"] for i in saved["inputs"]] == ["in_task"]
    assert response.status_code == 409


def test_concurrent_identical_result_retries_record_once(api):
    run_id, auth = start(api)
    admitted = check(api, run_id, auth, "read_calendar").json()
    payload = {"call_id": admitted["call_id"], "tool": "read_calendar", "result": []}
    barrier = threading.Barrier(6)

    def acknowledge():
        barrier.wait(3)
        return api.post(f"/runs/{run_id}/tool-results", headers=auth, json=payload).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: acknowledge(), range(6)))
    assert responses == [204] * 6
    assert len(gate.runs[run_id].tool_results) == 1
    assert len([e for e in events.read() if e.type == "tool.result"]) == 1


def test_failed_result_audit_does_not_consume_or_pollute_the_snapshot(api, monkeypatch):
    run_id, auth = start(api)
    admitted = check(api, run_id, auth, "read_calendar").json()
    payload = {"call_id": admitted["call_id"], "tool": "read_calendar", "result": []}
    original_emit = gate.emit

    def fail_result(kind, *args, **kwargs):
        if kind == "tool.result":
            raise OSError("Synthetic result persistence failure")
        return original_emit(kind, *args, **kwargs)

    monkeypatch.setattr(gate, "emit", fail_result)
    path = f"/runs/{run_id}/tool-results"
    assert api.post(path, headers=auth, json=payload).status_code == 500
    assert gate.runs[run_id].tool_results == []
    monkeypatch.setattr(gate, "emit", original_emit)
    assert api.post(path, headers=auth, json=payload).status_code == 204
    assert len(gate.runs[run_id].tool_results) == 1
    assert len([e for e in events.read() if e.type == "tool.result"]) == 1


def test_call_with_a_failed_decision_audit_has_no_result_authority(api, monkeypatch):
    run_id, auth = start(api)
    original_emit = gate.emit

    def fail_decision(kind, *args, **kwargs):
        if kind == "gate.decision":
            raise OSError("Synthetic decision persistence failure")
        return original_emit(kind, *args, **kwargs)

    monkeypatch.setattr(gate, "emit", fail_decision)
    assert check(api, run_id, auth, "read_calendar").status_code == 500
    requested = next(e for e in events.read() if e.type == "tool.requested")
    monkeypatch.setattr(gate, "emit", original_emit)
    response = api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": requested.payload["call_id"], "tool": "read_calendar", "result": []})
    assert response.status_code == 409
    assert gate.runs[run_id].tool_results == []


@pytest.mark.parametrize("tool_name", ["upload_contacts", "read_calendarchannelcommentary"])
def test_runtime_added_langgraph_callback_requires_registered_tool_admission(api, tool_name):
    import mirage
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    from agents.common.testing import call, scripted

    effects = []

    @tool
    def read_calendar() -> list:
        """Read synthetic calendar entries."""
        return []

    @tool(tool_name)
    def runtime_added(to: str) -> dict:
        """Capture a synthetic outbound effect."""
        effects.append(to)
        return {"status": "sent"}

    graph = mirage.protect(create_agent(scripted(call(tool_name, to=ATTACKER), AIMessage("done")),
                                       tools=[read_calendar]), name=AGENT["name"],
                           allow={"tools": ["read_calendar"], "email_to": [USER]}, entrypoint="")
    # Runtime tool catalogue drift: the real ToolNode now has a callback absent at registration.
    graph.nodes["tools"].bound.tools_by_name[tool_name] = runtime_added
    try:
        graph.invoke({"messages": [("user", "Read my calendar")]})
    except core.Blocked:
        pass
    assert effects == []
    decision = next(e.payload for e in events.read() if e.type == "gate.decision")
    assert (decision["decision"], decision["rule_id"]) == ("block", "UNKNOWN_TOOL")
    assert not any(e.type == "incident.opened" for e in events.read())
    assert not any(e.type == "tool.result" for e in events.read())


@pytest.mark.parametrize("other_run", [False, True])
def test_bound_wait_rejects_a_call_not_checked_for_its_run(api, other_run):
    run_id, auth = start(api)
    call_id = "call_missing"
    if other_run:
        other_id, other_auth = start(api)
        call_id = check(api, other_id, other_auth, "read_calendar").json()["call_id"]
    response = api.get(f"/runs/{run_id}/wait", headers=auth,
                       params={"timeout": 0, "call_id": call_id})
    assert response.status_code == 409
    assert gate.runs[run_id].tool_results == []


def test_legacy_unbound_wait_cannot_claim_a_held_release(api, monkeypatch):
    run_id, auth = start(api)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
    held = check(api, run_id, auth, "send_email", to=USER).json()
    params = {"timeout": 0, "call_id": held["call_id"]}
    path = f"/runs/{run_id}/wait"
    assert api.get(path, headers=auth, params=params).json() == {"status": "frozen"}
    assert api.post(f"/approvals/{held['call_id']}/approve", json=HUMAN).status_code == 200
    assert api.get(path, headers=auth, params={"timeout": 0}).status_code == 409
    assert api.get(path, headers=auth, params=params).json() == {"status": "running"}
    assert api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": held["call_id"], "tool": "send_email", "result": {"status": "sent"}}
                    ).status_code == 204
    assert api.get(path, headers=auth, params=params).status_code == 409


def test_unbound_wait_cannot_revive_a_revoked_hold_after_manual_unfreeze(api, monkeypatch):
    run_id, auth = start(api)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
    held = check(api, run_id, auth, "send_email", to=USER).json()
    assert api.post(f"/approvals/{held['call_id']}/approve", json=HUMAN).status_code == 200
    assert api.post(f"/runs/{run_id}/freeze", json=HUMAN).status_code == 200
    assert api.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 200
    path = f"/runs/{run_id}/wait"
    assert api.get(path, headers=auth, params={"timeout": 0}).status_code == 409
    assert api.get(path, headers=auth,
                   params={"timeout": 0, "call_id": held["call_id"]}).status_code == 409
