"""SDK failures reach the actual run/service API; isolated data and no network/provider."""

import socket

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from mirage import core
from mirage.protect import registry

from agents.common.testing import call
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
    graph = build(call("send_email", to=USER, body="Missing required subject"), AIMessage("handled"),
                  allow={"tools": ["send_email"], "email_to": [USER]})
    output = graph.invoke(TASK)
    assert output["messages"][-2].status == "error"
    (run,) = engine_client.get("/runs").json()
    assert run["status"] == "completed"
    result = next(e["payload"] for e in engine_client.get("/events").json()
                  if e["type"] == "tool.result")
    assert result["error"] and result["result"] is None
    assert engine_client.get("/services/outbox").json()["items"] == []
    assert sent == []
