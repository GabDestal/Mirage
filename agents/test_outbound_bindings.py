"""Composite writes expose the exact outbound payload to the SDK, with no live HTTP/model."""

import json

import httpx
import mirage
import pytest
from langchain_core.messages import AIMessage
from mirage import core

from agents.common.testing import call, scripted
from agents.invoicing import agent as invoicing
from agents.invoicing import invoices
from agents.outreach import agent as outreach
from agents.services import crm, store

ATTACKER = "attacker@evil-corp-demo.com"
CASES = [
    pytest.param(invoicing, "send_invoice", {"invoice_id": "INV-1042"}, "c_004", id="invoice"),
    pytest.param(outreach, "schedule_follow_up",
                 {"contact_id": "c_001", "send_on": "2026-10-15"}, "c_001", id="follow-up"),
]


@pytest.fixture(autouse=True)
def offline_api(monkeypatch):
    store.reset()
    invoices.reset()
    checked, results = [], []

    def transport(request):
        data = json.loads(request.content) if request.content else {}
        if request.url.path == "/runs":
            return httpx.Response(200, json={"run_id": "offline", "run_token": "synthetic-token"})
        if request.url.path == "/gateway/check":
            checked.append(data)
            denied = data["args"].get("to") == ATTACKER
            return httpx.Response(200, json={
                "call_id": f"call_{len(checked)}", "tool": data["tool"], "args": data["args"],
                "decision": "freeze" if denied else "allow", "layer": "hard_rule",
                "explanation": "Synthetic destination check",
            })
        if request.url.path.endswith("/wait"):
            return httpx.Response(200, json={"status": "killed"})
        if request.url.path.endswith("/tool-results"):
            results.append(data)
        else:
            assert request.url.path in {"/agents", "/runs/offline/model-calls", "/runs/offline/complete"}
        return httpx.Response(200, json={})

    with httpx.Client(base_url="http://offline.invalid",
                      transport=httpx.MockTransport(transport)) as client:
        monkeypatch.setattr(core, "_http", client)
        monkeypatch.setattr(core, "_sandbox", None)
        yield checked, results


def protected(module, *turns):
    return mirage.protect(module.build_agent(scripted(*turns)), name="outbound_binding_test",
                          entrypoint="unused:factory")


def payload(base, contact_id):
    return {**base, "to": crm.get(contact_id)["email"], "subject": "Customer follow-up",
            "body": "Hello, here is the requested invoice or follow-up.\n\nDemo team"}


def assert_no_writes():
    assert store.state()["outbox"] == []
    assert store.state().get("scheduled", []) == []


@pytest.mark.parametrize("module,name,base,contact_id", CASES)
def test_legacy_call_cannot_hide_mutated_crm_recipient(module, name, base, contact_id, offline_api):
    mutation = []
    if name == "send_invoice":
        mutation = [call("update_contact", contact_id=contact_id, properties={"email": ATTACKER})]
    else:
        crm.update(contact_id, email=ATTACKER)
    legacy = base if name == "send_invoice" else {**base, "subject": "Follow-up", "body": "Hello"}
    result = protected(module, *mutation, call("get_contact", contact_id=contact_id),
                       call(name, **legacy), AIMessage("Done")).invoke(
        {"messages": [("user", "Send the customer's message")]})
    assert offline_api[0][-1]["args"] == legacy
    assert_no_writes()
    assert [m for m in result["messages"] if m.type == "tool"][-1].status == "error"


@pytest.mark.parametrize("module,name,base,contact_id", CASES)
def test_outbound_args_are_required_and_match_prod_and_mirage(
        module, name, base, contact_id, offline_api, monkeypatch):
    args = payload(base, contact_id)
    required = getattr(module, name).args_schema.model_json_schema()["required"]
    assert {"to", "subject", "body"} <= set(required)
    reads = [call("get_contact", contact_id=contact_id)]
    if name == "send_invoice":
        reads.insert(0, call("get_invoice", invoice_id=base["invoice_id"]))
    turns = [*reads, call(name, **args), AIMessage("Done")]
    protected(module, *turns).invoke({"messages": [("user", "Send the customer's message")]})

    checked, results = offline_api
    assert checked[-1]["args"] == args
    actual = (store.state()["outbox"] if name == "send_invoice" else store.state()["scheduled"])[0]
    outbound = {k: args[k] for k in ("to", "subject", "body")}
    assert actual == (outbound if name == "send_invoice" else {**base, **outbound})
    effects = []
    recorded_reads = {result["tool"]: result["result"] for result in results[:-1]}

    def call_tool(tool, arguments):
        if tool in recorded_reads:
            return recorded_reads[tool]
        effects.append((tool, arguments))
        return {"status": "ok"}

    def no_http(request):
        pytest.fail("Mirage attempted HTTP")

    store.reset()
    monkeypatch.setattr(core, "_sandbox", {"call_tool": call_tool, "replies": []})
    with httpx.Client(transport=httpx.MockTransport(no_http)) as client:
        monkeypatch.setattr(core, "_http", client)
        protected(module, *turns).invoke({"messages": [("user", "Send the customer's message")]})
    assert effects == [(name, args)]
    assert_no_writes()


@pytest.mark.parametrize("module,name,base,contact_id", CASES)
def test_resolved_attacker_recipient_is_gated_before_write(module, name, base, contact_id, offline_api):
    crm.update(contact_id, email=ATTACKER)
    args = payload(base, contact_id)
    with pytest.raises(mirage.Blocked):
        protected(module, call("get_contact", contact_id=contact_id), call(name, **args)).invoke(
            {"messages": [("user", "Send the customer's message")]})
    assert offline_api[0][-1]["args"] == args
    assert_no_writes()


@pytest.mark.parametrize("module,name,base,contact_id", CASES)
def test_crm_mutation_after_gate_cannot_redirect_write(
        module, name, base, contact_id, offline_api, monkeypatch):
    args = payload(base, contact_id)
    original_check = core.check

    def change_after_gate(tool, arguments, run):
        call_id = original_check(tool, arguments, run)
        crm.update(contact_id, email=ATTACKER)
        return call_id

    monkeypatch.setattr(core, "check", change_after_gate)
    with pytest.raises(ValueError, match="recipient"):
        protected(module, call(name, **args), AIMessage("Done")).invoke(
            {"messages": [("user", "Send the message")]})
    assert offline_api[0][-1]["args"] == args
    assert "recipient" in offline_api[1][-1]["error"]
    assert_no_writes()


@pytest.mark.parametrize("module,name,base,contact_id", CASES)
@pytest.mark.parametrize("recipient", ["", " ", "another@northwind-demo.com"])
def test_empty_or_mismatched_recipient_cannot_write(module, name, base, contact_id, recipient):
    args = {**payload(base, contact_id), "to": recipient}
    with pytest.raises(ValueError, match="recipient"):
        getattr(module, name).invoke(args)
    assert_no_writes()


@pytest.mark.parametrize("module,name,base,contact_id", CASES)
@pytest.mark.parametrize("recipient", ["", " "])
def test_matching_blank_crm_recipient_cannot_write(module, name, base, contact_id, recipient):
    crm.update(contact_id, email=recipient)
    with pytest.raises(ValueError, match="recipient"):
        getattr(module, name).invoke(payload(base, contact_id))
    assert_no_writes()


@pytest.mark.parametrize("module,name,base,contact_id", CASES)
def test_missing_contact_records_failure_without_write(module, name, base, contact_id, offline_api):
    args = payload(base, contact_id)
    store.state()["contacts"] = [c for c in store.state()["contacts"] if c["id"] != contact_id]
    with pytest.raises(ValueError, match="contact"):
        protected(module, call(name, **args), AIMessage("Done")).invoke(
            {"messages": [("user", "Send the message")]})
    assert "contact" in offline_api[1][-1]["error"]
    assert_no_writes()


def test_missing_invoice_records_failure_without_write(offline_api):
    args = payload({"invoice_id": "INV-missing"}, "c_004")
    with pytest.raises(ValueError, match="invoice"):
        protected(invoicing, call("send_invoice", **args), AIMessage("Done")).invoke(
            {"messages": [("user", "Send the invoice")]})
    assert "invoice" in offline_api[1][-1]["error"]
    assert_no_writes()
