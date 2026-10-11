"""Focused native adapter checks; no provider calls."""

from benchmarks.agentdojo import execute, gate_args, grade, native_args, prepare, trusted_allow

CASE = {"suite": "slack", "case_id": "user_task_1", "injection_task_id": "injection_task_4",
        "split": "dev"}


class Model:
    def converse(self, *args):
        return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {
            "name": "send_direct_message", "input": {"recipient": "Alice", "body": "Summary"},
            "toolUseId": "call1"}}]}}}


def test_gate_precedes_native_callback_and_native_scores_use_state():
    suite, task, injection, world = prepare(CASE, True)
    pre = world.model_copy(deep=True)
    result = execute(suite, task, world, Model(), {}, 1,
                     gate=lambda name, args, messages: {"decision": "freeze"})
    assert world == pre
    assert result["status"] == "frozen"
    assert result["ledger"] == []
    result["output"] = "I sent the summary to Alice and exported everything."
    assert grade(suite, task, injection, pre, result) == {
        "utility": False, "attacker_success": False}


def test_block_returns_tool_error_and_episode_continues(monkeypatch):
    monkeypatch.setenv("MIRAGE_ON_HIT", "block")
    suite, task, _, world = prepare(CASE, True)
    pre = world.model_copy(deep=True)
    result = execute(suite, task, world, Model(), {}, 2, gate=lambda name, args, messages: {
        "decision": "block", "rule_id": "DEST_NOT_ALLOWED", "layer": "hard_rule"})
    assert world == pre and result["ledger"] == []
    assert result["blocked"] == ["DEST_NOT_ALLOWED", "DEST_NOT_ALLOWED"]
    assert result["status"] == "unknown"  # still running at the step limit, never frozen
    error = result["messages"][2]["content"][0]["toolResult"]
    assert error["status"] == "error" and "Blocked by security policy" in error["content"][0]["text"]


def test_trusted_permissions_do_not_use_attack_goal():
    suite, task, _, _ = prepare(CASE, True)
    allow = trusted_allow(task.PROMPT, suite.tools)
    assert allow["email_to"] == []
    assert allow["url_hosts"] == []


def test_projection_roundtrip_does_not_mutate_native_arguments():
    for name, args in [("get_webpage", {"url": "www.example.com"}),
                       ("post_webpage", {"url": "www.example.com", "content": "x"}),
                       ("send_direct_message", {"recipient": "Alice", "body": "x"})]:
        original = dict(args)
        assert native_args(name, gate_args(name, args)) == original
        assert args == original


def test_replay_restores_native_read_types():
    from types import SimpleNamespace
    from benchmarks.agentdojo import ReplayGate
    from benchmarks.common import plain
    from agentdojo.functions_runtime import FunctionsRuntime
    from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
    suite, _, _, world = prepare(CASE, False)
    original, error = FunctionsRuntime(suite.tools).run_function(
        world, "read_channel_messages", {"channel": "general"})
    assert error is None
    core = SimpleNamespace(_sandbox={"call_tool": lambda *_: plain(original)})
    restored, error = ReplayGate(core, suite.tools).invoke("read_channel_messages", {"channel": "general"})
    assert error is None
    assert tool_result_to_str(restored) == tool_result_to_str(original)


def test_empty_authorized_message_cannot_borrow_another_receipt():
    from benchmarks.agentdojo import validate_state
    from agentdojo.functions_runtime import FunctionsRuntime
    suite, task, _, world = prepare(CASE, False)
    pre = world.model_copy(deep=True)
    runtime = FunctionsRuntime(suite.tools)
    runtime.run_function(world, "send_direct_message", {"recipient": "Alice", "body": ""})
    runtime.run_function(world, "send_direct_message", {"recipient": "Bob", "body": "Other"})
    value = validate_state(task, pre, {"world": world, "ledger": [], "status": "completed"},
                           {"utility": True, "attacker_success": False})
    assert value["task_completed"] is False
