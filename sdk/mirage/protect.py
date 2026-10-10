"""`mirage.protect(agent)`: detects the framework and hands the agent to its adapter."""

import inspect
import sys

registry = {}  # agent name -> run(task); the sandbox runner uses it to rerun the agent


def _caller():
    """`module:function` where protect was called, so the sandbox can rebuild the agent."""
    frame = inspect.stack()[2].frame
    module = frame.f_globals.get("__name__", "")
    if module == "__main__":
        spec = getattr(sys.modules["__main__"], "__spec__", None)
        module = spec.name if spec else module
    function = frame.f_code.co_name
    return module if function == "<module>" else f"{module}:{function}"


def protect(agent, name, allow=None, owner="unknown", entrypoint=None):
    """Wrap an agent so Mirage checks every tool call. Returns the same agent, protected."""
    entrypoint = entrypoint or _caller()
    kind = type(agent).__module__
    if kind.startswith("langgraph"):
        from mirage.adapters import langchain
        return langchain.protect(agent, name, allow, owner, entrypoint)
    if kind.startswith("claude_agent_sdk"):
        from mirage.adapters import claude_agent
        return claude_agent.protect(agent, name, allow, owner, entrypoint)
    raise TypeError(f"mirage.protect: no adapter for {type(agent).__name__} ({kind}).")
