"""An admitted run keeps its policy when the next SDK factory registers by the same name."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from contracts.models import AgentSpec
from engine.api import server
from engine.detonation import sandbox, snapshot
from engine.gateway import gate

USER = "user@policy-demo.example"
ATTACKER = "attacker@policy-attacker.example"
AGENT = {
    "name": "policy_assistant", "owner": "synthetic-owner",
    "tools": ["read_calendar", "send_email", "upload_records", "export_contacts"],
    "allow": {"tools": ["read_calendar", "send_email", "upload_records"],
              "email_to": [USER], "url_hosts": ["policy-demo.example"]},
    "entrypoint": "tests.sandbox_agents:attacker",
}
HUMAN = {"actor": "synthetic-operator", "reason": "Policy authority regression"}
CALLS = [
    pytest.param("send_email", {"to": ATTACKER}, "DEST_NOT_ALLOWED", id="email"),
    pytest.param("upload_records", {"url": "https://policy-attacker.example/rows"},
                 "DEST_NOT_ALLOWED", id="url"),
    pytest.param("export_contacts", {}, "TOOL_NOT_ALLOWED", id="tool"),
]


@pytest.fixture
def api(monkeypatch):
    gate.reset()
    monkeypatch.setattr(gate.decision_model, "judge", lambda *_: None)
    client = TestClient(server.app)
    assert client.post("/agents", json=AGENT).status_code == 200
    yield client
    client.close()
    gate.reset()


def start(api):
    response = api.post("/runs", json={"agent": AGENT["name"], "task": "Prepare a brief"})
    assert response.status_code == 200
    body = response.json()
    return body["run_id"], {"Authorization": f"Bearer {body['run_token']}"}


def check(api, run_id, auth, tool, args):
    response = api.post("/gateway/check", headers=auth,
                        json={"run_id": run_id, "tool": tool, "args": args})
    assert response.status_code == 200
    return response.json()


def widen(spec):
    spec.allow.tools.append("export_contacts")
    spec.allow.email_to.append(ATTACKER)
    spec.allow.url_hosts.append("policy-attacker.example")


def wider_registration():
    spec = AgentSpec.model_validate(AGENT)
    widen(spec)
    return spec.model_dump(mode="json")


@pytest.mark.parametrize("tool,args,rule", CALLS)
def test_same_name_registration_cannot_loosen_an_active_run(api, tool, args, rule):
    original = copy.deepcopy(gate.policy_for(AGENT["name"]))
    old_id, old_auth = start(api)
    replacement = wider_registration()
    replacement["owner"] = "different-synthetic-owner"
    # Registration is trusted-local and has no token; run checks still need the old token.
    assert api.post("/agents", json=replacement).status_code == 200
    new_id, new_auth = start(api)
    assert check(api, new_id, new_auth, tool, args)["decision"] == "allow"
    decision = check(api, old_id, old_auth, tool, args)
    assert (decision["decision"], decision["rule_id"]) == ("freeze", rule)
    assert snapshot.load(gate.runs[old_id].incident_id)["policy"] == original


@pytest.mark.parametrize("tool,args,rule", CALLS)
def test_in_place_registration_lists_do_not_mutate_admitted_policy(api, tool, args, rule):
    original = copy.deepcopy(gate.policy_for(AGENT["name"]))
    run_id, auth = start(api)
    widen(gate.agents[AGENT["name"]])
    decision = check(api, run_id, auth, tool, args)
    assert (decision["decision"], decision["rule_id"]) == ("freeze", rule)
    assert snapshot.load(gate.runs[run_id].incident_id)["policy"] == original


@pytest.mark.parametrize("field,tool,args", [
    ("email_to", "send_email", {"to": USER}),
    ("url_hosts", "upload_records", {"url": "https://policy-demo.example/brief"}),
    ("tools", "read_calendar", {}),
])
def test_tightening_registration_applies_to_future_runs_only(api, field, tool, args):
    old_id, old_auth = start(api)
    replacement = copy.deepcopy(AGENT)
    replacement["allow"][field] = []
    assert api.post("/agents", json=replacement).status_code == 200
    new_id, new_auth = start(api)
    assert check(api, new_id, new_auth, tool, args)["decision"] == "freeze"
    assert check(api, old_id, old_auth, tool, args)["decision"] == "allow"


def test_removing_declared_tool_cannot_turn_a_denial_into_unknown_tool_allow(api):
    run_id, auth = start(api)
    spec = copy.deepcopy(AGENT)
    spec["tools"].remove("export_contacts")
    assert api.post("/agents", json=spec).status_code == 200
    decision = check(api, run_id, auth, "export_contacts", {})
    assert (decision["decision"], decision["rule_id"]) == ("freeze", "TOOL_NOT_ALLOWED")
    assert "export_contacts" in snapshot.load(gate.runs[run_id].incident_id)["policy"]["known_tools"]


def test_sdk_reregistration_changes_future_runs_only(api, monkeypatch):
    from mirage import core

    def request(req):
        response = api.request(req.method, req.url.path, content=req.content, headers=dict(req.headers))
        return httpx.Response(response.status_code, content=response.content)

    spec = copy.deepcopy(AGENT)
    with httpx.Client(base_url="http://synthetic-engine", transport=httpx.MockTransport(request)) as client:
        monkeypatch.setattr(core, "_http", client)
        core.register(spec["name"], spec["tools"], spec["allow"], spec["entrypoint"])
        old = core.open_run(spec["name"], "Prepare a brief")
        spec["allow"]["email_to"].append(ATTACKER)
        core.register(spec["name"], spec["tools"], spec["allow"], spec["entrypoint"])
        new = core.open_run(spec["name"], "Prepare a brief")
    old_auth = {"Authorization": f"Bearer {old['token']}"}
    new_auth = {"Authorization": f"Bearer {new['token']}"}
    assert check(api, new["id"], new_auth, "send_email", {"to": ATTACKER})["decision"] == "allow"
    assert check(api, old["id"], old_auth, "send_email", {"to": ATTACKER})["decision"] == "freeze"


def test_same_name_factory_replacement_keeps_admitted_snapshot_metadata(api):
    admitted = copy.deepcopy(AGENT)
    admitted["legit"] = {"tool": "send_email", "to": USER}
    assert api.post("/agents", json=admitted).status_code == 200
    run_id, auth = start(api)
    replacement = copy.deepcopy(admitted)
    replacement["entrypoint"] = "tests.sandbox_agents:ignores_invite"
    replacement["legit"]["to"] = ATTACKER
    assert api.post("/agents", json=replacement).status_code == 200
    assert check(api, run_id, auth, "send_email", {"to": ATTACKER})["decision"] == "freeze"
    snap = snapshot.load(gate.runs[run_id].incident_id)
    assert (snap["entrypoint"], snap["legit"]) == (admitted["entrypoint"], admitted["legit"])


@pytest.mark.parametrize("mutation", ["replace", "in_place"])
def test_slow_model_freeze_saves_admitted_policy_and_keeps_other_runs_working(
        api, monkeypatch, mutation):
    original = copy.deepcopy(gate.policy_for(AGENT["name"]))
    run_id, auth = start(api)
    healthy_id, healthy_auth = start(api)
    entered, release = threading.Event(), threading.Event()

    def judge(_agent, _task, _tool, args):
        if args.get("body") != "hold-model":
            return None
        entered.set()
        assert release.wait(5)
        return {"policy_id": "P6", "p": 1.0, "review": False,
                "explanation": "Synthetic model freeze"}

    monkeypatch.setattr(gate.decision_model, "judge", judge)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(check, api, run_id, auth, "send_email",
                              {"to": USER, "body": "hold-model"})
        try:
            assert entered.wait(5)
            if mutation == "replace":
                assert api.post("/agents", json=wider_registration()).status_code == 200
            else:
                widen(gate.agents[AGENT["name"]])
            assert check(api, healthy_id, healthy_auth, "read_calendar", {})["decision"] == "allow"
        finally:
            release.set()
        assert pending.result(timeout=5)["decision"] == "freeze"
    assert snapshot.load(gate.runs[run_id].incident_id)["policy"] == original
    assert api.post(f"/runs/{run_id}/unfreeze", json=HUMAN).status_code == 200
    assert check(api, run_id, auth, "send_email", {"to": ATTACKER})["decision"] == "freeze"


def test_registration_after_freeze_does_not_change_saved_replay_policy(api):
    run_id, auth = start(api)
    assert check(api, run_id, auth, "send_email", {"to": ATTACKER})["decision"] == "freeze"
    incident_id = gate.runs[run_id].incident_id
    original = snapshot.load(incident_id)
    assert api.post("/agents", json=wider_registration()).status_code == 200
    assert snapshot.load(incident_id) == original
    effect = {"tool": "send_email", "args": {"to": ATTACKER}}
    current = sandbox.current_policy(AGENT["name"])
    assert sandbox.violations(original, effect, [current]) == []
    assert sandbox.violations(original, effect, [original["policy"], current]) == ["P1", "P5"]


def test_current_verifier_can_tighten_policy_without_rewriting_the_original(api):
    run_id, auth = start(api)
    assert check(api, run_id, auth, "send_email", {"to": ATTACKER})["decision"] == "freeze"
    snap = snapshot.load(gate.runs[run_id].incident_id)
    current = copy.deepcopy(AGENT)
    current["allow"]["email_to"] = []
    assert api.post("/agents", json=current).status_code == 200
    effect = {"tool": "send_email", "args": {"to": USER}}
    assert sandbox.violations(snap, effect, [snap["policy"]]) == []
    assert sandbox.violations(snap, effect, [snap["policy"], sandbox.current_policy(AGENT["name"])]) == ["P1", "P5"]


def test_approved_restart_pins_policy_before_queued_sdk_takeover(api):
    old_id, _ = start(api)
    assert api.post(f"/runs/{old_id}/kill", json=HUMAN).status_code == 200
    queued = api.post(f"/runs/{old_id}/restart", json=HUMAN)
    assert queued.status_code == 200
    original = copy.deepcopy(gate.policy_for(AGENT["name"]))
    assert api.post("/agents", json=wider_registration()).status_code == 200
    body = {"agent": AGENT["name"], "task": "Prepare a brief", "restarted_from": old_id}
    assert api.post("/runs", json=body).status_code == 409
    assert api.get(f"/runs/{queued.json()['id']}").json()["status"] == "queued"
    assert api.post("/agents", json=AGENT).status_code == 200
    accepted = api.post("/runs", json=body)
    assert accepted.status_code == 200
    run_id = accepted.json()["run_id"]
    auth = {"Authorization": f"Bearer {accepted.json()['run_token']}"}
    assert run_id == queued.json()["id"]
    assert check(api, run_id, auth, "send_email", {"to": ATTACKER})["decision"] == "freeze"
    assert snapshot.load(gate.runs[run_id].incident_id)["policy"] == original


def test_a_human_restart_can_admit_current_policy_for_a_new_run(api):
    old_id, old_auth = start(api)
    assert api.post(f"/runs/{old_id}/kill", json=HUMAN).status_code == 200
    assert api.post("/agents", json=wider_registration()).status_code == 200
    assert api.post(f"/runs/{old_id}/restart", json=HUMAN).status_code == 200
    new_id, new_auth = start(api)
    assert new_id != old_id
    assert check(api, new_id, new_auth, "send_email", {"to": ATTACKER})["decision"] == "allow"
    assert check(api, old_id, old_auth, "send_email", {"to": ATTACKER})["decision"] == "block"


def test_dev_policy_fallback_is_copied_when_the_run_is_created(monkeypatch):
    gate.reset()
    original = copy.deepcopy(gate.POLICY)
    policy = copy.deepcopy(original)
    monkeypatch.setattr(gate, "POLICY", policy)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *_: None)
    run = gate.LiveRun(id="run_dev_policy", agent="assistant", task="Prepare a brief", status="running")
    gate.runs[run.id] = run
    policy["destinations"]["email_domains"].append(ATTACKER)
    decision = gate.check(run, "send_email", {"to": ATTACKER})
    assert (decision.decision, decision.rule_id) == ("freeze", "DEST_NOT_ALLOWED")
    assert snapshot.load(run.incident_id)["policy"] == original


def test_replacement_registration_does_not_grant_the_old_run_token(api):
    run_id, _ = start(api)
    assert api.post("/agents", json=wider_registration()).status_code == 200
    response = api.post("/gateway/check", headers={"Authorization": "Bearer synthetic-wrong"},
                        json={"run_id": run_id, "tool": "send_email", "args": {"to": ATTACKER}})
    assert response.status_code == 401
