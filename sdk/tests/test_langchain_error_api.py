"""SDK failures reach the actual run/service API; isolated data and no network/provider."""

import socket

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from mirage import Blocked, core
from mirage.protect import registry

from agents.common.testing import call
from contracts.models import GateDecision
from engine.api.server import app
from engine.gateway import gate
from sdk.tests.test_langchain_errors import TASK, USER, build, sent


@pytest.fixture
def engine_client(isolated_data, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("No sockets in SDK API regression tests")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(core, "_sandbox", None)
    token = core._run.set(None)
    previous = registry.copy()
    gate.reset()
    sent.clear()
    with TestClient(app) as client:
        monkeypatch.setattr(core, "_http", client)
        yield client
    core._run.reset(token)
    registry.clear()
    registry.update(previous)


@pytest.mark.parametrize("method", ["invoke", "stream"])
def test_crashed_model_is_failed_in_the_run_api(engine_client, method):
    failure = RuntimeError("synthetic secret, exclude from status")
    graph = build(failure)
    with pytest.raises(RuntimeError) as caught:
        output = getattr(graph, method)(TASK)
        if method == "stream":
            list(output)
    assert caught.value is failure
    (run,) = engine_client.get("/runs").json()
    assert run["status"] == "failed"
    assert run["ended_at"] is not None
    assert "RuntimeError" in run["status_reason"]
    assert "synthetic secret" not in run["status_reason"]
    statuses = [e["payload"] for e in engine_client.get("/events").json()
                if e["type"] == "run.status" and e["payload"]["to"] in
                {"completed", "failed", "killed", "halted"}]
    assert len(statuses) == 1 and statuses[0]["to"] == "failed"


def test_handled_email_validation_error_never_appears_as_sent(engine_client):
    # Not "assistant": that canonical role also applies policies.yaml, which rejects USER's domain.
    graph = build(call("send_email", to=USER, body="Missing required subject"), AIMessage("handled"),
                  name="error-assistant", allow={"tools": ["send_email"], "email_to": [USER]})
    output = graph.invoke(TASK)
    assert output["messages"][-2].status == "error"
    (run,) = engine_client.get("/runs").json()
    assert run["status"] == "completed"
    result = next(e["payload"] for e in engine_client.get("/events").json()
                  if e["type"] == "tool.result")
    assert result["error"] and result["result"] is None
    assert engine_client.get("/services/outbox").json()["items"] == []
    assert sent == []


@pytest.mark.parametrize("method", ["invoke", "stream"])
@pytest.mark.parametrize("state,revoked", [("running", False), ("frozen", False),
                                           ("killed", False), ("halted", False),
                                           ("killed", True)])
def test_blocked_exit_reports_failure_without_overwriting_containment(
        engine_client, monkeypatch, method, state, revoked):
    detail = "SYNTHETIC_PRIVATE_REJECTION_DETAIL"
    completions = []
    blocked = []
    original_post = core._post
    original_check = core.check

    def post(path, body=None, run=None):
        if path.endswith("/complete"):
            completions.append(body.model_dump())
        return original_post(path, body, run)

    def check(*args):
        try:
            return original_check(*args)
        except Blocked as error:
            blocked.append(error)
            raise

    def reject(run, tool, args):
        # Script the agreed UNKNOWN_TOOL block while exercising the real data plane.
        assert run.status == "running"
        if state in {"frozen", "killed"}:
            getattr(gate, "freeze" if state == "frozen" else "kill")(
                run.id, "synthetic-human", "Synthetic containment")
        elif state == "halted":
            gate.global_stop("synthetic-human", "Synthetic containment")
        if revoked:
            run.token = "synthetic-revoked-token"
        return GateDecision(call_id="synthetic-blocked-call", tool=tool, args=args,
                            decision="block", layer="hard_rule", rule_id="UNKNOWN_TOOL",
                            explanation=detail)

    monkeypatch.setattr(core, "_post", post)
    monkeypatch.setattr(core, "check", check)
    monkeypatch.setattr(gate, "check", reject)
    graph = build(call("send_emai"), AIMessage("must not continue"))
    with pytest.raises(Blocked) as caught:
        output = getattr(graph, method)(TASK)
        if method == "stream":
            list(output)
    assert str(caught.value) == detail
    assert caught.value is blocked[0]
    (run,) = engine_client.get("/runs").json()
    assert run["status"] == ("failed" if state == "running" else state)
    assert detail not in run["status_reason"]
    if state != "running":
        assert run["status_reason"] == "Synthetic containment"
    assert completions and all(body == {"error": "Blocked"} for body in completions)
    if revoked:
        notes = [n for n in caught.value.__notes__ if n.startswith("Mirage")]
        assert notes and all(n == "Mirage failure reporting failed: HTTPStatusError" for n in notes)
        assert detail not in " ".join(caught.value.__notes__)
    updates = [e["payload"]["to"] for e in engine_client.get("/events").json()
               if e["type"] == "run.status" and e["payload"]["from"] == "running"]
    assert updates == [("failed" if state == "running" else state)]
    assert core._run.get() is None and sent == []
    assert engine_client.get("/services/outbox").json()["items"] == []
