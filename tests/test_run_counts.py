"""Proof needs 1..10 complete replays, rejected before any state or execution side effect."""

import math
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from engine import bisect as engine_bisect
from engine import cli
from engine.api import server
from engine.api.replay import Replay
from engine.detonation import jobs, sandbox, snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, check, start
from tests.test_bisect import save_incident
from tests.test_verify import switch_code

INVALID_COUNTS = [0, -1, 11, 1000000, True, False, 1.5, 3.0, "3", None]
HTTP_INVALID_COUNTS = ["0", "-1", "11", "1000000", "1.5", "true", "oops"]
CLI_PATHS = [("detonate", []), ("detonate", ["--from-freeze"]), ("bisect", [])]


def idle(incident_id):
    deadline = time.monotonic() + 15
    while jobs.running(incident_id) and time.monotonic() < deadline:
        time.sleep(.01)
    assert not jobs.running(incident_id), "sandbox job did not finish"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(server, "PUBLIC", False)
    gate.reset()
    client = TestClient(server.app)
    assert client.post("/agents", json=AGENT).status_code == 200
    run_id, auth = start(client)
    assert check(client, run_id, auth, "send_email", to=ATTACKER).json()["decision"] == "freeze"
    yield client, gate.runs[run_id].incident_id
    jobs.shutdown()
    gate.reset()


@pytest.mark.parametrize("runs", INVALID_COUNTS)
@pytest.mark.parametrize("operation", ["detonate", "verify", "bisect"])
def test_direct_invalid_counts_fail_before_snapshot_or_events(monkeypatch, runs, operation):
    load = Mock(side_effect=AssertionError("invalid count must not load a snapshot"))
    monkeypatch.setattr(snapshot, "load", load)
    before = events.read()
    with pytest.raises(ValueError, match="1.*10"):
        if operation == "bisect":
            engine_bisect.bisect("inc_missing", runs_per_input=runs)
        else:
            sandbox.detonate("inc_missing", n_runs=runs, verify=operation == "verify")
    load.assert_not_called()
    assert events.read() == before


@pytest.mark.parametrize("runs", HTTP_INVALID_COUNTS)
@pytest.mark.parametrize("operation", ["detonate", "verify", "bisect"])
def test_http_invalid_counts_fail_before_lookup_or_reservation(api, monkeypatch, runs, operation):
    client, incident_id = api
    before = events.read()
    status = client.get(f"/incidents/{incident_id}").json()
    lookup = Mock(side_effect=AssertionError("invalid count must not look up an incident"))
    submit = Mock(side_effect=AssertionError("invalid count must not reserve a job"))
    with monkeypatch.context() as patch:
        patch.setattr(server, "get_incident", lookup)
        patch.setattr(jobs, "submit", submit)
        response = client.post(f"/incidents/{incident_id}/{operation}?runs={runs}")
    assert response.status_code == 422
    lookup.assert_not_called()
    submit.assert_not_called()
    assert events.read() == before
    assert client.get(f"/incidents/{incident_id}").json() == status


def test_zero_verify_never_emits_empty_proof_or_advances_incident(api, monkeypatch):
    client, incident_id = api
    before = events.read()
    child = Mock(side_effect=AssertionError("zero runs must not execute a child"))
    monkeypatch.setattr(sandbox, "run_once", child)
    response = client.post(f"/incidents/{incident_id}/verify?runs=0")
    idle(incident_id)
    assert not any(e.type == "fix.verified" for e in events.read(len(before)))
    assert response.status_code == 422
    child.assert_not_called()
    assert events.read() == before
    assert client.get(f"/incidents/{incident_id}").json()["status"] == "open"


@pytest.mark.parametrize("runs", ["0", "-1", "11", "1000000", "1.5", "true"])
@pytest.mark.parametrize("command,extra", CLI_PATHS)
def test_cli_invalid_counts_are_argument_errors_before_execution(monkeypatch, capsys,
                                                                runs, command, extra):
    execute = Mock(side_effect=AssertionError("invalid count must not execute"))
    monkeypatch.setattr(cli, "detonate", execute)
    monkeypatch.setattr(cli, "bisect", execute)
    before = events.read()
    with pytest.raises(SystemExit) as error:
        cli.main([command, "--incident", "inc_missing", "--runs", runs, *extra])
    assert error.value.code == 2
    assert "--runs" in capsys.readouterr().err
    execute.assert_not_called()
    assert events.read() == before


@pytest.mark.parametrize("command,extra", CLI_PATHS)
@pytest.mark.parametrize("runs", [None, 1, 10])
def test_cli_preserves_defaults_and_positive_counts(monkeypatch, command, extra, runs):
    if command == "bisect":
        execute = Mock(return_value=([], "in_01"))
        monkeypatch.setattr(cli, "bisect", execute)
    else:
        result = SimpleNamespace(passed=True, attack_blocked="1/1", legit_task_completed="1/1")
        verdict = SimpleNamespace(confirmed=False, compromised_runs="0/1", policies_violated=[],
                                  blast_radius=SimpleNamespace(summary="clean"))
        execute = Mock(return_value=(None, verdict, result))
        monkeypatch.setattr(cli, "detonate", execute)
    argv = [command, "--incident", "inc_001", *extra]
    if runs is not None:
        argv += ["--runs", str(runs)]
    assert cli.main(argv) == 0
    assert execute.call_args.args[1] == (runs if runs is not None else 2 if command == "bisect" else 3)
    if command == "detonate":
        assert execute.call_args.kwargs["verify"] == (not extra)


@pytest.mark.parametrize("operation", ["detonate", "verify", "bisect"])
@pytest.mark.parametrize("runs", HTTP_INVALID_COUNTS)
def test_managed_replay_invalid_counts_do_not_advance(monkeypatch, operation, runs):
    recording = Replay(server.FIXTURES / "fleet_demo_4agents.jsonl", speed=math.inf, managed=True)
    monkeypatch.setattr(server, "REPLAY", recording)
    client = TestClient(server.app)
    before = client.get("/events").json()
    assert client.post(f"/incidents/inc_001/{operation}?runs={runs}").status_code == 422
    assert client.get("/events").json() == before


def test_managed_replay_still_requires_recorded_positive_counts(monkeypatch):
    recording = Replay(server.FIXTURES / "fleet_demo_4agents.jsonl", speed=math.inf, managed=True)
    monkeypatch.setattr(server, "REPLAY", recording)
    client = TestClient(server.app)
    before = client.get("/events").json()
    assert client.post("/incidents/inc_001/bisect?runs=1").status_code == 409
    assert client.get("/events").json() == before
    assert client.post("/incidents/inc_001/bisect?runs=2").status_code == 200
    assert client.post("/incidents/inc_001/handoff").status_code == 200
    before = client.get("/events").json()
    assert client.post("/incidents/inc_001/verify?runs=2").status_code == 409
    assert client.get("/events").json() == before
    assert client.post("/incidents/inc_001/verify?runs=3").status_code == 200


@pytest.mark.parametrize("operation", ["detonate", "verify"])
@pytest.mark.parametrize("runs", [None, 1, 10])
def test_real_queued_replays_complete_every_requested_run(api, monkeypatch, operation, runs):
    client, incident_id = api
    save_incident(incident_id)
    # Existing fixed scripted agent, real jailed children, no model provider.
    switch_code(incident_id, "tests.sandbox_agents:ignores_invite")
    monkeypatch.setenv("MIRAGE_PARALLEL", "10")
    count = 3 if runs is None else runs
    query = "" if runs is None else f"?runs={runs}"
    assert client.post(f"/incidents/{incident_id}/{operation}{query}").status_code == 200
    idle(incident_id)
    ledger = [e for e in events.read() if e.incident_id == incident_id]
    completed = next(e.payload for e in ledger if e.type == "detonation.completed")
    assert completed["n_runs"] == count
    assert {e["run_index"] for e in completed["effects"]} == set(range(1, count + 1))
    if operation == "verify":
        proof = next(e.payload for e in ledger if e.type == "fix.verified")
        assert proof["passed"] is True
        assert proof["attack_blocked"] == proof["legit_task_completed"] == f"{count}/{count}"
        assert client.get(f"/incidents/{incident_id}").json()["status"] == "fix_verified"
    else:
        proof = next(e.payload for e in ledger if e.type == "verdict.ready")
        assert proof["compromised_runs"] == f"0/{count}"


@pytest.mark.parametrize("runs", [None, 1, 10])
def test_real_queued_bisection_completes_every_requested_run(api, monkeypatch, runs):
    client, incident_id = api
    save_incident(incident_id)
    events.emit("verdict.ready", {"incident_id": incident_id, "confirmed": True,
                "compromised_runs": "3/3", "policies_violated": ["P1"],
                "blast_radius": {"records": 2, "recipients": [ATTACKER], "secrets": [],
                                 "summary": "synthetic baseline"}},
                incident_id=incident_id, env="mirage")
    monkeypatch.setenv("MIRAGE_PARALLEL", "10")
    count = 2 if runs is None else runs
    query = "" if runs is None else f"?runs={runs}"
    before = len(events.read())
    assert client.post(f"/incidents/{incident_id}/bisect{query}").status_code == 200
    idle(incident_id)
    ledger = events.read(before)
    completed = [e.payload for e in ledger if e.type == "detonation.completed"]
    assert len(completed) == 2
    assert all(d["n_runs"] == count for d in completed)
    assert all({e["run_index"] for e in d["effects"]} == set(range(1, count + 1)) for d in completed)
    rows = [e.payload for e in ledger if e.type == "bisection.step"]
    assert {r["compromised_runs"] for r in rows} == {f"0/{count}", f"{count}/{count}"}
    assert next(e.payload for e in ledger if e.type == "bisection.completed")["cause_input_id"]
    assert client.get(f"/incidents/{incident_id}").json()["status"] == "root_caused"
