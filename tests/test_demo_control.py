"""Live /demo/start and /demo/reset: a clean slate, then Liam's fleet runner as its own process."""

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from engine.api import server
from engine.gateway import gate
from engine.store import events
from tests.test_api import AGENT, HUMAN


class FakeProcess:
    launched: ClassVar[list] = []

    def __init__(self, args, cwd, env):
        self.args, self.cwd, self.env, self.stopped = args, cwd, env, False
        FakeProcess.launched.append(self)

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, "REPLAY", None)
    monkeypatch.setattr(server.subprocess, "Popen", FakeProcess)
    FakeProcess.launched = []
    server._demo["proc"] = None
    gate.reset()
    yield TestClient(server.app)
    server._demo["proc"] = None


def test_start_resets_then_launches_the_fleet_runner(api):
    api.post("/agents", json=AGENT)
    api.post("/stop", json=HUMAN)  # a STOP from the last rehearsal
    assert api.post("/demo/start", json={}).status_code == 204  # the UI sends {}

    (proc,) = FakeProcess.launched
    assert proc.args[1:] == ["-m", "agents.run_demo_fleet"]
    assert proc.env["MIRAGE_URL"] == "http://testserver"  # the agents talk to this engine
    assert not gate.STOP.is_set() and not gate.agents and events.read() == []

    api.post("/demo/start")  # a second start replaces the first agents process
    assert proc.stopped and len(FakeProcess.launched) == 2


def test_reset_stops_the_agents_and_lifts_stop(api):
    api.post("/demo/start")
    api.post("/stop", json=HUMAN)
    assert api.post("/demo/reset").status_code == 204
    assert FakeProcess.launched[0].stopped and not gate.STOP.is_set()
    assert api.post("/agents", json=AGENT).status_code == 200


def test_only_the_calendar_scenario_is_built(api):
    assert api.post("/demo/start", json={"scenario": "false_positive"}).status_code == 501
    assert FakeProcess.launched == []


def test_engine_shutdown_stops_the_demo_fleet(api):
    with TestClient(server.app) as client:  # `with` runs the app's startup and shutdown
        client.post("/demo/start")
    assert FakeProcess.launched[-1].stopped
