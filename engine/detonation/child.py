"""Detonation child: runs inside the sandbox process. Only `sandbox.py` starts it.

Reads the snapshot from MIRAGE_SNAPSHOT, jails itself, then calls the snapshot's `runner`
(`module:function(snapshot, call_tool)`; None means `entrypoint` itself). Tools never run:
- a tool the run already called returns its recorded result (same args first, else same tool);
- anything else (the writes the gate never let through) is captured and answered "ok".
Every tool call, and every blocked escape attempt, is appended to MIRAGE_EFFECTS as it happens,
so a crash still leaves the evidence.
"""

import builtins
import importlib
import json
import os
from pathlib import Path

from contracts.models import ToolResult
from engine.detonation import jail


def main():
    snap = json.loads(Path(os.environ["MIRAGE_SNAPSHOT"]).read_text(encoding="utf-8"))
    effects = Path(os.environ["MIRAGE_EFFECTS"])
    step = 0
    current_spec = None

    def record(tool, args, error=None):
        nonlocal step
        step += 1
        with effects.open("a", encoding="utf-8") as f:
            effect = {"step": step, "tool": tool, "args": args}
            if error is not None:
                effect["error"] = error
            f.write(json.dumps(effect) + "\n")

    region = os.getenv("AWS_REGION", "us-east-1")
    jail.install({f"bedrock-runtime.{region}.amazonaws.com"},
                 lambda kind, target: record(f"sandbox.{kind}", {"target": target}))

    import dotenv  # the agent code may load .env; in here it must not (no third-party keys)
    dotenv.load_dotenv = lambda *a, **k: False

    def register_spec(spec):
        nonlocal current_spec
        if spec.get("name") == snap["agent"]:
            current_spec = spec

    def call_tool(tool, args):
        error = None
        known = (current_spec["tools"] if current_spec is not None
                 else snap.get("_current_tools", snap.get("policy", {}).get("known_tools")))
        if error is None and known is not None and tool not in known:
            error = "LookupError"
        same = [r for r in snap["tool_results"] if r["tool"] == tool]
        exact = [r for r in same if r["args"] == args]
        recorded = (exact or same)[0] if exact or same else None
        if error is None and recorded is not None and recorded.get("error") is not None:
            failure = recorded["error"]
            kind = getattr(builtins, failure.partition(":")[0], None)
            error = (kind.__name__ if isinstance(kind, type) and issubclass(kind, Exception)
                     else "ToolError")
        record(tool, args, error)
        if error is not None:
            return ToolResult(call_id=f"sandbox_call_{step}", tool=tool, error=error)
        if exact or same:
            return (exact or same)[0]["result"]
        return {"status": "ok"}

    call_tool.register_spec = register_spec
    module, function = (snap.get("runner") or snap["entrypoint"]).split(":")
    try:
        getattr(importlib.import_module(module), function)(snap, call_tool)
    finally:
        if path := os.environ.get("MIRAGE_CURRENT_SPEC"):
            Path(path).write_text(json.dumps(current_spec), encoding="utf-8")


if __name__ == "__main__":
    main()
