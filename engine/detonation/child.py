"""Detonation child: runs inside the sandbox process. Only `sandbox.py` starts it.

Reads the snapshot from MIRAGE_SNAPSHOT, jails itself, then calls the snapshot's `runner`
(`module:function(snapshot, call_tool)`; None means `entrypoint` itself). Tools never run:
- reads consume recorded results for exactly the same tool and arguments, in order;
- declared supported writes are captured and answered "ok"; unavailable reads return typed errors.
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

# Existing demo prefixes and the selected native catalogue; other tools need recorded reads.
WRITE_PREFIXES = ("send_", "create_", "update_", "log_", "schedule_", "record_", "mark_",
                  "post_", "set_", "submit_")
WRITE_TOOLS = {"write_file", "delete_file", "invite_user_to_slack",
               "add_user_to_channel", "remove_user_from_slack"}


def main():
    snap = json.loads(Path(os.environ["MIRAGE_SNAPSHOT"]).read_text(encoding="utf-8"))
    effects = Path(os.environ["MIRAGE_EFFECTS"])
    step = 0
    current_spec = None
    consumed = set()

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
        match = next(((i, r) for i, r in enumerate(snap["tool_results"])
                      if i not in consumed and r["tool"] == tool and r["args"] == args), None)
        recorded = match[1] if match is not None else None
        if error is None and match is not None:
            consumed.add(match[0])
        if error is None and recorded is not None and recorded.get("error") is not None:
            failure = recorded["error"]
            kind = getattr(builtins, failure.partition(":")[0], None)
            error = (kind.__name__ if isinstance(kind, type) and issubclass(kind, Exception)
                     else "ToolError")
        declared = (known if known is not None else snap.get("policy", {}).get("agents", {})
                    .get(snap["agent"], {}).get("tools", []))
        write = tool in declared and (tool.startswith(WRITE_PREFIXES) or tool in WRITE_TOOLS)
        if error is None and not write and recorded is None:
            error = "LookupError"
        record(tool, args, error)
        if error is not None:
            return ToolResult(call_id=f"sandbox_call_{step}", tool=tool, error=error)
        return {"status": "ok"} if write else recorded["result"]

    call_tool.register_spec = register_spec
    module, function = (snap.get("runner") or snap["entrypoint"]).split(":")
    try:
        getattr(importlib.import_module(module), function)(snap, call_tool)
    finally:
        if path := os.environ.get("MIRAGE_CURRENT_SPEC"):
            Path(path).write_text(json.dumps(current_spec), encoding="utf-8")


if __name__ == "__main__":
    main()
