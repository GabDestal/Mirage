"""Real CLI entrypoints in fresh processes, with synthetic dotenv and no providers."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = """
import atexit
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

import boto3
import dotenv

# Never discover the repository's dotenv or inherit a disabled synthetic loader.
os.environ.pop("PYTHON_DOTENV_DISABLED", None)
synthetic_dotenv = os.environ["CLI_TEST_DOTENV"]
load_dotenv = dotenv.load_dotenv
dotenv.load_dotenv = Mock(side_effect=lambda: load_dotenv(synthetic_dotenv))
boto3.client = Mock(side_effect=AssertionError("Provider construction is forbidden"))

def record_startup():
    if "engine.config" not in sys.modules:
        return  # Invalid configuration refused startup.
    from engine import config, handoff
    from engine.detonation import snapshot
    from engine.gateway import gate
    from engine.store import events

    Path(os.environ["CLI_TEST_RESULT"]).write_text(json.dumps({
        "mode": config.MODE, "gate_mode": gate.MODE,
        "snapshots": str(snapshot.SNAP_DIR), "db": str(events.DB_PATH),
        "tokens": str(handoff.TOKENS), "dotenv_calls": dotenv.load_dotenv.call_count,
        "provider_calls": boto3.client.call_count,
        "api_loaded": "engine.api.server" in sys.modules,
    }))

atexit.register(record_startup)
"""


def probe(tmp_path, entrypoint, *, dotenv_mode=None, shell_mode=None, shell_paths=False):
    paths = {"snapshots": str(tmp_path / "dotenv-snapshots"),
             "db": str(tmp_path / "dotenv.db"),
             "tokens": str(tmp_path / "dotenv-tokens.json")}
    variables = {"snapshots": "MIRAGE_SNAPSHOTS", "db": "MIRAGE_DB", "tokens": "MIRAGE_TOKENS"}
    dotenv_path = tmp_path / "synthetic.env"
    dotenv_text = "".join(f"{variables[key]}={value}\n" for key, value in paths.items())
    if dotenv_mode is not None:
        dotenv_text += f'MIRAGE_MODE="{dotenv_mode}"\n'
    dotenv_path.write_text(dotenv_text)
    (tmp_path / "sitecustomize.py").write_text(BOOTSTRAP)
    result_path = tmp_path / "startup.json"
    # Deliberate allowlist: no inherited provider secrets, mode, paths or Python settings.
    env = {"PATH": os.environ.get("PATH", ""),
           "PYTHONPATH": os.pathsep.join((str(tmp_path), str(ROOT))),
           "PYTHON_DOTENV_DISABLED": "1", "AWS_EC2_METADATA_DISABLED": "true",
           "MIRAGE_LAYER2": "0", "MIRAGE_JUDGE": "0",
           "CLI_TEST_DOTENV": str(dotenv_path), "CLI_TEST_RESULT": str(result_path)}
    if shell_mode is not None:
        env["MIRAGE_MODE"] = shell_mode
    if shell_paths:
        paths = {"snapshots": str(tmp_path / "shell-snapshots"),
                 "db": str(tmp_path / "shell.db"),
                 "tokens": str(tmp_path / "shell-tokens.json")}
        env.update({variables[key]: value for key, value in paths.items()})
    if entrypoint == "module":
        command = [sys.executable, "-m", "engine.cli", "--help"]
    else:
        console = tmp_path / "mirage"
        console.write_text("from engine.cli import main\nraise SystemExit(main())\n")
        command = [sys.executable, str(console), "--help"]
    process = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True,
                             check=False, timeout=20)
    return process, result_path, paths


@pytest.mark.parametrize("entrypoint", ["module", "console"])
@pytest.mark.parametrize("dotenv_mode,shell_mode,expected", [
    (None, None, "live"), ("replay", None, "replay"),
    ("replay", "live", "live"), ("live", "replay", "replay"),
])
def test_cli_dotenv_loads_before_paths_and_mode(tmp_path, entrypoint, dotenv_mode,
                                            shell_mode, expected):
    process, result_path, paths = probe(tmp_path, entrypoint, dotenv_mode=dotenv_mode,
                                       shell_mode=shell_mode)
    assert process.returncode == 0, process.stdout + process.stderr
    assert result_path.exists(), process.stdout + process.stderr
    assert json.loads(result_path.read_text()) == {
        **paths, "mode": expected, "gate_mode": expected, "dotenv_calls": 1,
        "provider_calls": 0, "api_loaded": False}


@pytest.mark.parametrize("entrypoint", ["module", "console"])
def test_cli_shell_paths_override_dotenv(tmp_path, entrypoint):
    process, result_path, paths = probe(tmp_path, entrypoint, dotenv_mode="replay",
                                       shell_paths=True)
    assert process.returncode == 0, process.stdout + process.stderr
    assert result_path.exists(), process.stdout + process.stderr
    assert json.loads(result_path.read_text()) == {
        **paths, "mode": "replay", "gate_mode": "replay", "dotenv_calls": 1,
        "provider_calls": 0, "api_loaded": False}


@pytest.mark.parametrize("entrypoint", ["module", "console"])
@pytest.mark.parametrize("source", ["shell", "dotenv"])
@pytest.mark.parametrize("mode", ["invalid", "LIVE", "", " live", "replay "])
def test_cli_invalid_mode_refuses_startup(tmp_path, entrypoint, source, mode):
    process, result_path, _ = probe(tmp_path, entrypoint,
                                   dotenv_mode=mode if source == "dotenv" else "live",
                                   shell_mode=mode if source == "shell" else None)
    assert process.returncode != 0
    assert "MIRAGE_MODE must be 'live' or 'replay'" in process.stderr
    assert not result_path.exists()
    assert not (tmp_path / "data").exists()
