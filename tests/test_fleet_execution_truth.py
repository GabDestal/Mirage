"""Protected fleet boundary checks: fake SDK transport and scripted models, no services."""

import copy
import importlib
import json
import runpy
import threading
from collections import Counter

import httpx
import pytest
from langchain_core.messages import AIMessage
from mirage import core

from agents.common.completion import matches_requirements
from agents.common.testing import scripted
from agents.invoicing import invoices
from agents.pr_reviewer import pull_requests
from agents.services import store


@pytest.fixture
def fleet(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    module = importlib.import_module("agents.run_demo_fleet")
    monkeypatch.setattr(module, "USER_EMAIL", "demo-user@mirage-demo.com")
    monkeypatch.setattr(core, "_sandbox", None)
    monkeypatch.setattr(store, "_state", None)
    monkeypatch.setattr(invoices, "_invoices", None)
    monkeypatch.setattr(pull_requests, "_state", None)
    for name in ("build_meeting_agent", "build_invoicing_agent", "build_outreach_agent",
                 "build_pr_agent"):
        build = getattr(module, name)
        monkeypatch.setattr(module, name, lambda build=build: build(scripted(AIMessage("done"))))
    return module


@pytest.fixture
def transport(monkeypatch):
    """Observe SDK lifecycle requests; terminal human states remain authoritative."""
    specs, runs, completions, starts = {}, {}, [], []
    failures = {"register": None, "start": None, "complete": None}
    lock = threading.Lock()

    def respond(request):
        body = json.loads(request.content) if request.content else {}
        path = request.url.path
        with lock:
            if path == "/agents":
                if body["name"] == failures["register"]:
                    return httpx.Response(503, json={"detail": "synthetic provider secret"})
                specs[body["name"]] = body
            elif path == "/runs":
                starts.append(body["agent"])
                if body["agent"] == failures["start"]:
                    return httpx.Response(503, json={"detail": "synthetic provider secret"})
                run_id = f"run_{len(runs)}"
                runs[run_id] = {**body, "status": "running"}
                return httpx.Response(200, json={"run_id": run_id, "run_token": "synthetic"})
            elif path.endswith("/complete"):
                run_id = path.split("/")[2]
                completions.append((run_id, body))
                if runs[run_id]["agent"] == failures["complete"]:
                    return httpx.Response(503, json={"detail": "synthetic provider secret"})
                if runs[run_id]["status"] == "running":
                    runs[run_id]["status"] = "failed" if body.get("error") else "completed"
            elif path == "/gateway/check":
                return httpx.Response(200, json={
                    "call_id": "call_synthetic", "tool": body["tool"], "args": body["args"],
                    "decision": "allow", "layer": "hard_rule", "explanation": "synthetic allow",
                })
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://synthetic") as client:
        monkeypatch.setattr(core, "_http", client)
        yield specs, runs, completions, starts, failures


def by_agent(runs):
    return {run["agent"]: run for run in runs.values()}


@pytest.mark.parametrize("phase", ["factory", "invoke"])
def test_failed_worker_is_visible_sanitized_and_siblings_complete(fleet, transport, monkeypatch,
                                                               capsys, phase):
    original = fleet.build_invoicing_agent

    def broken():
        if phase == "factory":
            raise RuntimeError("synthetic provider secret")
        graph = original()

        def invoke(*args, **kwargs):
            raise RuntimeError("synthetic provider secret")

        graph.invoke = invoke
        return graph

    monkeypatch.setattr(fleet, "build_invoicing_agent", broken)
    result = fleet.run_fleet()
    _, runs, completions, starts, _ = transport
    assert Counter(starts) == Counter(factory.__name__ for factory, _ in fleet.FLEET)
    assert len(runs) == len(completions) == 4
    assert len({run_id for run_id, _ in completions}) == 4
    assert by_agent(runs)["invoicing"]["status"] == "failed"
    assert all(run["status"] == "completed" for name, run in by_agent(runs).items()
               if name != "invoicing")
    failure = next(body for run_id, body in completions if runs[run_id]["agent"] == "invoicing")
    assert failure["error"]
    output = capsys.readouterr().out
    assert f"invoicing: {phase}_error" in output
    assert "Launched invoicing" not in output
    assert "synthetic provider secret" not in output + json.dumps(completions)
    assert result is False


def test_start_failure_is_not_launched_or_completed_and_siblings_continue(fleet, transport, capsys):
    transport[-1]["start"] = "invoicing"
    result = fleet.run_fleet()
    _, runs, completions, starts, _ = transport
    assert Counter(starts) == Counter(factory.__name__ for factory, _ in fleet.FLEET)
    assert len(runs) == len(completions) == 3
    assert "invoicing" not in by_agent(runs)
    assert all(run["status"] == "completed" for run in runs.values())
    output = capsys.readouterr().out
    assert "invoicing: start_error" in output
    assert "Launched invoicing" not in output
    assert "synthetic provider secret" not in output
    assert result is False


def test_registration_failure_has_no_fabricated_run_and_siblings_continue(fleet, transport, capsys):
    transport[-1]["register"] = "invoicing"
    result = fleet.run_fleet()
    _, runs, completions, starts, _ = transport
    assert "invoicing" not in starts
    assert len(runs) == len(completions) == 3
    assert all(run["status"] == "completed" for run in runs.values())
    output = capsys.readouterr().out
    assert "invoicing: register_error" in output
    assert "Launched invoicing" not in output
    assert "synthetic provider secret" not in output
    assert result is False


def test_completion_delivery_failure_is_not_reported_as_success(fleet, transport, capsys):
    transport[-1]["complete"] = "invoicing"
    result = fleet.run_fleet()
    _, runs, completions, starts, _ = transport
    assert len(starts) == len(runs) == len(completions) == 4
    assert by_agent(runs)["invoicing"]["status"] == "running"
    assert all(run["status"] == "completed" for name, run in by_agent(runs).items()
               if name != "invoicing")
    output = capsys.readouterr().out
    assert "invoicing: completion_error" in output
    assert "invoicing: completed" not in output
    assert "synthetic provider secret" not in output
    assert result is False


@pytest.mark.parametrize("failed_agent,code", [(None, 0), ("invoicing", 1)])
def test_blocking_cli_exit_matches_actual_fleet_outcome(fleet, transport, monkeypatch,
                                                     failed_agent, code):
    transport[-1]["start"] = failed_agent
    for package, builder in (("meeting_assistant", "build_meeting_agent"),
                             ("invoicing", "build_invoicing_agent"),
                             ("outreach", "build_outreach_agent"),
                             ("pr_reviewer", "build_pr_agent")):
        module = importlib.import_module(f"agents.{package}.agent")
        monkeypatch.setattr(module, "build_agent", getattr(fleet, builder))
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(fleet.__file__, run_name="__main__")
    assert exited.value.code == code


def test_success_has_exactly_one_lifecycle_per_protected_invoke(fleet, transport):
    assert fleet.run_fleet() is True
    _, runs, completions, starts, _ = transport
    assert Counter(starts) == Counter(factory.__name__ for factory, _ in fleet.FLEET)
    assert len(runs) == len(completions) == 4
    assert all(run["status"] == "completed" for run in runs.values())
    assert all(not body.get("error") for _, body in completions)


@pytest.mark.parametrize("status", ["killed", "halted", "frozen"])
def test_blocked_preserves_human_state_and_healthy_siblings(fleet, transport, monkeypatch, status):
    original = fleet.build_invoicing_agent

    def blocked_graph():
        graph = original()

        def invoke(*args, **kwargs):
            run = transport[1][core._run.get()["id"]]
            run["status"] = status
            raise core.Blocked("synthetic human stop")

        graph.invoke = invoke
        return graph

    monkeypatch.setattr(fleet, "build_invoicing_agent", blocked_graph)
    assert fleet.run_fleet() is False
    _, runs, completions, _, _ = transport
    assert len(runs) == len(completions) == 4
    assert by_agent(runs)["invoicing"]["status"] == status
    assert all(not body.get("error") for _, body in completions)
    assert all(run["status"] == "completed" for name, run in by_agent(runs).items()
               if name != "invoicing")


def test_nonblocking_requests_do_not_claim_completion(fleet, transport, monkeypatch, capsys):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = fleet.build_invoicing_agent

    def held():
        graph = original()

        def invoke(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            finished.set()

        graph.invoke = invoke
        return graph

    monkeypatch.setattr(fleet, "FLEET", [(fleet.invoicing, fleet.INVOICING_TASK)])
    monkeypatch.setattr(fleet, "build_invoicing_agent", held)
    try:
        assert fleet.run_fleet(blocking=False) is None
        assert entered.wait(5)
        output = capsys.readouterr().out
        assert "Launch requested for invoicing" in output
        assert "Launched" not in output and "completed" not in output
    finally:
        release.set()
        assert finished.wait(5)
        # The worker's completion request must finish before the mock transport closes.
        for thread in threading.enumerate():
            if thread.name == "agent-invoicing":
                thread.join(5)


def effects_for(legit):
    effects = []
    for requirement in legit["required"]:
        if (not requirement.get("nonempty") and not requirement.get("contains")
                and any(e["tool"] == requirement["tool"]
                        and requirement["args"].items() <= e["args"].items() for e in effects)):
            continue
        args = dict(requirement["args"])
        args.update({key: "Useful synthetic text" for key in requirement.get("nonempty", [])})
        args.update({key: " ".join(terms) for key, terms in requirement.get("contains", {}).items()})
        effects.append({"tool": requirement["tool"], "args": args})
    return effects


def declarations(fleet, transport):
    fleet.setup_demo_services()
    for factory, _ in fleet.FLEET:
        factory()
    return {name: spec.get("legit", {}) for name, spec in transport[0].items()}


def test_full_initial_entity_inventory_is_registered_not_one_lucky_effect(fleet, transport):
    wants = declarations(fleet, transport)
    expected = {"meeting_assistant": 2, "invoicing": 4, "outreach": 16, "pr_reviewer": 3}
    for name, count in expected.items():
        assert len(wants[name].get("required", [])) == count
        effects = effects_for(wants[name])
        assert matches_requirements(wants[name], effects)
        for index in range(len(effects)):
            assert not matches_requirements(wants[name], effects[:index] + effects[index + 1:])


def test_meeting_brief_pins_exact_user_clean_titles_times_and_single_email(fleet, transport):
    want = declarations(fleet, transport)["meeting_assistant"]
    effects = effects_for(want)
    assert matches_requirements(want, effects)
    assert "Evil Corp" not in json.dumps(want)
    assert "<system>" not in json.dumps(want)
    assert "10:00" in json.dumps(want) and "14:00" in json.dumps(want)
    assert not matches_requirements(want, effects * 2)
    incomplete = copy.deepcopy(effects)
    incomplete[0]["args"]["body"] = "Renewal call: Contoso Demo at 10:00"
    assert not matches_requirements(want, incomplete)
    incomplete[0]["args"]["to"] += ".attacker"
    assert not matches_requirements(want, incomplete)


def test_requirements_are_frozen_before_concurrent_service_mutations(fleet, transport):
    expected = declarations(fleet, transport)
    store.state()["contacts"][0]["stage"] = "unsubscribed"
    store.state()["contacts"][0]["email"] = "attacker@evil-corp-demo.com"
    store.state()["calendar"].clear()
    for invoice in invoices.all_invoices():
        invoice["reminded"] = True
    for pr in pull_requests.state()["pull_requests"]:
        pr["status"] = "closed"
    for factory, _ in fleet.FLEET:
        factory()
    actual = {name: spec.get("legit", {}) for name, spec in transport[0].items()}
    assert actual == expected
    assert len(actual["invoicing"].get("required", [])) == 4
    assert len(actual["outreach"].get("required", [])) == 16
    assert len(actual["pr_reviewer"].get("required", [])) == 3
