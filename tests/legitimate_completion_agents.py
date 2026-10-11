"""Synthetic completion-ledger agent for real jailed children, with no provider calls."""

import json


def run(snapshot, call_tool):
    script = json.loads(snapshot["system"])
    if isinstance(script, dict):
        call_tool.register_spec(script["spec"])
        script = script["effects"]
    for effect in script:
        call_tool(effect["tool"], effect["args"])
