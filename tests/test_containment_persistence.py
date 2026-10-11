"""Persistence faults must not restore production authority or produce incomplete proof."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from contracts.models import Snapshot
from engine.api import server
from engine.detonation import jobs, snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, USER, check, start
from tests.test_auto_detonation import idle


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    with TestClient(server.app, raise_server_exceptions=False) as client:
        assert client.post("/agents", json=AGENT).status_code == 200
        yield client
    gate.reset()


def fail_snapshot(*args, **kwargs):
    raise OSError("synthetic disk failure")


def assert_contained(api, run_id, auth):
    run = gate.runs[run_id]
    assert run.status == "frozen" and not run.resume.is_set()
    assert api.get(f"/runs/{run_id}/wait?timeout=0", headers=auth).json() == {
        "status": "frozen"}
    assert check(api, run_id, auth, "send_email", to=USER).json()["rule_id"] == "RUN_FROZEN"


def test_snapshot_oserror_keeps_incident_contained_and_healthy_run_authorized(api, monkeypatch):
    bad_id, bad_auth = start(api)
    healthy_id, healthy_auth = start(api)
    automatic = Mock()
    monkeypatch.setattr(jobs, "automatic", automatic)
    monkeypatch.setattr(snapshot, "save", fail_snapshot)

    response = check(api, bad_id, bad_auth, "send_email", to=ATTACKER)
    assert response.status_code == 200
    assert response.json()["decision"] == "freeze"
    assert_contained(api, bad_id, bad_auth)
    assert check(api, healthy_id, healthy_auth, "send_email", to=USER).json()["decision"] == "allow"
    incident = api.get("/incidents").json()[0]
    assert incident["id"] == gate.runs[bad_id].incident_id
    assert incident["status"] == "open" and incident["verdict"] is None
    failure = next(e for e in events.read() if e.type == "detonation.failed")
    assert failure.incident_id == incident["id"]
    assert "OSError" in failure.payload["error"] and "snapshot" in failure.payload["error"].lower()
    assert "synthetic disk failure" not in failure.payload["error"]  # no raw exception content
    assert not list(snapshot.SNAP_DIR.glob("*.json"))
    automatic.assert_not_called()


def test_concurrent_pending_and_already_frozen_checks_do_not_retry_failed_snapshot(api, monkeypatch):
    run_id, auth = start(api)
    run = gate.runs[run_id]
    entered, release = threading.Event(), threading.Event()
    automatic = Mock()

    def fail_held(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        fail_snapshot()

    save = Mock(side_effect=fail_held)
    monkeypatch.setattr(snapshot, "save", save)
    monkeypatch.setattr(jobs, "automatic", automatic)
    with ThreadPoolExecutor(max_workers=8) as pool:
        first = pool.submit(gate.check, run, "send_email", {"to": ATTACKER})
        try:
            assert entered.wait(2)
            pending = [pool.submit(gate.check, run, "send_email", {"to": USER})
                       for _ in range(7)]
            assert run.status == "frozen" and not run.resume.is_set()
        finally:
            release.set()
        assert first.result(2).decision == "freeze"
        assert all(f.result(2).rule_id == "RUN_FROZEN" for f in pending)
    assert_contained(api, run_id, auth)
    assert save.call_count == 1
    assert len(api.get("/incidents").json()) == 1
    automatic.assert_not_called()


def test_dev_tool_never_runs_after_snapshot_failure_then_human_kill(api, monkeypatch):
    run_id, _ = start(api)
    run = gate.runs[run_id]
    attempted = threading.Event()
    dispatch = Mock()

    def fail(*args, **kwargs):
        attempted.set()
        fail_snapshot()

    monkeypatch.setattr(snapshot, "save", fail)
    monkeypatch.setattr(gate.tools, "dispatch", dispatch)
    with ThreadPoolExecutor(max_workers=1) as pool:
        call = pool.submit(gate.execute, run, "send_email", {"to": ATTACKER})
        try:
            assert attempted.wait(2)
            assert run.status == "frozen" and not run.resume.is_set()
            dispatch.assert_not_called()
        finally:
            gate.kill(run_id, "operator", "Keep the failed incident contained")
        assert call.result(2) == {"error": "Access revoked by Mirage."}
    dispatch.assert_not_called()


@pytest.mark.parametrize("event_type", ["gate.decision", "run.status", "incident.opened"])
def test_freeze_survives_event_persistence_failure(api, monkeypatch, event_type):
    run_id, auth = start(api)
    original = gate.emit
    automatic = Mock()
    monkeypatch.setattr(jobs, "automatic", automatic)

    def fail(kind, *args, **kwargs):
        if kind == event_type:
            raise OSError("synthetic event storage failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert check(api, run_id, auth, "send_email", to=ATTACKER).status_code == 500
    assert_contained(api, run_id, auth)
    automatic.assert_not_called()


def test_approval_hold_precedes_fallible_gate_decision_write(api, monkeypatch):
    run_id, auth = start(api)
    original = gate.emit
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Review recipient"})

    def fail(kind, *args, **kwargs):
        if kind == "gate.decision":
            raise OSError("synthetic event storage failure")
        return original(kind, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(gate, "emit", fail)
        assert check(api, run_id, auth, "send_email", to=USER).status_code == 500
    assert_contained(api, run_id, auth)
    assert gate.runs[run_id].incident_id is None


@pytest.mark.parametrize("action", ["unfreeze", "kill", "stop", "reset"])
def test_human_authority_after_snapshot_failure_is_preserved(api, monkeypatch, action):
    run_id, auth = start(api)
    monkeypatch.setattr(snapshot, "save", fail_snapshot)
    check(api, run_id, auth, "send_email", to=ATTACKER)
    assert_contained(api, run_id, auth)
    if action == "reset":
        old = gate.runs[run_id]
        assert api.post("/demo/reset").status_code == 204
        assert check(api, run_id, auth, "send_email", to=USER).status_code == 404
        assert gate.check(old, "send_email", {"to": USER}).rule_id == "RUN_REVOKED"
    elif action == "stop":
        assert api.post("/stop", json=HUMAN).status_code == 200
        assert check(api, run_id, auth, "send_email", to=USER).json()["decision"] == "block"
    else:
        assert api.post(f"/runs/{run_id}/{action}", json=HUMAN).status_code == 200
        decision = check(api, run_id, auth, "send_email", to=USER).json()["decision"]
        assert decision == ("allow" if action == "unfreeze" else "block")
        if action == "kill":
            restarted = api.post(f"/runs/{run_id}/restart", json=HUMAN)
            assert restarted.status_code == 200
            assert restarted.json()["restarted_from"] == run_id
            new_id, new_auth = start(api)
            assert new_id != run_id and new_auth != auth
            assert check(api, run_id, new_auth, "read_calendar").status_code == 401


def test_repaired_storage_requires_explicit_durable_snapshot_and_manual_retry(api, monkeypatch):
    gate.agents[AGENT["name"]].allow.email_to.append("bob@northwind.example")
    run_id, auth = start(api)
    automatic = Mock()
    monkeypatch.setattr(jobs, "automatic", automatic)
    with monkeypatch.context() as fault:
        fault.setattr(snapshot, "save", fail_snapshot)
        assert check(api, run_id, auth, "send_email", to=ATTACKER).json()["decision"] == "freeze"
    run = gate.runs[run_id]
    incident_id = run.incident_id
    assert_contained(api, run_id, auth)
    automatic.assert_not_called()  # repairing storage does not automatically retry proof

    assert api.post(f"/incidents/{incident_id}/detonate?runs=1", json=HUMAN).status_code == 200
    idle(incident_id)
    assert api.get(f"/incidents/{incident_id}").json()["verdict"] is None
    assert not any(e.type in ("verdict.ready", "fix.verified", "detonation.completed")
                   for e in events.read())
    assert_contained(api, run_id, auth)

    # Explicit operator repair from the retained run context; storage recovery alone is insufficient.
    snapshot.save(run, incident_id, gate.policy_for(run.agent),
                  entrypoint="tests.sandbox_agents:clean")
    assert Snapshot.model_validate(snapshot.load(incident_id)).run_id == run_id
    assert api.post(f"/incidents/{incident_id}/detonate?runs=1", json=HUMAN).status_code == 200
    idle(incident_id)
    incident = api.get(f"/incidents/{incident_id}").json()
    assert incident["status"] == "false_positive"
    assert incident["verdict"]["compromised_runs"] == "0/1"
    assert_contained(api, run_id, auth)  # proof never releases production
    assert api.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 200


@pytest.mark.parametrize("boundary", ["write", "fsync", "replace"])
def test_snapshot_publish_failure_leaves_no_partial_proof_and_retry_succeeds(api, monkeypatch,
                                                                          boundary):
    run_id, _ = start(api)
    run = gate.runs[run_id]
    incident_id = "inc_persist"
    policy = gate.policy_for(run.agent)
    with monkeypatch.context() as fault:
        if boundary == "write":
            original = Path.write_text

            def fail_legacy_write(path, value, **kwargs):
                original(path, '{"partial":', **kwargs)
                fail_snapshot()

            def fail_write(value, stream, **kwargs):
                stream.write('{"partial":')
                fail_snapshot()

            fault.setattr(Path, "write_text", fail_legacy_write)
            fault.setattr(snapshot.json, "dump", fail_write)
        elif boundary == "fsync":
            fault.setattr(snapshot.os, "fsync", fail_snapshot)
        else:
            fault.setattr(snapshot.os, "replace", fail_snapshot)
        with pytest.raises(OSError):
            snapshot.save(run, incident_id, policy)
    assert not (snapshot.SNAP_DIR / f"{incident_id}.json").exists()
    assert not list(snapshot.SNAP_DIR.iterdir())
    saved = snapshot.save(run, incident_id, policy)
    assert snapshot.load(incident_id) == saved
    assert Snapshot.model_validate(saved).run_id == run_id


def test_directory_flush_failure_keeps_complete_snapshot_out_of_automatic_proof(api, monkeypatch):
    run_id, auth = start(api)
    original = snapshot.os.fsync
    flushes = []
    automatic = Mock()
    monkeypatch.setattr(jobs, "automatic", automatic)

    def fail_directory(fd):
        flushes.append(fd)
        if len(flushes) == 2:
            fail_snapshot()
        return original(fd)

    with monkeypatch.context() as fault:
        fault.setattr(snapshot.os, "fsync", fail_directory)
        response = check(api, run_id, auth, "send_email", to=ATTACKER)
    assert response.json()["decision"] == "freeze"
    assert len(flushes) == 2
    assert_contained(api, run_id, auth)
    assert Snapshot.model_validate(snapshot.load(gate.runs[run_id].incident_id)).run_id == run_id
    assert any(e.type == "detonation.failed" for e in events.read())
    automatic.assert_not_called()  # file is complete, but publication was not durably confirmed
