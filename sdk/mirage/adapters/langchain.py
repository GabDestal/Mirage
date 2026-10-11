"""LangGraph / LangChain `create_agent` graphs: plugs into the compiled graph's own hooks.

Tools: the ToolNode's `wrap_tool_call` hook (what tool middleware uses). Model calls: the model
node's `wrap_model_call` handler. Run start/end: `invoke` and `stream`.
"""

import json

from langchain.agents.factory import _chain_model_call_handlers
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import ToolMessage, messages_from_dict, messages_to_dict

from contracts.models import ToolResult
from mirage import core
from mirage.protect import registry


def _content(message):
    try:
        return json.loads(message.content)
    except (TypeError, ValueError):
        return message.content


def _tool_hook(prev):
    def wrap(request, execute):
        call, out = request.tool_call, {}

        def real():
            out["msg"] = prev(request, execute) if prev else execute(request)
            if isinstance(out["msg"], ToolMessage) and out["msg"].status == "error":
                return ToolResult(call_id=call["id"], tool=call["name"],
                                  error="ToolMessageError")
            return _content(out["msg"]) if isinstance(out["msg"], ToolMessage) else None

        result = core.tool(call["name"], call["args"], real)
        if "msg" in out:
            return out["msg"]
        status = "success"
        if isinstance(result, ToolResult):
            status = "error" if result.error is not None else "success"
            result = result.result if result.result is not None else result.error
            content = result if isinstance(result, (str, list)) else json.dumps(result)
        else:
            content = result if isinstance(result, str) else json.dumps(result)
        return ToolMessage(content=content, tool_call_id=call["id"], name=call["name"],
                           status=status)
    return wrap


def _model_hook(prev):
    def ours(request, execute):
        if (reply := core.replayed_reply()) is not None:
            return ModelResponse(result=messages_from_dict(reply["messages"]))
        response = execute(request)
        model = request.model
        messages = [ToolMessage(content="ToolMessageError", status="error",
                                tool_call_id=m.tool_call_id, name=m.name, id=m.id)
                    if isinstance(m, ToolMessage) and m.status == "error" else m
                    for m in request.messages]
        core.model_call(
            getattr(model, "model_id", None) or getattr(model, "model", None) or type(model).__name__,
            {"system": request.system_prompt, "messages": messages_to_dict(messages),
             "tools": [getattr(t, "name", str(t)) for t in request.tools]},
            {"messages": messages_to_dict(response.result)})
        return response

    composed = _chain_model_call_handlers([ours])

    def wrap(request, execute):
        # shortcut: drops Commands from the agent's own model middleware; fine for the demo agents
        inner = execute if prev is None else (lambda r: prev(r, execute).model_response)
        return composed(request, inner)
    return wrap


def _set_free_var(fn, var, value):
    # shortcut: create_agent keeps its model handler in a closure (and _chain_model_call_handlers
    # is private); patch it. Pinned by test_langgraph.py. Upgrade: a public middleware hook.
    fn.__closure__[fn.__code__.co_freevars.index(var)].cell_contents = value


def _task(graph_input):
    messages = graph_input.get("messages", []) if isinstance(graph_input, dict) else []
    last = messages[-1] if messages else ""
    return last[1] if isinstance(last, tuple) else getattr(last, "content", str(last))


def protect(graph, name, allow, owner, entrypoint):
    tool_node = graph.nodes["tools"].bound
    tool_node._wrap_tool_call = _tool_hook(tool_node._wrap_tool_call)
    model_node = graph.nodes["model"].bound.func
    handler = model_node.__closure__[model_node.__code__.co_freevars.index(
        "wrap_model_call_handler")].cell_contents
    _set_free_var(model_node, "wrap_model_call_handler", _model_hook(handler))
    # shortcut: sync invoke/stream only; add ainvoke/astream when an async agent needs it.
    invoke, stream = graph.invoke, graph.stream

    def protected_invoke(graph_input, *args, **kwargs):
        token = core.start(name, _task(graph_input))
        try:
            result = invoke(graph_input, *args, **kwargs)
        except BaseException as error:
            core.end(token, error)
            raise
        else:
            core.end(token)
            return result

    def protected_stream(graph_input, *args, **kwargs):
        token = core.start(name, _task(graph_input))
        try:
            yield from stream(graph_input, *args, **kwargs)
        except BaseException as error:
            core.end(token, error)
            raise
        else:
            core.end(token)

    graph.invoke, graph.stream = protected_invoke, protected_stream
    core.register(name, list(tool_node.tools_by_name), allow, entrypoint, owner)
    registry[name] = lambda task: protected_invoke({"messages": [("user", task)]})
    return graph
