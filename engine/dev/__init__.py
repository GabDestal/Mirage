"""Engine dev harness: a minimal agent, fake services and seed data to exercise the gate.

shortcut: temporary. The real demo agents live in `agents/` with the SDK (Liam). Once the SDK
talks to the data plane (CONTRACTS.md §11), the gate stops calling tools itself and this folder
only serves engine tests. Run: `uv run python -m engine.dev.runner`.
"""
