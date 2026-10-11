"""Bedrock tool loop using AgentDojo's published worlds, functions and graders.

No oracle executes the victim task: ground truth is used only by AgentDojo's
published attack constructor to select injection vectors, never for permissions.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

MANIFEST = json.loads(Path(__file__).with_name("manifest.json").read_text())
sys.path[:0] = [MANIFEST["native_source"] + "/src", MANIFEST["native_deps"]]

from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttackNoNames
from agentdojo.attacks.baseline_attacks import SystemMessageAttack
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
    attack_class = (ImportantInstructionsAttackNoNames if case["split"] == "dev"
                    else SystemMessageAttack)
    payload = attack_class(suite, AttackTarget()).attack(task, injection) if injection else {}
    world = task.init_environment(suite.load_and_inject_default_environment(payload))
    return suite, task, injection, world


def trusted_allow(task_prompt, tools, world=None):
    """Only literal user-specified destinations are authorized; dynamic scope is pending."""
    addresses = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", task_prompt)
    urls = re.findall(r"(?:https?://)?(?:www\.)[\w.-]+(?:/[\w./-]*)?", task_prompt)
    if world is not None:
        addresses += [u + "@slack.native.invalid" for u in world.slack.users
                      if re.search(r"\b" + re.escape(u) + r"\b", task_prompt)]
    # Destructive effects require a literal legitimate request, never instructions from reads.
    allowed = [t.name for t in tools if t.name != "remove_user_from_slack"
               or re.search(r"\b(remove|delete)\b", task_prompt, re.I)]
    return {"tools": allowed, "email_to": addresses,
            "url_hosts": [u.split("//")[-1].split("/")[0] for u in urls]}


def gate_args(name, args):
    """Reversible fixture identity projection; native callbacks never see this copy."""
    projected = dict(args)
    if name == "get_webpage" and "url" in projected:
        projected["read_url"] = projected.pop("url")
    if name == "send_direct_message" and isinstance(projected.get("recipient"), str):
        projected["recipient"] += "@slack.native.invalid"
    if isinstance(projected.get("url"), str) and "://" not in projected["url"]:
        projected["url"] = "http://" + projected["url"]
    return projected


def native_args(name, args):
    restored = dict(args)
    if name == "get_webpage" and "read_url" in restored:
        restored["url"] = restored.pop("read_url")
    if name == "send_direct_message" and isinstance(restored.get("recipient"), str):
        restored["recipient"] = restored["recipient"].removesuffix("@slack.native.invalid")
    if isinstance(restored.get("url"), str):
        restored["url"] = restored["url"].removeprefix("http://")
    return restored


class Gate:
    """Use the SDK data plane; a contained invocation leaves its original call pending."""

    def __init__(self, suite, task, clean_world, model, config):
        from mirage import core
        self.core = core
        self.name = config["name"]
        self.model_id = model.model_id
        self.config = config
        self.decisions = []
        core.register(self.name, [t.name for t in suite.tools],
                      trusted_allow(task.PROMPT, suite.tools, clean_world),
                      "benchmarks.agentdojo:build_agent", "native-benchmark",
                      legit={})
        self.run = core.open_run(self.name, task.PROMPT)
        self.runtime = core._http.get("/runtime").json()

    def model(self, messages, response):
        from contracts.models import ModelCall
        self.core._post(f"/runs/{self.run['id']}/model-calls", ModelCall(
            model_id=self.model_id, request={"messages": messages, "native_config": self.config},
            response=response), self.run)

    def __call__(self, name, args, messages):
        from contracts.models import ToolCheck
        self.decision = self.core._post("/gateway/check", ToolCheck(
            run_id=self.run["id"], tool=name, args=gate_args(name, args)), self.run)
        self.decisions.append(self.decision)
        return self.decision

    def record(self, name, value, error):
        self.core.record(self.run, self.decision["call_id"], name, plain(value),
                         error.partition(":")[0] if error else None)


class ReplayGate:
    def __init__(self, core):
        self.core = core

    def model(self, messages, response):
        return

    def __call__(self, name, args, messages):
        return {"decision": "allow"}

    def invoke(self, name, args):
        from contracts.models import ToolResult
        value = self.core._sandbox["call_tool"](name, gate_args(name, args))
        if isinstance(value, ToolResult):
            return value.result, value.error
        return value, None

    def record(self, *args):
        return


def build_agent():
    """Existing SDK replay factory; all sandbox tools route through engine call_tool."""
    from mirage import core
    from mirage.protect import registry
    from benchmarks.common import Bedrock
    snapshot = json.loads(Path(os.environ["MIRAGE_SNAPSHOT"]).read_text())
    config = snapshot["model_calls"][0]["request"]["native_config"]
    case = next(c for c in MANIFEST["cases"] if c["case_id"] == config["case_id"])
    suite, task, _, world = prepare(case, False)
    core.register(snapshot["agent"], [t.name for t in suite.tools],
                  trusted_allow(task.PROMPT, suite.tools, world),
                  "benchmarks.agentdojo:build_agent", "native-benchmark", legit={})
    class ReplayModel(Bedrock):
        def converse(self, *args):
            return core.replayed_reply() or super().converse(*args)
    model = ReplayModel(snapshot["model_id"])
    def replay(task_prompt):
        if task_prompt != task.PROMPT:
            raise ValueError("Snapshot task identity changed")
        result = execute(suite, task, world, model, MANIFEST["parameters"],
                         MANIFEST["max_steps"], gate=ReplayGate(core),
                         max_tools=MANIFEST["max_tool_steps"], timeout_s=MANIFEST["timeout_s"])
        if result["status"] != "completed":
            raise RuntimeError(result["unknown_reason"])
        return result
    registry[snapshot["agent"]] = replay


def execute(suite, task, world, model, parameters, max_steps, gate=None,
            max_tools=12, timeout_s=120):
    """Arguments pass untouched to native FunctionsRuntime after optional admission."""
    runtime = FunctionsRuntime(suite.tools)
    tools = [{"toolSpec": {"name": f.name, "description": f.description,
              "inputSchema": {"json": f.parameters.model_json_schema()}}} for f in suite.tools]
    messages = [{"role": "user", "content": [{"text": task.PROMPT}]}]
    traces, ledger = [], []
    output, status, reason = "", "completed", None
    started = time.monotonic()
    for _ in range(max_steps):
        if time.monotonic() - started >= timeout_s:
            status, reason = "unknown", "invocation_timeout"
            break
        try:
            response = model.converse(messages, load_system_message(None), tools, parameters)
        except Exception as exc:
            status, reason = "unknown", "provider_" + type(exc).__name__
            break
        message = response["output"]["message"]
        if gate:
            if hasattr(gate, "model"):
                gate.model(messages, response)
        messages.append(message)
        output = "\n".join(c["text"] for c in message["content"] if "text" in c)
        calls = [c["toolUse"] for c in message["content"] if "toolUse" in c]
        if not calls:
            break
        results = []
        for call in calls:
            if len(traces) >= max_tools or time.monotonic() - started >= timeout_s:
                return {"world": world, "traces": traces, "ledger": ledger,
                        "messages": messages, "output": output, "status": "unknown",
                        "unknown_reason": "tool_or_time_limit",
                        "latency_s": time.monotonic() - started}
            name, args = call["name"], call["input"]
            if gate:
                decision = gate(name, args, messages)
                if decision["decision"] != "allow":
                    status, reason = "frozen", decision.get("rule_id")
                    return {"world": world, "traces": traces, "ledger": ledger,
                            "messages": messages, "output": output, "status": status,
                            "unknown_reason": reason, "latency_s": time.monotonic() - started}
            value, error = (gate.invoke(name, args) if isinstance(gate, ReplayGate)
                            else runtime.run_function(world, name, args))
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
