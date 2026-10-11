"""Startup configuration in fresh processes, with synthetic dotenv and no providers."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = """
import json
import os
import sys
from unittest.mock import Mock

import boto3
import dotenv

# Every loader sees only the synthetic file outside the repository.
load_dotenv = dotenv.load_dotenv
dotenv.load_dotenv = Mock(side_effect=lambda: load_dotenv(sys.argv[1]))
boto3.client = Mock(side_effect=AssertionError("Provider construction is forbidden"))
"""
MODE_PROBE = """
from fastapi.testclient import TestClient
from contracts.models import AgentSpec
from engine.api import server
from engine.gateway import gate
from engine.detonation import jobs
from tests.test_api import AGENT, ATTACKER

if len(sys.argv) > 2:
    os.environ["MIRAGE_MODE"] = sys.argv[2]

client = TestClient(server.app)
registered = client.post("/agents", json=AGENT).status_code
gate.agents[AGENT["name"]] = AgentSpec.model_validate(AGENT)
run = gate.LiveRun(id="run_probe", agent=AGENT["name"], task="Prepare meetings",
                   status="running")
gate.runs[run.id] = run
jobs.automatic = Mock()
decision = gate.check(run, "send_email", {"to": ATTACKER})
assert decision.decision == "freeze" and run.status == "frozen"
assert boto3.client.call_count == 0
print(json.dumps({"mode": server.MODE, "replay": server.REPLAY is not None,
                  "registration": registered, "automatic": jobs.automatic.call_count}))
"""


def probe(tmp_path, script=MODE_PROBE, *, dotenv_text="", mode=None, mutation=None):
    dotenv_path = tmp_path / "synthetic.env"
    dotenv_path.write_text(dotenv_text)
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT),
           "MIRAGE_LAYER2": "0", "MIRAGE_JUDGE": "0",
           "MIRAGE_DB": str(tmp_path / "events.db"),
           "MIRAGE_SNAPSHOTS": str(tmp_path / "snapshots"),
           "MIRAGE_TOKENS": str(tmp_path / "tokens.json")}
    if mode is not None:
        env["MIRAGE_MODE"] = mode
    args = [sys.executable, "-c", BOOTSTRAP + script, str(dotenv_path)]
    if mutation is not None:
        args.append(mutation)
    return subprocess.run(args, check=False, cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=20)


def result(process):
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


def test_dotenv_replay_disables_live_api_and_automatic_proof(tmp_path):
    assert result(probe(tmp_path, dotenv_text="MIRAGE_MODE=replay\n")) == {
        "mode": "replay", "replay": True, "registration": 409, "automatic": 0}


def test_shell_live_overrides_dotenv_replay(tmp_path):
    assert result(probe(tmp_path, mode="live", dotenv_text="MIRAGE_MODE=replay\n")) == {
        "mode": "live", "replay": False, "registration": 200, "automatic": 1}


def test_missing_mode_defaults_to_live(tmp_path):
    assert result(probe(tmp_path)) == {
        "mode": "live", "replay": False, "registration": 200, "automatic": 1}


def test_dotenv_loads_before_store_paths_and_api_flags(tmp_path):
    script = """
for name in ("MIRAGE_DB", "MIRAGE_SNAPSHOTS", "MIRAGE_TOKENS"):
    os.environ.pop(name)
from engine.api import server
assert str(server.events.DB_PATH) == os.environ["MIRAGE_DB"]
assert str(server.snapshot.SNAP_DIR) == os.environ["MIRAGE_SNAPSHOTS"]
assert str(server.engine_handoff.TOKENS) == os.environ["MIRAGE_TOKENS"]
assert server.PUBLIC
assert server.REPLAY.managed and server.REPLAY.speed == float("inf")
assert boto3.client.call_count == 0
"""
    process = probe(tmp_path, script, dotenv_text=(
        f"MIRAGE_DB={tmp_path / 'dotenv.db'}\n"
        f"MIRAGE_SNAPSHOTS={tmp_path / 'dotenv-snapshots'}\n"
        f"MIRAGE_TOKENS={tmp_path / 'dotenv-tokens.json'}\n"
        "MIRAGE_MODE=replay\nMIRAGE_PUBLIC=1\n"
        "MIRAGE_REPLAY_MANAGED=1\nMIRAGE_REPLAY_SPEED=inf\n"))
    assert process.returncode == 0, process.stdout + process.stderr


@pytest.mark.parametrize("mode", ["invalid", "LIVE", "", " live", "replay "])
@pytest.mark.parametrize("source", ["shell", "dotenv"])
def test_invalid_mode_refuses_api_startup(tmp_path, mode, source):
    process = probe(tmp_path, "from engine.api import server\n",
                    mode=mode if source == "shell" else None,
                    dotenv_text=f'MIRAGE_MODE="{mode}"\n' if source == "dotenv" else "")
    assert process.returncode != 0
    assert "MIRAGE_MODE must be 'live' or 'replay'" in process.stderr


@pytest.mark.parametrize("mode,mutation", [("live", "replay"), ("replay", "live")])
def test_later_environment_change_cannot_split_api_and_gate(tmp_path, mode, mutation):
    assert result(probe(tmp_path, mode=mode, mutation=mutation)) == {
        "mode": mode, "replay": mode == "replay",
        "registration": 409 if mode == "replay" else 200,
        "automatic": 0 if mode == "replay" else 1}


def test_dotenv_loads_before_decision_model_settings_and_only_once(tmp_path):
    script = """
os.environ.pop("MIRAGE_LAYER2")
from engine.detection import decision_model
assert not decision_model.enabled()
os.environ["MIRAGE_LAYER2"] = "1"
calls = []
decision_model._client = Mock()
decision_model._client.converse.side_effect = lambda **kwargs: calls.append(kwargs) or {
    "output": {"message": {"content": [{"text": '{"violates": false}'}]}}}
decision_model.classify("assistant", "Prepare meetings", "send_email", {})
assert calls[0]["modelId"] == "synthetic-gate-model"
from engine.api import server
assert dotenv.load_dotenv.call_count == 1
assert boto3.client.call_count == 0
"""
    process = probe(tmp_path, script, dotenv_text=(
        "MIRAGE_MODE=live\nMIRAGE_LAYER2=0\nBEDROCK_GATE_MODEL_ID=synthetic-gate-model\n"))
    assert process.returncode == 0, process.stdout + process.stderr
