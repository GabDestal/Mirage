"""Failure truth through sync LangChain recording/replay; no engine, sockets or provider."""

import json
import socket

import httpx
import mirage
import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage, messages_to_dict
from langchain_core.tools import tool
from mirage import core, sandbox
from mirage.protect import registry

from agents.common.testing import call, scripted
from contracts.models import ToolResult

TASK = {"messages": [("user", "Send the synthetic brief")]}
USER = "demo-user@mirage-demo.com"
sent = []


@tool
def send_email(to: str, subject: str, body: str) -> dict:
    """Send a synthetic brief."""
    sent.append(to)
    return {"status": "sent"}


def turns(*items):
    for item in items:
        if isinstance(item, BaseException):
            raise item
        yield item


def build(*items, name="assistant", allow=None):
    model = scripted()
    model.messages = turns(*items)
    return mirage.protect(create_agent(model, tools=[send_email]), name=name, allow=allow)


@pytest.fixture
def offline(monkeypatch):
    requests = []

    def no_network(*args, **kwargs):
        raise AssertionError("No sockets in SDK regression tests")

    for obj, attr in [(socket.socket, "connect"), (socket, "create_connection"),
                      (socket, "getaddrinfo")]:
        monkeypatch.setattr(obj, attr, no_network)

    def handle(request):
        body = json.loads(request.content) if request.content else None
        requests.append((request.url.path, body, request.headers.get("Authorization")))
        if request.url.path == "/runs":
            response = {"run_id": "offline_1", "run_token": "synthetic-token"}
        elif request.url.path == "/gateway/check":
            response = {"call_id": "checked_call", "tool": body["tool"], "args": body["args"],
                        "decision": "allow", "layer": "hard_rule", "explanation": "Mock allow"}
        else:
            response = {}
        return httpx.Response(200, json=response)

    token = core._run.set(None)
    monkeypatch.setattr(core, "_sandbox", None)
    previous = registry.copy()
    sent.clear()
    with httpx.Client(base_url="http://offline.invalid",
                      transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(core, "_http", client)
        yield requests
    core._run.reset(token)
    registry.clear()
    registry.update(previous)


def run(graph, method):
    output = getattr(graph, method)(TASK)
    return list(output) if method == "stream" else output


def terminal(requests):
    return [(path, body, auth) for path, body, auth in requests if path.endswith("/complete")]


@pytest.mark.parametrize("method", ["invoke", "stream"])
def test_success_completes_once_even_when_invoke_nests_stream(offline, method):
    graph = build(call("send_email", to=USER, subject="Brief", body="Synthetic"), AIMessage("done"))
    run(graph, method)
    assert sent == [USER]
    assert len([r for r in offline if r[0] == "/runs"]) == 1
    assert terminal(offline) == [("/runs/offline_1/complete", None, "Bearer synthetic-token")]
    assert core._run.get() is None


@pytest.mark.parametrize("method", ["invoke", "stream"])
@pytest.mark.parametrize("fails", [False, True])
def test_outer_run_owns_completion_for_nested_protected_graph(offline, method, fails):
    failure = RuntimeError("synthetic failure") if fails else None
    graph = build(failure if fails else AIMessage("done"))
    token = core.start("assistant", "Synthetic task")
    outer_run = core._run.get()
    try:
        if fails:
            with pytest.raises(RuntimeError) as caught:
                run(graph, method)
            assert caught.value is failure
        else:
            run(graph, method)
        assert terminal(offline) == [] and core._run.get() is outer_run
    finally:
        core.end(token, failure)
    body = {"error": "RuntimeError"} if fails else None
    assert terminal(offline) == [("/runs/offline_1/complete", body, "Bearer synthetic-token")]
    assert len([r for r in offline if r[0] == "/runs"]) == 1
    assert core._run.get() is None


@pytest.mark.parametrize("method", ["invoke", "stream"])
@pytest.mark.parametrize("after_tool", [False, True])
def test_model_failure_is_reported_once_and_reraised(offline, method, after_tool):
    failure = RuntimeError("synthetic secret that must not enter terminal telemetry")
    before = [call("send_email", to=USER, subject="Brief", body="Synthetic")] if after_tool else []
    graph = build(*before, failure)
    with pytest.raises(RuntimeError) as caught:
        run(graph, method)
    assert caught.value is failure
    assert terminal(offline) == [("/runs/offline_1/complete", {"error": "RuntimeError"},
                                 "Bearer synthetic-token")]
    assert sent == ([USER] if after_tool else [])
    assert core._run.get() is None


@pytest.mark.parametrize("method", ["invoke", "stream"])
def test_failure_reporting_outage_does_not_replace_original_error(offline, method, monkeypatch):
    failure = ValueError("original synthetic failure")
    graph = build(failure)
    previous = core._post

    def unavailable(path, *args, **kwargs):
        if path.endswith("/complete"):
            raise OSError("synthetic reporting outage")
        return previous(path, *args, **kwargs)

    monkeypatch.setattr(core, "_post", unavailable)
    with pytest.raises(ValueError) as caught:
        run(graph, method)
    assert caught.value is failure
    assert "Mirage failure reporting failed: OSError" in caught.value.__notes__
    assert core._run.get() is None


@pytest.mark.parametrize("method", ["invoke", "stream"])
def test_tool_recording_outage_preserves_original_exception(offline, method, monkeypatch):
    failure = LookupError("original synthetic tool failure")

    def explode(*args, **kwargs):
        raise failure

    monkeypatch.setattr(send_email, "func", explode)
    previous = core._post

    def unavailable(path, *args, **kwargs):
        if path.endswith("/tool-results"):
            raise OSError("synthetic tool recording outage")
        return previous(path, *args, **kwargs)

    monkeypatch.setattr(core, "_post", unavailable)
    graph = build(call("send_email", to=USER, subject="Brief", body="Synthetic"))
    with pytest.raises(LookupError) as caught:
        run(graph, method)
    assert caught.value is failure
    assert "Mirage tool error recording failed: OSError" in caught.value.__notes__
    assert core._run.get() is None


@pytest.mark.parametrize("method", ["invoke", "stream"])
def test_human_block_is_not_reported_as_completion_or_model_failure(offline, method, monkeypatch):
    failure = mirage.Blocked("Run offline_1 is killed.")

    def killed(*args):
        raise failure

    monkeypatch.setattr(core, "check", killed)
    graph = build(call("send_email", to=USER, subject="Brief", body="Synthetic"))
    with pytest.raises(mirage.Blocked) as caught:
        run(graph, method)
    assert caught.value is failure
    assert terminal(offline) == []
    assert sent == []
    assert core._run.get() is None


def test_early_stream_close_is_not_success(offline):
    graph = build(call("send_email", to=USER, subject="Brief", body="Synthetic"), AIMessage("done"))
    stream = graph.stream(TASK)
    next(stream)
    stream.close()
    assert terminal(offline) == [("/runs/offline_1/complete", {"error": "GeneratorExit"},
                                 "Bearer synthetic-token")]
    assert sent == []
    assert core._run.get() is None


@pytest.mark.parametrize("tool_name,args", [
    ("send_email", {"to": USER, "body": "Missing required subject"}),
    ("unknown_tool", {}),
])
def test_handled_tool_error_is_recorded_without_failure_content(offline, tool_name, args):
    graph = build(call(tool_name, **args), AIMessage("handled"))
    output = graph.invoke(TASK)
    (message,) = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    (recorded,) = [body for path, body, _ in offline if path.endswith("/tool-results")]
    assert message.status == "error"
    assert (recorded["error"], recorded["result"]) == ("ToolMessageError", None)
    assert ("subject" if tool_name == "send_email" else tool_name) in message.content
    assert recorded["call_id"] == "checked_call"
    assert sent == []
    assert len(terminal(offline)) == 1


def test_later_model_record_sanitizes_error_copy_without_mutating_agent_message(offline):
    detail = "SYNTHETIC_PRIVATE_ERROR_DETAIL"
    original = ToolMessage(content=detail, status="error", name="send_email", id="safe_message",
                           tool_call_id="call_send_email", artifact={"detail": detail},
                           additional_kwargs={"detail": detail}, response_metadata={"detail": detail})
    before = original.model_dump()
    model = scripted(call("send_email", to=USER, subject="Brief", body="Synthetic"),
                     AIMessage("handled"))
    graph = create_agent(model, tools=[send_email])
    graph.nodes["tools"].bound._wrap_tool_call = lambda *args: original
    graph = mirage.protect(graph, name="assistant")
    output = graph.invoke(TASK)
    records = [body for path, body, _ in offline if path.endswith("/model-calls")]
    (recorded,) = [m["data"] for record in records for m in record["request"]["messages"]
                   if m["type"] == "tool"]
    assert recorded["content"] == "ToolMessageError"
    assert (recorded["tool_call_id"], recorded["name"], recorded["status"]) == (
        "call_send_email", "send_email", "error")
    assert recorded["artifact"] is None
    assert recorded["additional_kwargs"] == recorded["response_metadata"] == {}
    assert detail not in json.dumps(records)
    assert original.model_dump() == before
    (message,) = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    assert message.model_dump() == before
    assert sent == []


def factory():
    build(AIMessage("unused live reply"), name="replayed_error")


@pytest.mark.parametrize("content", ["Synthetic validation error", "", '{"error":"synthetic"}',
                                    [{"type": "text", "text": "Synthetic validation error"}], None])
def test_handled_error_replays_as_error_without_real_tool_or_http(offline, content):
    reply = [call("send_email", to=USER, body="Missing required subject"), AIMessage("handled")]
    snapshot = {"agent": "replayed_error", "task": "Synthetic task",
                "entrypoint": f"{__name__}:factory",
                "model_calls": [{"response": {"messages": messages_to_dict([m])}} for m in reply]}
    error = ToolResult(call_id="recorded_call", tool="send_email", result=content,
                       error="ToolMessageError")
    calls = []

    def call_tool(name, args):
        calls.append((name, args))
        return error

    output = sandbox.run(snapshot, call_tool)
    (message,) = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    assert (message.status, message.content, message.tool_call_id, message.name) == (
        "error", content if content is not None else "ToolMessageError", "call_send_email",
        "send_email")
    assert len(calls) == 1
    assert sent == [] and offline == []


def test_raw_error_field_in_successful_replay_result_stays_success(offline):
    replies = [call("send_email", to=USER, subject="Brief", body="Synthetic"), AIMessage("done")]
    snapshot = {"agent": "replayed_error", "task": "Synthetic task",
                "entrypoint": f"{__name__}:factory",
                "model_calls": [{"response": {"messages": messages_to_dict([m])}} for m in replies]}
    result = {"error": "Business data, not Mirage metadata", "status": "ok"}
    output = sandbox.run(snapshot, lambda *args: result)
    (message,) = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    assert message.status == "success" and json.loads(message.content) == result
    assert sent == [] and offline == []
