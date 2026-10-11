"""Offline launcher wiring: real callback, preserved checkpoint, explicit single SDK claim."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mirage import core

from agents import recovery_launcher as launcher
from agents.services import store


@pytest.fixture
def environment(tmp_path, monkeypatch):
    state = {"calendar": [{"description": "Marked untrusted synthetic input"}],
             "contacts": [{"name": "Synthetic attendee"}], "inbox": [], "outbox": []}
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(state))
    request = {"checkpoint_path": str(path),
               "checkpoint_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
               "config": {"DEMO_USER_EMAIL": "user@mirage-demo.com", "MEETING_ASSISTANT_MODEL_ID": "synthetic"},
               "entrypoint": launcher.ENTRYPOINT, "original_run_id": "old", "task": "Original useful task",
               "queued_run_id": "new", "state_output_path": str(tmp_path / "after.json")}
    spec = {"name": "meeting_assistant", "owner": "liam", "entrypoint": launcher.ENTRYPOINT,
            "tools": ["send_email"], "allow": {"tools": ["send_email"], "email_to": ["user@mirage-demo.com"]},
            "legit": {"required": [{"tool": "send_email", "args": {"to": "user@mirage-demo.com"}}]}}
    calls, invocations = [], []
    original = {"id": "old", "agent": "meeting_assistant", "task": request["task"], "status": "killed"}
    running = {**original, "id": "new", "status": "running", "restarted_from": "old"}

    def post(path, body=None, run=None):
        calls.append((path, body.model_dump() if body else None))
        if path == "/runs":
            return {"run_id": "new", "run_token": "synthetic"}
        if path.endswith("/complete"):
            running["status"] = "failed" if body and body.error else "completed"
        if path == "/gateway/check":
            return {"call_id": "call", "decision": "allow", "tool": "send_email", "args": body.args,
                    "layer": "hard_rule", "rule_id": "ALLOW", "explanation": "Synthetic admission"}

    def invoke(graph_input):
        invocations.append(graph_input)
        assert core.start("meeting_assistant", request["task"]) is None
        args = {"to": "user@mirage-demo.com", "subject": "Prep brief", "body": "Useful synthetic brief"}
        core.tool("send_email", args, lambda: store.state()["outbox"].append(args))

    def factory(_):
        core.register(spec["name"], spec["tools"], spec["allow"], spec["entrypoint"], spec["owner"], legit=spec["legit"])
        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr(launcher, "build_factory", factory)
    monkeypatch.setattr(launcher, "get_run", lambda run_id: dict(original if run_id == "old" else running))
    monkeypatch.setattr(core, "_post", post)
    monkeypatch.setattr(store, "reset", lambda *_: pytest.fail("Recovery must not seed or reset services"))
    monkeypatch.setattr(store, "_state", None)
    return request, state, spec, calls, invocations, running


def test_register_before_approval_then_execute_fresh_exact_task_once(environment):
    request, checkpoint, _, calls, invocations, _ = environment
    prepared = launcher.execute(request, "prepare")
    assert [path for path, _ in calls] == ["/agents"] and invocations == []
    assert store.state() == checkpoint
    receipt = launcher.execute({**request, **prepared}, "launch")
    assert calls[1][0] == "/runs" and calls[1][1]["restarted_from"] == "old"
    assert invocations == [{"messages": [("user", request["task"])]}]
    assert receipt["run"]["status"] == "completed"
    assert len(store.state()["outbox"]) == 1
    assert all(store.state()[key] == checkpoint[key] for key in ("calendar", "contacts", "inbox"))
    assert json.loads(Path(request["state_output_path"]).read_text()) == store.state()
    assert [path for path, _ in calls].count("/runs") == 1


def test_actual_protected_graph_claims_once_and_sends_one_preserved_brief(environment, monkeypatch):
    import mirage
    from langchain_core.messages import AIMessage

    from agents.common.testing import call, scripted
    from agents.meeting_assistant.agent import build_agent

    request, checkpoint, spec, calls, _, _ = environment

    def factory(_):
        graph = build_agent(scripted(call("send_email", to="user@mirage-demo.com",
                                          subject="Prep brief", body="Useful synthetic brief"), AIMessage("done")))
        return mirage.protect(graph, name=spec["name"], allow=spec["allow"], owner=spec["owner"],
                              entrypoint=spec["entrypoint"], legit=spec["legit"])

    monkeypatch.setattr(launcher, "build_factory", factory)
    prepared = launcher.execute(request, "prepare")
    result = launcher.execute({**request, **prepared}, "launch")
    assert result["run"]["status"] == "completed"
    assert store.state()["calendar"] == checkpoint["calendar"]
    assert len(store.state()["outbox"]) == 1
    assert [path for path, _ in calls].count("/runs") == 1
    assert [path for path, _ in calls].count("/runs/new/complete") == 1


def test_changed_spec_refused_before_claim(environment):
    request, _, _, calls, invocations, _ = environment
    prepared = launcher.execute(request, "prepare")
    prepared["agent_spec"]["owner"] = "changed"
    with pytest.raises(ValueError, match="AgentSpec changed"):
        launcher.execute({**request, **prepared}, "launch")
    assert [path for path, _ in calls] == ["/agents"] and not invocations


def test_wrong_claim_fails_without_invoking(environment):
    request, _, _, calls, invocations, running = environment
    prepared = launcher.execute(request, "prepare")
    running["restarted_from"] = "different"
    with pytest.raises(ValueError, match="exact running task"):
        launcher.execute({**request, **prepared}, "launch")
    assert running["status"] == "failed" and not invocations
    assert calls[-1] == ("/runs/new/complete", {"error": "ValueError"})


def test_checkpoint_tampering_fails_before_factory(environment):
    request, _, _, calls, _, _ = environment
    request["checkpoint_digest"] = "0" * 64
    with pytest.raises(ValueError, match="checkpoint changed"):
        launcher.execute(request, "prepare")
    assert not calls


def test_duplicate_brief_remains_failed(environment, monkeypatch):
    request, _, _, _, _, running = environment
    prepared = launcher.execute(request, "prepare")
    old = launcher.captured_factory

    def duplicate(entrypoint):
        agent, spec = old(entrypoint)
        invoke = agent.invoke
        def twice(value):
            invoke(value)
            invoke(value)
        agent.invoke = twice
        return agent, spec

    monkeypatch.setattr(launcher, "captured_factory", duplicate)
    with pytest.raises(ValueError, match="exactly one brief"):
        launcher.execute({**request, **prepared}, "launch")
    assert running["status"] == "failed"
