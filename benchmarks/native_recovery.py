"""Label-free native recovery bridge; native grading stays outside execution.

This is a benchmark extension, not an initial-state detector or engine incident.
Engine checkpoint transport is deliberately left to the accepted engine seam.
"""

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

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


def run_owner_turns(agent, owner_messages, *, messages=None, before_turn=None, after_turn=None):
    """Preserve each native owner turn and all prior model/tool messages."""
    from langchain_core.messages import HumanMessage

    history = list(messages or [])
    for index, owner in enumerate(owner_messages):
        history.append(HumanMessage(content=owner))
        if before_turn is not None:
            before_turn(index, history)
        result = agent.invoke({"messages": history},
                              {"recursion_limit": PARAMETERS["max_model_calls"] * 8,
                               "max_concurrency": 1})
        history = list(result["messages"])
        if after_turn is not None:
            after_turn(index, history)
    return history


def export_world(world):
    """Capture directories too: deleting a file leaves observable empty parents."""
    return {"files": world.snapshot(),
            "directories": [str(p.relative_to(world.root))
                            for p in sorted(world.root.rglob("*")) if p.is_dir()]}


class NativeCapture:
    """Private immutable producer; admission identity comes from real receipts."""

    def __init__(self, directory, world, payload, admission, runtime, admitted_spec, model_id):
        run_id = admission["run_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise ValueError("Invalid run identity")
        if admission["task"] != "\n\n".join(payload["owner_messages"]):
            raise ValueError("Original task mismatch")
        self.directory, self.world = Path(directory), world
        self.record = {"version": 1, "run_id": run_id, "agent": admitted_spec["name"],
                       "stream_epoch": runtime["stream_epoch"],
                       "task_sha256": content_hash(admission["task"]),
                       "admitted_spec_sha256": content_hash(admitted_spec),
                       "initial_world": export_world(world), "callbacks": [],
                       "owner_messages": deepcopy(payload["owner_messages"]), "owner_index": 0,
                       "system": payload["system"], "model_id": model_id}
        self.record["initial_sha256"] = content_hash(self.record["initial_world"])
        self.owner_context = []
        self.busy = False
        self.directory.mkdir(parents=True, exist_ok=True)
        if (self.directory / f"{run_id}.json").exists():
            raise ValueError("Capture already exists for admitted run")
        self.publish()

    def publish(self):
        self.record["frozen_world"] = export_world(self.world)
        self.record["frozen_sha256"] = content_hash(self.record["frozen_world"])
        frozen = deepcopy(self.record)
        digest = content_hash(frozen)
        target = self.directory / f"{digest}.json"
        data = json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode("utf-8")
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError("Immutable capture collision")
        else:
            with target.open("xb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             prefix=".capture-", delete=False) as file:
                temporary = Path(file.name)
                file.write(data.decode("utf-8"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.directory / f"{self.record['run_id']}.json")
            directory = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return digest

    def owner_turn(self, index, messages):
        if self.busy or not 0 <= index < len(self.record["owner_messages"]):
            raise ValueError("Invalid capture owner boundary")
        from langchain_core.messages import messages_to_dict
        self.record["owner_index"] = index
        self.owner_context = messages_to_dict(messages)
        self.publish()

    def invoke(self, model_call, execute, run_id):
        if self.busy:
            raise ValueError("Native callbacks must be sequential")
        if run_id != self.record["run_id"] or model_call["name"] not in FILE_TOOLS:
            raise ValueError("Original admitted native run required")
        self.busy = True
        before = len(self.world.calls)
        row = {"model_call_id": model_call["id"], "tool": model_call["name"],
               "args": deepcopy(model_call["args"]), "result": None, "error": None,
               "native_error": None}
        try:
            message = execute()
            from langchain_core.messages import ToolMessage
            if not isinstance(message, ToolMessage):
                raise ValueError("Native callback must return its tool message")
            if message.status == "error":
                row["error"] = "ToolMessageError"
            else:
                try:
                    row["result"] = json.loads(message.content)
                except (TypeError, ValueError):
                    row["result"] = message.content
            return message
        except Exception as exc:
            row["error"] = type(exc).__name__
            raise
        finally:
            native = self.world.calls[before:]
            if len(native) == 1:
                row["native_error"] = native[0].get("error")
            elif row["error"] is not None and row["error"] != "ToolMessageError":
                row["native_error"] = row["error"]
            self.record["callbacks"].append(row)
            self.busy = False
            self.publish()  # before the SDK posts this admitted result/error


def capture_middleware(get_capture):
    """SDK remains the outer gate; this runs only its admitted real callback."""
    from langchain.agents.middleware import wrap_tool_call

    @wrap_tool_call
    def capture_call(request, handler):
        from mirage import core
        run = core._run.get()
        return get_capture().invoke(request.tool_call, lambda: handler(request),
                                    run["id"] if run else None)

    return capture_call


def install_precheck_capture(agent, capture):
    """Observe before the existing SDK gate, retaining its callback authority."""
    node = agent.nodes["tools"].bound
    sdk_hook = node._wrap_tool_call

    def before_check(request, execute):
        capture.publish()
        return sdk_hook(request, execute)

    node._wrap_tool_call = before_check


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
