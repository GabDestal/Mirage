"""Synthetic execution failures stay failures across the HTTP/event/snapshot boundary."""

import json
import math
import threading
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from contracts.models import (
    AgentSpec,
    Effect,
    Event,
    RunCompletion,
    Snapshot,
    SnapshotToolResult,
    WaitResult,
)
from engine.api import server, services
from engine.api.replay import Replay
from engine.detonation import snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, ATTACKER, HUMAN, USER, check, start

LEGIT = {"required": [{"tool": "send_email", "args": {"to": USER},
                       "nonempty": ["subject", "body"], "contains": {"body": ["Q4 sync"]}}]}
PRIVATE = "synthetic-provider-detail FLAG{team26-private} bearer synthetic-token"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    client = TestClient(server.app)
    assert client.post("/agents", json=AGENT).status_code == 200
    yield client
    gate.reset()


def test_error_completion_never_reports_success(api):
    run_id, auth = start(api)
    response = api.post(f"/runs/{run_id}/complete", headers=auth,
                        json={"error": f"RuntimeError: {PRIVATE}"})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "failed"
    assert run["ended_at"] is not None
    assert "RuntimeError" in run["status_reason"]
    assert PRIVATE not in json.dumps(api.get("/events").json())
    assert api.get(f"/runs/{run_id}").json()["status_reason"] == run["status_reason"]
    assert api.get(f"/runs/{run_id}/wait?timeout=0", headers=auth).json() == {"status": "failed"}
    assert check(api, run_id, auth, "read_calendar").json()["decision"] == "block"
    # An old SDK's finalizer cannot overwrite an earlier failure with success.
    assert api.post(f"/runs/{run_id}/complete", headers=auth).json()["status"] == "failed"


@pytest.mark.parametrize("error, category", [(f"TimeoutError: {PRIVATE}", "TimeoutError"),
                                             ("", "ExecutionError")])
def test_failed_recorded_result_survives_snapshot_without_becoming_an_input(api, error, category):
    run_id, auth = start(api)
    decision = check(api, run_id, auth, "read_calendar").json()
    assert api.post(f"/runs/{run_id}/tool-results", headers=auth, json={
        "call_id": decision["call_id"], "tool": "read_calendar",
        "result": [{"title": "Unusable partial record", "description": PRIVATE}],
        "error": error,
    }).status_code == 204
    check(api, run_id, auth, "send_email", to=ATTACKER, body="synthetic rows")
    snap = snapshot.load(gate.runs[run_id].incident_id)
    assert len(snap["tool_results"]) == 1
    failed = SnapshotToolResult.model_validate(snap["tool_results"][0])
    assert failed.call_id == decision["call_id"]
    assert failed.error == category
    assert failed.result is None
    assert [i["kind"] for i in snap["inputs"]] == ["user_task"]
    assert PRIVATE not in json.dumps(snap)
    assert PRIVATE not in json.dumps(api.get("/events").json())
    assert api.get("/services/calendar").json()["items"] == []


@pytest.mark.parametrize("body", [None, {}, {"error": None}])
def test_empty_completion_body_preserves_old_clients(api, body):
    run_id, auth = start(api)
    response = api.post(f"/runs/{run_id}/complete", headers=auth, json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.parametrize("status", ["frozen", "killed", "halted"])
def test_completion_cannot_overwrite_containment(api, status):
    run_id, auth = start(api)
    gate.set_status(gate.runs[run_id], status, "human", "Keep contained.")
    before = len(events.read())
    result = api.post(f"/runs/{run_id}/complete", headers=auth,
                      json={"error": f"RuntimeError: {PRIVATE}"}).json()
    assert result["status"] == status
    assert len(events.read()) == before


@pytest.mark.parametrize("error", ["", PRIVATE, f"CustomProviderError: {PRIVATE}"])
def test_unknown_and_empty_failures_are_sanitized(api, error):
    run_id, auth = start(api)
    result = api.post(f"/runs/{run_id}/complete", headers=auth, json={"error": error}).json()
    assert result["status"] == "failed"
    assert result["status_reason"]
    assert PRIVATE not in json.dumps(api.get("/events").json())
    assert "CustomProviderError" not in result["status_reason"]


@pytest.mark.parametrize("error_type", ["TimeoutError", "ClientError", "HTTPStatusError",
                                        "ValidationError"])
def test_safe_common_error_categories_are_preserved(api, error_type):
    run_id, auth = start(api)
    result = api.post(f"/runs/{run_id}/complete", headers=auth,
                      json={"error": f"{error_type}: {PRIVATE}"}).json()
    assert result["status"] == "failed"
    assert result["status_reason"] == f"Run failed: {error_type}."
    assert PRIVATE not in json.dumps(api.get("/events").json())


def test_sdk_wait_blocks_on_failed_without_running_a_tool(monkeypatch):
    from mirage import core

    with httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"status": "failed"})),
            base_url="http://synthetic.invalid") as client:
        monkeypatch.setattr(core, "_http", client)
        with pytest.raises(core.Blocked, match="failed"):
            core._wait({"id": "run_failed", "token": "synthetic-token"})


def test_inflight_gate_check_cannot_release_a_failed_run(api, monkeypatch):
    run_id, auth = start(api)
    judging, finish = threading.Event(), threading.Event()
    decisions = []

    def judge(*_):
        judging.set()
        assert finish.wait(2)

    monkeypatch.setattr(gate.decision_model, "judge", judge)
    thread = threading.Thread(target=lambda: decisions.append(
        check(api, run_id, auth, "send_email", to=USER, body="Synthetic brief").json()))
    thread.start()
    try:
        assert judging.wait(2)
        gate.set_status(gate.runs[run_id], "failed", "sdk", "Run failed: RuntimeError.")
    finally:
        finish.set()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert decisions[0]["decision"] == "block"
    assert gate.runs[run_id].status == "failed"
    assert api.get("/incidents").json() == []


def test_story_completion_declaration_reaches_start_restart_and_frozen_snapshot(api):
    assert api.post("/agents", json={**AGENT, "legit": LEGIT}).status_code == 200
    run_id, auth = start(api)
    assert gate.runs[run_id].legit == LEGIT
    # A running run owns a copy, independent of later registration mutations.
    gate.agents[AGENT["name"]].legit["required"][0]["args"]["to"] = "new@mirage-demo.com"
    assert gate.runs[run_id].legit == LEGIT
    check(api, run_id, auth, "send_email", to=ATTACKER, body="synthetic rows")
    assert snapshot.load(gate.runs[run_id].incident_id)["legit"] == LEGIT

    api.post(f"/runs/{run_id}/kill", json=HUMAN)
    assert api.post("/agents", json={**AGENT, "legit": LEGIT}).status_code == 200
    restarted = api.post(f"/runs/{run_id}/restart", json=HUMAN).json()
    assert gate.runs[restarted["id"]].legit == LEGIT
    next_id, _ = start(api)
    assert next_id == restarted["id"]
    assert gate.runs[next_id].legit == LEGIT
    gate.agents[AGENT["name"]].legit["required"][0]["args"]["to"] = "new@mirage-demo.com"
    assert gate.runs[next_id].legit == LEGIT


def test_execution_fixture_folds_failed_status_and_reason_in_replay(monkeypatch):
    fixture = server.FIXTURES / "execution_failure.jsonl"
    for line in fixture.read_text(encoding="utf-8").splitlines():
        event = Event.model_validate_json(line)
        if event.type == "agent.registered":
            AgentSpec.model_validate(event.payload)
        elif event.type == "detonation.effect":
            Effect.model_validate(event.payload)
    monkeypatch.setattr(server, "REPLAY", Replay(fixture, speed=math.inf))
    client = TestClient(server.app)
    run = client.get("/runs/run_failed").json()
    assert run["status"] == "failed"
    assert run["ended_at"] is not None
    assert run["status_reason"] == "Run failed: RuntimeError."
    assert client.get("/services/outbox").json()["items"] == []
    assert WaitResult(status="failed").status == "failed"


def test_effect_and_snapshot_error_fields_are_optional():
    assert Effect(detonation_id="det", run_index=1, step=1, tool="send_email", args={}).error is None
    assert SnapshotToolResult(call_id="call", tool="read_calendar", args={}).error is None
    assert Effect(detonation_id="det", run_index=1, step=1, tool="send_email", args={},
                  error="TimeoutError").error == "TimeoutError"
    assert RunCompletion().error is None
    snap = Snapshot.model_validate_json(
        (server.FIXTURES / "execution_snapshot.json").read_text(encoding="utf-8"))
    assert snap.legit == LEGIT
    assert snap.tool_results[0].error == "TimeoutError"


def ledger_event(seq, kind, payload, env="prod"):
    return Event(seq=seq, ts=datetime.now(UTC), env=env, type=kind, payload=payload)


@pytest.mark.parametrize("error", ["TimeoutError", ""])
@pytest.mark.parametrize("env", ["prod", "mirage"])
def test_failed_outbound_attempts_do_not_populate_successful_outbox(error, env):
    args = {"to": USER, "subject": "Synthetic brief", "body": "Q4 sync"}
    if env == "prod":
        log = [ledger_event(1, "tool.requested", {"call_id": "c", "tool": "send_email",
                                                 "args": args}),
               ledger_event(2, "tool.result", {"call_id": "c", "tool": "send_email",
                                              "result": None, "error": error})]
    else:
        log = [ledger_event(1, "detonation.started", {"detonation_id": "d"}, env),
               ledger_event(2, "detonation.effect", {"detonation_id": "d", "run_index": 1,
                    "step": 1, "tool": "send_email", "args": args,
                    "violates": [], "error": error}, env)]
    assert services.view(log, "outbox", env).items == []


@pytest.mark.parametrize("env", ["prod", "mirage"])
def test_scheduled_follow_up_is_labeled_scheduled_and_direct_email_stays_sent(env):
    scheduled = {"to": USER, "subject": "Follow up", "body": "Q4 sync", "send_on": "2026-10-12"}
    direct = {"to": USER, "subject": "Invoice", "body": "Synthetic invoice"}
    log = []
    if env == "mirage":
        log.append(ledger_event(1, "detonation.started", {"detonation_id": "d"}, env))
    for step, (tool, args) in enumerate([("schedule_follow_up", scheduled), ("send_email", direct)], 1):
        if env == "prod":
            call_id = f"c{step}"
            log.extend([
                ledger_event(len(log) + 1, "tool.requested", {"call_id": call_id, "tool": tool,
                                                             "args": args}),
                ledger_event(len(log) + 2, "tool.result", {"call_id": call_id, "tool": tool,
                                                          "result": {"status": "ok"}}),
            ])
        else:
            log.append(ledger_event(len(log) + 1, "detonation.effect", {
                "detonation_id": "d", "run_index": 1, "step": step, "tool": tool,
                "args": args, "violates": []}, env))
    items = services.view(log, "outbox", env).items
    assert [i.title for i in items] == ["Follow up", "Invoice"]
    assert "scheduled for 2026-10-12" in items[0].subtitle
    assert "sent" not in items[0].subtitle
    assert "scheduled" not in items[1].subtitle


def test_released_follow_up_remains_scheduled_in_the_outbox():
    args = {"to": USER, "subject": "Follow up", "body": "Q4 sync", "send_on": "2026-10-12"}
    log = [
        ledger_event(1, "tool.requested", {"call_id": "c", "tool": "schedule_follow_up",
                                          "args": args}),
        ledger_event(2, "gate.decision", {"call_id": "c", "tool": "schedule_follow_up",
                  "args": args, "decision": "freeze", "layer": "hard_rule",
                  "rule_id": "NEEDS_APPROVAL", "explanation": "Synthetic review."}),
        ledger_event(3, "tool.result", {"call_id": "c", "tool": "schedule_follow_up",
                                       "result": {"status": "scheduled"}}),
    ]
    item, = services.view(log, "outbox", "prod").items
    assert item.flag == "normal"
    assert "scheduled for 2026-10-12" in item.subtitle
    assert "after a human unfroze" in item.subtitle
    assert "sent" not in item.subtitle
