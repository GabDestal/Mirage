import pytest

from engine import handoff
from engine.detonation import jobs, snapshot
from engine.store import events


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Every test, in every folder (tests/, agents/, sdk/tests/), writes events, snapshots and
    tokens to a temp folder, never to data/: a test run must not overwrite a real incident."""
    jobs.shutdown()
    jobs.start()
    # Freeze/unit tests do not implicitly run customer agents or call Bedrock. Scheduling
    # integration tests restore the real callback explicitly with scripted sandbox agents.
    monkeypatch.setattr(jobs, "automatic", lambda *_: None)
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "events.db")
    monkeypatch.setattr(snapshot, "SNAP_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(handoff, "TOKENS", tmp_path / "tokens.json")
    events.reset()
    yield
    jobs.shutdown()
    events.reset()
