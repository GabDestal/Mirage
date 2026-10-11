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
from tests.test_api import AGENT, HUMAN, USER, check, start


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



@pytest.mark.parametrize("action", ["freeze", "kill"])
def test_human_containment_survives_failed_audit_write(api, monkeypatch, action):
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
    status = run.status
    resumed = run.resume.is_set()
    effects = []
    if run.status == "running":
        protected(handle(run_id, auth), USER, effects)
    elif action == "freeze":
        assert check(api, run_id, auth, "send_email", to=USER).json()["decision"] == "freeze"
        assert api.post(f"/runs/{run_id}/kill", json=HUMAN).status_code == 200
    else:
        assert protected(handle(run_id, auth), USER, effects) == "blocked"
    assert effects == []
    assert status == ("frozen" if action == "freeze" else "killed")
    assert resumed == (action == "kill")


@pytest.mark.parametrize("action", ["unfreeze", "approve"])
@pytest.mark.parametrize("failed_event", ["human.action", "run.status"])
def test_release_requires_durable_human_audit(api, monkeypatch, action, failed_event):
    run_id, auth = start(api)
    if action == "approve":
        monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
            "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
        held = check(api, run_id, auth, "send_email", to=USER).json()
        path = f"/approvals/{held['call_id']}/approve"
    else:
        assert api.post(f"/runs/{run_id}/freeze", json=HUMAN).status_code == 200
        path = f"/runs/{run_id}/unfreeze"
    original = gate.emit

    def fail(kind, *args, **kwargs):
        if kind == failed_event:
            raise OSError("synthetic recovery audit failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert api.post(path, json=HUMAN).status_code == 500
    assert gate.runs[run_id].status == "frozen"
    assert not gate.runs[run_id].resume.is_set()


def test_reject_revokes_even_when_human_audit_fails(api, monkeypatch):
    run_id, auth = start(api)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
    held = check(api, run_id, auth, "send_email", to=USER).json()
    original = gate.emit

    def fail(kind, *args, **kwargs):
        if kind == "human.action":
            raise OSError("synthetic rejection audit failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert api.post(f"/approvals/{held['call_id']}/reject", json=HUMAN).status_code == 500
    assert gate.runs[run_id].status == "killed"
    effects = []
    assert protected(handle(run_id, auth), USER, effects) == "blocked"
    assert effects == []


@pytest.mark.parametrize("action", ["freeze", "kill", "stop"])
def test_sqlite_write_failure_does_not_leave_original_run_authorized(api, monkeypatch, action):
    run_id, auth = start(api)
    connection = events._db()

    class UnwritableStore:
        def execute(self, sql, *args):
            if sql == "BEGIN IMMEDIATE":
                raise OSError("synthetic SQLite write failure")
            return connection.execute(sql, *args)

    with monkeypatch.context() as fault:
        fault.setattr(events, "_db", lambda: UnwritableStore())
        path = "/stop" if action == "stop" else f"/runs/{run_id}/{action}"
        assert api.post(path, json=HUMAN).status_code == 500
    run = gate.runs[run_id]
    status = run.status
    effects = []
    if action == "stop":
        assert api.post("/stop/lift", json=HUMAN).status_code == 204
    if run.status == "frozen":
        assert api.post(f"/runs/{run_id}/kill", json=HUMAN).status_code == 200
    protected(handle(run_id, auth), USER, effects)
    assert effects == []
    assert status == {"freeze": "frozen", "kill": "killed", "stop": "halted"}[action]



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



@pytest.mark.parametrize("failed_event", ["human.action", "global.stop_lifted"])
def test_failed_stop_lift_does_not_grant_unaudited_authority(api, monkeypatch, failed_event):
    start(api)
    assert api.post("/stop", json=HUMAN).status_code == 200
    original = gate.emit

    def fail(kind, *args, **kwargs):
        if kind == failed_event:
            raise OSError("synthetic lift audit failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert api.post("/stop/lift", json=HUMAN).status_code == 500
    assert gate.STOP.is_set()
    assert api.post("/runs", json={"agent": AGENT["name"], "task": "Unaudited task"}
                    ).status_code == 409
