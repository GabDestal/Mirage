"""Recovery authority through real HTTP and SDK starts; synthetic and provider-free."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from mirage import core

from engine.api import server
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, HUMAN, USER

TASK = "Prep my meetings"
SPEC = {**AGENT, "entrypoint": "", "legit": {"tool": "send_email", "to": USER}}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    with TestClient(server.app) as client:
        monkeypatch.setattr(core, "_http", client)
        monkeypatch.setattr(core, "_sandbox", None)
        assert client.post("/agents", json=SPEC).status_code == 200
        yield client
    gate.reset()


def queue(api, action="restart"):
    old = core.open_run(SPEC["name"], TASK)
    if action == "restart":
        assert api.post(f"/runs/{old['id']}/kill", json=HUMAN).status_code == 200
    else:
        assert api.post("/stop", json=HUMAN).status_code == 200
    response = api.post(f"/runs/{old['id']}/{action}", json=HUMAN)
    assert response.status_code == 200
    new = response.json()
    assert new["status"] == "queued" and new["restarted_from"] == old["id"]
    return old, new


def claim(api, old, **changes):
    return api.post("/runs", json={"agent": SPEC["name"], "task": TASK,
                                   "restarted_from": old["id"], **changes})


def successors(old):
    return [r for r in gate.runs.values() if r.restarted_from == old["id"]]


def observe_contention(monkeypatch, boundary):
    """Signal blocked lock entry; unlocked paths signal at their actual mutation seam."""
    original = server.jobs.lock

    class ObservedLock:
        def __enter__(self):
            if not original.acquire(blocking=False):
                boundary.set()
                original.acquire()
            return self

        def __exit__(self, *args):
            original.release()

    monkeypatch.setattr(server.jobs, "lock", ObservedLock())


@pytest.mark.parametrize("action", ["restart", "resume"])
def test_sdk_matching_task_claims_approved_queue_once(api, action):
    old, new = queue(api, action)
    run = core.open_run(SPEC["name"], TASK)
    assert run["id"] == new["id"]
    assert gate.runs[run["id"]].status == "running"
    assert gate.runs[run["id"]].task == TASK
    assert claim(api, old).status_code == 409
    assert len(successors(old)) == 1


def test_new_sdk_tasks_still_start_without_claiming_another_tasks_queue(api):
    _, new = queue(api)
    run = core.open_run(SPEC["name"], "A different legitimate task")
    assert run["id"] != new["id"]
    assert gate.runs[run["id"]].task == "A different legitimate task"
    assert gate.runs[run["id"]].restarted_from is None
    assert gate.runs[new["id"]].status == "queued"
    assert core.open_run(SPEC["name"], TASK)["id"] == new["id"]


def test_ordinary_sdk_starts_without_lineage_remain_supported(api):
    first = core.open_run(SPEC["name"], TASK)
    second = core.open_run(SPEC["name"], TASK)
    assert first["id"] != second["id"]
    assert all(r.status == "running" and r.restarted_from is None for r in gate.runs.values())


def test_implicit_sdk_claim_refuses_ambiguous_originals_with_same_agent_task(api):
    originals = [core.open_run(SPEC["name"], TASK) for _ in range(2)]
    queued = []
    for old in originals:
        assert api.post(f"/runs/{old['id']}/kill", json=HUMAN).status_code == 200
        response = api.post(f"/runs/{old['id']}/restart", json=HUMAN)
        assert response.status_code == 200
        queued.append(response.json())
    with pytest.raises(httpx.HTTPStatusError) as error:
        core.open_run(SPEC["name"], TASK)
    assert error.value.response.status_code == 409
    assert all(gate.runs[r["id"]].status == "queued" for r in queued)
    for old, new in zip(originals, queued, strict=True):
        assert claim(api, old).json()["run_id"] == new["id"]


def test_stop_revoked_queue_cannot_be_claimed_after_stop_lift(api):
    old, new = queue(api)
    assert api.post("/stop", json=HUMAN).status_code == 200
    assert api.post("/stop/lift", json=HUMAN).status_code == 204
    before = set(gate.runs)
    assert claim(api, old).status_code == 409
    assert set(gate.runs) == before
    assert gate.runs[new["id"]].status == "halted"


@pytest.mark.parametrize("lineage", ["running", "killed", "unknown"])
def test_sdk_cannot_forge_lineage_without_approved_successor(api, lineage):
    old = core.open_run(SPEC["name"], TASK)
    if lineage == "killed":
        assert api.post(f"/runs/{old['id']}/kill", json=HUMAN).status_code == 200
    elif lineage == "unknown":
        old = {"id": "run_missing"}
    before = set(gate.runs)
    assert claim(api, old).status_code == 409
    assert set(gate.runs) == before


@pytest.mark.parametrize("mismatch", ["task", "agent", "lineage"])
def test_explicit_claim_cannot_take_an_unrelated_approved_queue(api, mismatch):
    old, new = queue(api)
    changes = {"task": "A different task"}
    if mismatch == "agent":
        other = {**SPEC, "name": "other_assistant"}
        assert api.post("/agents", json=other).status_code == 200
        changes = {"agent": other["name"]}
    elif mismatch == "lineage":
        changes = {"restarted_from": "run_missing"}
    before = set(gate.runs)
    assert claim(api, old, **changes).status_code == 409
    assert set(gate.runs) == before
    assert gate.runs[new["id"]].status == "queued"
    assert claim(api, old).json()["run_id"] == new["id"]


@pytest.mark.parametrize("field", ["owner", "tools", "allow_tools", "email_to", "url_hosts",
                                 "entrypoint", "legit"])
def test_changed_registration_cannot_claim_queue_until_matching_spec_restored(api, field):
    old, new = queue(api)
    changed = copy.deepcopy(SPEC)
    if field == "owner":
        changed[field] = "another-owner"
    elif field == "tools":
        changed[field].append("upload_records")
    elif field == "allow_tools":
        changed["allow"]["tools"] = ["send_email"]
    elif field == "email_to":
        changed["allow"][field] = ["different@synthetic.example"]
    elif field == "url_hosts":
        changed["allow"][field] = ["synthetic.example"]
    elif field == "entrypoint":
        changed[field] = "tests.sandbox_agents:attacker"
    else:
        changed[field] = {"tool": "send_email", "to": "different@synthetic.example"}
    assert api.post("/agents", json=changed).status_code == 200
    assert claim(api, old).status_code == 409
    assert gate.runs[new["id"]].status == "queued"
    with pytest.raises(httpx.HTTPStatusError) as error:
        core.open_run(SPEC["name"], TASK)
    assert error.value.response.status_code == 409
    assert gate.runs[new["id"]].status == "queued"
    assert api.post("/agents", json=SPEC).status_code == 200
    assert core.open_run(SPEC["name"], TASK)["id"] == new["id"]
    assert claim(api, old).status_code == 409


def test_two_http_starters_claim_one_approved_successor(api, monkeypatch):
    old, new = queue(api)
    paused, boundary, release = threading.Event(), threading.Event(), threading.Event()
    original = gate.set_status
    observe_contention(monkeypatch, boundary)

    def pause(run, to, actor, reason):
        if run.id == new["id"] and to == "running":
            if paused.is_set():
                boundary.set()
            paused.set()
            assert release.wait(5)
        return original(run, to, actor, reason)

    monkeypatch.setattr(gate, "set_status", pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(claim, api, old)
        try:
            assert paused.wait(2)
            second = pool.submit(claim, api, old)
            assert boundary.wait(2)
        finally:
            release.set()
        responses = [first.result(3), second.result(3)]
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r for r in responses if r.status_code == 200).json()["run_id"] == new["id"]
    assert len(successors(old)) == 1


@pytest.mark.parametrize("action", ["restart", "resume"])
@pytest.mark.parametrize("concurrent", [False, True])
def test_duplicate_human_recovery_queues_one_successor(api, monkeypatch, action, concurrent):
    old = core.open_run(SPEC["name"], TASK)
    path = f"/runs/{old['id']}/{action}"
    if action == "restart":
        assert api.post(f"/runs/{old['id']}/kill", json=HUMAN).status_code == 200
    else:
        assert api.post("/stop", json=HUMAN).status_code == 200
    if concurrent:
        paused, boundary, release = threading.Event(), threading.Event(), threading.Event()
        original = server._queue_restart
        observe_contention(monkeypatch, boundary)

        def pause(*args, **kwargs):
            if paused.is_set():
                boundary.set()
            paused.set()
            assert release.wait(5)
            return original(*args, **kwargs)

        monkeypatch.setattr(server, "_queue_restart", pause)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(api.post, path, json=HUMAN)
            try:
                assert paused.wait(2)
                second = pool.submit(api.post, path, json=HUMAN)
                assert boundary.wait(2)
            finally:
                release.set()
            responses = [first.result(3), second.result(3)]
    else:
        responses = [api.post(path, json=HUMAN), api.post(path, json=HUMAN)]
    assert responses[0].status_code == 200
    assert responses[1].status_code == 409 or responses[1].json()["id"] == responses[0].json()["id"]
    assert len(successors(old)) == 1
    actions = [e for e in events.read() if e.type == "human.action"
               and e.payload["action"] == ("approve_restart" if action == "restart" else "resume")]
    assert len(actions) == 1


@pytest.mark.parametrize("queued", [False, True])
def test_stop_racing_http_admission_cannot_leave_active_run(api, monkeypatch, queued):
    if queued:
        old, new = queue(api)
    paused, boundary, release = threading.Event(), threading.Event(), threading.Event()
    original_status, original_stop = gate.set_status, gate._global_stop
    observe_contention(monkeypatch, boundary)

    def pause(run, to, actor, reason):
        if to == "running":
            paused.set()
            assert release.wait(5)
        return original_status(run, to, actor, reason)

    def stop(*args):
        result = original_stop(*args)
        boundary.set()
        return result

    monkeypatch.setattr(gate, "set_status", pause)
    monkeypatch.setattr(gate, "_global_stop", stop)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(claim, api, old) if queued else pool.submit(core.open_run, SPEC["name"], TASK)
        try:
            assert paused.wait(2)
            stopping = pool.submit(api.post, "/stop", json=HUMAN)
            assert boundary.wait(2)
        finally:
            release.set()
        started = first.result(3)
        assert stopping.result(3).status_code == 200
    run_id = started.json()["run_id"] if queued else started["id"]
    assert gate.STOP.is_set()
    assert gate.runs[run_id].status == "halted"
    if queued:
        assert run_id == new["id"]
    assert api.post("/stop/lift", json=HUMAN).status_code == 204
    auth = {"Authorization": f"Bearer {gate.runs[run_id].token}"}
    decision = api.post("/gateway/check", headers=auth,
                        json={"run_id": run_id, "tool": "send_email", "args": {"to": USER}})
    assert decision.json()["decision"] == "block"


def test_failed_run_requires_human_restart_then_matching_sdk_claim(api):
    old = core.open_run(SPEC["name"], TASK)
    auth = {"Authorization": f"Bearer {old['token']}"}
    failed = api.post(f"/runs/{old['id']}/complete", headers=auth,
                      json={"error": "SyntheticError: failed task"})
    assert failed.status_code == 200 and failed.json()["status"] == "failed"
    response = api.post(f"/runs/{old['id']}/restart", json=HUMAN)
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert core.open_run(SPEC["name"], TASK)["id"] == response.json()["id"]
    assert gate.runs[old["id"]].status == "failed"
