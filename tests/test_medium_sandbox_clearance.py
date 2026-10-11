"""Automatic medium clearance through real HTTP and protected SDK callbacks, offline."""

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from mirage import core

from engine.api import server
from engine.detection import decision_model
from engine.detonation import jobs, sandbox, snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, USER, check, start
from tests.test_auto_detonation import idle
from tests.test_sandbox import make_snapshot

AUTOMATIC = jobs.automatic
ARGS = {"to": USER, "subject": "Meeting brief", "body": "Renewal call at 09:00."}
LEGIT = {"required": [{"tool": "send_email", "args": {"to": USER},
                       "nonempty": ["subject", "body"],
                       "contains": {"body": ["Renewal call", "09:00"]}}]}


@pytest.fixture
def model(monkeypatch):
    """Mock only the provider boundary; retain parsing, thresholds and fenced call data."""
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        if kwargs["modelId"] == "synthetic-gate":
            answer = {"violates": True, "policy_id": "P5", "p": 0.55,
                      "reason": "Synthetic medium suspicion."}
        else:
            assert kwargs["modelId"] == "synthetic-stronger-judge"
            answer = {"violates": False, "policy_id": None, "p": 0,
                      "reason": "The exact held brief fits the admitted task."}
        return {"output": {"message": {"content": [{"text": json.dumps(answer)}]}}}

    monkeypatch.setenv("MIRAGE_LAYER2", "1")
    monkeypatch.setenv("BEDROCK_GATE_MODEL_ID", "synthetic-gate")
    monkeypatch.setenv("BEDROCK_JUDGE_MODEL_ID", "synthetic-stronger-judge")
    monkeypatch.setattr(decision_model, "_converse", converse)
    return calls


@pytest.fixture
def api(monkeypatch, model):
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(gate, "MODE", "live")
    monkeypatch.setattr(jobs, "automatic", AUTOMATIC)
    monkeypatch.setenv("MIRAGE_PARALLEL", "1")
    monkeypatch.setattr(sandbox, "load_dotenv", lambda: None)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    gate.reset()
    with TestClient(server.app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(core, "_http", client)
        monkeypatch.setattr(core, "_sandbox", None)
        assert client.post("/agents", json={**AGENT, "legit": LEGIT}).status_code == 200
        yield client
    gate.reset()


def protected(run_id, auth, effects):
    run = {"id": run_id, "token": auth["Authorization"].removeprefix("Bearer ")}
    token = core._run.set(run)
    try:
        return core.tool("send_email", ARGS, lambda: effects.append(copy.deepcopy(ARGS))
                         or {"status": "sent"})
    finally:
        core._run.reset(token)


@contextmanager
def pending_effect(api, monkeypatch):
    """Leave the real SDK waiting, with bounded cleanup even when the assertion is RED."""
    waiting = threading.Event()
    original_wait = core._wait

    def observed(*args, **kwargs):
        waiting.set()
        return original_wait(*args, **kwargs)

    monkeypatch.setattr(core, "_wait", observed)
    effects = []
    run_id, auth = start(api)
    original_run = gate.runs[run_id]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(protected, run_id, auth, effects)
        try:
            assert waiting.wait(2)
            run = gate.runs[run_id]
            assert run.status == "frozen" and effects == []
            assert run.incident_id is not None, "medium call has no automatic proof incident"
            yield run, auth, pending, effects
        finally:
            current = gate.runs.get(run_id)
            if current and current.status in ("running", "frozen"):
                api.post(f"/runs/{run_id}/kill", json=HUMAN)
            if current is not original_run and original_run.status == "frozen":
                gate._apply_status(original_run, "killed", "Synthetic old-owner test cleanup")
            try:
                pending.result(5)
            except (core.Blocked, httpx.HTTPStatusError):
                pass


def raw_effect(args=None, *, error=None):
    return {"step": 1, "tool": "send_email", "args": copy.deepcopy(args or ARGS),
            "error": error}


def semantic_response(monkeypatch, answer):
    original = decision_model._converse

    def converse(**kwargs):
        if kwargs["modelId"] == "synthetic-gate":
            return original(**kwargs)
        assert kwargs["modelId"] == "synthetic-stronger-judge"
        if isinstance(answer, Exception):
            raise answer
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return {"output": {"message": {"content": [{"text": text}]}}}

    monkeypatch.setattr(decision_model, "_converse", converse)


def test_medium_freeze_persists_snapshot_and_queues_three_baselines(api, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def held(incident_id, n_runs, **kwargs):
        snap = snapshot.load(incident_id)
        run = gate.runs[snap["run_id"]]
        assert run.status == "frozen" and not run.resume.is_set()
        calls.append((incident_id, n_runs, kwargs))
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(sandbox, "detonate", held)
    run_id, auth = start(api)
    try:
        decision = check(api, run_id, auth, "send_email", **ARGS).json()
        assert decision["decision"] == "freeze" and decision["p"] == 0.55
        incident_id = gate.runs[run_id].incident_id
        assert incident_id is not None, "medium freeze needs a persisted incident, not an approval"
        assert entered.wait(2)
        snap = snapshot.load(incident_id)
        assert snap["run_id"] == run_id and snap["legit"] == LEGIT
        assert calls[0][1] == 3
        assert not calls[0][2].get("verify") and not calls[0][2].get("removed_input_id")
        incident = api.get(f"/incidents/{incident_id}").json()
        assert incident["status"] == "detonating"
        assert incident["automatic_clearance"]["status"] == "checking"
        assert incident["sandbox_job"]["n_runs"] == 3
        assert api.get("/approvals").json() == []
        assert api.post(f"/approvals/{decision['call_id']}/approve", json=HUMAN).status_code == 404
        assert api.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 409
        assert not any(event.type == "human.action" for event in events.read())
    finally:
        release.set()
        jobs.shutdown()


def test_safe_medium_resumes_original_protected_effect_once_without_human(api, monkeypatch,
                                                                       model):
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
    replays, effects = [], []
    original_wait = core._wait

    def observed_wait(*args, **kwargs):
        waiting.set()
        return original_wait(*args, **kwargs)

    def replay(snap, **kwargs):
        replays.append(copy.deepcopy(snap))
        entered.set()
        assert release.wait(10)
        return [{"step": 1, "tool": "send_email", "args": copy.deepcopy(ARGS)}], None

    monkeypatch.setattr(core, "_wait", observed_wait)
    monkeypatch.setattr(sandbox, "run_once", replay)
    run_id, auth = start(api)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(protected, run_id, auth, effects)
        try:
            assert waiting.wait(2)
            assert effects == [] and gate.runs[run_id].status == "frozen"
            incident_id = gate.runs[run_id].incident_id
            assert incident_id is not None, "medium call never reached automatic sandbox proof"
            assert entered.wait(2)
            release.set()
            assert pending.result(10) == {"status": "sent"}
            idle(incident_id)
            assert len(replays) == 3 and effects == [ARGS]
            assert gate.runs[run_id].status == "running"
            assert len(gate.runs[run_id].tool_results) == 1
            incident = api.get(f"/incidents/{incident_id}").json()
            assert incident["automatic_clearance"]["status"] == "cleared"
            assert incident["verdict"]["confirmed"] is False
            assert any(call["modelId"] == "synthetic-stronger-judge" for call in model)
            assert not any(event.type == "human.action" for event in events.read())
            original_call = gate.runs[run_id].tool_results[0]["call_id"]
            duplicate = api.get(f"/runs/{run_id}/wait", headers=auth,
                                params={"call_id": original_call, "timeout": 0})
            assert duplicate.status_code == 409
            jobs.automatic(incident_id, gate.runs[run_id])
            idle(incident_id)
            assert len(replays) == 3 and effects == [ARGS]
        finally:
            release.set()
            if gate.runs[run_id].status in ("running", "frozen"):
                api.post(f"/runs/{run_id}/kill", json=HUMAN)


@pytest.mark.parametrize("answer", [
    {"violates": True, "policy_id": "P3", "p": 0.01, "reason": "Unrelated task."},
    {"violates": True, "policy_id": "P5", "p": 0.9, "reason": "Unrequested recipient."},
    {"violates": True, "policy_id": "P6", "p": 0.9, "reason": "Follows injected content."},
    {"violates": False, "policy_id": None, "p": 0},
    {"violates": "false", "policy_id": None, "p": 0, "reason": "Malformed boolean."},
    "not a decision",
    TimeoutError("synthetic provider unavailable"),
])
def test_semantically_harmful_or_unavailable_clean_baseline_stays_frozen(api, monkeypatch,
                                                                       answer):
    semantic_response(monkeypatch, answer)
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", lambda *a, **k: ([raw_effect()], None))
    with pending_effect(api, monkeypatch) as (run, _, pending, effects):
        idle(run.incident_id)
        incident = api.get(f"/incidents/{run.incident_id}").json()
        assert incident["verdict"]["confirmed"] is False  # still code-owned
        assert incident["automatic_clearance"]["status"] == "inconclusive"
        assert run.status == "frozen" and not run.resume.is_set()
        assert effects == [] and not pending.done()
        assert api.get("/approvals").json() == []


@pytest.mark.parametrize("case", [
    "harm", "missing_original", "missing_one_original", "tool_error", "child_error",
    "partial_useful_completion", "extra_unknown_tool",
])
def test_incomplete_or_harmful_baseline_cannot_release_protected_call(api, monkeypatch, case):
    count = 0

    def replay(*args, **kwargs):
        nonlocal count
        count += 1
        if case == "harm":
            return [raw_effect({**ARGS, "to": ATTACKER})], None
        if case == "missing_original" or (case == "missing_one_original" and count == 2):
            return [raw_effect({**ARGS, "subject": "A different brief"})], None
        if case == "tool_error":
            return [raw_effect(error="ExecutionError")], None
        if case == "child_error":
            return [raw_effect()], "child exited with code 1"
        if case == "partial_useful_completion" and count == 2:
            return [], None
        if case == "extra_unknown_tool":
            return [raw_effect(), {"step": 2, "tool": "unknown_publish", "args": {}}], None
        return [raw_effect()], None

    monkeypatch.setattr(sandbox, "run_once", replay)
    with pending_effect(api, monkeypatch) as (run, _, pending, effects):
        idle(run.incident_id)
        assert count == 3
        assert run.status == "frozen" and not run.resume.is_set()
        assert effects == [] and not pending.done()
        incident = api.get(f"/incidents/{run.incident_id}").json()
        assert incident["automatic_clearance"]["status"] == "inconclusive"
        if case == "harm":
            assert incident["verdict"]["confirmed"] is True


@pytest.mark.parametrize("control", ["stop", "kill", "refreeze"])
def test_revocation_during_clean_baseline_prevents_release(api, monkeypatch, control):
    entered, release = threading.Event(), threading.Event()

    def replay(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return [raw_effect()], None

    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", replay)
    try:
        with pending_effect(api, monkeypatch) as (run, _, _, effects):
            assert entered.wait(2)
            path = "/stop" if control == "stop" else f"/runs/{run.id}/" + (
                "freeze" if control == "refreeze" else "kill")
            assert api.post(path, json=HUMAN).status_code == 200
            release.set()
            idle(run.incident_id)
            assert effects == []
            assert run.status == {"stop": "halted", "kill": "killed", "refreeze": "frozen"}[control]
    finally:
        release.set()


@pytest.mark.parametrize("tier", ["high", "hard", "escalation"])
def test_human_only_tiers_stay_frozen_after_clean_baselines(api, monkeypatch, tier):
    if tier == "high":
        original = decision_model._converse

        def high(**kwargs):
            response = original(**kwargs)
            if kwargs["modelId"] == "synthetic-gate":
                response["output"]["message"]["content"] = [{"text": json.dumps({
                    "violates": True, "policy_id": "P5", "p": 0.95,
                    "reason": "Synthetic high suspicion."})}]
            return response

        monkeypatch.setattr(decision_model, "_converse", high)
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", lambda *a, **k: ([raw_effect()], None))
    run_id, auth = start(api)
    if tier == "hard":
        decision = check(api, run_id, auth, "send_email", **{**ARGS, "to": ATTACKER}).json()
    elif tier == "escalation":
        check(api, run_id, auth, "unknown_tool_one")
        decision = check(api, run_id, auth, "unknown_tool_two").json()
    else:
        decision = check(api, run_id, auth, "send_email", **ARGS).json()
    assert decision["decision"] == "freeze"
    run = gate.runs[run_id]
    assert run.incident_id is not None
    idle(run.incident_id)
    assert run.status == "frozen" and not run.resume.is_set()
    incident = api.get(f"/incidents/{run.incident_id}").json()
    assert incident["verdict"]["confirmed"] is False
    assert incident.get("automatic_clearance") is None


@pytest.mark.parametrize("action", ["detonate", "verify"])
def test_manual_proof_retry_cannot_release_medium_call(api, monkeypatch, action):
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", lambda *a, **k: (
        [raw_effect({**ARGS, "subject": "Different initial call"})], None))
    with pending_effect(api, monkeypatch) as (run, _, pending, effects):
        idle(run.incident_id)
        assert run.status == "frozen" and effects == []
        monkeypatch.setattr(sandbox, "run_once", lambda *a, **k: ([raw_effect()], None))
        response = api.post(f"/incidents/{run.incident_id}/{action}", json=HUMAN)
        assert response.status_code == 200
        idle(run.incident_id)
        assert run.status == "frozen" and effects == [] and not pending.done()
        assert api.get(f"/incidents/{run.incident_id}").json()[
            "automatic_clearance"]["status"] == "inconclusive"


def test_absent_stronger_model_configuration_cannot_clear(api, monkeypatch):
    monkeypatch.delenv("BEDROCK_JUDGE_MODEL_ID", raising=False)
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", lambda *a, **k: ([raw_effect()], None))
    with pending_effect(api, monkeypatch) as (run, _, pending, effects):
        idle(run.incident_id)
        assert run.status == "frozen" and effects == [] and not pending.done()
        assert api.get(f"/incidents/{run.incident_id}").json()[
            "automatic_clearance"]["status"] == "inconclusive"


@pytest.mark.parametrize("failure", ["snapshot", "schedule"])
def test_medium_setup_failure_keeps_original_effect_contained(api, monkeypatch, failure):
    calls = []
    monkeypatch.setattr(sandbox, "run_once", lambda *a, **k: calls.append(a))
    if failure == "snapshot":
        def failed_save(*args, **kwargs):
            raise OSError("synthetic snapshot persistence failure")

        monkeypatch.setattr(snapshot, "save", failed_save)
    else:
        class BrokenPool:
            def submit(self, *args, **kwargs):
                raise RuntimeError("synthetic scheduling failure")

            def shutdown(self, **kwargs):
                pass

        monkeypatch.setattr(jobs, "_pool", BrokenPool())
    with pending_effect(api, monkeypatch) as (run, _, pending, effects):
        assert calls == [] and effects == [] and not pending.done()
        assert run.status == "frozen" and not run.resume.is_set()
        assert any(event.type == "detonation.failed" for event in events.read())


@pytest.mark.parametrize("mutation", ["snapshot", "catalogue", "token", "owner", "incident"])
def test_changed_clearance_authority_cannot_release_old_held_call(api, monkeypatch, mutation):
    entered, release = threading.Event(), threading.Event()

    def replay(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return [raw_effect()], None

    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", replay)
    try:
        with pending_effect(api, monkeypatch) as (run, _, _, effects):
            assert entered.wait(2)
            incident_id = run.incident_id
            with jobs.lock:
                if mutation == "snapshot":
                    snap = snapshot.load(incident_id)
                    snap["task"] = "Changed task after the automatic job was reserved"
                    (snapshot.SNAP_DIR / f"{incident_id}.json").write_text(json.dumps(snap))
                elif mutation == "catalogue":
                    gate.agents[run.agent].owner = "Changed admitted metadata"
                elif mutation == "token":
                    run.token = "changed-synthetic-token"
                elif mutation == "owner":
                    replacement = copy.copy(run)
                    replacement.resume = threading.Event()
                    gate.runs[run.id] = replacement
                else:
                    run.incident_id = "inc_replacement"
            release.set()
            idle(incident_id)
            assert effects == [] and run.status == "frozen"
            assert not run.resume.is_set()
            assert gate.runs[run.id].status == "frozen"
    finally:
        release.set()


def test_three_real_jailed_baselines_preserve_exact_useful_call_and_snapshot(api, monkeypatch):
    # Until the production parent pin lands, the real child must use this assigned SDK.
    monkeypatch.setattr(sandbox, "BOOT", "import sys, runpy; "
        "sys.path.insert(0, sys.argv[1] + '/sdk'); sys.path.insert(0, sys.argv[1]); "
        "runpy.run_module('engine.detonation.child', run_name='__main__')")
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    snap = make_snapshot("tests.legitimate_completion_agents:run")
    snap.update(agent=AGENT["name"], task="Prep my meetings", legit=copy.deepcopy(LEGIT),
                system=json.dumps([raw_effect()]), policy=gate.policy_for(AGENT["name"]))
    path = snapshot.SNAP_DIR / "inc_001.json"
    path.write_text(json.dumps(snap), encoding="utf-8")
    detonation, verdict, result = sandbox.detonate("inc_001", log=lambda *_: None)
    assert result.passed and result.legit_task_completed == result.attack_blocked == "3/3"
    assert detonation.n_runs == 3 and verdict.confirmed is False
    assert [effect.run_index for effect in result.effects] == [1, 2, 3]
    assert all(effect.args == ARGS and effect.error is None for effect in result.effects)
    assert snapshot.load("inc_001") == snap


def test_recovery_status_write_failure_cannot_grant_original_call(api, monkeypatch):
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", lambda *a, **k: ([raw_effect()], None))
    original_emit = gate.emit

    def failed_emit(kind, payload, **kwargs):
        if (kind == "run.status" and payload.get("from") == "frozen"
                and payload.get("to") == "running"):
            raise OSError("synthetic recovery evidence storage failure")
        return original_emit(kind, payload, **kwargs)

    monkeypatch.setattr(gate, "emit", failed_emit)
    with pending_effect(api, monkeypatch) as (run, _, pending, effects):
        idle(run.incident_id)
        assert run.status == "frozen" and not run.resume.is_set()
        assert effects == [] and not pending.done()


def test_replaced_stream_old_job_cannot_release_same_id_new_run(api, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def replay(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return [raw_effect()], None

    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "run_once", replay)
    try:
        with pending_effect(api, monkeypatch) as (old, _, _, effects):
            assert entered.wait(2)
            events.reset()  # external store replacement; runtime read revokes the old owner
            api.get("/runtime")
            assert api.post("/agents", json={**AGENT, "legit": LEGIT}).status_code == 200
            new_id, _ = start(api)
            assert new_id == old.id
            assert api.post(f"/runs/{new_id}/freeze", json=HUMAN).status_code == 200
            replacement = gate.runs[new_id]
            release.set()
            jobs.shutdown()  # drain physical old work, even after its stale reservation vanished
            assert old.status == "halted" and old.revoked_by_reset
            assert replacement is not old and replacement.status == "frozen"
            assert not replacement.resume.is_set() and effects == []
            assert not any(event.type in ("verdict.ready", "detonation.completed")
                           for event in events.read())
    finally:
        release.set()
