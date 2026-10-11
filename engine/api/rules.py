"""The local operator's typed Rules HTTP surface; all decisions stay in the engine."""

from fastapi import APIRouter, HTTPException, Query

from contracts.models import (
    AgentSpec,
    GateDecision,
    HumanRequest,
    RuleDraftRequest,
    RulePreview,
    RulePreviewRequest,
    RuleRevision,
)
from engine import rules
from engine.detection.rules import POLICY, hard_rule
from engine.detonation import jobs
from engine.gateway import gate

router = APIRouter(prefix="/rules")


DEMO_AGENTS = {
    "meeting_assistant": AgentSpec(
        name="meeting_assistant",
        owner="demo",
        tools=["read_calendar", "send_email", "export_contacts", "search_contacts"],
        allow={"tools": ["read_calendar", "send_email", "export_contacts", "search_contacts"],
               "email_to": ["*@mirage-demo.com", "*@synthetic.example", "*@contoso-demo.com"],
               "url_hosts": []},
        entrypoint="tests.sandbox_agents:ignores_invite",
    ),
    "pr_reviewer": AgentSpec(
        name="pr_reviewer",
        owner="demo",
        tools=["read_pull_request", "list_pull_requests", "submit_review"],
        allow={"tools": ["read_pull_request", "list_pull_requests", "submit_review"],
               "email_to": ["*@mirage-demo.com", "*@synthetic.example"],
               "url_hosts": []},
        entrypoint="tests.sandbox_agents:pr_review",
    ),
    "outreach": AgentSpec(
        name="outreach",
        owner="demo",
        tools=["read_calendar", "send_email", "search_contacts"],
        allow={"tools": ["read_calendar", "send_email", "search_contacts"],
               "email_to": ["*@mirage-demo.com", "*@contoso-demo.com", "*@synthetic.example"],
               "url_hosts": []},
        entrypoint="tests.sandbox_agents:outreach",
    ),
    "support": AgentSpec(
        name="support",
        owner="demo",
        tools=["read_ticket", "send_email", "search_contacts"],
        allow={"tools": ["read_ticket", "send_email", "search_contacts"],
               "email_to": ["*@mirage-demo.com", "*@proseware-demo.com", "*@synthetic.example"],
               "url_hosts": []},
        entrypoint="tests.sandbox_agents:support",
    ),
}


def _stream():
    from engine.api import server

    return server._event_batch()[1]


def _writable():
    from engine.api import server

    if server.PUBLIC:
        raise HTTPException(403, "Rule changes require the trusted local operator interface")


def _catalogue():
    from engine.api import server

    stream = _stream()
    registered = {event.payload["name"]: AgentSpec.model_validate(event.payload)
                  for event in stream if event.type == "agent.registered"}
    combined = {**gate.agents, **registered}
    if not combined and server.REPLAY:
        return dict(DEMO_AGENTS)
    return combined


def _spec(agent):
    spec = _catalogue().get(agent)
    if spec is None:
        raise HTTPException(404, f"Agent {agent} is not registered")
    return spec


def _read(version):
    try:
        return rules.read(version, _stream())
    except KeyError:
        raise HTTPException(404, "Rule revision does not exist") from None


@router.get("")
def list_rules(agent: str | None = None, offset: int = Query(0, ge=0),
               limit: int = Query(100, ge=1, le=100)) -> list[RuleRevision]:
    with jobs.lock:
        values = reversed(list(rules.revisions(_stream()).values()))
        return [r for r in values if agent is None or r["agent"] == agent][offset:offset + limit]


@router.get("/agents")
def registered_agents() -> list[AgentSpec]:
    with jobs.lock:
        return sorted(_catalogue().values(), key=lambda spec: spec.name)


@router.post("")
def create_rule(body: RuleDraftRequest) -> RuleRevision:
    with jobs.lock:
        _writable()
        spec = _spec(body.agent)
        try:
            return rules.draft(body.agent, body.allow, spec, POLICY)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None


@router.get("/{version}")
def get_rule(version: str) -> RuleRevision:
    with jobs.lock:
        return _read(version)


@router.post("/{version}/preview")
def preview_rule(version: str, body: RulePreviewRequest | None = None) -> RulePreview:
    with jobs.lock:
        rule = _read(version)
        spec = _spec(rule["agent"])
        policy = rules.overlay(rules.base_policy(spec.name, spec, POLICY), spec.name, rule)
        allow = rules.effective_allow(spec.name, policy)
        decision = None
        if body is not None and body.tool is not None:
            if not gate.is_known(policy, body.tool):
                action, hit = "block", ("UNKNOWN_TOOL", "Tool is not registered; execution is blocked.")
            else:
                hit = hard_rule(spec.name, body.tool, body.args, policy)
                action = "freeze" if hit else "allow"
            decision = GateDecision(call_id="preview", tool=body.tool, args=body.args,
                                    decision=action, layer="hard_rule",
                                    rule_id=hit[0] if hit else None,
                                    explanation=hit[1] if hit else "No hard rule matched.")
        tools = ", ".join(allow.tools) or "no tools"
        emails = ", ".join(allow.email_to) or "no email recipients"
        return RulePreview(version=version, effective_allow=allow, decision=decision,
                           authoritative=True, summary=f"{spec.name} may use {tools}; "
                           f"email recipients are limited to {emails}. "
                           "Existing URL host, canary and bulk restrictions still apply. "
                           "Activation affects new runs only; existing and approved queued runs "
                           "keep their admitted policy.")


@router.post("/{version}/activate")
def activate_rule(version: str, body: HumanRequest) -> RuleRevision:
    with jobs.lock:
        _writable()
        rule = _read(version)
        spec = _spec(rule["agent"])
        try:
            return rules.activate(version, body, spec, POLICY)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
