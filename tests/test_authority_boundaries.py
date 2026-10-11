"""Synthetic authority races through the SDK's protected callbacks; no provider calls."""

import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from mirage import core

from engine.api import server
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


@pytest.mark.parametrize("action", ["stop", "kill"])
def test_slow_decision_cannot_admit_effect_after_revocation(api, monkeypatch, action):
    run_id, auth = start(api)
    entered, release = threading.Event(), threading.Event()
    effects = []

    def slow(*args):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(gate.decision_model, "judge", slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(protected, handle(run_id, auth), USER, effects)
        try:
            assert entered.wait(2)
            path = "/stop" if action == "stop" else f"/runs/{run_id}/kill"
            assert api.post(path, json=HUMAN).status_code == 200
        finally:
            release.set()
        assert pending.result(3) == "blocked"
    assert effects == []


def test_stop_cannot_undo_started_effect_but_blocks_the_next_one(api):
    run_id, auth = start(api)
    entered, release = threading.Event(), threading.Event()
    effects = []

    def admitted():
        effects.append(USER)
        entered.set()
        assert release.wait(5)
        return {"status": "sent"}

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(protected, handle(run_id, auth), USER, effects, admitted)
        try:
            assert entered.wait(2)
            assert api.post("/stop", json=HUMAN).status_code == 200
        finally:
            release.set()
        assert pending.result(3) == {"status": "sent"}
    # This acknowledgment belongs to a call admitted before STOP; it grants no new effect.
    assert len(gate.runs[run_id].tool_results) == 1
    assert protected(handle(run_id, auth), USER, effects) == "blocked"
    assert effects == [USER]


def test_manual_freeze_during_slow_decision_holds_effect_until_human_kill(api, monkeypatch):
    run_id, auth = start(api)
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
    original_wait = core._wait
    effects = []

    def slow(*args):
        entered.set()
        assert release.wait(5)

    def observed_wait(run):
        waiting.set()
        return original_wait(run)

    monkeypatch.setattr(gate.decision_model, "judge", slow)
    monkeypatch.setattr(core, "_wait", observed_wait)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(protected, handle(run_id, auth), USER, effects)
        try:
            assert entered.wait(2)
            assert api.post(f"/runs/{run_id}/freeze", json=HUMAN).status_code == 200
            release.set()
            assert waiting.wait(2)
            assert effects == []
        finally:
            release.set()
            api.post(f"/runs/{run_id}/kill", json=HUMAN)
        assert pending.result(3) == "blocked"
    assert effects == []


def test_approval_releases_only_the_original_checked_call(api, monkeypatch):
    run_id, auth = start(api)
    safe_wait, unsafe_checked = threading.Event(), threading.Event()
    safe_effects, unsafe_effects = [], []
    original_wait, original_post = core._wait, core._post

    def observed_wait(run):
        safe_wait.set()
        return original_wait(run)

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


@pytest.mark.parametrize("action,status", [("freeze", "frozen"), ("kill", "killed")])
def test_human_containment_survives_failed_audit_write(api, monkeypatch, action, status):
    run_id, auth = start(api)
    original = gate.emit

    def fail(kind, *args, **kwargs):
        if kind == "human.action":
            raise OSError("synthetic audit storage failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert api.post(f"/runs/{run_id}/{action}", json=HUMAN).status_code == 500
    run = gate.runs[run_id]
    effects = []
    if run.status == "running":
        protected(handle(run_id, auth), USER, effects)
    elif action == "freeze":
        assert check(api, run_id, auth, "send_email", to=USER).json()["decision"] == "freeze"
        assert api.post(f"/runs/{run_id}/kill", json=HUMAN).status_code == 200
    else:
        assert protected(handle(run_id, auth), USER, effects) == "blocked"
    assert effects == []
    if action == "kill":
        assert run.status == status


@pytest.mark.parametrize("failed_event", ["human.action", "global.stop", "run.status"])
def test_stop_revokes_every_run_even_when_diagnostics_fail(api, monkeypatch, failed_event):
    first_id, first_auth = start(api)
    second_id, second_auth = start(api)
    original = gate.emit

    def fail(kind, *args, **kwargs):
        if kind == failed_event:
            raise OSError("synthetic STOP storage failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert api.post("/stop", json=HUMAN).status_code == 500
    assert gate.STOP.is_set()
    assert api.post("/stop/lift", json=HUMAN).status_code == 204
    effects = []
    for run_id, auth in ((first_id, first_auth), (second_id, second_auth)):
        protected(handle(run_id, auth), USER, effects)
    assert effects == []
    assert [gate.runs[r].status for r in (first_id, second_id)] == ["halted", "halted"]


def test_failed_stop_lift_does_not_grant_unaudited_authority(api, monkeypatch):
    start(api)
    assert api.post("/stop", json=HUMAN).status_code == 200
    original = gate.emit

    def fail(kind, *args, **kwargs):
        if kind == "human.action":
            raise OSError("synthetic lift audit failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert api.post("/stop/lift", json=HUMAN).status_code == 500
    assert gate.STOP.is_set()
    assert api.post("/runs", json={"agent": AGENT["name"], "task": "Unaudited task"}
                    ).status_code == 409


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
    assert response.status_code in (401, 409, 422)
    assert gate.runs[target].tool_results == []
    assert not any(e.type == "tool.result" for e in events.read())


def test_result_cannot_acknowledge_a_call_still_held_for_a_human(api):
    run_id, auth = start(api)
    held = check(api, run_id, auth, "send_email", to=ATTACKER).json()
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
    assert api.post(path, headers=auth, json=payload).status_code in (204, 409)
    assert api.post(path, headers=auth, json={**payload, "result": ["changed"]}
                    ).status_code == 409
    assert len(gate.runs[run_id].tool_results) == 1
    assert len([e for e in events.read() if e.type == "tool.result"]) == 1


def test_duplicate_completion_emits_one_terminal_transition(api):
    run_id, auth = start(api)
    for _ in range(2):
        assert api.post(f"/runs/{run_id}/complete", headers=auth).json()["status"] == "completed"
    assert len([e for e in events.read() if e.type == "run.status"
                and e.payload["to"] == "completed"]) == 1


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


def test_queued_restart_cannot_be_claimed_by_a_different_task(api):
    run_id, _ = start(api)
    assert api.post(f"/runs/{run_id}/kill", json=HUMAN).status_code == 200
    queued = api.post(f"/runs/{run_id}/restart", json=HUMAN).json()
    started = api.post("/runs", json={"agent": AGENT["name"], "task": "Different task"})
    assert started.status_code == 409 or started.json()["run_id"] != queued["id"]
    assert gate.runs[queued["id"]].status == "queued"


def test_sdk_cannot_forge_restart_lineage_without_a_human_queued_restart(api):
    run_id, _ = start(api)
    response = api.post("/runs", json={"agent": AGENT["name"], "task": "Prep my meetings",
                                       "restarted_from": run_id})
    assert response.status_code == 409


def test_two_starters_cannot_claim_the_same_approved_restart(api, monkeypatch):
    run_id, _ = start(api)
    assert api.post(f"/runs/{run_id}/kill", json=HUMAN).status_code == 200
    queued = api.post(f"/runs/{run_id}/restart", json=HUMAN).json()
    first_paused, second_at_boundary, release = (
        threading.Event(), threading.Event(), threading.Event())
    first_thread = []
    original_status, original_lock = gate.set_status, server.jobs.lock

    class ObservedLock:
        def __enter__(self):
            if first_paused.is_set() and threading.get_ident() != first_thread[0]:
                second_at_boundary.set()
            return original_lock.__enter__()

        def __exit__(self, *args):
            return original_lock.__exit__(*args)

    def paused_status(run, to, actor, reason):
        if run.id == queued["id"] and to == "running":
            if not first_paused.is_set():
                first_thread.append(threading.get_ident())
                first_paused.set()
            else:
                second_at_boundary.set()
            assert release.wait(5)
        return original_status(run, to, actor, reason)

    monkeypatch.setattr(server.jobs, "lock", ObservedLock())
    monkeypatch.setattr(gate, "set_status", paused_status)
    body = {"agent": AGENT["name"], "task": "Prep my meetings", "restarted_from": run_id}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(api.post, "/runs", json=body)
        try:
            assert first_paused.wait(2)
            second = pool.submit(api.post, "/runs", json=body)
            assert second_at_boundary.wait(2)
        finally:
            release.set()
        responses = [first.result(3), second.result(3)]
    claims = [r for r in responses if r.status_code == 200
              and r.json()["run_id"] == queued["id"]]
    assert len(claims) == 1
    assert any(r.status_code == 409 for r in responses)


@pytest.mark.parametrize("action", ["restart", "resume"])
def test_duplicate_human_recovery_does_not_queue_two_successors(api, action):
    run_id, _ = start(api)
    if action == "restart":
        assert api.post(f"/runs/{run_id}/kill", json=HUMAN).status_code == 200
    else:
        assert api.post("/stop", json=HUMAN).status_code == 200
    path = f"/runs/{run_id}/{action}"
    first = api.post(path, json=HUMAN)
    second = api.post(path, json=HUMAN)
    assert first.status_code == 200
    assert second.status_code == 409 or second.json()["id"] == first.json()["id"]
    assert len([r for r in gate.runs.values() if r.restarted_from == run_id]) == 1


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
