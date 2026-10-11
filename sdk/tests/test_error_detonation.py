"""Scripted recorded error through the actual jailed engine callback and this checkout SDK."""

from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage, messages_to_dict
from mirage import core, sandbox

from agents.common.testing import call
from engine.detonation import sandbox as detonation
from sdk.tests.test_langchain_errors import USER


def assert_error_runner(snapshot, call_tool):
    # The shared .venv is editable to main; prove the child tests this worktree's SDK.
    assert Path(core.__file__).resolve() == Path(__file__).resolve().parents[1] / "mirage/core.py"
    output = sandbox.run(snapshot, call_tool)
    (message,) = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    assert (message.status, message.content) == ("error", "ExecutionError")


def test_recorded_tool_error_replays_in_the_jail(monkeypatch):
    args = {"to": USER, "body": "Missing required subject"}
    replies = [call("send_email", **args), AIMessage("handled")]
    snapshot = {
        "agent": "replayed_error", "task": "Synthetic brief",
        "runner": "sdk.tests.test_error_detonation:assert_error_runner",
        "entrypoint": "sdk.tests.test_langchain_errors:factory",
        "model_calls": [{"response": {"messages": messages_to_dict([m])}} for m in replies],
        "tool_results": [{"call_id": "recorded_call", "tool": "send_email", "args": args,
                          "result": None, "error": "ExecutionError"}],
    }
    monkeypatch.setattr(detonation, "BOOT",
                        "import sys; sys.path.insert(0, sys.argv[1] + '/sdk'); " + detonation.BOOT)
    effects, error = detonation.run_once(snapshot)
    assert error is None
    assert len(effects) == 1
    assert (effects[0]["tool"], effects[0]["args"], effects[0]["error"]) == (
        "send_email", args, "ExecutionError")
