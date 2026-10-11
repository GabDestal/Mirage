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
import shutil
import signal
import tempfile
import time

from benchmarks.harnessrisk import (FILE_TOOLS, PARAMETERS, FileWorld, grade, load_case,
                                   native_module, result_row, revision, tools_for, write_json)

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


def build_native_agent(world, system, model_id, *, middleware=(), stop_epoch=None):
    from langchain.agents import create_agent
    from langchain.agents.middleware import after_model, wrap_model_call
    from agents.common.model import chat_model, clean_tool_names

    trace = {"calls": 0, "replies": 0, "tokens_known": True, "tokens": 0, "messages": []}

    @wrap_model_call
    def budget(request, handler):
        if (trace["calls"] >= PARAMETERS["max_model_calls"]
                or stop_epoch is not None and time.time() >= stop_epoch):
            raise TimeoutError("Model call cap reached")
        trace["calls"] += 1
        response = handler(request)
        trace["replies"] += 1
        for message in response.result:
            tokens = (getattr(message, "usage_metadata", None) or {}).get("total_tokens")
            if tokens is None:
                trace["tokens_known"] = False
            else:
                trace["tokens"] += tokens
        return response

    @after_model
    def observed(state, runtime):
        trace["messages"] = list(state["messages"])

    model = chat_model(model_id)
    model.max_tokens = PARAMETERS["max_tokens"]
    agent = create_agent(model, tools_for(world), system_prompt=system,
                         middleware=[clean_tool_names, budget, observed, *middleware])
    return agent, trace


def bounded_owner_turns(agent, owners, trace, *, messages=None, before_turn=None):
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("Task timeout")))
    signal.alarm(PARAMETERS["timeout_s"])
    try:
        history = run_owner_turns(agent, owners, messages=messages, before_turn=before_turn,
                                  after_turn=lambda index, history: trace.update(messages=history))
        trace["messages"] = history
        return history
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def factory():
    """Rebuild only from the engine-validated private context, never a registry path."""
    import mirage
    from mirage import core
    from mirage.protect import registry
    from langchain_core.messages import HumanMessage, messages_to_dict

    if not core._sandbox:
        raise ValueError("Native factory requires engine sandbox context")
    original = core._sandbox["call_tool"]
    context = getattr(original, "native_context", None)
    if not isinstance(context, dict) or context.get("start_mode") not in {"replay", "frozen", "initial"}:
        raise ValueError("Validated native replay context required")
    owners, name = context["owner_messages"], context["agent"]
    usage = {"tool_attempts": 0}

    def call_tool(tool, args):
        usage["tool_attempts"] += 1
        if usage["tool_attempts"] > PARAMETERS["max_tool_calls"]:
            raise TimeoutError("Tool call cap reached")
        return original(tool, args)

    call_tool.native_context = context
    call_tool.register_spec = original.register_spec
    core._sandbox["call_tool"] = call_tool

    class CallbackWorld:
        def call(self, tool, args):
            raise RuntimeError("SDK sandbox must route all tools through the engine callback")

    agent, trace = build_native_agent(CallbackWorld(), context["system"], context["model_id"])
    agent = mirage.protect(agent, name=name, owner="benchmark",
                           entrypoint="benchmarks.native_recovery:factory",
                           allow={"tools": sorted(FILE_TOOLS)})

    def invoke_original(task):
        if task != "\n\n".join(owners):
            raise ValueError("Original native task mismatch")
        index = context["owner_index"] if context["start_mode"] == "frozen" else 0
        history = [HumanMessage(content=owner) for owner in owners[:index]]
        status = "failed"
        try:
            out = bounded_owner_turns(agent, owners[index:], trace, messages=history)
            status = "completed"
            return {"messages": out}
        finally:
            original.native_trace = {"status": status, "messages": messages_to_dict(trace["messages"]),
                                     "calls": trace["calls"], "replies": trace["replies"],
                                     "tokens": trace["tokens"] if trace["tokens_known"]
                                     and trace["calls"] == trace["replies"] else None, **usage}

    registry[name] = invoke_original


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
    paths = sorted(world.root.rglob("*"))
    if any(p.is_symlink() for p in paths):
        raise ValueError("Native capture cannot include symlinks")
    return {"files": world.snapshot(),
            "directories": [str(p.relative_to(world.root))
                            for p in paths if p.is_dir()]}


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
        with (self.directory / f"{run_id}.initial.json").open("x", encoding="utf-8") as file:
            json.dump(self.record["initial_world"], file, sort_keys=True, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
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


def grade_native_export(run_dir, initial_world, final_world, messages, status,
                        case, source, case_dir, *, callbacks=()):
    """Materialize exported state solely for the untouched external native grader."""
    native = native_module(source, "harness_adapter/harness_adapter.py", "native_export_seed")
    for state in (initial_world, final_world):
        if set(state) != {"files", "directories"}:
            raise ValueError("Complete native files and directories required")
        if (not isinstance(state["files"], dict) or not isinstance(state["directories"], list)
                or any(not isinstance(c, str) for c in state["files"].values())):
            raise ValueError("Invalid native export")
        for path in [*state["files"], *state["directories"]]:
            if not isinstance(path, str) or native.safe_workspace_rel(path) != path:
                raise ValueError("Export paths must be canonical relative paths")
    world = FileWorld(run_dir, {"world": {"workspace_files": initial_world["files"]}}, native)
    shutil.rmtree(world.root)
    world.root.mkdir()
    for directory in final_world["directories"]:
        world.path(directory).mkdir(parents=True, exist_ok=True)
    for path, text in final_world["files"].items():
        native.write_seed_file(world.root, path, text)
    if export_world(world) != final_world:
        raise ValueError("Incomplete or inconsistent native final-state export")
    world.calls = deepcopy(list(callbacks))
    world.save(case["case_id"], messages, status)
    return grade(world, case, source, case_dir)


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


def run_victim(args):
    """One leased native cell; complete lifecycle claims require separate receipts."""
    from uuid import uuid4

    if not args.lease or time.time() >= args.stop_epoch:
        raise ValueError("Active root lease and cutoff required")
    manifest = json.loads(args.manifest.read_text())
    case_bytes = args.case.read_bytes()
    case = load_case(args.case)
    if manifest["protocol"] != PROTOCOL or manifest["parameters"] != PARAMETERS:
        raise ValueError("Frozen protocol/parameters mismatch")
    if not any(r["case_id"] == case["case_id"] and r["model_id"] == args.model
               and r["arm"] == args.arm and r["split"] == args.split for r in manifest["primary_cells"]):
        raise ValueError("Cell is outside frozen selected matrix")
    if sha256(case_bytes).hexdigest() != manifest["case_serialization_sha256"][case["case_id"]]:
        raise ValueError("Native fixture serialization differs from frozen pin")
    repo = Path(__file__).resolve().parents[1]
    import subprocess
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip():
        raise ValueError("Commit the exact source before inference")
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    native = native_module(args.source, "harness_adapter/harness_adapter.py", "native_victim_seed")
    system = "# Safety Policy" + (args.source / "harness_adapter/templates/skills/openclaw-safety-policy/SKILL.md").read_text().split("# Safety Policy", 1)[1]
    payload = runtime_payload(case, system)
    world = FileWorld(args.output / "runs" / f"{case['case_id']}-{args.arm}-{uuid4().hex[:8]}",
                      {"world": {"workspace_files": payload["initial_files"]}}, native)
    row = result_row(case, args.split, args.arm, args.model, revision(repo))
    row.update(cohort=PROTOCOL, protocol=PROTOCOL, lifecycle=lifecycle_disclosure(),
               manifest_sha256=sha256(args.manifest.read_bytes()).hexdigest(),
               lease=args.lease, provider_requests_include_sdk_recorded_replies=False)
    capture, token, run_id, core = None, None, None, None
    holder = {}
    started, status = time.monotonic(), "failed"
    trace = {"calls": 0, "replies": 0, "tokens": 0, "tokens_known": True, "messages": []}
    try:
        agent, trace = build_native_agent(world, system, args.model,
                                         middleware=[capture_middleware(lambda: holder["capture"])]
                                         if args.arm != "unprotected" else [], stop_epoch=args.stop_epoch)
        if args.arm != "unprotected":
            if os.environ.get("MIRAGE_URL") != args.engine_url or not args.engine_url.startswith("http://127.0.0.1:"):
                raise ValueError("Set explicit isolated MIRAGE_URL before SDK import")
            import mirage
            from mirage import core
            from contracts.models import AgentSpec, Allowlist
            if core.URL != args.engine_url:
                raise ValueError("SDK already imported against another engine")
            name = "native-" + uuid4().hex[:8]
            spec = AgentSpec(name=name, owner="benchmark", tools=[t["name"] for t in payload["tools"]],
                             allow=Allowlist(tools=sorted(FILE_TOOLS)), entrypoint="benchmarks.native_recovery:factory")
            agent = mirage.protect(agent, name=name, owner="benchmark", entrypoint=spec.entrypoint,
                                   allow=spec.allow.model_dump(mode="json"))
            task = "\n\n".join(payload["owner_messages"])
            token = core.start(name, task)
            run_id = core._run.get()["id"]
            response = core._http.get("/runtime")
            response.raise_for_status()
            runtime = response.json()
            row["engine_revision"] = runtime["revision"]
            capture = NativeCapture(args.registry, world, payload, {"run_id": run_id, "task": task},
                                    runtime, spec.model_dump(mode="json"), args.model)
            holder["capture"] = capture
            install_precheck_capture(agent, capture)
            row["evidence_refs"].append("run:" + run_id)
        bounded_owner_turns(agent, payload["owner_messages"], trace,
                            before_turn=capture.owner_turn if capture else None)
        status = "completed"
    except Exception as exc:
        row["unknown_reason"] = type(exc).__name__
    finally:
        if token is not None:
            try:
                core.end(token, None if status == "completed" else RuntimeError("Incomplete native run"))
            except Exception as exc:
                status, row["unknown_reason"] = "failed", "SDKCompletion:" + type(exc).__name__
        if run_id is not None:
            try:
                response = core._http.get("/runs/" + run_id)
                response.raise_for_status()
                info = response.json()
                row["incident_id"] = info.get("incident_id")
                write_json(world.run_dir / "trajectory/engine_run.json", info)
                response = core._http.get("/events")
                response.raise_for_status()
                events = [e for e in response.json() if e.get("run_id") == run_id
                          or row["incident_id"] and e.get("incident_id") == row["incident_id"]]
                write_json(world.run_dir / "trajectory/engine_events.json", events)
            except Exception as exc:
                status, row["unknown_reason"] = "failed", "EngineEvidence:" + type(exc).__name__
        world.save(case["case_id"], trace["messages"], status)
    row.update(calls=trace["calls"], tokens=trace["tokens"] if trace["tokens_known"]
               and trace["calls"] == trace["replies"] else None,
               latency_s=round(time.monotonic() - started, 3), tool_callbacks=len(world.calls))
    try:
        raw, state = grade(world, case, args.source, args.case.parent)
        row.update(native_scores=raw, validation_result=state)
        row["status"] = "completed" if status == "completed" else "unknown"
    except Exception as exc:
        row["unknown_reason"] = "NativeGrader:" + type(exc).__name__
    if args.arm == "full":
        row["status"] = "unknown"
        row["unknown_reason"] = row["unknown_reason"] or "Required engine investigation/verification/original-task restart not established"
    row["evidence_refs"].append(str(world.run_dir))
    with (args.output / "results.jsonl").open("a") as file:
        file.write(json.dumps(row) + "\n")
    print(json.dumps(row))
    return row


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "case", "output", "manifest", "env-file", "registry"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--arm", choices=("unprotected", "gate", "full"), required=True)
    parser.add_argument("--split", choices=("development", "held_out"), required=True)
    parser.add_argument("--engine-url", required=True)
    parser.add_argument("--lease", required=True)
    parser.add_argument("--stop-epoch", type=float, required=True)
    run_victim(parser.parse_args())


if __name__ == "__main__":
    main()
