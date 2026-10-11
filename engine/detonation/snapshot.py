"""Snapshot: everything a frozen run read, saved at freeze. The sandbox's only input.

File: data/snapshots/<incident_id>.json, shape `Snapshot` in contracts/models.py (validated on save).
`runner` is what the sandbox child calls; None means `entrypoint` itself (engine dev agents).

Each item a read tool returned (one calendar event, one contact...) is one Input. Bisection
removes list items from every tool result, or empties one exactly located scalar string read.
"""

import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from contracts.models import Input, Snapshot
from engine.detonation.child import FILE_TOOLS, WRITE_PREFIXES, WRITE_TOOLS, NativeFileWorld

SNAP_DIR = Path(os.getenv("MIRAGE_SNAPSHOTS", "data/snapshots"))
KINDS = [("calendar", "calendar_event"), ("contact", "crm_record"), ("crm", "crm_record"),
         ("mail", "email"), ("inbox", "email"), ("url", "web_page"), ("web", "web_page")]
NATIVE_ENTRYPOINT = "benchmarks.native_recovery:factory"
NATIVE_KEYS = {"version", "run_id", "agent", "stream_epoch", "task_sha256",
               "admitted_spec_sha256", "initial_world", "initial_sha256", "frozen_world",
               "frozen_sha256", "callbacks", "owner_messages", "owner_index", "system", "model_id"}
CALLBACK_KEYS = {"tool", "args", "result", "error", "native_error", "model_call_id"}


def native_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def native_world(state):
    if (not isinstance(state, dict) or set(state) != {"files", "directories"}
            or not isinstance(state["files"], dict) or not isinstance(state["directories"], list)):
        raise ValueError("Invalid native world")
    world = NativeFileWorld(**state)
    if world.snapshot() != state:
        raise ValueError("Native world is not canonical and complete")
    return world


def native_recorded_value(value):
    # The installed SDK parses JSON ToolMessage content before recording it.
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def _native_capture(run, snap):
    registry = os.getenv("MIRAGE_NATIVE_FIXTURES")
    if not registry or snap["entrypoint"] != NATIVE_ENTRYPOINT:
        return
    from engine.store import events

    spec = run.admitted_spec
    if (spec is None or set(spec.tools) != FILE_TOOLS or set(spec.allow.tools) != FILE_TOOLS
            or not re.fullmatch(r"run_\d+", run.id)):
        raise ValueError("Native capture requires the exact admitted fixture catalogue")
    root = Path(registry).resolve()

    def read(name):
        path = root / name
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError("Native capture registry path escapes root")
        return json.loads(path.read_text(encoding="utf-8"))

    data = read(run.id + ".json")
    server = sys.modules.get("engine.api.server")
    epoch = events.read_batch()[0]
    if (not isinstance(data, dict) or set(data) != NATIVE_KEYS or data["version"] != 1
            or not server or data["stream_epoch"] != server.INSTANCE_ID + ":" + epoch
            or data["run_id"] != run.id or data["agent"] != run.agent
            or data["task_sha256"] != native_hash(run.task)
            or data["admitted_spec_sha256"] != native_hash(spec.model_dump(mode="json"))):
        raise ValueError("Native capture binding mismatch")
    owners, index = data["owner_messages"], data["owner_index"]
    if (not isinstance(owners, list) or not owners or any(not isinstance(m, str) for m in owners)
            or "\n\n".join(owners) != run.task or type(index) is not int
            or not 0 <= index < len(owners) or not run.model_calls):
        raise ValueError("Native owner context mismatch")
    request = run.model_calls[-1]["request"]
    observed = [m["data"]["content"] for m in request.get("messages", []) if m.get("type") == "human"]
    if (observed != owners[:index + 1] or request.get("system") != data["system"]
            or set(request.get("tools", [])) != FILE_TOOLS or data["model_id"] != run.model_id
            or any(m["model_id"] != data["model_id"] for m in run.model_calls)):
        raise ValueError("Native model context mismatch")
    initial = native_world(data["initial_world"])
    native_world(data["frozen_world"])
    if (data["initial_sha256"] != native_hash(data["initial_world"])
            or data["frozen_sha256"] != native_hash(data["frozen_world"])
            or read(run.id + ".initial.json") != data["initial_world"]):
        raise ValueError("Native state hash or immutable initial capture mismatch")
    callbacks = data["callbacks"]
    if not isinstance(callbacks, list) or len(callbacks) != len(run.tool_results):
        raise ValueError("Native callback coverage mismatch")
    if any(call.get("state") == "admitted" for call in run.calls.values()):
        raise ValueError("Native capture has an in-flight callback")
    bound = []
    for callback, record in zip(callbacks, run.tool_results, strict=True):
        if (not isinstance(callback, dict) or set(callback) != CALLBACK_KEYS
                or any(callback[k] != record.get(k) for k in ("tool", "args", "result", "error"))
                or callback["tool"] not in FILE_TOOLS):
            raise ValueError("Native callback recording mismatch")
        call = run.calls.get(record["call_id"], {})
        if call.get("state") != "consumed" or call.get("result") != record:
            raise ValueError("Native callback has no consumed engine authority")
        failure = callback["native_error"]
        if failure is not None and (not isinstance(failure, str) or not re.fullmatch(r"[A-Za-z]+Error", failure)):
            raise ValueError("Invalid native failure category")
        if callback["error"] is None:
            result = initial.call(callback["tool"], callback["args"])
            if native_recorded_value(result) != callback["result"]:
                raise ValueError("Native callback state differs from engine recording")
        elif callback["result"] is not None:
            raise ValueError("Failed native callback contains a successful result")
        bound.append({**callback, "call_id": record["call_id"]})
    if initial.snapshot() != data["frozen_world"]:
        raise ValueError("Native frozen state differs from admitted callbacks")
    envelope = {"version": 1, "snapshot_id": snap["id"], "incident_id": snap["incident_id"],
                "run_id": snap["run_id"], "data": {**data, "callbacks": bound},
                "original_item": snap["inputs"][0]["item"]}
    envelope["sha256"] = native_hash(envelope)
    snap["inputs"][0]["item"] = {"_native_file_world": envelope}


def native_fixture(snap):
    """Only the engine-generated envelope on the original task activates native replay."""
    task = next((i for i in snap["inputs"] if i["id"] == "in_task"), None)
    if not task or not isinstance(task.get("item"), dict) or "_native_file_world" not in task["item"]:
        return None
    envelope = task["item"]["_native_file_world"]
    if (task["kind"] != "user_task" or task["source_tool"] is not None
            or set(task["item"]) != {"_native_file_world"}
            or not isinstance(envelope, dict)
            or set(envelope) - {"version", "snapshot_id", "incident_id", "run_id", "data", "original_item", "sha256", "variant"}
            or not {"version", "snapshot_id", "incident_id", "run_id", "data", "original_item", "sha256"} <= set(envelope)
            or envelope["version"] != 1
            or any(envelope[k] != snap[v] for k, v in (("snapshot_id", "id"), ("incident_id", "incident_id"), ("run_id", "run_id")))
            or envelope["sha256"] != native_hash({k: v for k, v in envelope.items() if k != "sha256"})):
        raise ValueError("Invalid engine native envelope")
    data = envelope["data"]
    if (not isinstance(data, dict) or set(data) != NATIVE_KEYS
            or snap["entrypoint"] != NATIVE_ENTRYPOINT
            or data["run_id"] != snap["run_id"] or data["agent"] != snap["agent"]
            or data["task_sha256"] != native_hash(snap["task"])):
        raise ValueError("Native envelope identity mismatch")
    for name in ("initial", "frozen"):
        native_world(data[name + "_world"])
        if native_hash(data[name + "_world"]) != data[name + "_sha256"]:
            raise ValueError("Native envelope state hash mismatch")
    records = [{k: c[k] for k in ("call_id", "tool", "args", "result", "error")} for c in data["callbacks"]]
    if records != snap["tool_results"]:
        raise ValueError("Native envelope callback history mismatch")
    return copy.deepcopy(envelope)


def _items(result):
    """The list of records inside a tool result: a list, or the one list inside a dict."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        lists = [v for v in result.values() if isinstance(v, list)]
        return lists[0] if len(lists) == 1 else []
    return []


def _text(item, *keys):
    return next((str(item[k]) for k in keys if isinstance(item, dict) and item.get(k)), "")


def _inputs(task, tool_results):
    found = [{"id": "in_task", "kind": "user_task", "label": "User task", "source_tool": None,
              "preview": task[:160], "item": None}]
    seen = []
    for index, r in enumerate(tool_results):
        if r.get("error") is not None:
            continue
        if (isinstance(r["result"], str) and r["tool"] not in WRITE_TOOLS
                and not r["tool"].startswith(WRITE_PREFIXES)):
            # Private item metadata binds equal strings to one exact recorded read.
            found.append({
                "id": f"in_scalar_{len(found):02d}", "kind": "web_page" if any(
                    word in r["tool"] for word in ("url", "web")) else "attachment",
                "source_tool": r["tool"], "label": r["tool"], "preview": r["result"][:160],
                "item": {"_read_locator": {"index": index, "call_id": r["call_id"],
                                          "tool": r["tool"], "args": copy.deepcopy(r["args"])}}})
            continue
        for item in _items(r["result"]):
            if item in seen:
                continue
            seen.append(item)
            kind = next((k for word, k in KINDS if word in r["tool"]), "attachment")
            found.append({
                "id": f"in_{len(found):02d}", "kind": kind, "source_tool": r["tool"],
                "label": _text(item, "title", "name", "subject", "url") or r["tool"],
                "preview": _text(item, "description", "body", "notes", "email")[:160],
                "item": item,
            })
    return found


def save(run, incident_id, policy, entrypoint="", runner=None):
    results = [{"call_id": r["call_id"], "tool": r["tool"], "args": r["args"],
                "result": r["result"] if r.get("error") is None else None,
                "error": r.get("error")} for r in run.tool_results]
    snap = Snapshot(
        id=f"snap_{incident_id.removeprefix('inc_')}", incident_id=incident_id, run_id=run.id,
        agent=run.agent, task=run.task, entrypoint=run.entrypoint or entrypoint, runner=runner,
        system=run.system or None, model_id=run.model_id or None, policy=policy, legit=run.legit,
        taken_at=datetime.now(UTC), model_calls=run.model_calls, tool_results=results,
        inputs=_inputs(run.task, results),
    ).model_dump(mode="json")  # the contract checks the shape before it is written
    _native_capture(run, snap)  # complete immutable capture before publish and automatic queue
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # Publish only a complete, flushed recording; failed writes are never replay inputs.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=SNAP_DIR,
                                         prefix=f".{incident_id}.", suffix=".tmp",
                                         delete=False) as file:
            temporary = Path(file.name)
            json.dump(snap, file, indent=1)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, SNAP_DIR / f"{incident_id}.json")
        directory = os.open(SNAP_DIR, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return snap


def load(incident_id):
    return json.loads((SNAP_DIR / f"{incident_id}.json").read_text(encoding="utf-8"))


def inputs(snap) -> list[Input]:
    return [Input(**{k: v for k, v in i.items() if k != "item"}) for i in snap["inputs"]]


def without(snap, input_id):
    """A copy of the snapshot with one input removed (bisection)."""
    original_hash = hashlib.sha256(json.dumps(snap).encode("utf-8")).hexdigest()
    snap = copy.deepcopy(snap)
    snap["model_calls"] = []  # rerun from the start: recorded replies saw the removed input
    target = next(i for i in snap["inputs"] if i["id"] == input_id)
    native = native_fixture(snap)
    if native is not None and not (target["id"].startswith("in_scalar_")
                                  and target["source_tool"] == "read_file"):
        raise ValueError("Native counterfactual needs an exactly located file read")
    if (target["id"].startswith("in_scalar_") and isinstance(target["item"], dict)
            and set(target["item"]) == {"_read_locator"}):
        locator = target["item"]["_read_locator"]
        for index, r in enumerate(snap["tool_results"]):
            if (locator == {"index": index, "call_id": r["call_id"], "tool": r["tool"],
                           "args": r["args"]} and isinstance(r["result"], str)):
                if native is not None:
                    path = NativeFileWorld.path(r["args"]["path"])
                    data = native["data"]
                    reads = [c for c in data["callbacks"] if c["tool"] == "read_file"
                             and c["error"] is None and NativeFileWorld.path(c["args"]["path"]) == path]
                    if len(reads) != 1 or data["initial_world"]["files"].get(path) != r["result"]:
                        raise ValueError("Native scalar mapping is stale or ambiguous")
                    native["variant"] = {"input_id": input_id, "locator": locator,
                                         "original_snapshot_sha256": original_hash,
                                         "original_envelope_sha256": native["sha256"],
                                         "original_initial_sha256": data["initial_sha256"]}
                    data["initial_world"]["files"][path] = ""
                    data["initial_sha256"] = native_hash(data["initial_world"])
                    data["callbacks"][index]["result"] = ""
                    native["sha256"] = native_hash({k: v for k, v in native.items() if k != "sha256"})
                    snap["inputs"][0]["item"] = {"_native_file_world": native}
                r["result"] = ""
                return snap
    if target["kind"] == "user_task":
        snap["task"] = "(no task)"
    for r in snap["tool_results"]:
        items = _items(r["result"])
        if target["item"] in items:
            items[:] = [x for x in items if x != target["item"]]
    return snap
