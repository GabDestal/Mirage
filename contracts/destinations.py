"""Shared stdlib destination parser for policy checks and completion evidence."""

import re
from email import policy as email_policy
from email.parser import HeaderParser
from urllib.parse import urlparse

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
