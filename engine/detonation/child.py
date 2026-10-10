"""Detonation child: runs inside the sandbox process. Only `sandbox.py` starts it.

Reads the snapshot from MIRAGE_SNAPSHOT, jails itself, rebuilds the agent from the snapshot's
entrypoint (`module:function(snapshot, call_tool)`) and runs the task. Tools never run:
- a tool the run already called returns its recorded result (same args first, else same tool);
- anything else (the writes the gate never let through) is captured and answered "ok".
Every tool call, and every blocked escape attempt, is appended to MIRAGE_EFFECTS as it happens,
so a crash still leaves the evidence.
"""

import importlib
import json
import os
from pathlib import Path

from engine.detonation import jail


def main():
    snap = json.loads(Path(os.environ["MIRAGE_SNAPSHOT"]).read_text(encoding="utf-8"))
    effects = Path(os.environ["MIRAGE_EFFECTS"])
    step = 0

    def record(tool, args):
        nonlocal step
        step += 1
        with effects.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"step": step, "tool": tool, "args": args}) + "\n")

    region = os.getenv("AWS_REGION", "us-east-1")
    jail.install({f"bedrock-runtime.{region}.amazonaws.com"},
                 lambda kind, target: record(f"sandbox.{kind}", {"target": target}))

    import dotenv  # the agent code may load .env; in here it must not (no third-party keys)
    dotenv.load_dotenv = lambda *a, **k: False

    def call_tool(tool, args):
        record(tool, args)
        same = [r for r in snap["tool_results"] if r["tool"] == tool]
        exact = [r for r in same if r["args"] == args]
        if exact or same:
            return (exact or same)[0]["result"]
        return {"status": "ok"}

    module, function = snap["entrypoint"].split(":")
    getattr(importlib.import_module(module), function)(snap, call_tool)


if __name__ == "__main__":
    main()
