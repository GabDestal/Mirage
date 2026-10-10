"""Layer 1 hard rules: deterministic checks on one tool call (PRODUCT.md §4)."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

POLICY_FILE = Path(__file__).parent / "policies.yaml"


def load_policy():
    """Read policies.yaml now (fix verification sees an edit without a restart)."""
    return yaml.safe_load(POLICY_FILE.read_text())


POLICY = load_policy()


def _allowed(domain, allowed):
    return any(domain == d or domain.endswith("." + d) for d in allowed)


def hard_rules(agent, tool, args, policy=POLICY):
    """Yield (rule_id, explanation) for every rule the call breaks.

    Destinations are read from the `to` and `url` arguments of any tool, so tools of
    registered agents are checked whatever their names.
    """
    if tool not in policy["agents"][agent]["tools"]:
        yield "TOOL_NOT_ALLOWED", f"Tool {tool} is not on the allowlist of agent {agent}."

    if "to" in args:
        allowed = [a.lower() for a in policy["destinations"]["email_domains"]]
        for address in filter(None, re.split(r"[,;\s]+", str(args["to"]).lower())):
            domain = address.rpartition("@")[2]
            if address not in allowed and not _allowed(domain, allowed):
                yield "DEST_NOT_ALLOWED", f"Domain {domain or address} is not on the allowlist."
                break
    if "url" in args:
        host = (urlparse(str(args.get("url", ""))).hostname or "").lower()
        if not _allowed(host, policy["destinations"]["url_domains"]):
            yield "DEST_NOT_ALLOWED", f"Host {host or 'unknown'} is not on the allowlist."

    if policy["canary"] in json.dumps(args):
        yield "CANARY", "The canary secret appears in the tool arguments."


def hard_rule(agent, tool, args, policy=POLICY):
    """The first rule the call breaks, else None. The gate freezes on it."""
    return next(hard_rules(agent, tool, args, policy), None)
