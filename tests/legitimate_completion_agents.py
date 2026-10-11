"""Synthetic completion-ledger agent for real jailed children, with no provider calls."""

import json


def run(snapshot, call_tool):
    for effect in json.loads(snapshot["system"]):
        call_tool(effect["tool"], effect["args"])
