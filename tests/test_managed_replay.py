"""Managed recording through the real HTTP API, without providers or live state."""

import json
import math
import runpy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace

import boto3
import pytest
from fastapi.testclient import TestClient

from contracts.models import DetonateResult, Detonation, Effect, Event, HumanAction, Verdict
from engine.api import replay, server
from engine.api.replay import Replay

FLEET = server.FIXTURES / "fleet_demo_4agents.jsonl"
HUMAN = {"actor": "Liam via Miragio (MCP)", "reason": "Approved recorded demonstration"}
PR = "https://example.invalid/recorded-demo/pr/42"


@pytest.fixture
def api(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Managed replay reached live state or execution")

    with monkeypatch.context() as patch:
        patch.setattr(server, "REPLAY", Replay(FLEET, speed=math.inf, managed=True))
        for module, names in [
            (server.events, ["_db", "read", "emit", "reset"]),
            (server.snapshot, ["save", "load"]),
            (server.engine_handoff, ["create", "pr_opened", "token_ok"]),
            (server.jobs, ["start", "shutdown", "submit", "running"]),
            (server.sandbox, ["detonate"]),
            (server.subprocess, ["Popen"]),
            (boto3, ["client"]),
            (server, ["restore", "_reset_live", "_stop_demo_agents"]),
        ]:
            for name in names:
                patch.setattr(module, name, forbidden)
        with TestClient(server.app) as client:
            yield client
        assert not server.events.DB_PATH.exists()
        assert not server.snapshot.SNAP_DIR.exists()
        assert not server.engine_handoff.TOKENS.exists()


def incident(api):
    response = api.get("/incidents/inc_001")
    assert response.status_code == 200
    return response.json()


def post(api, action):
    return api.post(f"/incidents/inc_001/{action}", json=HUMAN)


def test_managed_boot_flag_is_opt_in(monkeypatch):
    monkeypatch.setenv("MIRAGE_MODE", "replay")
    monkeypatch.setattr("engine.config.MODE", "replay")
    monkeypatch.setenv("MIRAGE_FIXTURE", str(FLEET))
    monkeypatch.setenv("MIRAGE_REPLAY_SPEED", "inf")
    monkeypatch.delenv("MIRAGE_REPLAY_MANAGED", raising=False)
    assert not runpy.run_path(server.__file__)["REPLAY"].managed
    monkeypatch.setenv("MIRAGE_REPLAY_MANAGED", "1")
    assert runpy.run_path(server.__file__)["REPLAY"].managed
    monkeypatch.delenv("MIRAGE_FIXTURE")
    default = runpy.run_path(server.__file__)["REPLAY"]
    assert {r.agent for r in default.state()[0].values()} == {
        "meeting_assistant", "outreach", "support", "pr_reviewer"}


def test_auto_baseline_three_runs_and_recorded_services(api):
    inc = incident(api)
    assert inc["status"] == "confirmed" and inc["next_action"] == "find_cause"
    Verdict.model_validate(inc["verdict"])
    assert inc["verdict"]["confirmed"] and inc["verdict"]["compromised_runs"] == "3/3"
    runs = {r["agent"]: r for r in api.get("/runs").json()}
    assert set(runs) == {"meeting_assistant", "outreach", "support", "pr_reviewer"}
    assert runs["meeting_assistant"]["status"] == "frozen"
    assert all(r["status"] == "completed" for key, r in runs.items() if key != "meeting_assistant")
    ledger = api.get("/events").json()
    start = next(e for e in ledger if e["type"] == "detonation.started")
    assert start["payload"]["n_runs"] == 3
    done = next(e for e in ledger if e["type"] == "detonation.completed")
    assert Detonation.model_validate(done["payload"]).compromised_runs == 3
    assert {e["payload"]["run_index"] for e in ledger if e["type"] == "detonation.effect"} == {1, 2, 3}
    assert not any(e["type"] == "human.action" for e in ledger)
    prod = api.get("/services/outbox").json()["items"]
    assert len([e for e in prod if e["flag"] == "normal"]) == 2
    assert len([e for e in prod if e["flag"] == "blocked"]) == 1
    mirage = api.get("/services/outbox?env=mirage").json()["items"]
    assert len([e for e in mirage if e["flag"] == "malicious"]) == 3
    assert api.get("/services/calendar").json()["items"]
    assert api.get("/services/crm").json()["items"]
    policies = api.get("/policies").json()
    assert set(policies["agents"]) == set(runs)
    assert all(not spec["entrypoint"] for spec in policies["agents"].values())


def test_human_stages_and_wait_false_cursor_are_mcp_compatible(api):
    cursor = api.get("/events").json()[-1]["seq"]
    assert post(api, "bisect").json() == {"incident_id": "inc_001", "status": "bisecting"}
    completed = api.get(f"/events?after={cursor}").json()
    assert completed[-1]["type"] == "bisection.completed"
    inc = incident(api)
    assert inc["cause_input_id"] == "in_cal_03" and inc["next_action"] == "send_fix"
    assert [r["is_cause"] for r in inc["bisection"]].count(True) == 1
    assert any(e["flag"] == "malicious" for e in api.get("/services/calendar").json()["items"])
    handoff = post(api, "handoff").json()
    assert "Recorded demo only" in handoff["prompt"]
    assert "no usable live snapshot" in handoff["prompt"]
    assert "No fix has been written" in handoff["prompt"]
    assert "mirage_token" not in handoff and "report" not in handoff
    assert handoff["codex_url"] and handoff["claude_code_url"]
    assert incident(api)["status"] == "fix_pending"
    cursor = api.get("/events").json()[-1]["seq"]
    assert post(api, "verify").json() == {"incident_id": "inc_001", "status": "verifying"}
    finished = api.get(f"/events?after={cursor}").json()
    verified = next(e for e in finished if e["type"] == "fix.verified")
    assert DetonateResult.model_validate(verified["payload"]).passed
    assert incident(api)["status"] == "fix_verified" and not incident(api)["pr_url"]
    assert api.post("/incidents/inc_001/pr", json={"url": PR}).json()["url"] == PR
    assert incident(api)["status"] == "pr_open" and incident(api)["pr_url"] == PR
    assert api.get("/runs/run_002").json()["status"] == "frozen"
    ledger = api.get("/events").json()
    assert [e["seq"] for e in ledger] == list(range(1, len(ledger) + 1))
    audits = [HumanAction.model_validate(e["payload"]) for e in ledger if e["type"] == "human.action"]
    assert [a.action for a in audits] == ["find_cause", "handoff", "verify"]
    assert all(a.actor == HUMAN["actor"] and a.reason == HUMAN["reason"] for a in audits)


def test_bad_actions_and_controls_do_not_advance_or_write(api):
    before = api.get("/events").json()
    for action in ["detonate", "handoff", "verify"]:
        assert post(api, action).status_code == 409
    for action in ["freeze", "unfreeze", "kill", "resume", "restart"]:
        response = api.post(f"/runs/run_002/{action}", json=HUMAN)
        assert response.status_code == 409
        if action == "unfreeze":
            assert "confirmed this run is compromised" in response.json()["detail"]
    assert api.post("/resume-all", json=HUMAN).status_code == 409
    assert api.post("/incidents/inc_001/pr", json={"url": PR}).status_code == 409
    assert api.post("/incidents/inc_missing/bisect", json=HUMAN).status_code == 404
    assert api.post("/runs/missing/kill", json=HUMAN).status_code == 404
    assert api.post("/approvals/missing/approve", json=HUMAN).status_code == 404
    assert api.post("/runs", json={"agent": "support", "task": "x"}).status_code == 409
    assert api.post("/incidents/inc_001/bisect?runs=5", json=HUMAN).status_code == 409
    assert api.get("/events").json() == before
    assert post(api, "bisect").status_code == 200
    after = api.get("/events").json()
    assert post(api, "bisect").status_code == 409
    assert api.get("/events").json() == after
    post(api, "handoff")
    before = api.get("/events").json()
    assert api.post("/incidents/inc_001/verify?runs=0", json=HUMAN).status_code == 409
    assert api.get("/events").json() == before
    post(api, "verify")
    before = api.get("/events").json()
    assert api.post("/incidents/inc_001/pr", json={"url": "https://github.com/GabDestal/Mirage/pull/42"}).status_code == 409
    assert api.get("/events").json() == before
    assert api.post("/incidents/inc_001/pr", json={"url": PR}).status_code == 200
    assert api.post("/incidents/inc_001/pr", json={"url": PR}).status_code == 409


@pytest.mark.parametrize("resume_path", ["/stop/lift", "/resume-all"])
def test_timed_auto_baseline_and_stop_preserve_position(api, monkeypatch, resume_path):
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(replay, "time", SimpleNamespace(monotonic=lambda: clock.now))
    server.REPLAY.speed = 1
    server.REPLAY.restart()
    clock.now += 23
    assert incident(api)["status"] == "open"
    assert post(api, "bisect").status_code == 409
    clock.now += 18
    assert incident(api)["status"] == "detonating"
    assert "running" in api.post("/runs/run_002/unfreeze", json=HUMAN).json()["detail"]
    assert api.post("/stop", json=HUMAN).status_code == 200
    paused = api.get("/events").json()
    assert all(r["status"] == "halted" for r in api.get("/runs").json())
    evidence = incident(api)
    clock.now += 100
    assert api.get("/events").json() == paused
    assert post(api, "bisect").status_code == 409
    assert api.post("/stop", json=HUMAN).status_code == 409
    resume_human = {"actor": "Gabi via dashboard", "reason": "Continue recorded proof"}
    response = api.post(resume_path, json=resume_human)
    assert response.status_code == (200 if resume_path == "/resume-all" else 204)
    if resume_path == "/resume-all":
        assert response.json() == {"resumed": [], "skipped": []}
    assert incident(api) == evidence
    assert incident(api)["status"] == "detonating"
    assert api.get("/runs/run_002").json()["status"] == "frozen"
    assert all(r["status"] == "running" for r in api.get("/runs").json()
               if r["id"] != "run_002")
    resumed = api.get("/events").json()
    assert resumed[:len(paused)] == paused
    assert api.post(resume_path, json=resume_human).status_code == 409
    assert api.get("/events").json() == resumed
    clock.now += 20
    assert incident(api)["status"] == "confirmed"
    cursor = api.get("/events").json()[-1]["seq"]
    assert post(api, "bisect").status_code == 200
    assert post(api, "handoff").status_code == 409
    clock.now += 30
    follow = api.get(f"/events?after={cursor}").json()
    assert follow[-1]["type"] == "bisection.completed"
    assert post(api, "handoff").status_code == 200
    assert post(api, "verify").status_code == 200
    assert incident(api)["status"] == "fix_pending"
    clock.now += 21
    assert incident(api)["status"] == "fix_verified"
    audits = [e["payload"] for e in api.get("/events").json() if e["type"] == "human.action"]
    assert [a["action"] for a in audits][:2] == ["global_stop", "lift_stop"]
    assert {key: audits[1][key] for key in ("actor", "reason")} == resume_human
    assert all(a["actor"] == HUMAN["actor"] and a["reason"] == HUMAN["reason"]
               for a in [audits[0], *audits[2:]])
    assert api.post("/stop/lift", json=HUMAN).status_code == 409


def test_healthy_runs_continue_during_baseline_with_contiguous_cursor(api, monkeypatch):
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(replay, "time", SimpleNamespace(monotonic=lambda: clock.now))
    server.REPLAY.speed = 1
    server.REPLAY.restart()
    cursor = 0
    ledger = []
    for elapsed in [22.5, 41, 45, 54, 59]:
        clock.now = 1000.0 + elapsed
        follow = api.get(f"/events?after={cursor}").json()
        assert follow
        assert [e["seq"] for e in follow] == list(range(cursor + 1, follow[-1]["seq"] + 1))
        ledger.extend(follow)
        cursor = follow[-1]["seq"]
        runs = {r["id"]: r for r in api.get("/runs").json()}
        assert runs["run_002"]["agent"] == "meeting_assistant"
        assert runs["run_002"]["status"] == "frozen"
        assert {key: runs[key]["agent"] for key in ("run_001", "run_003", "run_004")} == {
            "run_001": "outreach", "run_003": "support", "run_004": "pr_reviewer"}
        assert all(runs[key]["status"] == ("running" if elapsed < 54 else "completed")
                   for key in ("run_001", "run_003", "run_004"))
        assert incident(api)["status"] == ("open" if elapsed < 40 else
                                           "detonating" if elapsed < 59 else "confirmed")
    assert api.get("/events").json() == ledger
    timestamps = [datetime.fromisoformat(e["ts"]) for e in ledger]
    assert timestamps == sorted(timestamps)
    baseline = next(e["seq"] for e in ledger if e["type"] == "detonation.started")
    verdict = next(e["seq"] for e in ledger if e["type"] == "verdict.ready")
    for run_id, tool in [("run_001", "send_email"), ("run_003", "send_email"),
                         ("run_004", "submit_review")]:
        progress = [e for e in ledger if e["run_id"] == run_id and baseline < e["seq"] < verdict]
        assert [e["type"] for e in progress] == [
            "tool.requested", "gate.decision", "tool.result", "agent.message", "run.status"]
        assert all(e["payload"]["tool"] == tool for e in progress[:3])
        assert progress[-1]["payload"]["to"] == "completed"


def test_existing_wrong_incident_and_concurrent_actions(api, tmp_path):
    fixture = [json.loads(line) for line in FLEET.read_text().splitlines()]
    opened = next(e for e in fixture if e["type"] == "incident.opened")
    other = json.loads(json.dumps(opened))
    other["incident_id"] = other["payload"]["incident_id"] = "inc_other"
    fixture.insert(fixture.index(opened) + 1, other)
    path = tmp_path / "two-incidents.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in fixture))
    server.REPLAY = Replay(path, speed=math.inf, managed=True)
    before = api.get("/events").json()
    assert api.post("/incidents/inc_other/bisect", json=HUMAN).status_code == 409
    assert api.get("/events").json() == before
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: post(api, "bisect").status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert len([e for e in api.get("/events").json() if e["type"] == "human.action"]) == 1


def test_reset_restores_recording_and_clears_decisions(api):
    before = api.get("/events").json()
    post(api, "bisect")
    post(api, "handoff")
    assert api.post("/demo/start", json={"scenario": "support"}).status_code == 409
    assert incident(api)["status"] == "fix_pending"
    api.post("/stop", json=HUMAN)
    assert api.post("/demo/reset").status_code == 204
    assert api.get("/events").json() == before
    assert incident(api)["status"] == "confirmed"
    post(api, "bisect")
    assert api.post("/demo/start", json={"scenario": "calendar"}).status_code == 204
    assert api.get("/events").json() == before


def test_fleet_fixture_typed_payloads_and_no_scripted_kill():
    typed = {"detonation.effect": Effect, "detonation.completed": Detonation,
             "verdict.ready": Verdict, "fix.verified": DetonateResult, "human.action": HumanAction}
    events = [Event.model_validate_json(line) for line in FLEET.read_text().splitlines()]
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert [e.ts for e in events] == sorted(e.ts for e in events)
    for event in events:
        if event.type in typed:
            typed[event.type].model_validate(event.payload)
        assert not (event.type == "run.status" and event.payload["to"] == "killed")


def test_legacy_replay_pr_never_reaches_live_store(api):
    server.REPLAY = Replay(server.FIXTURES / "sample_demo.jsonl", speed=math.inf)
    before = api.get("/events").json()
    assert api.post("/incidents/inc_001/pr", json={"url": PR}).status_code == 409
    assert api.get("/events").json() == before
