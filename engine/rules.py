"""Human-activated, immutable restrictions, folded from the existing event stream."""

import copy
import hashlib
import json
from datetime import UTC, datetime

from contracts.models import Allowlist
from engine.detection.rules import EMAIL, _allowed, hard_rules
from engine.store import events


def revisions(stream=None):
    drafts, active = {}, {}
    for event in events.read() if stream is None else stream:
        payload = event.payload
        if event.type == "rule.drafted":
            drafts[payload["version"]] = {**copy.deepcopy(payload), "status": "draft",
                                          "created_at": event.ts, "activated_at": None}
        elif event.type == "rule.activated" and payload["version"] in drafts:
            rule = drafts[payload["version"]]
            previous = active.get(rule["agent"])
            if previous:
                drafts[previous]["status"] = "superseded"
            rule.update(status="active", activated_at=event.ts)
            active[rule["agent"]] = rule["version"]
    return drafts


def read(version, stream=None):
    try:
        return revisions(stream)[version]
    except KeyError:
        raise KeyError("Rule revision does not exist") from None


def base_policy(agent, spec, canonical):
    """Preserve registered roles; a canonical role applies only to its exact name."""
    if spec is None:
        return copy.deepcopy(canonical)
    policy = {"canary": canonical["canary"],
              "agents": {agent: {"tools": list(spec.allow.tools)}},
              "destinations": {"email_domains": list(spec.allow.email_to),
                               "url_domains": list(spec.allow.url_hosts)},
              "known_tools": list(spec.tools)}
    if agent in canonical["agents"]:
        policy["agents"][agent]["tools"] = [
            tool for tool in spec.allow.tools if tool in canonical["agents"][agent]["tools"]]
        policy["constraints"] = [copy.deepcopy(canonical)]
    return policy


def policy_for_spec(agent, spec, canonical):
    policy = base_policy(agent, spec, canonical)
    active = next((r for r in revisions().values()
                   if r["agent"] == agent and r["status"] == "active"), None)
    return overlay(policy, agent, active) if active else policy


def overlay(policy, agent, rule):
    """Intersect by evaluating both complete policies with the same hard-rule evaluator."""
    original = copy.deepcopy(policy)
    effective = copy.deepcopy(policy)
    allow = rule["allow"]
    effective["agents"][agent]["tools"] = [
        tool for tool in original["agents"][agent]["tools"] if tool in allow["tools"]]
    effective["destinations"]["email_domains"] = list(allow["email_to"])
    effective["constraints"] = [original]
    effective["rule_revision"] = rule["version"]
    return effective


def validate(agent, allow, spec, canonical):
    if allow.url_hosts:
        raise ValueError("This rule type cannot edit URL hosts")
    policy = base_policy(agent, spec, canonical)
    if any(tool not in spec.tools or tool not in policy["agents"][agent]["tools"]
           for tool in allow.tools):
        raise ValueError("Rule tools must narrow the registered role's allowed tools")
    if any(not EMAIL.fullmatch(address) or "*" in address for address in allow.email_to):
        raise ValueError("Rule recipients must be exact email addresses")
    for address in allow.email_to:
        if any(rule == "DEST_NOT_ALLOWED" for rule, _ in
               hard_rules(agent, "", {"to": address}, policy)):
            raise ValueError("Rule recipients must narrow the registered role's destinations")
    return {"agent": agent, "allow": Allowlist(
        tools=sorted(set(allow.tools)), email_to=sorted({a.lower() for a in allow.email_to})
    ).model_dump(mode="json")}


def draft(agent, allow, spec, canonical):
    content = validate(agent, allow, spec, canonical)
    version = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"))
                             .encode()).hexdigest()
    if version not in revisions():
        events.emit("rule.drafted", {"version": version, **content})
    return read(version)


def activate(version, human, spec, canonical):
    if not human.actor.strip() or not human.reason.strip():
        raise ValueError("Activation requires a nonempty human actor and reason")
    rule = read(version)
    validate(rule["agent"], Allowlist.model_validate(rule["allow"]), spec, canonical)
    if rule["status"] != "active":
        # Authority changes only after durable operator evidence, never on a failed preview.
        events.emit("human.action", {"actor": human.actor, "action": "activate_rule",
                    "target": version, "reason": human.reason,
                    "ts": datetime.now(UTC).isoformat()})
        events.emit("rule.activated", {"version": version, "agent": rule["agent"],
                                      "actor": human.actor, "reason": human.reason})
    return read(version)


def effective_allow(agent, policy):
    emails = policy["destinations"]["email_domains"]
    emails = [address for address in emails if not any(
        rule == "DEST_NOT_ALLOWED" for rule, _ in hard_rules(agent, "", {"to": address}, policy))]
    hosts = policy["destinations"]["url_domains"]
    for constraint in policy.get("constraints", []):
        other = effective_allow(agent, constraint).url_hosts
        hosts = sorted({host for host in hosts + other
                        if _allowed(host, hosts) and _allowed(host, other)})
    return Allowlist(tools=policy["agents"][agent]["tools"], email_to=emails, url_hosts=hosts)
