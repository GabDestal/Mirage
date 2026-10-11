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
