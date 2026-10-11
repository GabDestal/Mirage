"""Native four-tool memory state: provider-free checks, no host fixture writes."""

import copy
import hashlib
import json

import pytest

from engine.detonation import child


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


@pytest.fixture
def capture(tmp_path, monkeypatch):
    from contracts.models import AgentSpec
    from engine.api import server
    from engine.gateway import gate
    from engine.store import events

    registry = tmp_path / "registry"
    registry.mkdir()
    monkeypatch.setenv("MIRAGE_NATIVE_FIXTURES", str(registry))
    spec = AgentSpec(name="native", owner="test", tools=sorted(child.FILE_TOOLS),
                     allow={"tools": sorted(child.FILE_TOOLS)},
                     entrypoint="benchmarks.native_recovery:factory")
    owners = ["Inspect the local files.", "Finish the report."]
    run = gate.LiveRun(id=gate.next_id("run"), agent=spec.name,
                       task="\n\n".join(owners), admitted_spec=spec,
                       entrypoint=spec.entrypoint, model_id="offline", status="running")
    run.model_calls = [{"model_id": "offline", "request": {
        "system": "Fixture policy", "tools": sorted(child.FILE_TOOLS),
        "messages": [{"type": "human", "data": {"content": owners[0]}}]},
        "response": {"messages": []}}]
    initial = world().snapshot()
    initial["files"]["context/equal.md"] = "A"
    initial["files"]["data.json"] = '{"value": 3}'
    fixture = child.NativeFileWorld(**initial)
    callbacks = []
    for tool, args in [("write_file", {"path": "outputs/prefix.md", "content": "once"}),
                       ("read_file", {"path": "context/a.md"}),
                       ("read_file", {"path": "data.json"})]:
        receipt = gate.check(run, tool, args)
        assert receipt.decision == "allow"
        result = fixture.call(tool, args)
        from langchain_core.messages import ToolMessage
        from mirage.adapters.langchain import _content
        result = _content(ToolMessage(content=result if isinstance(result, str) else json.dumps(result),
                                      tool_call_id=receipt.call_id))
        gate.record_result(run, receipt.call_id, tool, result)
        callbacks.append({"tool": tool, "args": args, "result": result, "error": None,
                          "native_error": None, "model_call_id": None})
    data = {"version": 1, "run_id": run.id, "agent": run.agent,
            "stream_epoch": server.INSTANCE_ID + ":" + events.read_batch()[0],
            "task_sha256": digest(run.task),
            "admitted_spec_sha256": digest(spec.model_dump(mode="json")),
            "initial_world": initial, "initial_sha256": digest(initial),
            "frozen_world": fixture.snapshot(), "frozen_sha256": digest(fixture.snapshot()),
            "callbacks": callbacks, "owner_messages": owners, "owner_index": 0,
            "system": "Fixture policy", "model_id": "offline"}
    path = registry / (run.id + ".json")

    def publish():
        path.write_text(json.dumps(data))
        (registry / (run.id + ".initial.json")).write_text(json.dumps(initial))

    publish()
    return run, data, path, publish


def world(files=None, directories=()):
    return child.NativeFileWorld(files or {".env": "MODE=unsafe\n", "context/a.md": "A"},
                                 directories)


def test_reads_creates_overwrites_and_utf8_results_are_actual_state():
    fixture = world()
    assert fixture.call("read_file", {"path": "workspace/.env"}) == "MODE=unsafe\n"
    assert fixture.call("list_dir", {"path": "/workspace/"}) == [
        {"path": ".env", "type": "file"}, {"path": "context", "type": "directory"}]
    args = {"path": "workspace/outputs/report.md", "content": "Résumé"}
    assert fixture.call("write_file", args) == {"ok": True, "path": args["path"], "bytes": 8}
    assert fixture.call("read_file", {"path": "/workspace/outputs/report.md"}) == "Résumé"
    assert fixture.call("list_dir", {"path": "outputs"}) == [
        {"path": "outputs/report.md", "type": "file"}]
    fixture.call("write_file", {"path": "outputs/report.md", "content": "replacement"})
    assert fixture.snapshot()["files"]["outputs/report.md"] == "replacement"


def test_delete_directory_is_recursive_missing_delete_succeeds_empty_parent_remains():
    fixture = world()
    fixture.call("write_file", {"path": "context/sub/b.md", "content": "B"})
    assert fixture.call("delete_file", {"path": "workspace/context/sub"}) == {
        "ok": True, "path": "workspace/context/sub", "deleted": True}
    with pytest.raises(FileNotFoundError):
        fixture.call("read_file", {"path": "context/sub/b.md"})
    fixture.call("delete_file", {"path": "context/a.md"})
    assert fixture.call("list_dir", {"path": "context"}) == []
    fixture.call("delete_file", {"path": "missing"})


@pytest.mark.parametrize("path", ["", ".", "/", "workspace", "workspace/",
                                   "/workspace", "/workspace/"])
def test_root_aliases_stay_confined_and_cannot_be_deleted_or_written(path):
    fixture = world()
    assert fixture.call("list_dir", {"path": path})
    with pytest.raises(ValueError):
        fixture.call("delete_file", {"path": path})
    with pytest.raises(IsADirectoryError):
        fixture.call("write_file", {"path": path, "content": "no"})


@pytest.mark.parametrize("path", ["../outside", "workspace/../../outside", "a/../b",
                                   "workspace\\..\\outside", "/workspace/../outside"])
def test_traversal_is_rejected_without_mutating_state(path):
    fixture = world()
    before = fixture.snapshot()
    with pytest.raises(RuntimeError):
        fixture.call("write_file", {"path": path, "content": "no"})
    assert fixture.snapshot() == before


def test_absolute_paths_are_logical_aliases_never_host_files(tmp_path):
    target = tmp_path / ".env"
    target.write_text("host data")
    fixture = world()
    fixture.call("write_file", {"path": str(target), "content": "inert fixture data"})
    assert fixture.call("read_file", {"path": str(target)}) == "inert fixture data"
    assert target.read_text() == "host data"


def test_errors_and_file_directory_conflicts_preserve_state():
    fixture = world()
    before = fixture.snapshot()
    for tool, args, error in [
        ("read_file", {"path": "missing"}, FileNotFoundError),
        ("list_dir", {"path": "missing"}, FileNotFoundError),
        ("read_file", {"path": "context"}, IsADirectoryError),
        ("list_dir", {"path": ".env"}, NotADirectoryError),
        ("read_file", {"path": ".env/child"}, NotADirectoryError),
        ("list_dir", {"path": ".env/child"}, NotADirectoryError),
        ("write_file", {"path": ".env/child", "content": "no"}, FileExistsError),
        ("write_file", {"path": ".env/sub/child", "content": "no"}, NotADirectoryError),
        ("write_file", {"path": "context", "content": "no"}, IsADirectoryError),
        ("write_file", {"path": "a", "content": 3}, TypeError),
        ("read_file", {}, KeyError),
        ("shell", {"path": "."}, ValueError),
    ]:
        with pytest.raises(error):
            fixture.call(tool, args)
        assert fixture.snapshot() == before


def test_fresh_worlds_and_returned_snapshots_are_independent_of_immutable_source():
    seed = {".env": "MODE=unsafe\n", "context/a.md": "A"}
    original = copy.deepcopy(seed)
    a, b = world(seed), world(seed)
    a.call("write_file", {"path": ".env", "content": "MODE=safe\n"})
    returned = a.snapshot()
    returned["files"][".env"] = "tampered"
    assert a.call("read_file", {"path": ".env"}) == "MODE=safe\n"
    assert b.call("read_file", {"path": ".env"}) == original[".env"]
    assert seed == original


def test_empty_directories_survive_round_trip():
    a = world(directories=["empty", "empty/nested"])
    state = a.snapshot()
    b = child.NativeFileWorld(**state)
    assert b.snapshot() == state
    assert b.call("list_dir", {"path": "empty"}) == [
        {"path": "empty/nested", "type": "directory"}]


@pytest.mark.parametrize("files,dirs", [({"../outside": "no"}, []),
                                       ({"a": "file", "a/b": "no"}, []),
                                       ({"a": "file"}, ["a"]), ({"a": {}}, [])])
def test_invalid_seed_is_rejected(files, dirs):
    with pytest.raises((ValueError, TypeError, NotADirectoryError, RuntimeError)):
        child.NativeFileWorld(files, dirs)


def test_four_tool_results_errors_and_directory_state_match_exact_w3(tmp_path):
    from pathlib import Path

    from benchmarks.harnessrisk import FileWorld, native_module

    source = Path("/tmp/mirage-benchmaxing/run_1d89fe10e4c5/c3-source/HarnessRisk")
    native = native_module(source, "harness_adapter/harness_adapter.py", "native_world_parity")
    disk = FileWorld(tmp_path / "native", {"world": {"workspace_files": {
        "workspace/a": "A", "workspace/context/b": "B"}}}, native)
    memory = child.NativeFileWorld(disk.snapshot())
    calls = [("list_dir", {"path": "/workspace/"}),
             ("write_file", {"path": "outputs/report.md", "content": "Résumé"}),
             ("read_file", {"path": "workspace/outputs/report.md"}),
             ("write_file", {"path": "outputs/report.md", "content": "replacement"}),
             ("write_file", {"path": "a/child", "content": "no"}),
             ("write_file", {"path": "a/sub/child", "content": "no"}),
             ("read_file", {"path": "a/child"}),
             ("list_dir", {"path": "a/child"}),
             ("write_file", {"path": "../outside", "content": "no"}),
             ("read_file", {"path": "context"}),
             ("list_dir", {"path": "a"}),
             ("delete_file", {"path": "context/b"}),
             ("list_dir", {"path": "context"}),
             ("delete_file", {"path": "context"}),
             ("list_dir", {"path": "context"}),
             ("delete_file", {"path": "absent"}),
             ("delete_file", {"path": "outputs"}),
             ("read_file", {"path": "outputs/report.md"})]
    for tool, args in calls:
        results = []
        for fixture in (disk, memory):
            try:
                results.append(fixture.call(tool, args))
            except (OSError, RuntimeError) as exc:
                results.append(type(exc).__name__)
        assert results[0] == results[1], (tool, args, results)
        assert memory.snapshot()["files"] == disk.snapshot()
        assert memory.snapshot()["directories"] == sorted(
            str(p.relative_to(disk.root)) for p in disk.root.rglob("*") if p.is_dir())


def test_capture_copies_complete_bound_world_before_gate_queues_proof(capture, monkeypatch):
    from contracts.models import Snapshot
    from engine.detonation import jobs, snapshot
    from engine.gateway import gate

    run, data, path, _ = capture
    observed = []
    monkeypatch.setattr(jobs, "automatic", lambda incident, _: observed.append(snapshot.load(incident)))
    receipt = gate.check(run, "write_file", {"path": "blocked", "content": "FLAG{team26-canary}"})
    assert receipt.decision == "freeze" and run.status == "frozen"
    saved = snapshot.load(run.incident_id)
    envelope = saved["inputs"][0]["item"]["_native_file_world"]
    assert envelope["data"]["frozen_world"] == data["frozen_world"]
    assert envelope["incident_id"] == run.incident_id and envelope["run_id"] == run.id
    assert [r["call_id"] for r in envelope["data"]["callbacks"]] == [
        r["call_id"] for r in run.tool_results]
    assert envelope["original_item"] is None
    assert observed == [saved]
    Snapshot.model_validate(saved)
    path.write_text("changed after freeze")
    assert snapshot.load(run.incident_id) == saved


@pytest.mark.parametrize("field", ["run_id", "agent", "stream_epoch", "task_sha256",
                                   "admitted_spec_sha256", "initial_sha256", "frozen_sha256",
                                   "owner_index", "system", "model_id"])
def test_capture_binding_mismatch_is_rejected(capture, field):
    from engine.detonation import snapshot

    run, data, _, publish = capture
    data[field] = 99 if field == "owner_index" else "mismatch"
    publish()
    with pytest.raises(ValueError):
        snapshot.save(run, "inc_native", run.policy, runner="mirage.sandbox:run")
    assert not (snapshot.SNAP_DIR / "inc_native.json").exists()


@pytest.mark.parametrize("change", ["missing", "ahead", "stale", "result", "error",
                                    "unknown", "state", "directory", "initial"])
def test_missing_partial_or_modified_capture_never_publishes_proof(capture, change):
    from engine.detonation import snapshot

    run, data, path, publish = capture
    if change == "ahead":
        data["callbacks"].append(copy.deepcopy(data["callbacks"][0]))
    elif change == "stale":
        data["callbacks"].pop()
    elif change in {"result", "error"}:
        data["callbacks"][0][change] = "changed"
    elif change == "unknown":
        data["oracle_scorer"] = {"answer": "forbidden"}
    elif change in {"state", "directory"}:
        if change == "state":
            data["frozen_world"]["files"]["outputs/prefix.md"] = "different"
        else:
            data["frozen_world"]["directories"].append("extra")
        data["frozen_sha256"] = digest(data["frozen_world"])
    elif change == "initial":
        data["initial_world"]["files"]["context/a.md"] = "changed"
        data["initial_sha256"] = digest(data["initial_world"])
    publish()
    if change == "missing":
        path.unlink()
    elif change == "initial":
        initial = copy.deepcopy(data["initial_world"])
        initial["files"]["context/a.md"] = "A"
        (path.parent / (run.id + ".initial.json")).write_text(json.dumps(initial))
    with pytest.raises((ValueError, FileNotFoundError)):
        snapshot.save(run, "inc_native", run.policy, runner="mirage.sandbox:run")
    assert not (snapshot.SNAP_DIR / "inc_native.json").exists()


def native_probe(snap, call_tool):
    from contracts.models import ToolResult

    context = call_tool.native_context
    tools = snap.get("native_current_tools", sorted(child.FILE_TOOLS))
    call_tool.register_spec({"name": snap["agent"], "owner": "test", "tools": tools,
                             "allow": {"tools": tools}, "entrypoint": snap["entrypoint"]})
    if context["start_mode"] == "replay":
        for record in snap["tool_results"]:
            call_tool(record["tool"], record["args"])
    observed = []
    for tool, args in snap.get("native_calls", []):
        result = call_tool(tool, args)
        observed.append({"error": result.error} if isinstance(result, ToolResult) else result)
    call_tool("write_file", {"path": "observed.json", "content": json.dumps(observed)})
    if snap.get("native_crash"):
        raise RuntimeError("Synthetic crash after native writes")


def native_snap(capture):
    from engine.detonation import snapshot

    run = capture[0]
    return snapshot.save(run, "inc_native", run.policy,
                         runner="tests.test_native_file_world:native_probe")


def test_real_children_serve_state_and_keep_frozen_source_and_host_independent(capture, tmp_path):
    from engine.detonation import sandbox

    snap = native_snap(capture)
    original = copy.deepcopy(snap)
    host = tmp_path / ".env"
    host.write_text("host unchanged")
    snap["native_calls"] = [
        ("read_file", {"path": "workspace/.env"}),
        ("write_file", {"path": ".env", "content": "MODE=safe\n"}),
        ("read_file", {"path": ".env"}),
        ("list_dir", {"path": "workspace/outputs"}),
        ("write_file", {"path": "outputs/report.md", "content": "Actual report"}),
        ("read_file", {"path": "outputs/report.md"}),
        ("delete_file", {"path": "outputs/report.md"}),
        ("read_file", {"path": "outputs/report.md"}),
    ]
    states = []
    for _ in range(3):
        state = {}
        effects, error = sandbox.run_once(snap, final_state=state)
        assert error is None, error
        values = json.loads(state["files"]["observed.json"])
        assert values[0] == "MODE=unsafe\n" and values[2] == "MODE=safe\n"
        assert values[3] == [{"path": "outputs/prefix.md", "type": "file"}]
        assert values[5] == "Actual report" and values[7] == {"error": "FileNotFoundError"}
        assert effects[-2]["error"] == values[7]["error"]
        assert state["completed"] and state["frozen_reached"]
        assert sum(e["args"].get("path") == "outputs/prefix.md" for e in effects) == 1
        assert "outputs/report.md" not in state["files"]
        states.append(state)
    assert [s["state_sha256"] for s in states] == [states[0]["state_sha256"]] * 3
    assert host.read_text() == "host unchanged"
    assert capture[1]["initial_world"] == original["inputs"][0]["item"]["_native_file_world"]["data"]["initial_world"]


@pytest.mark.parametrize("mode,exists", [("frozen", True), ("initial", False)])
def test_explicit_start_modes_do_not_reapply_recorded_prefix(capture, mode, exists):
    from engine.detonation import sandbox

    snap = native_snap(capture)
    snap["native_calls"] = [("read_file", {"path": "outputs/prefix.md"})]
    state = {}
    effects, error = sandbox.run_once(snap, native_mode=mode, final_state=state)
    assert error is None, error
    assert effects[0]["tool"] == "read_file"
    values = json.loads(state["files"]["observed.json"])
    assert values == ["once"] if exists else values == [{"error": "FileNotFoundError"}]
    assert state["start_mode"] == mode and not state["replayed_callbacks"]


def test_precrash_state_is_retained_with_failed_completion(capture):
    from engine.detonation import sandbox

    snap = native_snap(capture)
    snap["native_calls"] = [("write_file", {"path": "outputs/precrash.md", "content": "retained"})]
    snap["native_crash"] = True
    state = {}
    effects, error = sandbox.run_once(snap, final_state=state)
    assert error and "RuntimeError" in error
    assert state["files"]["outputs/precrash.md"] == "retained"
    assert not state["completed"] and state["error"]
    assert any(e["args"].get("path") == "outputs/precrash.md" for e in effects)


def test_current_catalogue_denial_remains_typed_and_ledger_bound(capture):
    from engine.detonation import sandbox

    snap = native_snap(capture)
    snap["native_current_tools"] = ["write_file"]
    snap["native_calls"] = [("read_file", {"path": ".env"}), ("delete_file", {"path": ".env"})]
    state = {}
    effects, error = sandbox.run_once(snap, native_mode="frozen", final_state=state)
    assert error is None, error
    values = json.loads(state["files"]["observed.json"])
    assert values == [{"error": "LookupError"}] * 2
    assert [e["error"] for e in effects[:2]] == ["LookupError"] * 2
    assert state["files"][".env"] == "MODE=unsafe\n"


def test_scalar_counterfactual_changes_only_exact_native_source_and_keeps_original(capture):
    from engine.detonation import sandbox, snapshot

    snap = native_snap(capture)
    original = copy.deepcopy(snap)
    target = next(i for i in snap["inputs"] if i["source_tool"] == "read_file" and i["preview"] == "A")
    smaller = snapshot.without(snap, target["id"])
    smaller["native_calls"] = [("read_file", {"path": "context/a.md"}),
                                ("read_file", {"path": "context/equal.md"})]
    state = {}
    _, error = sandbox.run_once(smaller, final_state=state)
    assert error is None, error
    assert json.loads(state["files"]["observed.json"]) == ["", "A"]
    assert state["start_mode"] == "initial" and not state["replayed_callbacks"]
    variant = smaller["inputs"][0]["item"]["_native_file_world"]["variant"]
    assert variant["original_snapshot_sha256"] == hashlib.sha256(json.dumps(original).encode()).hexdigest()
    assert snap == original and snapshot.load("inc_native") == original


def test_changed_source_cannot_be_silently_mapped_to_original_input(capture):
    from engine.detonation import snapshot

    snap = native_snap(capture)
    target = next(i for i in snap["inputs"] if i["source_tool"] == "read_file" and i["preview"] == "A")
    envelope = snap["inputs"][0]["item"]["_native_file_world"]
    envelope["data"]["initial_world"]["files"]["context/a.md"] = "changed source"
    envelope["data"]["initial_sha256"] = digest(envelope["data"]["initial_world"])
    envelope["sha256"] = digest({k: v for k, v in envelope.items() if k != "sha256"})
    with pytest.raises(ValueError, match="stale"):
        snapshot.without(snap, target["id"])


def test_paired_w6_sdk_factory_in_actual_jailed_child(capture, monkeypatch):
    import subprocess
    from pathlib import Path

    from langchain_core.messages import AIMessage, messages_to_dict

    from engine.detonation import sandbox

    adapter = Path("/Users/liamszefner/orca/workspaces/Mirage/bench-p2-native-adapter")
    if not adapter.exists():
        pytest.skip("Pinned paired adapter checkout required")
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=adapter, text=True).strip() == "44c0a29a855c4eff9e14587cc9c3cccfc304cb17"
    run, data, _, publish = capture
    calls = [(r["tool"], r["args"]) for r in run.tool_results]
    calls.append(("write_file", {"path": "blocked.md", "content": "FLAG{team26-canary}"}))
    request = copy.deepcopy(run.model_calls[0]["request"])
    run.model_calls = [{"model_id": "offline", "request": request,
                        "response": {"messages": messages_to_dict([AIMessage(content="", tool_calls=[{
                            "name": tool, "args": args, "id": f"offline-{i}"}])])}}
                       for i, (tool, args) in enumerate(calls)]
    publish()
    snap = native_snap(capture)
    snap["runner"] = "mirage.sandbox:run"
    boot = """
import sys, runpy
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/sdk')
sys.path.append(ADAPTER)
from agents.common import model
from agents.common.testing import ScriptedModel, call
from langchain_core.messages import AIMessage
class Offline(ScriptedModel):
    max_tokens: int = 4096
    model_id: str = 'offline'
def offline_model(*args, **kwargs):
    return Offline(messages=iter([AIMessage(content='Inspected.'),
        call('write_file', path='outputs/report.md', content='Actual report'),
        AIMessage(content='Finished.')]))
model.chat_model = offline_model
runpy.run_module('engine.detonation.child', run_name='__main__')
""".replace("ADAPTER", repr(str(adapter)))
    monkeypatch.setattr(sandbox, "BOOT", boot)
    state = {}
    effects, error = sandbox.run_once(snap, final_state=state)
    assert error is None, error
    assert state["files"]["blocked.md"] == "FLAG{team26-canary}"
    assert state["files"]["outputs/report.md"] == "Actual report"
    assert state["frozen_reached"] and state["replayed_callbacks"] == 3
    assert [e["tool"] for e in effects] == [r[0] for r in calls] + ["write_file"]
    trace = state["native_trace"]
    assert trace["status"] == "completed" and trace["calls"] == trace["replies"] == 3
    assert [m["data"]["content"] for m in trace["messages"] if m["type"] == "human"] == data["owner_messages"]


@pytest.mark.parametrize("mode", ["frozen", "initial"])
def test_fresh_native_execution_uses_current_state_after_old_failed_read(capture, mode):
    from engine.detonation import sandbox
    from engine.gateway import gate

    run, data, _, publish = capture
    receipt = gate.check(run, "read_file", {"path": "later.txt"})
    gate.record_result(run, receipt.call_id, "read_file", None, "FileNotFoundError")
    data["callbacks"].append({"tool": "read_file", "args": {"path": "later.txt"},
                              "result": None, "error": "FileNotFoundError",
                              "native_error": "FileNotFoundError", "model_call_id": None})
    args = {"path": "later.txt", "content": "created after failed read"}
    receipt = gate.check(run, "write_file", args)
    fixture = child.NativeFileWorld(**data["frozen_world"])
    result = fixture.call("write_file", args)
    gate.record_result(run, receipt.call_id, "write_file", result)
    data["callbacks"].append({"tool": "write_file", "args": args, "result": result,
                              "error": None, "native_error": None, "model_call_id": None})
    data["frozen_world"] = fixture.snapshot()
    data["frozen_sha256"] = digest(fixture.snapshot())
    publish()
    snap = native_snap(capture)
    snap["native_calls"] = [("read_file", {"path": "later.txt"})]
    if mode == "initial":
        snap["native_calls"].insert(0, ("write_file", args))
    state = {}
    effects, error = sandbox.run_once(snap, native_mode=mode, final_state=state)
    assert error is None, error
    assert json.loads(state["files"]["observed.json"])[-1] == args["content"]
    assert not any(e.get("error") for e in effects)


def test_automatic_style_children_retain_distinct_final_worlds_without_output_dict(capture):
    from concurrent.futures import ThreadPoolExecutor

    from engine.detonation import sandbox, snapshot

    snap = native_snap(capture)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: sandbox.run_once(snap), range(2)))
    assert all(error is None for _, error in results)
    directory = snapshot.SNAP_DIR / "native-proofs" / snap["incident_id"]
    proofs = [json.loads(path.read_text()) for path in directory.glob("*.json")]
    assert len(proofs) == len({p["attempt_id"] for p in proofs}) == 2
    for proof in proofs:
        assert proof["snapshot_id"] == snap["id"] and proof["run_id"] == snap["run_id"]
        assert proof["state"]["files"]["outputs/prefix.md"] == "once"
        assert proof["state"]["completed"] and proof["state"]["frozen_reached"]
        assert len(proof["source_revision"]) == 40
        assert proof["source_sha256"]["engine/detonation/child.py"]
    snap["native_crash"] = True
    snap["native_calls"] = [("write_file", {"path": "precrash.txt", "content": "retained"})]
    _, error = sandbox.run_once(snap)
    assert error
    failed = [json.loads(path.read_text()) for path in directory.glob("*.json")
              if not json.loads(path.read_text())["state"]["completed"]]
    assert len(failed) == 1 and failed[0]["state"]["files"]["precrash.txt"] == "retained"
