"""Layer 1 hard rules: deterministic checks on one tool call (PRODUCT.md §4)."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

POLICY = yaml.safe_load((Path(__file__).parent / "policies.yaml").read_text())


def _allowed(domain, allowed):
    return any(domain == d or domain.endswith("." + d) for d in allowed)


def hard_rule(agent, tool, args, policy=POLICY):
    """Return (rule_id, explanation) for the first rule the call breaks, else None.

    Destinations are read from the `to` and `url` arguments of any tool, so tools of
    registered agents are checked whatever their names.
    """
    if tool not in policy["agents"][agent]["tools"]:
        return "TOOL_NOT_ALLOWED", f"Tool {tool} is not on the allowlist of agent {agent}."

    if "to" in args:
        allowed = [a.lower() for a in policy["destinations"]["email_domains"]]
        for address in filter(None, re.split(r"[,;\s]+", str(args["to"]).lower())):
            domain = address.rpartition("@")[2]
            if address not in allowed and not _allowed(domain, allowed):
                return "DEST_NOT_ALLOWED", f"Domain {domain or address} is not on the allowlist."
    if "url" in args:
        host = (urlparse(str(args.get("url", ""))).hostname or "").lower()
        if not _allowed(host, policy["destinations"]["url_domains"]):
            return "DEST_NOT_ALLOWED", f"Host {host or 'unknown'} is not on the allowlist."

    if policy["canary"] in json.dumps(args):
        return "CANARY", "The canary secret appears in the tool arguments."
    return None
