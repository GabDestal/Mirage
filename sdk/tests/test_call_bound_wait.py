"""Held demo callbacks need their own human grant, through the real HTTP data plane."""

import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import mirage
import pytest
import test_langgraph as langgraph
import test_openai_agents as openai
from fastapi.testclient import TestClient
from mirage import core

from engine.api import server
from engine.gateway import gate
from engine.store import events

HUMAN = {"actor": "synthetic-human", "reason": "Synthetic call authority test"}


@pytest.fixture
def api(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("These synthetic tests must not connect to a provider")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(core, "_sandbox", None)
    monkeypatch.setattr(gate.decision_model, "judge", lambda *args: {
        "review": True, "policy_id": "P5", "p": 0.5, "explanation": "Synthetic review"})
    gate.reset()
    with TestClient(server.app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(core, "_http", client)
        yield client
    gate.reset()


@pytest.fixture(params=["langgraph-invoke", "langgraph-stream", "openai"])
def demo(request, api):
    """Reuse the installed-framework scripted models and public protect builders."""
    mode = request.param
    if mode == "openai":
        demo_modules = openai._pop_agents()
        openai.sys.modules.update(openai._openai)
        openai.sent.clear()
        agent = openai.build(openai.call("send_email", to=openai.USER, body="Synthetic brief"),
                             openai.say("done"))
        effects = openai.sent
    else:
        langgraph.sent.clear()
        agent = langgraph.build(langgraph.call("send_email", to=langgraph.USER,
                                              body="Synthetic brief"), langgraph.AIMessage("done"))
        task = {"messages": [("user", "Prep my meetings")]}
        effects = langgraph.sent

    def invoke():
        if mode == "openai":
            return openai.Runner.run_sync(agent, "Prep my meetings")
        if mode == "langgraph-invoke":
            return agent.invoke(task)
        return list(agent.stream(task))
    yield invoke, effects, mode
    if mode == "openai":
        openai._openai.update(openai._pop_agents())
        openai.sys.modules.update(demo_modules)


@pytest.fixture
def held(demo, api, monkeypatch):
    invoke, effects, mode = demo
    entered, release = threading.Event(), threading.Event()
    original_wait = core._wait
    polls = []
    original_get = core._http.get

    def observed_get(path, **kwargs):
        if path.endswith("/wait"):
            polls.append(dict(kwargs["params"]))
        return original_get(path, **kwargs)

    def delayed_wait(run, *args, **kwargs):
        entered.set()
        assert release.wait(5), "The synthetic human did not finish the control action"
        return original_wait(run, *args, **kwargs)

    monkeypatch.setattr(core._http, "get", observed_get)
    monkeypatch.setattr(core, "_wait", delayed_wait)
    with ThreadPoolExecutor(max_workers=1) as pool:
        run = None
        result = pool.submit(invoke)
        try:
            assert entered.wait(3)
            (run,) = gate.runs.values()
            (approval,) = api.get("/approvals").json()
            assert run.status == "frozen" and effects == []
            yield run, approval["call_id"], result, release, effects, polls, mode
        finally:
            if run is not None and run.status in ("frozen", "running"):
                api.post(f"/runs/{run.id}/kill", json=HUMAN)
            release.set()
            result.exception(timeout=5)


def denied(result, mode):
    error = result.exception(timeout=3)
    if mode == "openai":
        assert isinstance(error, openai.UserError)
        error = error.__cause__
    assert isinstance(error, mirage.Blocked)
    assert "Synthetic" not in str(error)  # no server error body in the public denial


@pytest.mark.parametrize("action", ["approve", "unfreeze"])
def test_exact_human_grant_executes_the_original_callback_once(held, api, action):
    run, call_id, result, release, effects, polls, _ = held
    path = (f"/approvals/{call_id}/approve" if action == "approve" else
            f"/runs/{run.id}/unfreeze")
    assert api.post(path, json=HUMAN).status_code == 200
    assert effects == []  # approval still precedes the real callback
    release.set()
    error = result.exception(timeout=3)
    assert effects == [langgraph.USER] and run.status == "completed"
    assert error is None
    assert polls == [{"timeout": 60, "call_id": call_id}]
    assert len(run.tool_results) == 1
    assert run.tool_results[0]["call_id"] == call_id
    assert len([e for e in events.read() if e.type == "tool.result"]) == 1
    assert api.get(f"/runs/{run.id}/wait", headers={"Authorization": f"Bearer {run.token}"},
                   params={"timeout": 0, "call_id": call_id}).status_code == 409


@pytest.mark.parametrize("action", ["reject", "kill", "stop", "freeze", "stale-grant"])
def test_containment_and_later_freeze_generation_never_release_callback(held, api, action):
    run, call_id, result, release, effects, polls, mode = held
    if action in ("freeze", "stale-grant"):
        assert api.post(f"/approvals/{call_id}/approve", json=HUMAN).status_code == 200
        assert api.post(f"/runs/{run.id}/freeze", json=HUMAN).status_code == 200
        if action == "stale-grant":
            assert api.post(f"/runs/{run.id}/unfreeze", json=HUMAN).status_code == 200
    else:
        path = (f"/approvals/{call_id}/reject" if action == "reject" else
                "/stop" if action == "stop" else f"/runs/{run.id}/kill")
        assert api.post(path, json=HUMAN).status_code == 200
    release.set()
    result.exception(timeout=3)
    assert effects == [] and run.tool_results == []
    denied(result, mode)
    assert polls == [{"timeout": 60, "call_id": call_id}]
    expected = {"reject": "killed", "kill": "killed", "stop": "halted", "freeze": "frozen",
                "stale-grant": "running" if mode == "openai" else "failed"}[action]
    assert run.status == expected


def test_sibling_approval_never_releases_the_original_callback(held, api):
    run, call_id, result, release, effects, _, mode = held
    sibling = api.post("/runs", json={"agent": run.agent, "task": "Synthetic sibling"}).json()
    auth = {"Authorization": f"Bearer {sibling['run_token']}"}
    other = api.post("/gateway/check", headers=auth, json={
        "run_id": sibling["run_id"], "tool": "send_email",
        "args": {"to": langgraph.USER, "body": "Synthetic sibling"}}).json()
    assert other["decision"] == "freeze" and other["call_id"] != call_id
    assert api.post(f"/approvals/{other['call_id']}/approve", json=HUMAN).status_code == 200
    assert run.status == "frozen" and effects == []
    assert api.get(f"/runs/{run.id}/wait", headers={"Authorization": f"Bearer {run.token}"},
                   params={"timeout": 0, "call_id": call_id}).json() == {"status": "frozen"}
    assert api.post(f"/runs/{run.id}/kill", json=HUMAN).status_code == 200
    release.set()
    denied(result, mode)
    assert effects == [] and run.tool_results == [] and run.status == "killed"


@pytest.mark.parametrize("identity", ["unknown", "other-run", "consumed"])
def test_invalid_bound_wait_is_a_safe_denial_before_callback(held, api, monkeypatch, identity):
    run, call_id, result, release, effects, _, mode = held
    assert api.post(f"/approvals/{call_id}/approve", json=HUMAN).status_code == 200
    if identity == "consumed":
        auth = {"Authorization": f"Bearer {run.token}"}
        assert api.get(f"/runs/{run.id}/wait", headers=auth,
                       params={"timeout": 0, "call_id": call_id}).json() == {"status": "running"}
        assert api.post(f"/runs/{run.id}/tool-results", headers=auth, json={
            "call_id": call_id, "tool": "send_email", "result": {"status": "synthetic prior result"}
        }).status_code == 204
    else:
        wrong_id = "call_missing"
        if identity == "other-run":
            sibling = api.post("/runs", json={"agent": run.agent, "task": "Synthetic sibling"}).json()
            wrong_id = api.post("/gateway/check", headers={
                "Authorization": f"Bearer {sibling['run_token']}"}, json={
                    "run_id": sibling["run_id"], "tool": "read_calendar", "args": {}}
            ).json()["call_id"]
        original_get = core._http.get

        def wrong_identity(path, **kwargs):
            if path.endswith("/wait"):
                kwargs["params"] = {**kwargs["params"], "call_id": wrong_id}
            return original_get(path, **kwargs)

        monkeypatch.setattr(core._http, "get", wrong_identity)
    release.set()
    result.exception(timeout=3)
    assert effects == []
    denied(result, mode)
    assert len(run.tool_results) == (1 if identity == "consumed" else 0)


def test_unbound_running_status_cannot_grant_a_held_callback(monkeypatch):
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"status": "running"})),
            base_url="http://synthetic.invalid") as client:
        monkeypatch.setattr(core, "_http", client)
        with pytest.raises(mirage.Blocked, match="call_id"):
            core._wait({"id": "synthetic-run", "token": "synthetic-token"})


def test_bound_conflict_is_safe_and_never_retried(monkeypatch):
    requests = []

    def conflict(request):
        requests.append(request)
        return httpx.Response(409, json={"detail": "Synthetic private server error"})

    with httpx.Client(transport=httpx.MockTransport(conflict),
                      base_url="http://synthetic.invalid") as client:
        monkeypatch.setattr(core, "_http", client)
        with pytest.raises(mirage.Blocked, match="no longer authorized") as blocked:
            core._wait({"id": "synthetic-run", "token": "synthetic-token"}, "original-call")
    assert "private" not in str(blocked.value) and len(requests) == 1


def test_frozen_polls_keep_the_original_call_identity(monkeypatch):
    requests = []
    statuses = iter(["frozen", "frozen", "running"])

    def poll(request):
        requests.append(request)
        return httpx.Response(200, json={"status": next(statuses)})

    with httpx.Client(transport=httpx.MockTransport(poll),
                      base_url="http://synthetic.invalid") as client:
        monkeypatch.setattr(core, "_http", client)
        core._wait({"id": "synthetic-run", "token": "synthetic-token"}, "original-call")
    assert len(requests) == 3
    assert all(dict(r.url.params) == {"timeout": "60", "call_id": "original-call"}
               and r.headers["Authorization"] == "Bearer synthetic-token" for r in requests)
