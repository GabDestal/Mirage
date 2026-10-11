"""Trusted one-agent recovery process; engine authority is accessed only over HTTP."""

import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path

from contracts.models import AgentSpec
from mirage import core

from agents.services import store

ENTRYPOINT = "agents.run_demo_fleet:meeting_assistant"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def restore_checkpoint(path, expected_digest):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError("Service checkpoint changed")
    checkpoint = json.loads(raw)
    if not isinstance(checkpoint, dict) or any(
        not isinstance(checkpoint.get(key), list)
        for key in ("calendar", "contacts", "inbox", "outbox")
    ):
        raise ValueError("A complete trusted service checkpoint is required")
    # This explicit checkpoint is the preserved service state, never a clean demo seed.
    store._state = copy.deepcopy(checkpoint)
    return checkpoint


def configure(config):
    if not isinstance(config, dict) or not config.get("DEMO_USER_EMAIL") or not any(
        config.get(key) for key in ("MEETING_ASSISTANT_MODEL_ID", "BEDROCK_AGENT_MODEL_ID",
                                   "BEDROCK_MODEL_ID")
    ):
        raise ValueError("Original non-secret model and user configuration is required")
    for key, value in config.items():
        if not (key.endswith("_MODEL_ID") or key in ("DEMO_USER_EMAIL", "AWS_REGION")) or not isinstance(value, str):
            raise ValueError("Only non-secret agent configuration is accepted")
        os.environ[key] = value


def build_factory(entrypoint):
    if entrypoint != ENTRYPOINT:
        raise ValueError("Only the original meeting-assistant factory is supported")
    module, name = entrypoint.split(":")
    return getattr(importlib.import_module(module), name)()


def captured_factory(entrypoint):
    """Build protected graph and capture its full registration without starting a run."""
    specs = []

    def no_tools(*_):
        raise RuntimeError("Factory construction must not execute tools")

    no_tools.register_spec = specs.append
    if core._sandbox or core._run.get():
        raise RuntimeError("Factory preparation requires an isolated process")
    core._sandbox = {"call_tool": no_tools, "replies": []}
    try:
        agent = build_factory(entrypoint)
    finally:
        core._sandbox = None
    if len(specs) != 1:
        raise ValueError("Factory must register exactly one complete AgentSpec")
    spec = AgentSpec.model_validate(specs[0])
    if spec.name != "meeting_assistant" or spec.entrypoint != entrypoint or not spec.legit:
        raise ValueError("Factory does not declare the original agent and useful task")
    return agent, spec


def get_run(run_id):
    response = core._http.get(f"/runs/{run_id}")
    response.raise_for_status()
    return response.json()


def execute(request, phase):
    checkpoint = restore_checkpoint(request["checkpoint_path"], request["checkpoint_digest"])
    configure(request["config"])
    original = get_run(request["original_run_id"])
    if original["agent"] != "meeting_assistant" or original["task"] != request["task"]:
        raise ValueError("Original agent or task mismatch")
    agent, spec = captured_factory(request["entrypoint"])
    if store._state != checkpoint:
        raise ValueError("Factory changed the preserved service state")
    receipt = {"agent_spec": spec.model_dump(mode="json"),
               "config_digest": digest(request["config"]),
               "checkpoint_digest": request["checkpoint_digest"]}
    if phase == "prepare":
        core._post("/agents", spec)
        return receipt
    if phase != "launch":
        raise ValueError("Unknown recovery phase")
    if receipt["agent_spec"] != request["agent_spec"]:
        raise ValueError("Repaired AgentSpec changed after preparation")
    if receipt["config_digest"] != request["config_digest"]:
        raise ValueError("Agent configuration changed after preparation")
    if original["status"] not in ("killed", "halted", "failed"):
        raise ValueError("Original run must remain contained")
    try:
        with core.recovery_run(spec.name, original["task"],
                               restarted_from=original["id"]) as handle:
            running = get_run(handle["id"])
            if (running["id"] != request["queued_run_id"]
                or running["restarted_from"] != original["id"]
                or running["agent"] != spec.name or running["task"] != original["task"]
                or running["status"] != "running"):
                raise ValueError("Approved queue claim did not enter the exact running task")
            # Fresh graph, one trusted user message; compromised messages never enter it.
            agent.invoke({"messages": [("user", original["task"])]})
            after = store._state
            if (any(after.get(key) != value for key, value in checkpoint.items() if key != "outbox")
                or after["outbox"][:-1] != checkpoint["outbox"]
                or len(after["outbox"]) != len(checkpoint["outbox"]) + 1
                or after["outbox"][-1].get("to") != request["config"]["DEMO_USER_EMAIL"]
                or not all(after["outbox"][-1].get(key) for key in ("subject", "body"))):
                raise ValueError("Recovery must preserve service state and produce exactly one brief")
    finally:
        Path(request["state_output_path"]).write_text(
            json.dumps(store._state, ensure_ascii=False, indent=2) + "\n")
    receipt.update(run_id=handle["id"], run=get_run(handle["id"]),
                   state_digest=digest(store._state),
                   state_output_path=request["state_output_path"])
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "launch"), required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = execute(json.loads(Path(args.request).read_text()), args.phase)
    except Exception as error:  # sanitized receipt; no provider text or credentials
        Path(args.output).write_text(json.dumps({"error": type(error).__name__}) + "\n")
        return 1
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
