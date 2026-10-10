"""An SDK-protected LangGraph agent the sandbox child rebuilds (test_detonation.py)."""

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

import mirage
from agents.common.testing import scripted


@tool
def read_calendar() -> list:
    """Read tomorrow's events."""
    raise RuntimeError("the real tool must never run in the sandbox")


@tool
def send_email(to: str, body: str) -> dict:
    """Send an email."""
    raise RuntimeError("the real tool must never run in the sandbox")


def factory():
    graph = create_agent(scripted(AIMessage("live reply after the freeze")),
                         tools=[read_calendar, send_email])
    mirage.protect(graph, name="assistant")
