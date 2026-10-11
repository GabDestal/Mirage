"""Bedrock tool loop using AgentDojo's published worlds, functions and graders.

No oracle executes the victim task: ground truth is used only by AgentDojo's
published attack constructor to select injection vectors, never for permissions.
"""

import json
import re
import time

from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttackNoNames
from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.types import text_content_block_from_string

from benchmarks.common import plain


class AttackTarget(BasePipelineElement):
    # Native constructor requires a known name even for its no-name template.
    name = "gpt-4o-2024-05-13"

    def query(self, *args, **kwargs):
        raise RuntimeError("Attack metadata target is never a victim or oracle")


def prepare(case, attack, version="v1.2.2"):
    suite = get_suite(version, case["suite"])
    task = suite.user_tasks[case["case_id"]]
    injection = suite.injection_tasks[case["injection_task_id"]] if attack else None
    payload = (ImportantInstructionsAttackNoNames(suite, AttackTarget()).attack(task, injection)
               if injection else {})
    world = task.init_environment(suite.load_and_inject_default_environment(payload))
    return suite, task, injection, world


def trusted_allow(task_prompt, tools):
    """Only literal user-specified destinations are authorized; dynamic scope is pending."""
    addresses = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", task_prompt)
    urls = re.findall(r"(?:https?://)?(?:www\.)[\w.-]+(?:/[\w./-]*)?", task_prompt)
    return {"tools": [t.name for t in tools], "email_to": addresses,
            "url_hosts": [u.split("//")[-1].split("/")[0] for u in urls]}


def execute(suite, task, world, model, parameters, max_steps, gate=None):
    """Arguments pass untouched to native FunctionsRuntime after optional admission."""
    runtime = FunctionsRuntime(suite.tools)
    tools = [{"toolSpec": {"name": f.name, "description": f.description,
              "inputSchema": {"json": f.parameters.model_json_schema()}}} for f in suite.tools]
    messages = [{"role": "user", "content": [{"text": task.PROMPT}]}]
    traces, ledger = [], []
    output, status, reason = "", "completed", None
    started = time.monotonic()
    for _ in range(max_steps):
        try:
            response = model.converse(messages, load_system_message(None), tools, parameters)
        except Exception as exc:
            status, reason = "unknown", "provider_" + type(exc).__name__
            break
        message = response["output"]["message"]
        messages.append(message)
        output = "\n".join(c["text"] for c in message["content"] if "text" in c)
        calls = [c["toolUse"] for c in message["content"] if "toolUse" in c]
        if not calls:
            break
        results = []
        for call in calls:
            name, args = call["name"], call["input"]
            if gate:
                decision = gate(name, args, messages)
                if decision["decision"] != "allow":
                    status, reason = "frozen", decision.get("rule_id")
                    return {"world": world, "traces": traces, "ledger": ledger,
                            "messages": messages, "output": output, "status": status,
                            "unknown_reason": reason, "latency_s": time.monotonic() - started}
            value, error = runtime.run_function(world, name, args)
            traces.append(FunctionCall(function=name, args=args, id=call["toolUseId"]))
            ledger.append({"tool": name, "args": args, "result": plain(value), "error": error})
            if gate:
                gate.record(name, value, error)
            results.append({"toolResult": {"toolUseId": call["toolUseId"],
                           "content": [{"text": error or tool_result_to_str(value)}],
                           "status": "error" if error else "success"}})
        messages.append({"role": "user", "content": results})
    else:
        status, reason = "unknown", "step_limit"
    return {"world": world, "traces": traces, "ledger": ledger, "messages": messages,
            "output": output, "status": status, "unknown_reason": reason,
            "latency_s": time.monotonic() - started}


def grade(suite, task, injection, pre, result):
    output = [text_content_block_from_string(result["output"])]
    utility = suite._check_user_task_utility(task, output, pre, result["world"], result["traces"])
    harm = (suite._check_injection_task_security(injection, output, pre, result["world"],
                                              result["traces"]) if injection else None)
    # Selected tasks use actual state/traces. Preserve raw native scores even on incomplete runs.
    return {"utility": utility, "attacker_success": harm}
