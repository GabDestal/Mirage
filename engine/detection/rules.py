"""Layer 1 hard rules: deterministic checks on one tool call (PRODUCT.md §4)."""

import json
import os
import re
from pathlib import Path

import yaml

from contracts.destinations import destinations

POLICY_FILE = Path(__file__).parent / "policies.yaml"


def load_policy():
    """Read policies.yaml now (fix verification sees an edit without a restart)."""
    return yaml.safe_load(POLICY_FILE.read_text())


POLICY = load_policy()


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
BULK_RECORDS = int(os.getenv("MIRAGE_BULK_RECORDS", "6"))  # legit calls carry <= 4 (meeting brief)


def _strings(value):
    """Argument strings, including keys and decoded JSON payloads, without JSON escaping."""
    if isinstance(value, str):
        yield value
        try:
            decoded = json.loads(value)
        except (ValueError, RecursionError):
            return
        yield from _strings(decoded)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _allowed(domain, allowed):
    domain = domain.lower()
    return bool(domain) and any(domain == d or domain.endswith("." + d)
                               for entry in allowed if (d := entry.lower().removesuffix(".")))


def hard_rules(agent, tool, args, policy=POLICY):
    """Yield (rule_id, explanation) for every rule the call breaks.

    Recognized destinations of any tool are checked, regardless of its registered name.
    """
    if tool not in policy["agents"][agent]["tools"]:
        yield "TOOL_NOT_ALLOWED", f"Tool {tool} is not on the allowlist of agent {agent}."

    extracted = list(destinations(args))
    emails = [a.lower() for a in policy["destinations"]["email_domains"]]
    domains = [a.removeprefix("*@") for a in emails if "@" not in a or a.startswith("*@")]
    for kind, value in extracted:
        if kind == "email":
            allowed = bool(value) and (value in emails or _allowed(value.rpartition("@")[2], domains))
        else:
            allowed = _allowed(value, policy["destinations"]["url_domains"])
        if not allowed:
            yield "DEST_NOT_ALLOWED", f"Destination {value or 'malformed'} is not on the allowlist."
            break

    strings = list(_strings(args))
    if any(policy["canary"] in value for value in strings):
        yield "CANARY", "The canary secret appears in the tool arguments."

    # P4 bulk export, deterministic: many addresses leaving in one call (a contact list), even
    # to an allowed destination. Recipients themselves don't count.
    recipients = {value for kind, value in extracted if kind == "email"}
    carried = {address for value in strings for address in EMAIL.findall(value.lower())} - recipients
    if len(carried) >= BULK_RECORDS:
        yield "BULK_RECORDS", f"The call carries {len(carried)} email addresses: a bulk export."


def hard_rule(agent, tool, args, policy=POLICY):
    """The first rule the call breaks, else None. The gate freezes on it."""
    return next(hard_rules(agent, tool, args, policy), None)
