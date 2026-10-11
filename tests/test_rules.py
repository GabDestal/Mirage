"""Rules intersect existing authority and reuse the gate/verifier evaluator."""

import copy

import pytest

from contracts.models import AgentSpec, Allowlist
from engine import rules
from engine.detection.rules import POLICY, hard_rule, hard_rules
from engine.detonation import sandbox

USER = "user@synthetic.example"
OTHER = "other@synthetic.example"
SPEC = AgentSpec(name="meeting_assistant", owner="synthetic-operator",
                 tools=["read_calendar", "send_email", "fetch_url", "crm_export"],
                 allow=Allowlist(tools=["read_calendar", "send_email", "fetch_url"],
                                email_to=[USER, OTHER], url_hosts=["synthetic.example"]),
                 entrypoint="tests.sandbox_agents:ignores_invite")


def restriction(spec=SPEC):
    return {"version": "synthetic-revision", **rules.validate(
        spec.name, Allowlist(tools=["read_calendar", "send_email", "fetch_url"],
                             email_to=[USER]), spec, POLICY)}


def test_registered_noncanonical_role_keeps_its_legitimate_baseline():
    policy = rules.base_policy(SPEC.name, SPEC, POLICY)
    assert hard_rule(SPEC.name, "send_email", {"to": USER}, policy) is None
    assert hard_rule(SPEC.name, "read_calendar", {}, policy) is None
    assert "constraints" not in policy


def test_canonical_exact_role_remains_conjunctive():
    spec = SPEC.model_copy(update={"name": "assistant"}, deep=True)
    policy = rules.base_policy(spec.name, spec, POLICY)
    assert hard_rule(spec.name, "send_email", {"to": USER}, policy)[0] == "DEST_NOT_ALLOWED"
    assert hard_rule(spec.name, "crm_export", {}, policy)[0] == "TOOL_NOT_ALLOWED"


@pytest.mark.parametrize("allow", [
    Allowlist(tools=["crm_export"], email_to=[USER]),
    Allowlist(tools=["made_up_tool"], email_to=[USER]),
    Allowlist(tools=["send_email"], email_to=["outside@synthetic-attacker.example"]),
    Allowlist(tools=["send_email"], email_to=["synthetic.example"]),
    Allowlist(tools=["send_email"], email_to=["*@synthetic.example"]),
    Allowlist(tools=["send_email"], email_to=[USER], url_hosts=["synthetic.example"]),
])
def test_rule_cannot_broaden_role_or_use_arbitrary_destinations(allow):
    with pytest.raises(ValueError):
        rules.validate(SPEC.name, allow, SPEC, POLICY)


@pytest.mark.parametrize("tool,args,expected", [
    ("send_email", {"to": USER}, None),
    ("send_email", {"to": OTHER}, "DEST_NOT_ALLOWED"),
    ("send_email", {"to": USER, "bcc": OTHER}, "DEST_NOT_ALLOWED"),
    ("send_email", {"to": USER, "body": POLICY["canary"]}, "CANARY"),
    ("send_email", {"to": USER, "body": [f"c{i}@records.example" for i in range(6)]},
     "BULK_RECORDS"),
    ("fetch_url", {"url": "https://child.synthetic.example/brief"}, None),
    ("fetch_url", {"url": "https://synthetic.example.attacker.example/brief"}, "DEST_NOT_ALLOWED"),
    ("crm_export", {}, "TOOL_NOT_ALLOWED"),
])
def test_overlay_shared_evaluator_preserves_all_hard_rules(tool, args, expected):
    baseline = rules.base_policy(SPEC.name, SPEC, POLICY)
    policy = rules.overlay(baseline, SPEC.name, restriction())
    hit = hard_rule(SPEC.name, tool, args, policy)
    assert (hit[0] if hit else None) == expected
    effect = {"tool": tool, "args": args}
    snap = {"agent": SPEC.name, "policy": policy}
    assert bool(sandbox.violations(snap, effect, [policy])) == bool(hit)
    assert baseline == rules.base_policy(SPEC.name, SPEC, POLICY)
    assert rules.effective_allow(SPEC.name, policy).email_to == [USER]
    assert rules.effective_allow(SPEC.name, policy).url_hosts == ["synthetic.example"]


def test_later_registration_tightening_cannot_be_broadened_by_an_older_rule():
    rule = restriction()
    changed = SPEC.model_copy(deep=True)
    changed.allow.email_to = [OTHER]
    policy = rules.overlay(rules.base_policy(SPEC.name, changed, POLICY), SPEC.name, rule)
    assert hard_rule(SPEC.name, "send_email", {"to": USER}, policy)[0] == "DEST_NOT_ALLOWED"
    assert rules.effective_allow(SPEC.name, policy).email_to == []


def test_saved_policy_is_independent_of_mutable_draft_and_registration():
    spec, rule = SPEC.model_copy(deep=True), restriction()
    pinned = rules.overlay(rules.base_policy(spec.name, spec, POLICY), spec.name, rule)
    original = copy.deepcopy(pinned)
    spec.allow.email_to.append("outside@synthetic-attacker.example")
    rule["allow"]["email_to"].append(OTHER)
    assert pinned == original
    assert {r for r, _ in hard_rules(spec.name, "send_email", {"to": OTHER}, pinned)} == {
        "DEST_NOT_ALLOWED"}
