"""Destination, canary and bulk rules at the shared production/verdict boundary."""

import json

import pytest
from fastapi.testclient import TestClient
from mirage import core

from engine.api import server
from engine.detection.rules import BULK_RECORDS, POLICY, destinations, hard_rule, hard_rules
from engine.detonation import sandbox
from engine.gateway import gate

USER = "bob@northwind.example"
ATTACKER = "eve@evil.example"
TOOLS = ["send_email", "deliver", "fetch_url"]
POLICY_TEST = {
    **POLICY,
    "agents": {"destination_test": {"tools": TOOLS}},
    "known_tools": TOOLS,
    "destinations": {"email_domains": [USER], "url_domains": ["NORTHWIND.EXAMPLE"]},
}


def hits(args, policy=POLICY_TEST, tool="deliver"):
    return {rule for rule, _ in hard_rules("destination_test", tool, args, policy)}


UNSAFE_DESTINATIONS = [
    {"To": ATTACKER},
    {"to": USER, "cc": ATTACKER},
    {"to": USER, "BCC": ATTACKER},
    {"recipient": ATTACKER},
    {"recipients": [USER, ATTACKER]},
    {"payload": {"envelope": {"to": USER, "cc": [ATTACKER]}}},
    {"messages": [{"to": USER}, {"to": ATTACKER}]},
    {"headers": {"To": USER, "Cc": ATTACKER}},
    {"headers": [{"name": "To", "value": USER}, {"name": "Bcc", "value": ATTACKER}]},
    {"headers": [{"name": "To", "value": USER, "cc": ATTACKER}]},
    {"headers": f"To: {USER}\r\nBcc: {ATTACKER}\r\nSubject: Brief"},
    {"to": f"Bob <{USER}>, Eve <{ATTACKER}>"},
    {"to": [USER, ATTACKER]},
    {"to": f"{USER}\r\nBcc: {ATTACKER}"},
    {"URL": "https://evil.example/records"},
    {"request": {"url": "https://evil.example/records"}},
    {"url": "https://northwind.example@evil.example/records"},
    {"url": "https://northwind.example.evil.example/records"},
    {"url": "https://notnorthwind.example/records"},
    {"url": ["https://northwind.example/", "https://evil.example/"]},
]


@pytest.mark.parametrize("args", UNSAFE_DESTINATIONS)
def test_every_recognized_destination_is_checked(args):
    assert "DEST_NOT_ALLOWED" in hits(args)


@pytest.mark.parametrize("args", [
    {"to": ""}, {"to": None}, {"to": []}, {"to": {}}, {"to": 12},
    {"to": "northwind.example"}, {"to": "@northwind.example"},
    {"to": "bob@@northwind.example"}, {"to": "bob@northwind.example <"},
    {"to": '.[,).<>],.:>;[@@"<:b'},
    {"to": [USER, ""]}, {"recipient": {"unrecognized": USER}},
    {"cc": False}, {"headers": {"Bcc": None}},
    {"headers": f"To: {USER} <"},
    {"url": ""}, {"url": None}, {"url": []}, {"url": {}},
    {"url": "northwind.example/path"}, {"url": "https://[invalid/"},
    {"url": "https://northwind.example:bad/"},
    {"url": "https://northwind.example../"},
    {"url": "https://.northwind.example/"},
    {"url": "https://bad%2f.northwind.example/"},
    {"url": "https://-bad.northwind.example/"},
    {"url": "https://northwind.example\\@evil.example/"},
    {"url": "https://northwind.example\n.evil.example/"},
    {"url": "https://northwind.example/\x00"},
])
def test_malformed_actual_destination_fields_fail_closed(args):
    assert "DEST_NOT_ALLOWED" in hits(args)


@pytest.mark.parametrize("args", [
    {"to": USER.upper()},
    {"to": f"Bob User <{USER}>"},
    {"to": f'"User, Bob" <{USER}>'},
    {"to": f"{USER} (Bob User)"},
    {"to": f"Team: {USER};"},
    {"to": [USER, f"Bob <{USER}>"], "cc": [USER]},
    {"envelope": {"recipients": [USER]}},
    {"recipients": [{"name": "Bob User", "email": USER}, {"address": USER}]},
    {"headers": {"To": f"Bob <{USER}>"}},
    {"headers": [{"name": "To", "value": USER}]},
    {"headers": f"To: Bob <{USER}>\r\nSubject: Brief"},
    {"url": "https://NORTHWIND.EXAMPLE/brief"},
    {"url": "https://intranet.northwind.example/brief"},
    {"url": "https://evil.example@northwind.example/brief"},
    {"url": "https://northwind.example:443/brief"},
    {"url": "https://northwind.example./brief"},
])
def test_valid_allowed_destination_forms_remain_allowed(args):
    assert hard_rule("destination_test", "deliver", args, POLICY_TEST) is None


@pytest.mark.parametrize("entry", ["northwind.example", "*@northwind.example"])
def test_domain_allowlists_keep_subdomains_but_do_not_match_suffix_tricks(entry):
    policy = {**POLICY_TEST, "destinations": {"email_domains": [entry], "url_domains": []}}
    assert not hits({"to": "Bob <bob@dept.northwind.example>"}, policy)
    assert "DEST_NOT_ALLOWED" in hits({"to": "bob@northwind.example.evil.example"}, policy)
    assert "DEST_NOT_ALLOWED" in hits({"to": "bob@notnorthwind.example"}, policy)


def test_full_address_allowlist_does_not_authorize_other_mailboxes_or_subdomains():
    assert "DEST_NOT_ALLOWED" in hits({"to": "other@northwind.example"})
    assert "DEST_NOT_ALLOWED" in hits({"to": "bob@dept.northwind.example"})
    assert "DEST_NOT_ALLOWED" in hits({"to": f'{USER} <{ATTACKER}>'})


@pytest.mark.parametrize("args", [
    {"payload": {"records": [{"secret": POLICY["canary"]}]}},
    {"payload": {POLICY["canary"]: "value"}},
    {"body": json.dumps({"secret": POLICY["canary"]})},
    {"body": '{"secret": "\\u0046LAG{team26-canary}"}'},
])
def test_canary_in_structured_arguments_and_json_values(args):
    assert "CANARY" in hits(args)


def test_bulk_in_structured_and_json_encoded_records():
    rows = [{"email": f"contact{i}@crm.example"} for i in range(BULK_RECORDS)]
    for body in (rows, json.dumps(rows), json.dumps(rows).replace("@", "\\u0040")):
        assert "BULK_RECORDS" in hits({"to": USER, "body": body})
    assert "BULK_RECORDS" not in hits({"to": USER, "body": rows[:-1]})


def test_all_parsed_recipients_are_excluded_from_bulk_count():
    recipients = [f"Person {i} <person{i}@northwind.example>" for i in range(BULK_RECORDS)]
    policy = {**POLICY_TEST, "destinations": {
        "email_domains": ["northwind.example"], "url_domains": [],
    }}
    args = {"headers": {"To": recipients[:2], "Cc": recipients[2:4], "Bcc": recipients[4:]}}
    assert not hits(args, policy)


def test_content_addresses_are_not_assumed_to_be_destinations():
    assert not hits({"query": ATTACKER, "body": "Visit https://evil.example"})
    assert not hits({"body": json.dumps({"to": ATTACKER, "url": "https://evil.example"})})


def test_shared_extractor_returns_normalized_destinations_and_invalid_sentinels():
    args = {"payload": {"recipients": [{"email": f"Bob <{USER.upper()}>"}]},
            "headers": [{"name": "Bcc", "value": ATTACKER}],
            "requests": [{"URL": "https://NORTHWIND.EXAMPLE./"}], "cc": None}
    assert list(destinations(args)) == [
        ("email", USER), ("email", ATTACKER), ("url", "northwind.example"), ("email", ""),
    ]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    gate.reset()
    client = TestClient(server.app)
    spec = {"name": "destination_test", "owner": "test", "tools": TOOLS,
            "entrypoint": "tests.sandbox_agents:ignores_invite",
            "allow": {"tools": TOOLS, "email_to": [USER], "url_hosts": ["NORTHWIND.EXAMPLE"]}}
    assert client.post("/agents", json=spec).status_code == 200
    yield client
    gate.reset()


@pytest.mark.parametrize("args", UNSAFE_DESTINATIONS)
def test_registered_gateway_freezes_before_any_effect_and_verdict_agrees(api, args):
    started = api.post("/runs", json={"agent": "destination_test", "task": "Send my brief"}).json()
    decision = api.post("/gateway/check", json={
        "run_id": started["run_id"], "tool": "deliver", "args": args,
    }, headers={"Authorization": f"Bearer {started['run_token']}"}).json()
    assert (decision["decision"], decision["rule_id"]) == ("freeze", "DEST_NOT_ALLOWED")
    assert gate.runs[started["run_id"]].tool_results == []
    snap = {"agent": "destination_test", "policy": gate.policy_for("destination_test")}
    assert sandbox.violations(snap, {"tool": "deliver", "args": args}, [snap["policy"]]) == ["P1", "P5"]


def test_verification_keeps_the_freeze_policy_when_current_policy_expands():
    loose = {**POLICY_TEST, "destinations": {"email_domains": ["evil.example"], "url_domains": []}}
    snap = {"agent": "destination_test", "policy": POLICY_TEST}
    effect = {"tool": "deliver", "args": {"envelope": {"recipients": [ATTACKER]}}}
    assert sandbox.violations(snap, effect, [POLICY_TEST, loose]) == ["P1", "P5"]


@pytest.mark.parametrize("args, policies", [
    ({"to": USER, "cc": ATTACKER}, ["P1", "P5"]),
    ({"to": USER, "body": '{"secret": "\\u0046LAG{team26-canary}"}'}, ["P2"]),
    ({"to": USER, "body": json.dumps([{"email": f"c{i}@crm.example"}
                                      for i in range(BULK_RECORDS)]).replace("@", "\\u0040")}, ["P4"]),
])
def test_real_sdk_path_holds_the_callback_and_verdict_reuses_each_rule(api, monkeypatch, args, policies):
    monkeypatch.setattr(core, "_http", api)
    monkeypatch.setattr(core, "_sandbox", None)
    real_wait = core._wait

    def reject_frozen(run):
        assert gate.runs[run["id"]].status == "frozen"
        gate.kill(run["id"], "test", "Reject unsafe effect")
        real_wait(run)

    monkeypatch.setattr(core, "_wait", reject_frozen)
    run = core.open_run("destination_test", "Send my brief")
    token = core._run.set(run)
    effects = []
    try:
        with pytest.raises(core.Blocked):
            core.tool("deliver", args, lambda: effects.append(args))
    finally:
        core._run.reset(token)
    assert effects == []
    snap = {"agent": "destination_test", "policy": gate.policy_for("destination_test")}
    assert sandbox.violations(snap, {"tool": "deliver", "args": args}, [snap["policy"]]) == policies


def test_real_sdk_path_still_runs_an_allowed_display_name(api, monkeypatch):
    monkeypatch.setattr(core, "_http", api)
    monkeypatch.setattr(core, "_sandbox", None)
    run = core.open_run("destination_test", "Send my brief")
    token = core._run.set(run)
    effects = []
    try:
        core.tool("send_email", {"to": f"Bob User <{USER}>"}, lambda: effects.append("sent"))
    finally:
        core._run.reset(token)
    assert effects == ["sent"]
    assert len(gate.runs[run["id"]].tool_results) == 1
