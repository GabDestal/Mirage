"""Data plane client (CONTRACTS.md §11). Every decision is in the engine: this asks, waits, records.

Prod: each tool call is checked before it runs, waits while frozen, raises when killed.
Sandbox: `sandbox.run` sets `_sandbox`; tools go to the engine's `call_tool`, no HTTP at all
(the jail only allows Bedrock). Engine down = fail closed: the tool does not run.
"""

import contextvars
import json
import os

import httpx

from contracts.models import (  # shortcut: monorepo import; vendor the models when the SDK ships alone
    AgentSpec,
    Allowlist,
    GateDecision,
    ModelCall,
    RunStart,
    RunStarted,
    ToolCheck,
    ToolResult,
    WaitResult,
)

URL = os.getenv("MIRAGE_URL", "http://localhost:8000")
_http = httpx.Client(base_url=URL, timeout=httpx.Timeout(10, read=90))  # read > wait's 60 s cap
_run = contextvars.ContextVar("mirage_run", default=None)
_sandbox = None  # set by sandbox.run: {"call_tool": fn, "replies": [recorded model responses]}


class Blocked(Exception):
    """Mirage stopped this run (killed, halted or revoked). The tool did not run."""


def _json(value):
    return json.loads(json.dumps(value, default=str))


def _post(path, body=None, run=None):
    headers = {"Authorization": f"Bearer {run['token']}"} if run else {}
    r = _http.post(path, json=body.model_dump(mode="json") if body else None, headers=headers)
    r.raise_for_status()
    return r.json() if r.content else None


def register(name, tools, allow=None, entrypoint="", owner="unknown"):
    if _sandbox:
        return
    allow = Allowlist.model_validate(allow or {"tools": tools})
    _post("/agents", AgentSpec(name=name, owner=owner, tools=tools, allow=allow,
                               entrypoint=entrypoint))


def start(agent, task):
    """Start a run for this thread / task. Returns a token for `end`; None when nested."""
    if _sandbox or _run.get():  # invoke calls stream: one run, not two
        return None
    return _run.set(open_run(agent, task))


def open_run(agent, task):
    """Start a run and return its handle; for adapters whose hooks cannot share a contextvar."""
    started = RunStarted.model_validate(_post("/runs", RunStart(agent=agent, task=task)))
    return {"id": started.run_id, "token": started.run_token}


def end(token):
    if token is None:
        return
    run = _run.get()
    _run.reset(token)
    complete(run)


def complete(run):
    _post(f"/runs/{run['id']}/complete", run=run)


def model_call(model_id, request, response):
    run = _run.get()
    if run and not _sandbox:
        _post(f"/runs/{run['id']}/model-calls",
              ModelCall(model_id=model_id, request=_json(request), response=_json(response)), run)


def replayed_reply():
    """Sandbox only: the next recorded model reply, or None once past the freeze (go live)."""
    if _sandbox and _sandbox["replies"]:
        return _sandbox["replies"].pop(0)
    return None


def _wait(run):
    while True:
        r = _http.get(f"/runs/{run['id']}/wait", params={"timeout": 60},
                      headers={"Authorization": f"Bearer {run['token']}"})
        r.raise_for_status()
        status = WaitResult.model_validate(r.json()).status
        if status == "running":
            return
        if status != "frozen":
            raise Blocked(f"Run {run['id']} is {status}.")


def check(name, args, run):
    """Gate one tool call: returns its call_id once allowed, waits while frozen, raises Blocked."""
    if run is None:  # fail closed: a protected tool only runs inside a checked run
        raise Blocked(f"{name} was called outside a Mirage run.")
    gate = GateDecision.model_validate(_post("/gateway/check", ToolCheck(
        run_id=run["id"], tool=name, args=_json(args)), run))
    if gate.decision == "block":
        raise Blocked(gate.explanation)
    if gate.decision == "freeze":
        _wait(run)  # only this run's thread waits; a human decides
    return gate.call_id


def record(run, call_id, name, result=None, error=None):
    _post(f"/runs/{run['id']}/tool-results",
          ToolResult(call_id=call_id, tool=name, result=_json(result), error=error), run)


def tool(name, args, fn):
    """Run one tool call through Mirage. `fn()` runs the real tool (prod, once allowed)."""
    args = _json(args)
    if _sandbox:
        return _sandbox["call_tool"](name, args)
    run = _run.get()
    call_id = check(name, args, run)
    try:
        result = fn()
    except Exception as e:
        record(run, call_id, name, error=f"{type(e).__name__}: {e}")
        raise
    record(run, call_id, name, result)
    return result
