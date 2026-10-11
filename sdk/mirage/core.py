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
    RunCompletion,
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


def register(name, tools, allow=None, entrypoint="", owner="unknown", *, legit=None):
    allow = Allowlist.model_validate(allow or {"tools": tools})
    spec = AgentSpec(name=name, owner=owner, tools=tools, allow=allow, entrypoint=entrypoint,
                     **({"legit": legit} if legit is not None else {}))
    if _sandbox:
        register_spec = getattr(_sandbox["call_tool"], "register_spec", None)
        if callable(register_spec):
            register_spec(spec.model_dump(mode="json"))
        return
    _post("/agents", spec)


def start(agent, task):
    """Start a run for this thread / task. Returns a token for `end`; None when nested."""
    if _sandbox or _run.get():  # invoke calls stream: one run, not two
        return None
    return _run.set(open_run(agent, task))


def open_run(agent, task):
    """Start a run and return its handle; for adapters whose hooks cannot share a contextvar."""
    started = RunStarted.model_validate(_post("/runs", RunStart(agent=agent, task=task)))
    return {"id": started.run_id, "token": started.run_token}


def end(token, error=None):
    if token is None:
        return
    run = _run.get()
    _run.reset(token)
    if error is None:
        complete(run)
    else:
        try:
            complete(run, type(error).__name__)
        except Exception as reporting_error:  # noqa: BLE001 - preserve the agent exception
            error.add_note(f"Mirage failure reporting failed: {type(reporting_error).__name__}")


def complete(run, error=None):
    body = RunCompletion(error=error) if error is not None else None
    _post(f"/runs/{run['id']}/complete", body, run)


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


def _deny(run, explanation):
    blocked = Blocked(explanation)
    if run is not None:
        try:
            complete(run, type(blocked).__name__)
        except Exception as reporting_error:  # noqa: BLE001 - preserve the denial
            blocked.add_note(f"Mirage failure reporting failed: {type(reporting_error).__name__}")
    raise blocked


def _wait(run, call_id=None):
    params = {"timeout": 60}
    if call_id is not None:
        params["call_id"] = call_id
    while True:
        r = _http.get(f"/runs/{run['id']}/wait", params=params,
                      headers={"Authorization": f"Bearer {run['token']}"})
        if r.status_code == 409:
            _deny(run, f"The held call is no longer authorized for run {run['id']}.")
        r.raise_for_status()
        status = WaitResult.model_validate(r.json()).status
        if status == "running":
            if call_id is None:
                _deny(run, "A checked call_id is required to resume a held tool.")
            return
        if status != "frozen":
            _deny(run, f"Run {run['id']} is {status}.")


def check(name, args, run):
    """Gate one tool call: returns its call_id once allowed, waits while frozen, raises Blocked."""
    if run is None:  # fail closed: a protected tool only runs inside a checked run
        _deny(run, f"{name} was called outside a Mirage run.")
    gate = GateDecision.model_validate(_post("/gateway/check", ToolCheck(
        run_id=run["id"], tool=name, args=_json(args)), run))
    if gate.decision == "block":
        if gate.rule_id == "RUN_FROZEN":  # a denied sibling cannot cancel a later human grant
            raise Blocked(gate.explanation)
        _deny(run, gate.explanation)
    if gate.decision == "freeze":
        _wait(run, gate.call_id)  # only this checked call can claim its release
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
        try:
            record(run, call_id, name, error=type(e).__name__)
        except Exception as reporting_error:  # noqa: BLE001 - preserve the tool exception
            e.add_note(f"Mirage tool error recording failed: {type(reporting_error).__name__}")
        raise
    if isinstance(result, ToolResult):
        record(run, call_id, name, result.result, result.error)
    else:
        record(run, call_id, name, result)
    return result
