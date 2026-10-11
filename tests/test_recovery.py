"""Recovery proof checks use synthetic ledgers; no service or model calls."""

from datetime import UTC, datetime

import pytest

from agents.common.completion import meeting_requirements
from contracts.models import AgentSpec, Event
from engine.api import recovery
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, USER


def legit():
    return meeting_requirements([{"title": "Q4 sync", "start": "2026-10-11T09:00:00"}],
                                USER, "2026-10-11")


def brief():
    return {"to": USER, "subject": "Prep", "body": "Q4 sync at 09:00"}


def event(kind, run="original", **payload):
    return Event(seq=1, ts=datetime.now(UTC), env="prod", run_id=run,
                 type=kind, payload=payload)


def test_successful_ledger_scopes_call_identity_and_excludes_failed_or_blocked_calls():
    request = event("tool.requested", call_id="c1", tool="send_email", args=brief())
    result = event("tool.result", call_id="c1", tool="send_email", result="sent")
    log = [request, result, result,
           event("tool.requested", call_id="c2", tool="send_email", args=brief()),
           event("tool.result", call_id="c2", tool="send_email", error="TimeoutError"),
           event("tool.requested", call_id="blocked", tool="send_email", args=brief()),
           event("tool.result", run="sibling", call_id="blocked", tool="send_email"),
           event("tool.result", call_id="unknown", tool="send_email"),
           event("tool.requested", call_id="mismatch", tool="read_calendar", args={}),
           event("tool.result", call_id="mismatch", tool="send_email")]
    assert recovery.successful_effects("original", log) == [{"tool": "send_email", "args": brief()}]


@pytest.mark.parametrize("declaration", [{}, {"tool": "send_email", "to": USER},
                                        {"required": []}, {"required": [{"tool": "send_email"}]}])
def test_incomplete_completion_declaration_is_refused(declaration):
    assert not recovery.complete_meeting_declaration(declaration)


def test_complete_declaration_requires_exactly_one_grounded_brief():
    assert recovery.complete_meeting_declaration(legit())
    changed = legit()
    changed["required"][0]["count"] = 2
    assert not recovery.complete_meeting_declaration(changed)


@pytest.mark.parametrize("field,value", [("nonempty", None), ("nonempty", [{}]),
                                        ("contains", {"body": [None]}),
                                        ("contains", {"body": []}), ("args", None)])
def test_malformed_story_declaration_fails_closed(field, value):
    declaration = legit()
    declaration["required"][0][field] = value
    assert not recovery.complete_meeting_declaration(declaration)


def record(tool, args, *, run="restarted", error=None):
    call = gate.next_id("call")
    events.emit("tool.requested", {"call_id": call, "tool": tool, "args": args}, run_id=run)
    events.emit("tool.result", {"call_id": call, "tool": tool, "result": "ok", "error": error},
                run_id=run)


def test_prior_write_guard_uses_original_successful_results_not_sibling_or_attempts():
    events.emit("tool.requested", {"call_id": "blocked", "tool": "send_email", "args": brief()},
                run_id="original")
    record("send_email", brief(), run="sibling")
    record("send_email", brief(), run="original", error="TimeoutError")
    record("read_calendar", {}, run="original")
    assert recovery.no_prior_writes("original")
    record("send_email", brief(), run="original")
    assert not recovery.no_prior_writes("original")


@pytest.mark.parametrize("effect", ["missing", "failed", "unrelated", "duplicate", "unsafe", "useful"])
def test_useful_completion_requires_one_successful_safe_expected_brief(effect):
    spec = AgentSpec.model_validate({**AGENT, "legit": legit()})
    run = gate.LiveRun(id="restarted", agent=spec.name, task="Prep", admitted_spec=spec)
    if effect != "missing":
        args = brief()
        if effect == "unrelated":
            args["body"] = "Unrelated email"
        elif effect == "unsafe":
            args["body"] += " FLAG{team26-canary}"
        record("send_email", args, error="TimeoutError" if effect == "failed" else None)
        if effect == "duplicate":
            record("send_email", brief())
    assert recovery.useful_completed(run) is (effect == "useful")
