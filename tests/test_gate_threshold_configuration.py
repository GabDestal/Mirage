"""Gate thresholds are startup authority. Fresh processes, synthetic dotenv, no providers."""

import json
import os
import subprocess
import sys

import pytest

from tests.test_startup_mode import BOOTSTRAP, ROOT

REVIEW = "MIRAGE_GATE_REVIEW"
FREEZE = "MIRAGE_GATE_THRESHOLD"
ERROR = f"0 <= {REVIEW} <= {FREEZE} <= 1"
RECEIPT = """
import atexit
from pathlib import Path

def record_startup():
    Path(sys.argv[2]).write_text(json.dumps({
        "provider_calls": boto3.client.call_count,
        "dotenv_calls": dotenv.load_dotenv.call_count,
        "data_modules": [name for name in (
            "engine.api.server", "engine.gateway.gate", "engine.store.events",
            "engine.detonation.snapshot", "engine.cli",
        ) if name in sys.modules],
    }))

atexit.register(record_startup)
"""
GATE_PROBE = """
from fastapi.testclient import TestClient
from engine.api import server
from engine.detection import decision_model
from engine.detonation import jobs
from engine.gateway import gate
from tests.test_api import AGENT, USER, check, start

jobs.automatic = Mock()
client = TestClient(server.app)
assert client.post("/agents", json=AGENT).status_code == 200
actions = []
for p in (0, 0.3999, 0.4, 0.55, 0.6999, 0.7, 0.75, 1):
    answer = {"violates": True, "policy_id": "P6", "p": p,
              "reason": "Content changed the task."}
    decision_model._converse = Mock(return_value={
        "output": {"message": {"content": [{"text": json.dumps(answer)}]}}})
    run_id, auth = start(client)
    decision = check(client, run_id, auth, "send_email", to=USER, body="Brief").json()
    if decision["decision"] == "allow":
        assert gate.runs[run_id].status == "running"
        actions.append("allow")
    else:
        assert decision["decision"] == "freeze" and decision["layer"] == "decision_model"
        assert decision["policy_id"] == "P6" and gate.runs[run_id].status == "frozen"
        if decision["rule_id"] == "NEEDS_APPROVAL":
            assert gate.runs[run_id].incident_id is None
            actions.append("hold")
        else:
            assert gate.runs[run_id].incident_id is not None
            actions.append("freeze")
    assert decision_model._converse.call_count == 1
assert boto3.client.call_count == 0
assert dotenv.load_dotenv.call_count == 1
print(json.dumps(actions))
"""
DEFAULT_ACTIONS = ["allow", "allow", "hold", "hold", "hold", "freeze", "freeze", "freeze"]
INVALID = [
    pytest.param({name: value}, id=f"{name}-{label}")
    for name in (REVIEW, FREEZE)
    for label, value in (
        ("empty", ""), ("text", "synthetic-invalid-value"), ("nan", "nan"),
        ("infinity", "inf"), ("negative-infinity", "-Infinity"), ("overflow", "1e999"),
        ("negative", "-0.1"), ("over-one", "1.1"),
    )
] + [pytest.param({REVIEW: "0.8", FREEZE: "0.7"}, id="reversed")]


def probe(tmp_path, script, *, dotenv_values=None, shell=None):
    dotenv_path = tmp_path / "synthetic.env"
    dotenv_path.write_text("".join(f'{name}="{value}"\n'
                                  for name, value in (dotenv_values or {}).items()))
    receipt_path = tmp_path / "startup.json"
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT),
           "AWS_EC2_METADATA_DISABLED": "true", "MIRAGE_MODE": "live",
           "MIRAGE_LAYER2": "1", "MIRAGE_JUDGE": "0",
           "MIRAGE_DB": str(tmp_path / "events.db"),
           "MIRAGE_SNAPSHOTS": str(tmp_path / "snapshots"),
           "MIRAGE_TOKENS": str(tmp_path / "tokens.json"), **(shell or {})}
    process = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP + RECEIPT + script, str(dotenv_path), str(receipt_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False, timeout=20)
    return process, json.loads(receipt_path.read_text())


def assert_refused(process, receipt, tmp_path):
    assert process.returncode != 0, "Invalid gate thresholds admitted engine startup"
    assert ERROR in process.stderr
    assert "synthetic-invalid-value" not in process.stderr
    assert receipt == {"provider_calls": 0, "dotenv_calls": 1, "data_modules": []}
    assert not (tmp_path / "events.db").exists()
    assert not (tmp_path / "snapshots").exists()
    assert not (tmp_path / "tokens.json").exists()


@pytest.mark.parametrize("values", INVALID)
@pytest.mark.parametrize("source", ["shell", "dotenv"])
def test_invalid_thresholds_refuse_api_startup(tmp_path, values, source):
    process, receipt = probe(tmp_path, "from engine.api import server\n",
                             shell=values if source == "shell" else None,
                             dotenv_values=values if source == "dotenv" else None)
    assert_refused(process, receipt, tmp_path)


@pytest.mark.parametrize("module", ["engine.gateway.gate", "engine.detection.decision_model",
                                    "engine.cli"])
@pytest.mark.parametrize("values", [{REVIEW: "nan"}, {FREEZE: "nan"},
                                    {REVIEW: "0.8", FREEZE: "0.7"}])
def test_other_engine_entrypoints_refuse_invalid_thresholds(tmp_path, module, values):
    process, receipt = probe(tmp_path, f"import {module}\n", shell=values)
    assert_refused(process, receipt, tmp_path)


def test_invalid_shell_wins_over_valid_dotenv_even_with_layer2_disabled(tmp_path):
    process, receipt = probe(tmp_path, "from engine.api import server\n",
                             dotenv_values={REVIEW: "0.4", FREEZE: "0.7"},
                             shell={REVIEW: "nan", "MIRAGE_LAYER2": "0"})
    assert_refused(process, receipt, tmp_path)


@pytest.mark.parametrize("values,actions", [
    ({}, DEFAULT_ACTIONS),
    ({REVIEW: "0.4", FREEZE: "0.7"}, DEFAULT_ACTIONS),
    ({REVIEW: "0.6", FREEZE: "0.8"}, ["allow"] * 4 + ["hold"] * 3 + ["freeze"]),
    ({REVIEW: "0", FREEZE: "0"}, ["freeze"] * 8),
    ({REVIEW: "0", FREEZE: "1"}, ["hold"] * 7 + ["freeze"]),
    ({REVIEW: "1", FREEZE: "1"}, ["allow"] * 7 + ["freeze"]),
    ({REVIEW: "0.7", FREEZE: "0.7"}, ["allow"] * 5 + ["freeze"] * 3),
])
def test_valid_dotenv_thresholds_control_actual_gate_boundaries(tmp_path, values, actions):
    process, receipt = probe(tmp_path, GATE_PROBE, dotenv_values=values)
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(process.stdout) == actions
    assert receipt["provider_calls"] == 0


def test_valid_shell_thresholds_override_invalid_dotenv(tmp_path):
    process, _ = probe(tmp_path, GATE_PROBE,
                       dotenv_values={REVIEW: "nan", FREEZE: "synthetic-invalid-value"},
                       shell={REVIEW: "0.4", FREEZE: "0.7"})
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(process.stdout) == DEFAULT_ACTIONS


@pytest.mark.parametrize("mutation", [
    {REVIEW: "nan"}, {FREEZE: "inf"}, {REVIEW: "0.8", FREEZE: "0.7"},
    {REVIEW: "synthetic-invalid-value", FREEZE: ""}, {REVIEW: "0.9", FREEZE: "1"},
])
def test_later_environment_mutation_cannot_change_active_gate_thresholds(tmp_path, mutation):
    script = ("from engine.api import server\n"
              f"os.environ.update({mutation!r})\n" + GATE_PROBE)
    process, _ = probe(tmp_path, script, dotenv_values={REVIEW: "0.4", FREEZE: "0.7"})
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(process.stdout) == DEFAULT_ACTIONS


def test_later_dotenv_reload_cannot_change_active_gate_thresholds(tmp_path):
    script = """
from engine.api import server
Path(sys.argv[1]).write_text("MIRAGE_GATE_REVIEW=nan\\nMIRAGE_GATE_THRESHOLD=inf\\n")
load_dotenv(sys.argv[1], override=True)
""" + GATE_PROBE
    process, _ = probe(tmp_path, script, dotenv_values={REVIEW: "0.4", FREEZE: "0.7"})
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(process.stdout) == DEFAULT_ACTIONS
