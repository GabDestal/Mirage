"""Parent collection failures retain available proof, without claiming clean completion."""

import json
import threading
from pathlib import Path

import boto3
import botocore.session
import pytest

from engine.detonation import sandbox
from engine.store import events
from tests.parent_proof_failure_agents import PRIVATE, forbid_provider
from tests.test_sandbox import make_snapshot

PREFIX = "tests.parent_proof_failure_agents:"
MALFORMED = ["leaks_then_bad_json", "leaks_then_bad_shape", "leaks_then_bad_args",
             "leaks_then_bad_utf8"]


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    monkeypatch.setattr(boto3, "client", forbid_provider)
    monkeypatch.setattr(boto3, "resource", forbid_provider)
    monkeypatch.setattr(botocore.session.Session, "create_client", forbid_provider)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")


def public_diagnostics(logs, verdict=None, failure=None):
    diagnostics = [e.payload for e in events.read() if e.type == "agent.message"]
    public = json.dumps(logs + diagnostics) + str(failure or "")
    if verdict:
        public += verdict.model_dump_json()
    assert PRIVATE not in public
    assert "Traceback (most recent call last)" not in public
    return public


@pytest.mark.parametrize("runner", MALFORMED)
def test_run_once_keeps_valid_harm_before_malformed_ledger(runner):
    snap = make_snapshot(PREFIX + runner)
    effects, error = sandbox.run_once(snap)
    assert effects[0]["args"]["to"] == "attacker@evil-corp-demo.com"
    assert len(effects) == 3  # leak and legitimate effects were flushed before corruption
    assert error  # even a zero-exit child cannot make malformed evidence complete


@pytest.mark.parametrize("verify", [False, True])
@pytest.mark.parametrize("runner", MALFORMED)
def test_malformed_collection_preserves_harm_but_never_completes_task(runner, verify):
    make_snapshot(PREFIX + runner)
    logs = []
    detonation, verdict, result = sandbox.detonate(
        "inc_001", n_runs=1, verify=verify, log=logs.append)
    assert detonation.n_runs == detonation.compromised_runs == 1
    assert verdict.confirmed and verdict.compromised_runs == "1/1"
    assert {"P1", "P5"} <= set(verdict.policies_violated)
    assert verdict.blast_radius.recipients == ["attacker@evil-corp-demo.com"]
    assert result.attack_blocked == result.legit_task_completed == "0/1"
    assert not result.passed and len(result.effects) == 3
    assert "0 of 1 replays completed; 1 crashed" in verdict.blast_radius.summary
    assert PREFIX + runner in public_diagnostics(logs, verdict)


@pytest.mark.parametrize("runner", ["missing_ledger", "directory_ledger"])
def test_real_jailed_filesystem_fault_is_an_attempt_error(runner):
    effects, error = sandbox.run_once(make_snapshot(PREFIX + runner))
    assert effects == [] and error


@pytest.mark.parametrize("verify", [False, True])
@pytest.mark.parametrize("runner", ["clean_then_bad_json", "missing_ledger", "directory_ledger"])
def test_clean_collection_failure_never_emits_clean_verdict_or_fix(runner, verify):
    make_snapshot(PREFIX + runner)
    logs = []
    with pytest.raises(sandbox.DetonationError) as failure:
        sandbox.detonate("inc_001", n_runs=1, verify=verify, log=logs.append)
    assert "1 of 1 replays crashed" in str(failure.value)
    assert not any(e.type in {"detonation.completed", "verdict.ready", "fix.verified"}
                   for e in events.read())
    assert PREFIX + runner in public_diagnostics(logs, failure=failure.value)


@pytest.mark.parametrize("verify", [False, True])
@pytest.mark.parametrize("fault", ["missing_ledger", "directory_ledger", "parent_exception"])
def test_parallel_harm_survives_a_later_parent_collection_failure(monkeypatch, verify, fault):
    make_snapshot(PREFIX + "harm")
    real_run_once = sandbox.run_once
    lock, sibling_collected = threading.Lock(), threading.Event()
    attempt = 0

    def run_next(snap):
        nonlocal attempt
        with lock:
            attempt += 1
            index = attempt
        if index == 1:
            result = real_run_once({**snap, "entrypoint": PREFIX + "harm"})
            sibling_collected.set()
            return result
        if index == 2:
            assert sibling_collected.wait(10), "harmful sibling never finished"
            if fault == "parent_exception":
                raise OSError(PRIVATE)  # separate future-boundary fault, not a filesystem claim
            return real_run_once({**snap, "entrypoint": PREFIX + fault})
        return real_run_once({**snap, "entrypoint": "tests.sandbox_agents:clean"})

    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", run_next)
    logs = []
    detonation, verdict, result = sandbox.detonate(
        "inc_001", n_runs=3, verify=verify, log=logs.append)
    assert attempt == 3
    assert detonation.n_runs == 3 and detonation.compromised_runs == 1
    assert verdict.confirmed and verdict.compromised_runs == "1/3"
    assert result.attack_blocked == "1/3" and result.legit_task_completed == "2/3"
    assert not result.passed
    assert "2 of 3 replays completed; 1 crashed" in verdict.blast_radius.summary
    assert len({e.run_index for e in result.effects if e.violates}) == 1
    assert len({e.run_index for e in result.effects}) == 2
    assert [e.run_index for e in result.effects] == sorted(e.run_index for e in result.effects)
    public_diagnostics(logs, verdict)
    proof = next(e.payload for e in events.read()
                 if e.type == ("fix.verified" if verify else "verdict.ready"))
    assert proof["passed" if verify else "confirmed"] is (not verify)


@pytest.mark.parametrize("verify", [False, True])
def test_parent_read_failure_is_safe_and_inconclusive(monkeypatch, verify):
    make_snapshot("tests.sandbox_agents:clean")
    real_open = Path.open

    def unreadable(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path.name == "effects.jsonl" and "r" in mode:
            raise PermissionError(PRIVATE)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable)
    logs = []
    with pytest.raises(sandbox.DetonationError) as failure:
        sandbox.detonate("inc_001", n_runs=1, verify=verify, log=logs.append)
    assert "PermissionError" in public_diagnostics(logs, failure=failure.value)
    assert not any(e.type in {"verdict.ready", "fix.verified"} for e in events.read())
