"""Claude Agent SDK `ClaudeAgentOptions`: plugs into the CLI's hooks.

Run start: `UserPromptSubmit`. Tool check (wait while frozen, deny on kill): `PreToolUse`.
Tool result: `PostToolUse`. Run end: `Stop`. Hooks run in separate tasks, so the run handle is
kept per `session_id` instead of in core's contextvar.
shortcut: model calls are not recorded (no per-call hook, the model runs in the CLI); read the
session transcript when the snapshot needs them.
Sandbox: custom tools (`create_sdk_mcp_server`) answer from the engine's `call_tool`, every other
tool is denied. The model cannot be replayed to the freeze, so the sandbox reruns it live from
the task.
"""

import asyncio
import json

import anyio
from claude_agent_sdk import HookMatcher, SdkMcpTool, query

from mirage import core
from mirage.protect import registry

_runs = {}  # session_id -> run handle
_calls = {}  # tool_use_id -> engine call_id, from PreToolUse to PostToolUse


def _find_tools(fn, depth=4):
    # shortcut: create_sdk_mcp_server keeps its SdkMcpTools in closures; walk them. Pinned by
    # test_claude_agent.py. Upgrade: a public way to list a server's tool definitions.
    for cell in getattr(fn, "__closure__", None) or ():
        value = cell.cell_contents
        if isinstance(value, dict) and value and all(isinstance(t, SdkMcpTool) for t in value.values()):
            return list(value.values())
        if callable(value) and depth and (found := _find_tools(value, depth - 1)):
            return found
    return []


def _sdk_tools(options):
    """{full tool name: SdkMcpTool} for the in-process MCP servers."""
    tools, servers = {}, options.mcp_servers
    for server, config in (servers.items() if isinstance(servers, dict) else ()):  # or a config path
        if config.get("type") != "sdk":
            continue
        instance = config["instance"]
        handlers = getattr(instance, "_request_handlers", None) or getattr(instance, "request_handlers", {})
        for entry in handlers.values():
            for t in _find_tools(getattr(entry, "handler", entry)):
                tools[f"mcp__{server}__{t.name}"] = t
    return tools


def _sandboxed(name):
    async def answer(args):
        result = await asyncio.to_thread(core._sandbox["call_tool"], name, core._json(args))
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    return answer


def _deny(reason, stop=False):
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                  "permissionDecisionReason": reason}}
    return {**out, "continue_": False, "stopReason": reason} if stop else out


def _hooks(name, sdk_tools):
    async def on_prompt(data, tool_use_id, context):
        if not core._sandbox:
            _runs[data["session_id"]] = await asyncio.to_thread(core.open_run, name, data["prompt"])
        return {}

    async def on_pre_tool(data, tool_use_id, context):
        tool = data["tool_name"]
        if core._sandbox:
            return {} if tool in sdk_tools else _deny(f"{tool} is not available in the Mirage sandbox.")
        try:
            _calls[data["tool_use_id"]] = await asyncio.to_thread(
                core.check, tool, data["tool_input"], _runs.get(data["session_id"]))
        except Exception as e:  # noqa: BLE001 - killed, halted, blocked or engine down: fail closed
            return _deny(str(e) or type(e).__name__, stop=True)
        return {}

    async def on_post_tool(data, tool_use_id, context):
        call_id = _calls.pop(data["tool_use_id"], None)
        if call_id and not core._sandbox:
            await asyncio.to_thread(core.record, _runs[data["session_id"]], call_id,
                                    data["tool_name"], data["tool_response"])
        return {}

    async def on_stop(data, tool_use_id, context):
        if (run := _runs.pop(data["session_id"], None)) and not core._sandbox:
            await asyncio.to_thread(core.complete, run)
        return {}

    return {
        "UserPromptSubmit": HookMatcher(hooks=[on_prompt]),
        "PreToolUse": HookMatcher(hooks=[on_pre_tool], timeout=3600),  # waits while frozen
        "PostToolUse": HookMatcher(hooks=[on_post_tool]),
        "Stop": HookMatcher(hooks=[on_stop]),
    }


def protect(options, name, allow, owner, entrypoint):
    sdk_tools = _sdk_tools(options)
    if core._sandbox:
        for full_name, t in sdk_tools.items():
            t.handler = _sandboxed(full_name)
    options.hooks = options.hooks or {}
    for event, matcher in _hooks(name, sdk_tools).items():
        options.hooks.setdefault(event, []).append(matcher)
    core.register(name, list(sdk_tools), allow, entrypoint, owner)

    async def run(task):
        return [message async for message in query(prompt=task, options=options)]

    registry[name] = lambda task: anyio.run(run, task)
    return options
