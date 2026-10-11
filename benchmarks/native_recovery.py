"""Label-free native recovery bridge; native grading stays outside execution.

This is a benchmark extension, not an initial-state detector or engine incident.
Engine checkpoint transport is deliberately left to the accepted engine seam.
"""

from copy import deepcopy
from hashlib import sha256
import json

from benchmarks.harnessrisk import FILE_TOOLS, PARAMETERS, tools_for

W3_SHA = "463d943c9684899590f2b87e7d38c8861e1e736b"
PROTOCOL = "native-recovery-v1"


def content_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def runtime_payload(case, system):
    """Project permitted fixture data only; no case identity, labels or objectives."""
    world = case["world"]
    if set(world.get("allowed_tools", [])) != FILE_TOOLS:
        raise ValueError("Unsupported native tools")
    if world.get("mock_services") or world.get("environment"):
        raise ValueError("Unsupported native environment")
    files = world["workspace_files"]
    owners = case["task"]["user_messages"]
    if not isinstance(files, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                         for k, v in files.items()):
        raise ValueError("Fixture files must be text")
    if not isinstance(owners, list) or not owners or any(not isinstance(m, str) or not m
                                                       for m in owners):
        raise ValueError("Native sequential owner messages required")
    if not isinstance(system, str):
        raise ValueError("System prompt must be text")
    return deepcopy({"initial_files": files, "owner_messages": owners,
                     "system": system, "tools": tool_definitions()})


def tool_definitions():
    class SchemaOnly:
        def call(self, *args):
            raise RuntimeError("Schema extraction cannot execute tools")

    return [{"name": t.name, "description": t.description,
             "parameters": t.args_schema.model_json_schema()}
            for t in tools_for(SchemaOnly())]


def run_owner_turns(agent, owner_messages, *, messages=None, after_turn=None):
    """Preserve each native owner turn and all prior model/tool messages."""
    from langchain_core.messages import HumanMessage

    history = list(messages or [])
    for index, owner in enumerate(owner_messages):
        history.append(HumanMessage(content=owner))
        result = agent.invoke({"messages": history},
                              {"recursion_limit": PARAMETERS["max_model_calls"] * 8,
                               "max_concurrency": 1})
        history = list(result["messages"])
        if after_turn is not None:
            after_turn(index, history)
    return history


def diagnosis_evidence(payload, calls, final_files):
    """Only owner task, observed reads/actions and actual state reach diagnosis."""
    return deepcopy({"owner_messages": payload["owner_messages"],
                     "tool_trace": [{k: row[k] for k in ("tool", "args", "result", "error")
                                     if k in row} for row in calls],
                     "initial_files": payload["initial_files"],
                     "final_files": final_files})


def lifecycle_disclosure():
    return {
        "production_admission": "engine SDK/gateway only in protected arms",
        "initial_state_detection": "unsupported; no native-state engine detector",
        "incident": "only a genuine gateway incident receipt establishes an incident",
        "manual_freeze": "benchmark operator action; creates no engine incident",
        "detonation": "engine child only after root accepts exact W5 source",
        "native_verdict": "external benchmark state predicates; separate from engine verdict",
        "cause_isolation": "benchmark extension over preselected exact read inputs",
        "fix": "generic trust/input handling correction; no scripted task answers",
        "verification": "independent worlds; external native utility AND safety",
        "restart": "exact original task with automated receipt; no human approval claim",
    }
