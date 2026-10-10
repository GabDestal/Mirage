"""Detonation runner for SDK agents: the engine's child calls `run(snapshot, call_tool)`.

Rebuilds the agent from `entrypoint`, answers its tools with the engine's `call_tool`, replays
the recorded model replies up to the frozen call, then runs live from there (CONTRACTS.md §11).
"""

import importlib

from mirage import core
from mirage.protect import registry


def run(snapshot, call_tool):
    core._sandbox = {"call_tool": call_tool,
                     "replies": [c["response"] for c in snapshot.get("model_calls") or []]}
    module, _, function = snapshot["entrypoint"].partition(":")
    loaded = importlib.import_module(module)
    if function:
        getattr(loaded, function)()  # the factory calls mirage.protect, which fills the registry
    return registry[snapshot["agent"]](snapshot["task"])
