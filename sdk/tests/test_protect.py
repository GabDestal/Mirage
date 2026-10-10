"""Public wrapper dispatch, with no framework or network calls."""

from types import SimpleNamespace
from unittest.mock import Mock

import mirage
import pytest
from mirage import adapters


@pytest.mark.parametrize("module,adapter", [
    ("langgraph.graph", "langchain"),
    ("agents.agent", "openai_agents"),
    ("claude_agent_sdk.types", "claude_agent"),
])
@pytest.mark.parametrize("kwargs", [{}, {"api_key": None}, {"api_key": "mirage_live_demo"}])
def test_protect_ignores_demo_api_key(module, adapter, kwargs, monkeypatch):
    agent = type("Agent", (), {"__module__": module, "tools": [], "instructions": "task"})()
    result = object()
    wrap = Mock(return_value=result)
    monkeypatch.setattr(adapters, adapter, SimpleNamespace(protect=wrap), raising=False)
    allow = {"tools": ["read_calendar"]}

    assert mirage.protect(agent, "assistant", allow, "liam", "demo:build", **kwargs) is result
    wrap.assert_called_once_with(agent, "assistant", allow, "liam", "demo:build")
