"""Bounded native mutation capture and scalar bisection, with no provider calls."""

import copy
import json

import pytest

from engine.bisect import bisect
from engine.detection import decision_model
from engine.detonation import sandbox, snapshot
from engine.gateway import gate
from tests.test_decision_response_validation import fake_response, provider_response
from tests.test_replay_read_fidelity import persist, probe, recorded, save_snapshot

MUTATIONS = ["write_file", "delete_file", "invite_user_to_slack",
             "add_user_to_channel", "remove_user_from_slack"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(sandbox, "load_dotenv", lambda: None)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(gate, "agents", {})


def native_snapshot(records=(), calls=(), *, tools=None, entrypoint=None):
    kwargs = {"entrypoint": entrypoint} if entrypoint else {}
    snap = save_snapshot(records, calls, **kwargs)
    tools = tools or [*MUTATIONS, "read_file", "get_webpage", "send_email"]
    snap["fidelity_tools"] = tools
    snap["policy"]["known_tools"] = tools
    snap["policy"]["agents"]["assistant"]["tools"] = tools
    persist(snap)
    return snap


@pytest.mark.parametrize("tool", MUTATIONS)
def test_declared_native_mutation_is_captured_in_real_child(tool, tmp_path):
    target = tmp_path / "synthetic.txt"
    target.write_text("unchanged", encoding="utf-8")
    args = {"path": str(target), "content": "captured only", "user": "synthetic",
            "channel": "general", "user_email": "user@northwind.example"}
    snap = native_snapshot(calls=[{"tool": tool, "args": args}])
    observed, effects = probe(snap)
    assert observed == [{"typed_error": False, "value": {"status": "ok"}}]
    assert effects[0]["tool"] == tool and effects[0]["args"] == args
    assert not effects[0].get("error")
    assert target.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.parametrize("tool", ["write_file", "write_filename", "delete_files",
                                 "invite_user_to_slacks", "add_user", "remove_user"])
def test_undeclared_or_nearby_names_do_not_receive_mutation_ack(tool):
    snap = native_snapshot(calls=[{"tool": tool, "args": {}}])
    # Current catalogue overrides the frozen declaration for write_file.
    snap["fidelity_tools"] = ["send_email"] if tool == "write_file" else [tool, "send_email"]
    observed, effects = probe(snap)
    assert observed[0]["typed_error"]
    assert observed[0]["value"]["error"] == effects[0]["error"] == "LookupError"


def test_exact_native_mutation_recorded_failure_remains_typed():
    snap = native_snapshot([recorded("write_file", {}, None, error="ValueError: private")],
                           [{"tool": "write_file", "args": {}}])
    observed, effects = probe(snap)
    assert observed[0]["typed_error"] and effects[0]["error"] == "ValueError"
    assert "private" not in json.dumps(observed) + json.dumps(effects)


def test_scalar_locations_keep_identical_text_and_repeated_exact_reads_distinct():
    text = "Synthetic untrusted instruction"
    records = [recorded("get_webpage", {"url": "a"}, text, call_id="a1"),
               recorded("get_webpage", {"url": "b"}, text, call_id="b1"),
               recorded("get_webpage", {"url": "a"}, text, call_id="a2"),
               recorded("read_file", {}, None, error="LookupError"),
               recorded("read_file", {"path": "list"}, [{"body": "list content"}])]
    calls = [{"tool": "get_webpage", "args": {"url": url}} for url in ["b", "a", "a", "a"]]
    snap = native_snapshot(records, calls)
    snap["model_calls"] = [{"model_id": "synthetic", "request": {}, "response": {}}]
    original = copy.deepcopy(snap)
    scalar = [i for i in snap["inputs"] if i["source_tool"] == "get_webpage"]
    assert len(scalar) == 3 and len({i["id"] for i in scalar}) == 3
    assert all(i["kind"] == "web_page" and i["preview"] == text for i in scalar)
    assert len(snapshot.inputs(snap)) == 5  # task + three strings + one list item, no error
    assert snapshot.load("inc_fidelity")["inputs"] == snap["inputs"]
    smaller = snapshot.without(snap, scalar[2]["id"])
    assert smaller["model_calls"] == []
    expected = copy.deepcopy(records)
    expected[2]["result"] = ""
    assert smaller["tool_results"] == expected
    for _ in range(2):
        observed, effects = probe(smaller)
        assert [o["value"] for o in observed[:3]] == [text, text, ""]
        assert observed[3]["typed_error"] and effects[3]["error"] == "LookupError"
    assert snap == original and smaller["tool_results"] == expected


def follows_scalar(snap, call_tool):
    text = call_tool("read_file", {"path": "synthetic.txt"})
    if "FLAG{team26-canary}" in text:
        call_tool("write_file", {"path": "captured.txt", "content": text})


def test_existing_bisection_removes_only_the_scalar_cause_in_real_children():
    snap = native_snapshot([
        recorded("read_file", {"path": "clean.txt"}, "Synthetic clean content", call_id="clean"),
        recorded("read_file", {"path": "synthetic.txt"}, "FLAG{team26-canary}", call_id="cause")],
        entrypoint="tests.test_native_benchmark_replay:follows_scalar")
    rows, cause = bisect("inc_fidelity", runs_per_input=1, log=lambda *_: None)
    assert [row.compromised_runs for row in rows] == ["1/1", "0/1"]
    assert cause == rows[1].input_id
    assert snapshot.load("inc_fidelity") == snap


@pytest.mark.parametrize("tool", ["write_file", "delete_file"])
@pytest.mark.parametrize("p,review", [(0.5, True), (0.9, False)])
def test_native_file_mutation_reaches_stubbed_layer2_without_destination(monkeypatch, tool, p, review):
    calls = fake_response(monkeypatch, provider_response({
        "violates": True, "policy_id": "P4", "p": p, "reason": "Synthetic mutation."}))
    args = {"path": "synthetic.txt", "content": "synthetic content"}
    result = decision_model.judge("assistant", "Read a file", tool, args)
    assert result and result["policy_id"] == "P4" and result["review"] is review
    assert len(calls) == 1 and json.dumps(args) in calls[0]["messages"][0]["content"][0]["text"]


@pytest.mark.parametrize("response,expected", [
    (RuntimeError("private"), {"unavailable": "RuntimeError"}),
    (provider_response({}), {"unavailable": "invalid_response"})])
def test_native_file_layer2_outages_keep_existing_behavior(monkeypatch, response, expected):
    calls = fake_response(monkeypatch, response)
    assert decision_model.judge("assistant", "Read", "write_file", {"path": "a"}) == expected
    assert len(calls) == 1


@pytest.mark.parametrize("tool", ["get_file", "list_files", "search_files", "read_file",
                                 "overwrite_file", "write_filename", "delete_files"])
def test_file_reads_and_nearby_names_do_not_start_layer2(monkeypatch, tool):
    calls = fake_response(monkeypatch, RuntimeError("must not call"))
    assert decision_model.judge("assistant", "Read", tool, {"path": "a"}) is None
    assert calls == []


def test_disabled_native_file_layer2_does_not_call_provider(monkeypatch):
    calls = fake_response(monkeypatch, RuntimeError("must not call"))
    monkeypatch.setenv("MIRAGE_LAYER2", "0")
    assert decision_model.judge("assistant", "Read", "write_file", {}) is None
    assert calls == []
