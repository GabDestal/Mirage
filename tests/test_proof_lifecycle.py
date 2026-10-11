"""Proof retries/failures retain containment and only expose current evidence."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from engine import bisect as engine_bisect
from engine.api import server, state
from engine.detonation import jobs, sandbox
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, check, start
from tests.test_bisect import save_incident

INCIDENT = "inc_001"


def emit(kind, payload):
    return events.emit(kind, payload, incident_id=INCIDENT, env="mirage")


def incident():
    return state.fold(events.read())[1][INCIDENT]


def drain():
    jobs._pool.submit(lambda: None).result(timeout=5)
    assert not jobs.running(INCIDENT)


def confirmed():
    trigger = {"call_id": "c1", "tool": "send_email", "args": {"to": ATTACKER},
               "decision": "freeze", "layer": "hard_rule", "rule_id": "DEST_NOT_ALLOWED",
               "explanation": "synthetic attack"}
    events.emit("run.started", {"task": "Prep", "agent": "assistant"}, run_id="run_001")
    events.emit("gate.decision", trigger, run_id="run_001")
    events.emit("incident.opened", {"incident_id": INCIDENT, "trigger_call_id": "c1"},
                run_id="run_001", incident_id=INCIDENT)
    emit("verdict.ready", {"incident_id": INCIDENT, "confirmed": True,
         "compromised_runs": "3/3", "policies_violated": ["P1"],
         "blast_radius": {"records": 2, "recipients": [ATTACKER],
                          "secrets": [], "summary": "Synthetic leak"}})


def row(input_id="in_02", is_cause=True):
    return {"input_id": input_id, "label": input_id,
            "compromised_runs": "0/2" if is_cause else "2/2", "is_cause": is_cause}


def removal_started(input_id="in_02"):
    emit("detonation.started", {"detonation_id": "removal", "removed_input_id": input_id,
                                "purpose": "detonate"})


@pytest.mark.parametrize("purpose", ["verify", "detonate"])
@pytest.mark.parametrize("stage", ["confirmed", "root_caused", "fix_pending"])
def test_job_failure_preserves_proof_stage(purpose, stage):
    gate.reset()
    confirmed()
    if stage != "confirmed":
        emit("bisection.step", row())
        emit("bisection.completed", {"cause_input_id": "in_02"})
    if stage == "fix_pending":
        emit("handoff.created", {})

    def fail(_):
        raise sandbox.DetonationError("synthetic timeout")

    jobs.submit(INCIDENT, fail, purpose=purpose)
    drain()
    folded = incident()
    assert folded.status == stage
    assert folded.verdict.confirmed
    assert not any(e.type == "fix.verified" for e in events.read())


def test_crashed_verification_keeps_production_frozen(monkeypatch):
    gate.reset()
    monkeypatch.setattr(server, "REPLAY", None)
    client = TestClient(server.app)
    client.post("/agents", json=AGENT)
    run_id, auth = start(client)
    check(client, run_id, auth, "send_email", to=ATTACKER)
    incident_id = gate.runs[run_id].incident_id
    assert incident_id == INCIDENT
    emit("verdict.ready", {"incident_id": INCIDENT, "confirmed": True,
         "compromised_runs": "3/3", "policies_violated": [],
         "blast_radius": {"records": 0, "recipients": [], "secrets": [], "summary": ""}})

    def fail(*args, **kwargs):
        raise sandbox.DetonationError("synthetic crash")

    monkeypatch.setattr(sandbox, "detonate", fail)
    assert client.post(f"/incidents/{INCIDENT}/verify", json=HUMAN).status_code == 200
    drain()
    assert client.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 409
    assert gate.runs[run_id].status == "frozen"
    assert not gate.runs[run_id].resume.is_set()
    assert client.get(f"/incidents/{INCIDENT}").json()["status"] == "confirmed"


def test_repeated_bisection_replaces_rows_and_clears_old_cause():
    confirmed()
    removal_started()
    emit("bisection.step", row())
    emit("bisection.completed", {"cause_input_id": "in_02"})
    removal_started("in_01")
    assert incident().cause_input_id is None
    assert incident().bisection == []
    emit("bisection.step", row("in_01", False))
    emit("bisection.step", row("in_02", False))
    emit("bisection.completed", {"cause_input_id": None})
    folded = incident()
    assert folded.status == "confirmed"
    assert folded.cause_input_id is None
    assert [r.input_id for r in folded.bisection] == ["in_01", "in_02"]
    assert not any(r.is_cause for r in folded.bisection)


def test_repeated_fixture_rows_do_not_retain_an_old_cause():
    confirmed()
    emit("bisection.step", row())
    emit("bisection.completed", {"cause_input_id": "in_02"})
    emit("bisection.step", row(is_cause=False))
    emit("bisection.completed", {"cause_input_id": None})
    assert len(incident().bisection) == 1
    assert not incident().bisection[0].is_cause


def test_a_new_baseline_verdict_invalidates_previous_bisection():
    confirmed()
    emit("bisection.step", row())
    emit("bisection.completed", {"cause_input_id": "in_02"})
    verdict = incident().verdict.model_dump(mode="json")
    verdict["confirmed"] = False
    verdict["compromised_runs"] = "0/3"
    emit("verdict.ready", verdict)
    assert incident().status == "false_positive"
    assert incident().cause_input_id is None
    assert incident().bisection == []


def test_a_bisection_retry_failing_before_the_first_row_clears_old_evidence():
    gate.reset()
    confirmed()
    emit("bisection.step", row())
    emit("bisection.completed", {"cause_input_id": "in_02"})

    def fail(_):
        raise FileNotFoundError("synthetic missing snapshot")

    jobs.submit(INCIDENT, fail, purpose="bisect")
    drain()
    assert incident().status == "confirmed"
    assert incident().cause_input_id is None
    assert incident().bisection == []


def test_handoff_during_bisection_does_not_drop_current_rows():
    confirmed()
    removal_started("in_01")
    emit("bisection.step", row("in_01", False))
    emit("handoff.created", {})
    removal_started("in_02")
    emit("bisection.step", row())
    emit("bisection.completed", {"cause_input_id": "in_02"})
    assert [r.input_id for r in incident().bisection] == ["in_01", "in_02"]


@pytest.mark.parametrize("runs", [0, -1])
def test_bisection_requires_positive_runs_before_any_evidence(runs):
    save_incident()
    with pytest.raises(ValueError, match="positive"):
        engine_bisect.bisect(INCIDENT, runs_per_input=runs, log=lambda *_: None)
    assert events.read() == []


@pytest.mark.parametrize("error", ["synthetic crash", "timeout after 180s"])
def test_crashed_bisection_cannot_prove_a_cause(monkeypatch, error):
    gate.reset()
    save_incident()
    confirmed()
    monkeypatch.setattr(sandbox, "run_once", lambda _: ([], error))
    monkeypatch.setattr(sandbox.time, "sleep", lambda _: None)
    jobs.submit(INCIDENT, lambda _: engine_bisect.bisect(INCIDENT, 1, log=lambda *_: None),
                purpose="bisect")
    drain()
    assert incident().status == "confirmed"
    assert incident().cause_input_id is None
    assert not incident().bisection
    assert not any(e.type in ("fix.verified", "verdict.ready", "bisection.step")
                   for e in events.read()[4:])
    failure = events.read()[-1].payload
    assert failure["error"] == "execution_failed"
    assert "synthetic crash" not in str([e.payload for e in events.read()])
    assert failure["purpose"] == "bisect"


@pytest.mark.parametrize("harmful", [True, False])
def test_judge_fields_cannot_change_the_deterministic_verdict(monkeypatch, harmful):
    save_incident()
    effects = [{"step": 1, "tool": "send_email", "args": {"to": ATTACKER}}] if harmful else []
    monkeypatch.setattr(sandbox, "run_once", lambda _: (effects, None))
    monkeypatch.setattr(sandbox.time, "sleep", lambda _: None)
    monkeypatch.setattr(sandbox.judge, "judge", lambda *args: {
        "confirmed": not harmful, "compromised_runs": "99/1",
        "policies": ["P6"], "summary": "Synthetic model explanation"})
    _, verdict, _ = sandbox.detonate(INCIDENT, 1, log=lambda *_: None)
    assert verdict.confirmed is harmful
    assert verdict.compromised_runs == ("1/1" if harmful else "0/1")


def test_executor_submit_failure_releases_reservation(monkeypatch):
    gate.reset()
    confirmed()

    class BrokenPool:
        def submit(self, work):
            raise RuntimeError("synthetic submit failure")

        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(jobs, "_pool", BrokenPool())
    with pytest.raises(RuntimeError, match="submit failure"):
        jobs.submit(INCIDENT, lambda _: pytest.fail("work must not start"))
    assert not jobs.running(INCIDENT)
    assert incident().status == "confirmed"
    monkeypatch.setattr(jobs, "_pool", None)


def test_queued_callback_failure_cannot_run_or_remove_a_new_reservation():
    gate.reset()
    confirmed()
    calls = []

    def failed_callback():
        raise RuntimeError("synthetic queued callback failure")

    with jobs.lock:
        with pytest.raises(RuntimeError, match="queued callback failure"):
            jobs.submit(INCIDENT, lambda _: calls.append("stale"), queued=failed_callback)
        assert not jobs.running(INCIDENT)
        jobs.submit(INCIDENT, lambda _: calls.append("retry"))
    drain()
    assert calls == ["retry"]


def test_active_work_excludes_reset_and_shutdown_cancels_queued(monkeypatch):
    gate.reset()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def active(_):
        entered.set()
        assert release.wait(5)
        calls.append("active")

    jobs.submit(INCIDENT, active)
    assert entered.wait(2)
    jobs.submit("inc_002", lambda _: calls.append("queued"))
    stopping = threading.Event()
    original = jobs._pool.shutdown

    def shutdown_pool(**kwargs):
        stopping.set()
        original(**kwargs)

    monkeypatch.setattr(jobs._pool, "shutdown", shutdown_pool)
    try:
        with pytest.raises(jobs.Busy, match="active"), jobs.resetting():
            pytest.fail("reset must not start")
        with ThreadPoolExecutor(max_workers=1) as pool:
            shutdown = pool.submit(jobs.shutdown)
            assert stopping.wait(2)
            with jobs.lock:
                assert jobs.running(INCIDENT)
            release.set()
            shutdown.result(timeout=5)
        assert calls == ["active"]
        assert not jobs.running(INCIDENT) and not jobs.running("inc_002")
        with pytest.raises(jobs.Busy):
            jobs.submit("inc_new", lambda _: None)
    finally:
        release.set()
