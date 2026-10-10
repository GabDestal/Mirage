import pytest

from engine import handoff
from engine.detonation import snapshot
from engine.store import events


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Every test writes events and snapshots to a temp folder, never to data/."""
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "events.db")
    monkeypatch.setattr(snapshot, "SNAP_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(handoff, "TOKENS", tmp_path / "tokens.json")
    events.reset()
    yield
    events.reset()
