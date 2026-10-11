"""Explicit recovery identity and nested adapter invocations, without provider calls."""

import pytest
from mirage import core


def test_recovery_claim_sends_original_identity_and_completes_once(monkeypatch):
    requests = []

    def post(path, body=None, run=None):
        requests.append((path, body.model_dump() if body else None, run))
        return {"run_id": "new", "run_token": "synthetic"} if path == "/runs" else None

    monkeypatch.setattr(core, "_post", post)
    with core.recovery_run("assistant", "Original task", restarted_from="old") as run:
        assert run["id"] == "new"
        assert core.start("assistant", "Original task") is None
        core.end(None)
    assert requests[0][1]["restarted_from"] == "old"
    assert [path for path, _, _ in requests] == ["/runs", "/runs/new/complete"]
    assert core._run.get() is None


def test_failed_invocation_stays_failed_and_restores_context(monkeypatch):
    requests = []

    def post(path, body=None, run=None):
        requests.append((path, body.model_dump() if body else None))
        return {"run_id": "new", "run_token": "synthetic"} if path == "/runs" else None

    monkeypatch.setattr(core, "_post", post)
    with pytest.raises(ValueError):
        with core.recovery_run("assistant", "Original task", restarted_from="old"):
            raise ValueError("Synthetic callback error")
    assert requests[-1] == ("/runs/new/complete", {"error": "ValueError"})
    assert core._run.get() is None


def test_recovery_refuses_nested_context_before_claim(monkeypatch):
    token = core._run.set({"id": "existing", "token": "synthetic"})
    try:
        with pytest.raises(core.Blocked):
            with core.recovery_run("assistant", "Original task", restarted_from="old"):
                pytest.fail("Nested recovery must not execute")
    finally:
        core._run.reset(token)
