"""Replay accounting with real jailed children and synthetic agents, without providers."""

import os

import pytest

from engine.bisect import bisect
from engine.detonation import sandbox
from engine.store import events
from tests.sandbox_agents import clean, leaks_then_crashes
from tests.test_sandbox import make_snapshot


def clean_then_crashes(snapshot, call_tool):
    clean(snapshot, call_tool)
    raise RuntimeError("agent crashed after its task")


def completes_then_leaks_and_crashes(snapshot, call_tool):
    clean(snapshot, call_tool)
    leaks_then_crashes(snapshot, call_tool)


def silent_crash(snapshot, call_tool):
    clean(snapshot, call_tool)
    os._exit(7)


@pytest.mark.parametrize("verify", [False, True])
@pytest.mark.parametrize("entrypoints,compromised,blocked,legit,completed", [
    (["tests.sandbox_agents:leaks_then_crashes", "tests.sandbox_agents:clean",
      "tests.test_sandbox_accounting:clean_then_crashes"], 1, 1, 1, 1),
    (["tests.sandbox_agents:leaks_then_crashes", "tests.sandbox_agents:attacker",
      "tests.sandbox_agents:clean"], 2, 1, 2, 2),
])
def test_mixed_replays_use_one_attempt_denominator(
        monkeypatch, verify, entrypoints, compromised, blocked, legit, completed):
    make_snapshot(entrypoints[0])
    real_run_once = sandbox.run_once
    scripted = iter(entrypoints)

    def run_next(snap):
        return real_run_once({**snap, "entrypoint": next(scripted)})

    monkeypatch.setenv("MIRAGE_PARALLEL", "1")
    monkeypatch.setattr(sandbox, "run_once", run_next)
    detonation, verdict, result = sandbox.detonate(
        "inc_001", n_runs=3, verify=verify, log=lambda *_: None)

    assert detonation.n_runs == 3 and detonation.compromised_runs == compromised
    assert verdict.compromised_runs == f"{compromised}/3"
    assert result.attack_blocked == f"{blocked}/3"
    assert result.legit_task_completed == f"{legit}/3" and not result.passed
    assert f"{completed} of 3 replays completed; {3 - completed} crashed" in (
        verdict.blast_radius.summary)
    assert "run 1: RuntimeError: agent crashed after leaking" in verdict.blast_radius.summary
    if completed == 1:
        assert "run 3: RuntimeError: agent crashed after its task" in verdict.blast_radius.summary
    assert {e.run_index for e in result.effects} == {1, 2, 3}


def test_task_effects_before_a_crash_do_not_count_as_completion():
    make_snapshot("tests.test_sandbox_accounting:completes_then_leaks_and_crashes")
    _, verdict, result = sandbox.detonate("inc_001", n_runs=1, verify=True, log=lambda *_: None)
    assert verdict.confirmed and verdict.compromised_runs == "1/1"
    assert result.attack_blocked == "0/1" and result.legit_task_completed == "0/1"
    assert not result.passed
    assert any(e.args.get("to") == "bob@northwind.example" for e in result.effects)


@pytest.mark.parametrize("verify", [False, True])
def test_clean_task_followed_by_crash_is_inconclusive(verify):
    make_snapshot("tests.test_sandbox_accounting:clean_then_crashes")
    with pytest.raises(sandbox.DetonationError, match="crashed after its task"):
        sandbox.detonate("inc_001", n_runs=1, verify=verify, log=lambda *_: None)
    assert any(e.type == "detonation.effect" for e in events.read())
    assert not any(e.type in {"verdict.ready", "fix.verified"} for e in events.read())


def test_bisection_clean_crash_cannot_prove_a_cause():
    make_snapshot("tests.test_sandbox_accounting:clean_then_crashes")
    with pytest.raises(sandbox.DetonationError, match="crashed after its task"):
        bisect("inc_001", runs_per_input=1, log=lambda *_: None)
    assert not any(e.type in {"bisection.step", "bisection.completed"} for e in events.read())


def test_nonzero_exit_without_stderr_is_a_crash():
    snap = make_snapshot("tests.test_sandbox_accounting:silent_crash")
    effects, error = sandbox.run_once(snap)
    assert effects and effects[-1]["args"]["to"] == "bob@northwind.example"
    assert error and "7" in error
    with pytest.raises(sandbox.DetonationError, match="crashed"):
        sandbox.detonate("inc_001", n_runs=1, verify=True, log=lambda *_: None)
    assert not any(e.type == "fix.verified" for e in events.read())
