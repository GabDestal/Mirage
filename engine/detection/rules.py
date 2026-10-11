"""Layer 1 hard rules: deterministic checks on one tool call (PRODUCT.md §4)."""

import json
import os
import re
from email import policy as email_policy
from email.parser import HeaderParser
from pathlib import Path
from urllib.parse import urlparse

import yaml

POLICY_FILE = Path(__file__).parent / "policies.yaml"


def load_policy():
    """Read policies.yaml now (fix verification sees an edit without a restart)."""
    return yaml.safe_load(POLICY_FILE.read_text())


POLICY = load_policy()


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
BULK_RECORDS = int(os.getenv("MIRAGE_BULK_RECORDS", "6"))  # legit calls carry <= 4 (meeting brief)
RECIPIENT_FIELDS = {"to", "cc", "bcc", "recipient", "recipients"}


def _email_addresses(value):
    if isinstance(value, list):
        if not value:
            yield ""
        for item in value:
            yield from _email_addresses(item)
        return
    if isinstance(value, dict):
        fields = [v for k, v in value.items() if k.lower() in RECIPIENT_FIELDS | {"email", "address"}]
        if not fields:
            yield ""
        for item in fields:
            yield from _email_addresses(item)
        return
    if not isinstance(value, str) or not value.strip() or "\r" in value or "\n" in value:
        yield ""
        return
    try:
        header = email_policy.default.header_factory("To", value)
        if header.defects or not header.addresses:
            yield ""
        for address in header.addresses:
            yield address.addr_spec.lower() if address.username and address.domain else ""
    except (ValueError, IndexError, AttributeError):
        # Some malformed groups crash the stdlib parser rather than reporting a defect.
        yield ""


def _url_hosts(value):
    if isinstance(value, list):
        if not value:
            yield ""
        for item in value:
            yield from _url_hosts(item)
        return
    if (not isinstance(value, str) or "\\" in value
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)):
        yield ""
        return
    try:
        url = urlparse(value)
        host = (url.hostname or "").lower().removesuffix(".")
        if ":" not in host:
            host = host.encode("idna").decode("ascii")
            if len(host) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                                     for label in host.split(".")):
                host = ""
        # Accessing port also validates it; urlparse alone accepts malformed ports.
        _ = url.port
        yield host if url.scheme.lower() in {"http", "https"} else ""
    except ValueError:
        yield ""


def _header_destinations(value):
    if isinstance(value, str):
        headers = HeaderParser(policy=email_policy.default).parsestr(value)
        if headers.defects or headers.get_payload():
            yield "email", ""
        for name, header in headers.raw_items():
            if name.lower() in RECIPIENT_FIELDS:
                unfolded = re.sub(r"\r?\n[ \t]+", " ", header)
                yield from (("email", a) for a in _email_addresses(unfolded))
    elif isinstance(value, list):
        for item in value:
            yield from _header_destinations(item)
    elif isinstance(value, dict):
        if any(k.lower() == "name" and isinstance(v, str) and v.lower() in RECIPIENT_FIELDS
               for k, v in value.items()):
            values = [v for k, v in value.items() if k.lower() == "value"] or [None]
            for item in values:
                yield from (("email", a) for a in _email_addresses(item))
        yield from destinations(value)
    else:
        yield "email", ""


def destinations(args):
    """Yield (email, lowercase addr-spec) or (url, lowercase hostname); empty = malformed.

    Recognize case-insensitive to/cc/bcc/recipient/recipients/url fields in JSON containers
    and headers (mapping, name/value list, or raw block). Recipient objects accept email/address.
    shortcut: only named fields are inferred, add adapter-owned checks for tool-resolved destinations.
    """
    if isinstance(args, dict):
        for key, value in args.items():
            key = key.lower()
            if key in RECIPIENT_FIELDS:
                yield from (("email", a) for a in _email_addresses(value))
            elif key == "url":
                yield from (("url", h) for h in _url_hosts(value))
            elif key == "headers":
                yield from _header_destinations(value)
            elif isinstance(value, (dict, list)):
                yield from destinations(value)
    elif isinstance(args, list):
        for value in args:
            yield from destinations(value)


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
