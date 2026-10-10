"""The fleet runner's agents can be rebuilt by the sandbox (module-level factories)."""

import importlib
from pathlib import Path


def test_every_fleet_agent_has_a_module_level_factory():
    fleet = importlib.import_module("agents.run_demo_fleet")
    for factory, task in fleet.FLEET:
        # what the sandbox does with entrypoint "agents.run_demo_fleet:<name>"
        assert getattr(fleet, factory.__name__) is factory
        assert task


def test_the_runner_does_not_import_the_engine():
    source = importlib.import_module("agents.run_demo_fleet").__file__
    text = Path(source).read_text(encoding="utf-8")
    assert "from engine" not in text and "import engine" not in text  # CONTRACTS.md §8
