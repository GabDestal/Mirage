"""OpenAI Agents SDK `Agent`: plugs into the agent's own hooks.

Tools: each `FunctionTool.on_invoke_tool`. Model calls: `agent.model.get_response`.
Run start/end: `agent.hooks` `on_start` / `on_end`.
"""

import asyncio
import contextvars
import dataclasses
import json

from openai.types.responses import ResponseOutputItem
from pydantic import TypeAdapter

# `agents` here is the openai-agents package: protect.py only imports this module once it holds an
# `agents.*` Agent, so the name already resolves to it (not this repo's demo `agents/` package).
from agents import AgentHooks, ModelResponse, Runner, Usage
from mirage import core
from mirage.protect import registry

_output_item = TypeAdapter(ResponseOutputItem)


def _task(turn_input):
    last = turn_input[-1] if turn_input else ""
    return last.get("content", str(last)) if isinstance(last, dict) else str(last)


def _tool_hook(tool, state):
    prev = tool.on_invoke_tool

    async def invoke(tool_context, args_json):
        loop = asyncio.get_running_loop()

        def real():  # the real tool stays on the agent's loop; only the check waits in a thread
            return asyncio.run_coroutine_threadsafe(prev(tool_context, args_json), loop).result()

        # a thread so a frozen run never blocks the loop (other runs on it keep going)
        return await asyncio.to_thread(state["ctx"].copy().run, core.tool, tool.name,
                                       json.loads(args_json or "{}"), real)
    return invoke


def _model_hook(model, state):
    prev = model.get_response

    async def get_response(**kwargs):
        if (reply := core.replayed_reply()) is not None:
            return ModelResponse(output=[_output_item.validate_python(i) for i in reply["output"]],
                                 usage=Usage(), response_id=None)
        response = await prev(**kwargs)
        state["ctx"].copy().run(
            core.model_call, getattr(model, "model", None) or type(model).__name__,
            {"system": kwargs.get("system_instructions"), "input": kwargs.get("input"),
             "tools": [t.name for t in kwargs.get("tools") or []]},
            {"output": [i.model_dump(mode="json") for i in response.output]})
        return response
    return get_response


def protect(agent, name, allow, owner, entrypoint):
    # Hooks run in their own asyncio tasks, so core's run contextvar set there would be lost.
    # Keep the run in a Context and enter a copy of it for each tool / model call.
    # shortcut: one run at a time per Agent instance; give each concurrent run its own Agent.
    state = {"ctx": contextvars.Context()}  # empty = no run: tools fail closed
    # copies: a FunctionTool object is often shared by several agents
    agent.tools = [dataclasses.replace(t, on_invoke_tool=_tool_hook(t, state))
                   if hasattr(t, "on_invoke_tool") else t for t in agent.tools]
    tools = [t for t in agent.tools if hasattr(t, "on_invoke_tool")]
    if hasattr(agent.model, "get_response"):
        agent.model.get_response = _model_hook(agent.model, state)
    # shortcut: a model given by name (str/None) is not recorded or replayed, and
    # stream_response (Runner.run_streamed) is not recorded; pass a Model instance for both.

    hooks = agent.hooks or AgentHooks()
    prev_start, prev_end = hooks.on_start, hooks.on_end

    async def on_start(context, current):
        # shortcut: a handoff back to this agent starts a new Mirage run
        state["ctx"] = contextvars.copy_context()
        state["token"] = state["ctx"].run(core.start, name, _task(context.turn_input))
        await prev_start(context, current)

    async def on_end(context, current, output):
        state["ctx"].run(core.end, state.pop("token", None))
        await prev_end(context, current, output)

    hooks.on_start, hooks.on_end = on_start, on_end
    agent.hooks = hooks
    core.register(name, [t.name for t in tools], allow, entrypoint, owner)
    registry[name] = lambda task: Runner.run_sync(agent, task)
    return agent
