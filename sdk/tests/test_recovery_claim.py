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
    with pytest.raises(ValueError), core.recovery_run("assistant", "Original task", restarted_from="old"):
        raise ValueError("Synthetic callback error")
    assert requests[-1] == ("/runs/new/complete", {"error": "ValueError"})
    assert core._run.get() is None


def test_recovery_refuses_nested_context_before_claim(monkeypatch):
    token = core._run.set({"id": "existing", "token": "synthetic"})
    try:
        with pytest.raises(core.Blocked), core.recovery_run("assistant", "Original task", restarted_from="old"):
            pytest.fail("Nested recovery must not execute")
    finally:
        core._run.reset(token)


def test_http_claim_selects_exact_approved_queue_and_executes_callback(monkeypatch):
    from fastapi.testclient import TestClient

    from engine.api.server import app
    from engine.gateway import gate

    gate.reset()
    client = TestClient(app)
    monkeypatch.setattr(core, "_http", client)
    core.register("assistant", ["send_email"], {"tools": ["send_email"], "email_to": ["user@mirage-demo.com"]})
    human = {"actor": "synthetic-human", "reason": "Focused queue identity check"}
    originals = [core.open_run("assistant", "Exact original task")["id"] for _ in range(2)]
    queues = []
    for old in originals:
        assert client.post(f"/runs/{old}/kill", json=human).status_code == 200
        queues.append(client.post(f"/runs/{old}/restart", json=human).json()["id"])
    effects = []
    with core.recovery_run("assistant", "Exact original task", restarted_from=originals[1]) as run:
        assert run["id"] == queues[1]
        core.tool("send_email", {"to": "user@mirage-demo.com", "body": "Synthetic useful task"},
                  lambda: effects.append("one brief"))
    assert effects == ["one brief"]
    assert client.get(f"/runs/{queues[1]}").json()["status"] == "completed"
    assert client.get(f"/runs/{queues[0]}").json()["status"] == "queued"
    assert all(client.get(f"/runs/{old}").json()["status"] == "killed" for old in originals)
    with pytest.raises(Exception) as denied, core.recovery_run(
        "assistant", "Exact original task", restarted_from=originals[1]
    ):
        pytest.fail("An already claimed queue must never start twice")
    assert denied.value.response.status_code == 409
