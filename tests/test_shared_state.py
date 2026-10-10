"""Several processes share one event log: seq stays unique, and the API sees everyone's runs."""

import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from engine.api import server
from engine.detection.rules import POLICY
from engine.detonation import snapshot
from engine.gateway import gate
from engine.store import events

REPO = Path(__file__).parents[1]
WRITER = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from engine.store import events
events.DB_PATH = Path(sys.argv[2])
for i in range(100):
    events.emit("agent.message", {"role": "assistant", "text": f"{sys.argv[3]} {i}"})
"""


def test_two_processes_never_share_a_seq():
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(REPO), str(events.DB_PATH), name])
             for name in ("a", "b")]
    assert [p.wait(60) for p in procs] == [0, 0]
    with closing(sqlite3.connect(events.DB_PATH)) as db:  # Windows locks open files
        rows = db.execute("SELECT seq, body, prev_hash, hash FROM events ORDER BY seq").fetchall()
    assert [r[0] for r in rows] == list(range(1, 201))
    prev = ""
    for _, body, prev_hash, digest in rows:  # the hash chain is intact
        assert prev_hash == prev
        assert digest == hashlib.sha256((prev + body).encode()).hexdigest()
        prev = digest


def test_api_sees_an_incident_frozen_by_another_process(monkeypatch):
    # what the dev runner (another process) leaves behind: events + a snapshot on disk
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    run = SimpleNamespace(
        id="run_009", agent="assistant", task="Prep", system="", model_id="",
        entrypoint="tests.sandbox_agents:clean",
        legit={"tool": "send_email", "to": "bob@northwind.example"},
        model_calls=[], tool_results=[])
    snapshot.save(run, "inc_009", POLICY)
    trigger = {"call_id": "call_9", "tool": "send_email", "args": {"to": "x@evil.com"},
               "decision": "freeze", "layer": "hard_rule", "rule_id": "DEST_NOT_ALLOWED",
               "explanation": "Domain evil.com is not on the allowlist."}
    events.emit("run.started", {"task": "Prep", "agent": "assistant"}, run_id="run_009")
    events.emit("gate.decision", trigger, run_id="run_009")
    events.emit("incident.opened", {"incident_id": "inc_009", "trigger_call_id": "call_9"},
                run_id="run_009", incident_id="inc_009")
    events.emit("run.status", {"from": "running", "to": "frozen", "actor": "gate",
                               "reason": "x"}, run_id="run_009", incident_id="inc_009")

    api = TestClient(server.app)
    assert api.get("/runs/run_009").json()["status"] == "frozen"
    assert api.get("/incidents/inc_009").json()["next_action"] == "detonate"
    r = api.post("/runs/run_009/unfreeze", json={"actor": "gabi", "reason": "t"})
    assert r.status_code == 409 and "another process" in r.json()["detail"]

    api.post("/incidents/inc_009/detonate?runs=1")
    for _ in range(100):
        incident = api.get("/incidents/inc_009").json()
        if incident["status"] in ("confirmed", "false_positive"):
            break
        time.sleep(0.1)
    assert incident["status"] == "false_positive"  # the clean agent did nothing wrong
    assert json.loads(api.get("/events").text)[-1]["type"] == "verdict.ready"
