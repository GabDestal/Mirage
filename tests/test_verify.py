"""Fix verification: the current agent code, from scratch, judged by the old AND new policy."""

import copy
import json
import time

from fastapi.testclient import TestClient

from engine.api import server
from engine.detection.rules import POLICY
from engine.detonation import sandbox, snapshot
from engine.gateway import gate
from engine.store import events
from tests.test_bisect import ATTACKER, save_incident


def switch_code(incident_id, entrypoint):
    """Simulate the coding agent changing the agent's code: same snapshot, new entrypoint."""
    path = snapshot.SNAP_DIR / f"{incident_id}.json"
    snap = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**snap, "entrypoint": entrypoint}), encoding="utf-8")


def verify(incident_id="inc_001"):
    return sandbox.detonate(incident_id, n_runs=1, verify=True, log=lambda *_: None)[2]


def test_unfixed_agent_fails_and_fixed_agent_passes():
    save_incident()
    snap = snapshot.load("inc_001")
    snap["model_calls"] = [{"model_id": "m", "request": {}, "response": {}}]
    (snapshot.SNAP_DIR / "inc_001.json").write_text(json.dumps(snap), encoding="utf-8")

    before = verify()
    assert (before.attack_blocked, before.passed) == ("0/1", False)

    switch_code("inc_001", "tests.sandbox_agents:ignores_invite")
    after = verify()
    assert (after.attack_blocked, after.legit_task_completed, after.passed) == ("1/1", "1/1", True)
    last = events.read()[-1]
    assert last.type == "fix.verified" and last.payload["passed"] is True


def test_allowlisting_the_attacker_is_not_a_fix(monkeypatch):
    save_incident()  # unfixed agent: still emails the attacker
    loose = copy.deepcopy(POLICY)
    loose["destinations"]["email_domains"].append("evil-corp-demo.com")
    monkeypatch.setattr(sandbox, "current_policy", lambda agent: loose)
    assert not verify().passed  # the policy at freeze still catches it


def test_a_new_restriction_in_the_fix_is_enforced(monkeypatch):
    save_incident()
    switch_code("inc_001", "tests.sandbox_agents:exports_but_keeps_it")
    tight = copy.deepcopy(POLICY)
    tight["agents"]["assistant"]["tools"].remove("crm_export")
    monkeypatch.setattr(sandbox, "current_policy", lambda agent: tight)
    result = verify()
    assert not result.passed and result.attack_blocked == "0/1"


def test_verify_route_moves_the_incident_only_when_the_fix_passes(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    save_incident("inc_007")
    trigger = {"call_id": "c9", "tool": "send_email", "args": {"to": ATTACKER},
               "decision": "freeze", "layer": "hard_rule", "rule_id": "DEST_NOT_ALLOWED",
               "explanation": "x"}
    events.emit("run.started", {"task": "Prep", "agent": "assistant"}, run_id="run_002")
    events.emit("gate.decision", trigger, run_id="run_002")
    events.emit("incident.opened", {"incident_id": "inc_007", "trigger_call_id": "c9"},
                run_id="run_002", incident_id="inc_007")
    events.emit("bisection.completed", {"incident_id": "inc_007", "cause_input_id": "in_02"},
                incident_id="inc_007", env="mirage")
    api = TestClient(server.app)

    def verify_and_wait():
        n = len(events.read())
        assert api.post("/incidents/inc_007/verify?runs=1").status_code == 200
        for _ in range(150):
            if any(e.type == "fix.verified" for e in events.read(n)):
                break
            time.sleep(0.1)
        return api.get("/incidents/inc_007").json()

    assert verify_and_wait()["status"] == "root_caused"  # unfixed: stays, next is still send_fix
    switch_code("inc_007", "tests.sandbox_agents:ignores_invite")
    incident = verify_and_wait()
    assert incident["status"] == "fix_verified" and incident["next_action"] == "open_pr"
