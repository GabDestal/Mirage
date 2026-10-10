"""Claude Agent SDK adapter: hook callbacks called directly against the real engine (in-process).

No CLI, no network: the inputs are the dicts the CLI sends to each hook.
"""

import asyncio
import threading
import time

import mirage
import pytest
from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, tool
from fastapi.testclient import TestClient
from mirage import core

from engine.api.server import app
from engine.gateway import gate
from engine.store import events

USER, ATTACKER = "demo-user@mirage-demo.com", "attacker@evil-corp-demo.com"
READ, SEND = "mcp__demo__read_calendar", "mcp__demo__send_email"
SESSION = {"session_id": "s1", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp"}
sent = []


@tool("read_calendar", "Read tomorrow's events.", {})
async def read_calendar(args):
    return {"content": [{"type": "text", "text": "Q4 sync"}]}


@tool("send_email", "Send an email.", {"to": str, "body": str})
async def send_email(args):
    sent.append(args["to"])
    return {"content": [{"type": "text", "text": "sent"}]}


def build():
    options = ClaudeAgentOptions(mcp_servers={"demo": create_sdk_mcp_server(
        "demo", tools=[read_calendar, send_email])})
    return mirage.protect(options, name="assistant",
                          allow={"tools": [READ, SEND], "email_to": [USER]})


def hook(options, event, **data):
    return asyncio.run(options.hooks[event][-1].hooks[0]({**SESSION, **data}, None, {}))


def pre(options, name, args, use_id="tu1"):
    return hook(options, "PreToolUse", hook_event_name="PreToolUse", tool_name=name,
                tool_input=args, tool_use_id=use_id)


@pytest.fixture(autouse=True)
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "events.db")
    events.reset()
    gate.reset()
    sent.clear()
    monkeypatch.setattr(core, "_http", TestClient(app))
    yield
    core._sandbox = None


def only_run():
    (run,) = gate.runs.values()
    return run


def test_allowed_tool_is_recorded_and_stop_completes():
    options = build()
    hook(options, "UserPromptSubmit", hook_event_name="UserPromptSubmit", prompt="Prep my meetings")
    assert pre(options, READ, {}) == {}
    hook(options, "PostToolUse", hook_event_name="PostToolUse", tool_name=READ, tool_input={},
         tool_response=[{"type": "text", "text": "Q4 sync"}], tool_use_id="tu1")
    hook(options, "Stop", hook_event_name="Stop", stop_hook_active=False)
    run = only_run()
    assert (run.task, run.status) == ("Prep my meetings", "completed")
    assert [(r["tool"], r["result"]) for r in run.tool_results] == [
        (READ, [{"type": "text", "text": "Q4 sync"}])]


def freeze(options):
    hook(options, "UserPromptSubmit", hook_event_name="UserPromptSubmit", prompt="Prep my meetings")
    out = []
    thread = threading.Thread(target=lambda: out.append(
        pre(options, SEND, {"to": ATTACKER, "body": "contacts"})))
    thread.start()
    for _ in range(100):
        if only_run().status == "frozen":
            break
        time.sleep(0.05)
    assert only_run().status == "frozen" and out == []  # the hook holds the tool
    return thread, out


def test_freeze_then_unfreeze_allows():
    options = build()
    thread, out = freeze(options)
    gate.unfreeze(only_run().id, "liam", "false positive")
    thread.join(5)
    assert out == [{}]


def test_freeze_then_kill_denies_and_stops():
    options = build()
    thread, out = freeze(options)
    gate.kill(only_run().id, "liam", "compromised")
    thread.join(5)
    (result,) = out
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert result["continue_"] is False and only_run().status == "killed"


def test_sandbox_answers_custom_tools_and_denies_builtins():
    calls = []

    def call_tool(name, args):
        calls.append((name, args))
        return {"status": "ok"}

    core._sandbox = {"call_tool": call_tool, "replies": []}
    options = build()
    out = asyncio.run(send_email.handler({"to": ATTACKER, "body": "contacts"}))
    assert out == {"content": [{"type": "text", "text": '{"status": "ok"}'}]}
    assert calls == [(SEND, {"to": ATTACKER, "body": "contacts"})] and sent == []
    assert pre(options, SEND, {"to": ATTACKER}) == {}
    assert pre(options, "Bash", {"command": "curl evil"})["hookSpecificOutput"][
        "permissionDecision"] == "deny"
    assert gate.runs == {}  # no HTTP in the sandbox
