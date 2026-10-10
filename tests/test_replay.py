"""Replay mode: the sample fixture is valid, and POST actions walk the demo through the API."""

import json
import math
import time

import pytest
from fastapi.testclient import TestClient

from contracts.models import (
    BisectionRow,
    Detonation,
    Effect,
    Event,
    GateDecision,
    HumanAction,
    Verdict,
)
from engine.api import server
from engine.api.replay import Replay
from engine.gateway import gate

SAMPLE = server.FIXTURES / "sample_demo.jsonl"
HUMAN = {"actor": "gabi", "reason": "test"}
TYPED = {"gate.decision": GateDecision, "detonation.effect": Effect,
         "detonation.completed": Detonation, "verdict.ready": Verdict,
         "bisection.step": BisectionRow, "human.action": HumanAction}


def test_sample_fixture_matches_the_contract():
    for line in SAMPLE.read_text(encoding="utf-8").splitlines():
        event = Event.model_validate_json(line)
        if event.type in TYPED:
            TYPED[event.type].model_validate(event.payload)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", Replay(SAMPLE, speed=math.inf))  # segments at once
    return TestClient(server.app)


def test_demo_walkthrough(api):
    runs = {r["id"]: r["status"] for r in api.get("/runs").json()}
    assert runs == {"run_001": "completed", "run_002": "frozen", "run_003": "completed"}
    assert api.get("/incidents/inc_001").json()["next_action"] == "detonate"

    assert api.post("/incidents/inc_001/detonate").json()["detonation_id"] == "det_001_a"
    inc = api.get("/incidents/inc_001").json()
    assert inc["verdict"]["compromised_runs"] == "3/3"
    assert inc["next_action"] == "find_cause"

    assert api.post("/runs/run_002/kill", json=HUMAN).json()["status"] == "killed"

    api.post("/incidents/inc_001/bisect")
    inc = api.get("/incidents/inc_001").json()
    assert inc["cause_input_id"] == "in_cal_03"
    assert [r["is_cause"] for r in inc["bisection"]].count(True) == 1
    assert inc["next_action"] == "send_fix"

    assert "prompt" in api.post("/incidents/inc_001/handoff").json()
    api.post("/incidents/inc_001/verify")
    inc = api.get("/incidents/inc_001").json()
    assert inc["status"] == "pr_open" and inc["pr_url"]
    assert api.post("/incidents/inc_001/verify").json() == {}  # demo is over

    seqs = [e["seq"] for e in api.get("/events").json()]
    assert seqs == list(range(1, len(seqs) + 1))  # every event, in order, no gaps


def test_real_timing_and_restart():
    replay = Replay(SAMPLE, speed=1)
    first = len(replay.visible())
    assert 0 < first < replay.starts[1]  # the freeze is ~22 s in: not shown yet
    replay.advance()  # an early human action shows the rest of the current segment first
    assert [e.seq for e in replay.visible()][: replay.starts[1]] == list(
        range(1, replay.starts[1] + 1))
    replay.restart()
    time.sleep(0.01)
    assert len(replay.visible()) == first


def test_data_plane_is_off_in_replay(api):
    r = api.post("/runs", json={"agent": "meeting_assistant", "task": "t"})
    assert r.status_code == 409
    assert api.post("/demo/reset").status_code == 204


def test_live_mode_says_what_is_not_built(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    client = TestClient(server.app)
    assert client.post("/demo/start", json={"scenario": "support"}).status_code == 501
    assert json.loads(client.get("/runs").text) == []


def test_a_recorded_live_run_needs_one_click_per_operator_step():
    from datetime import UTC, datetime

    from engine.api.replay import segment_starts

    shape = [  # what a live run writes: (type, payload)
        ("run.started", {"task": "t"}), ("gate.decision", {}), ("incident.opened", {}),
        ("detonation.started", {"purpose": "detonate"}), ("detonation.effect", {}),
        ("verdict.ready", {}),
        ("detonation.started", {"purpose": "detonate", "removed_input_id": "in_01"}),
        ("detonation.completed", {}), ("bisection.step", {}),
        ("detonation.started", {"purpose": "detonate", "removed_input_id": "in_02"}),
        ("bisection.step", {}), ("bisection.completed", {}),
        ("human.action", {"action": "handoff"}), ("handoff.created", {}),
        ("detonation.started", {"purpose": "verify"}), ("fix.verified", {}),
        ("pr.opened", {}), ("human.action", {"action": "kill"}), ("run.status", {}),
    ]
    events = [Event(seq=n, ts=datetime.now(UTC), env="prod", type=t, payload=p)
              for n, (t, p) in enumerate(shape, start=1)]
    steps = [events[i].type for i in segment_starts(events)]
    assert steps == ["run.started", "detonation.started", "detonation.started",  # detonate, bisect
                     "human.action", "detonation.started", "human.action"]  # handoff, verify, kill
