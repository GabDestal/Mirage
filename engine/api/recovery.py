"""Verified rollout and useful-task proof for the demo's clean meeting restart."""

from contracts.completion import matches_requirements
from engine.detection.rules import hard_rules
from engine.detonation.child import WRITE_PREFIXES
from engine.store import events


def successful_effects(run_id, log=None):
    """Join successful results to this run's requested arguments, once per call."""
    requested, effects = {}, {}
    for event in events.read() if log is None else log:
        if event.run_id != run_id or event.env != "prod":
            continue
        payload = event.payload
        if event.type == "tool.requested":
            requested[payload["call_id"]] = payload
        elif event.type == "tool.result" and payload.get("error") is None:
            call = requested.get(payload["call_id"])
            if call and call["tool"] == payload["tool"]:
                effects[payload["call_id"]] = {"tool": call["tool"], "args": call["args"]}
    return list(effects.values())


def outward_writes(effects):
    return [effect for effect in effects if effect["tool"].startswith(WRITE_PREFIXES)]


def no_prior_writes(run_id):
    """shortcut: restart only before any successful task write; no general idempotency."""
    return not outward_writes(successful_effects(run_id))


def complete_meeting_declaration(legit):
    """Recovery needs the existing grounded, exactly-one-brief story declaration."""
    if not isinstance(legit, dict) or set(legit) != {"required"}:
        return False
    required = legit["required"]
    if not isinstance(required, list) or not required:
        return False
    for want in required:
        if not isinstance(want, dict):
            return False
        nonempty = want.get("nonempty", [])
        if (want.get("tool") == "send_email" and want.get("count", 1) == 1
                and isinstance(want.get("args"), dict)
                and isinstance(want["args"].get("to"), str)
                and isinstance(nonempty, list)
                and all(isinstance(key, str) for key in nonempty)
                and {"subject", "body"} <= set(nonempty)
                and isinstance(want.get("contains"), dict)
                and isinstance(want["contains"].get("body"), list)
                and want["contains"]["body"]):
            body = want["contains"]["body"]
            if any(not isinstance(term, str) or not term.strip() for term in body):
                return False
            example = {"tool": "send_email", "args": {
                **want["args"], "subject": "Meeting brief", "body": " ".join(body)}}
            return matches_requirements(legit, [example])
    return False


def useful_completed(run):
    effects = successful_effects(run.id)
    return (complete_meeting_declaration(run.legit)
            and len(outward_writes(effects)) == 1
            and not any(list(hard_rules(run.agent, effect["tool"], effect["args"], run.policy))
                        for effect in effects)
            and matches_requirements(run.legit, effects))
