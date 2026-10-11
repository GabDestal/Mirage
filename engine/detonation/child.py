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
from pathlib import Path, PurePosixPath

from contracts.models import ToolResult
from engine.detonation import jail

# Existing demo prefixes and the selected native catalogue; other tools need recorded reads.
WRITE_PREFIXES = ("send_", "create_", "update_", "log_", "schedule_", "record_", "mark_",
                  "post_", "set_", "submit_")
WRITE_TOOLS = {"write_file", "delete_file", "invite_user_to_slack",
               "add_user_to_channel", "remove_user_from_slack"}
FILE_TOOLS = {"list_dir", "read_file", "write_file", "delete_file"}


class NativeFileWorld:
    """Four native tools over inert text, including logical .env files; never host paths."""

    @staticmethod
    def path(raw):
        if not isinstance(raw, str):
            raise TypeError("Fixture path must be text")
        path = raw.replace("\\", "/").lstrip("/")
        if path == "workspace":
            path = ""
        elif path.startswith("workspace/"):
            path = path[len("workspace/"):]
        if ".." in path.split("/"):
            raise RuntimeError("Fixture path escapes root")
        return "/".join(part for part in path.split("/") if part and part != ".")

    def __init__(self, files, directories=()):
        self.files, self.directories = {}, {""}
        for raw, text in files.items():
            path = self.path(raw)
            if not path or path in self.files:
                raise ValueError("Invalid or duplicate fixture file")
            if not isinstance(text, str):
                raise TypeError("Fixture contents must be text")
            text.encode("utf-8")
            self.files[path] = text
        for raw in [*self.files, *directories]:
            path = self.path(raw)
            self.directories.update(str(p) if str(p) != "." else ""
                                    for p in PurePosixPath(path).parents)
        self.directories.update(self.path(p) for p in directories)
        if self.directories & self.files.keys():
            raise NotADirectoryError("Fixture file conflicts with directory")

    def snapshot(self):
        return {"files": dict(self.files), "directories": sorted(self.directories - {""})}

    def call(self, tool, args):
        if tool not in FILE_TOOLS:
            raise ValueError("Unsupported fixture tool")
        path = self.path(args["path"])
        parents = {str(p) if str(p) != "." else "" for p in PurePosixPath(path).parents}
        if tool in {"read_file", "list_dir"} and parents & self.files.keys():
            raise NotADirectoryError("Fixture parent is a file")
        if tool == "read_file":
            if path in self.directories:
                raise IsADirectoryError("Fixture path is a directory")
            if path not in self.files:
                raise FileNotFoundError("Fixture file is absent")
            return self.files[path]
        if tool == "list_dir":
            if path in self.files:
                raise NotADirectoryError("Fixture path is a file")
            if path not in self.directories:
                raise FileNotFoundError("Fixture directory is absent")
            prefix = path + "/" if path else ""
            return [{"path": p, "type": "file" if p in self.files else "directory"}
                    for p in sorted(self.files.keys() | self.directories)
                    if p.startswith(prefix) and p != path and "/" not in p[len(prefix):]]
        if tool == "write_file":
            text = args["content"]
            if not isinstance(text, str):
                raise TypeError("Fixture contents must be text")
            size = len(text.encode("utf-8"))
            if path in self.directories:
                raise IsADirectoryError("Fixture path is a directory")
            if parents & self.files.keys():
                if str(PurePosixPath(path).parent) in self.files:
                    raise FileExistsError("Fixture parent is a file")
                raise NotADirectoryError("Fixture parent is a file")
            self.directories.update(parents)
            self.files[path] = text
            return {"ok": True, "path": args["path"], "bytes": size}
        if not path:
            raise ValueError("Cannot delete fixture root")
        self.files = {p: text for p, text in self.files.items()
                      if p != path and not p.startswith(path + "/")}
        self.directories = {p for p in self.directories
                            if p != path and not p.startswith(path + "/")}
        return {"ok": True, "path": args["path"], "deleted": True}


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
