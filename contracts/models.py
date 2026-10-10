"""Mirage contract: the data shapes shared by the engine and the UI.

Source of truth. Mirrors CONTRACTS.md sections 4 and 6. Any change here also updates
CONTRACTS.md and the fixtures in the same commit. All times are UTC, all IDs are strings.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    # Unknown fields are an error, so engine/UI drift fails loudly instead of silently.
    model_config = ConfigDict(extra="forbid")


Env = Literal["prod", "mirage"]
RunStatus = Literal["queued", "running", "frozen", "completed", "killed", "halted"]
IncidentStatus = Literal[
    "open", "detonating", "false_positive", "confirmed", "bisecting", "root_caused",
    "fix_pending", "fix_verified", "pr_open", "merged", "closed",
]
NextAction = Literal["detonate", "find_cause", "send_fix", "open_pr", "none"]
EventType = Literal[
    "run.started", "agent.message", "tool.requested", "gate.decision", "tool.result",
    "run.status", "global.stop", "incident.opened", "detonation.started", "detonation.effect",
    "detonation.completed", "verdict.ready", "bisection.step", "bisection.completed",
    "handoff.created", "fix.verified", "pr.opened", "human.action",
]
InputKind = Literal["calendar_event", "email", "crm_record", "web_page", "attachment", "user_task"]
HumanActionType = Literal[
    "freeze", "unfreeze", "kill", "approve_restart", "global_stop", "approve", "reject",
    "handoff", "merge",
]


class Run(Model):
    id: str
    agent: str
    env: Env
    task: str
    status: RunStatus
    started_at: datetime
    ended_at: datetime | None = None
    incident_id: str | None = None
    restarted_from: str | None = None
    tool_calls: int = 0


class Event(Model):
    """One stream for everything. `payload` shape depends on `type` (CONTRACTS.md §4)."""

    seq: int
    ts: datetime
    run_id: str | None = None
    incident_id: str | None = None
    env: Env
    type: EventType
    payload: dict[str, Any] = {}


class GateDecision(Model):
    call_id: str
    tool: str
    args: dict[str, Any]
    decision: Literal["allow", "freeze", "block"]
    layer: Literal["hard_rule", "decision_model"]
    rule_id: str | None = None
    policy_id: str | None = None  # P1..P6, only when layer is decision_model
    p: float | None = Field(default=None, ge=0, le=1)
    explanation: str


class Input(Model):
    """One thing the run read. Bisection removes inputs one at a time."""

    id: str
    kind: InputKind
    label: str
    source_tool: str | None = None  # None for the user task
    preview: str


class Effect(Model):
    """One action inside Mirage."""

    detonation_id: str
    run_index: int
    step: int
    tool: str
    args: dict[str, Any]
    violates: list[str] = []


class Detonation(Model):
    id: str
    incident_id: str
    n_runs: int
    removed_input_id: str | None = None  # None for the full replay
    compromised_runs: int
    effects: list[Effect] = []


class BlastRadius(Model):
    records: int
    recipients: list[str]
    secrets: list[str]
    summary: str


class Verdict(Model):
    incident_id: str
    confirmed: bool  # decided by code from the effects ledger, never by the judge
    compromised_runs: str  # "3/3"
    policies_violated: list[str]
    blast_radius: BlastRadius


class BisectionRow(Model):
    input_id: str
    label: str
    compromised_runs: str  # "0/2"
    is_cause: bool


class Incident(Model):
    id: str
    run_id: str
    status: IncidentStatus
    opened_at: datetime
    trigger: GateDecision
    snapshot_id: str
    inputs: list[Input] = []
    verdict: Verdict | None = None
    bisection: list[BisectionRow] = []
    cause_input_id: str | None = None
    pr_url: str | None = None
    # Set by the engine. The dashboard's one main button and the MCP suggestion both read it.
    next_action: NextAction = "detonate"


class HumanAction(Model):
    actor: str
    action: HumanActionType
    target: str
    reason: str
    ts: datetime


class HumanRequest(Model):
    """Body of every POST that is a human action (CONTRACTS.md §5): unfreeze, kill, stop..."""

    actor: str  # MCP calls use "<actor> via <client> (MCP)" (§12)
    reason: str


class ServiceItem(Model):
    id: str
    title: str
    subtitle: str
    ts: datetime
    flag: Literal["normal", "malicious", "blocked"] = "normal"


class ServiceView(Model):
    service: Literal["outbox", "calendar", "crm"]
    env: Env
    items: list[ServiceItem]


class DetonateResult(Model):
    """Output of `mirage detonate`. Same for CLI, MCP and HTTP (CONTRACTS.md §6)."""

    incident_id: str
    attack_blocked: str  # "3/3"
    legit_task_completed: str  # "3/3"
    passed: bool  # true only if both values are "n/n"
    effects: list[Effect]


# --- Data plane: SDK -> engine (CONTRACTS.md §11) ----------------------------------------
# Auth: the SDK sends the run's token as `Authorization: Bearer <run_token>`.


class Allowlist(Model):
    tools: list[str]  # tools this agent may call; anything else trips TOOL_NOT_ALLOWED
    email_to: list[str] = []  # allowed email domains or full addresses
    url_hosts: list[str] = []  # allowed hosts for web fetches


class AgentSpec(Model):
    """POST /agents. Registers a protected agent. The engine uses `entrypoint` to rebuild it
    in mirage mode for detonation."""

    name: str
    owner: str
    tools: list[str]  # every tool the agent has, allowed or not
    allow: Allowlist
    entrypoint: str  # "agents.assistant:build_agent"


class RunStart(Model):
    """POST /runs."""

    agent: str
    task: str
    env: Env = "prod"
    restarted_from: str | None = None


class RunStarted(Model):
    run_id: str
    run_token: str


class ModelCall(Model):
    """POST /runs/{id}/model-calls. One provider call, as the SDK saw it."""

    model_id: str
    request: dict[str, Any]  # system prompt, messages, tools, inference settings
    response: dict[str, Any]


class ToolCheck(Model):
    """POST /gateway/check. Returns a GateDecision; the engine assigns `call_id`."""

    run_id: str
    tool: str
    args: dict[str, Any]


class ToolResult(Model):
    """POST /runs/{id}/tool-results. The snapshot is built from these."""

    call_id: str
    tool: str
    result: Any = None
    error: str | None = None


class WaitResult(Model):
    """GET /runs/{id}/wait. Long poll while frozen. `frozen`: still frozen, poll again."""

    status: Literal["running", "frozen", "killed", "halted"]
