# Mirage — Team Split and Contracts

Status: source-aligned, 2026-10-11. Read with `PRODUCT.md`.

Live medium suspicion now uses an incident and automatic initial sandbox clearance.
`Incident.automatic_clearance` is optional/null for existing/high incidents; otherwise
it is `{status: "checking" | "cleared" | "inconclusive", reason: string}` (bounded system category).
Only the initial three full baselines may clear: all must finish useful work without errors or
deterministic harm and capture the exact held call; the configured stronger judge must classify
the held and actual outbound calls SAFE. This is model-assisted evidence, not universal proof.
Live approvals are empty; inconclusive medium cannot unfreeze. High/hard-rule recovery stays human.

Full definitions and examples are linked below. The numbered sections and their
subsection anchors remain here for existing references.

## 1. Team split

Two people. Two roles. One contract between them.

| | Person A: Engine (Gabi) | Person B: Experience (Liam) |
|---|---|---|
| Owns | Everything that is real in the background | Everything the audience sees |
| Builds | Engine: API (data + control plane), gate, detection, snapshot store, detonation runner, judge, bisection, `mirage detonate` (CLI + HTTP) | SDK (`mirage.protect`, plugged into agents), web dashboard, MCP server (operator tools + `detonate` for coding agents), demo agents with their tools (Gmail, Calendar, HubSpot), demo script, pitch, backup video |
| Also owns | The API server and its replay mode | Account setup and keys (Google, CRM, GitHub), seed data (synthetic contacts, poisoned invite), policy pack text P1–P6, "legit task completed" check per story, fixture `.jsonl` files, handoff prompt + Copy / Send to Codex, synthetic test set for metrics |
| Done when | The UI and MCP work with `MIRAGE_MODE=live` | The demo runs end to end in 3 minutes |

Rule: **the contract is the only link.** Person B never waits for Person A.
Person B builds on the server in replay mode. Person A builds the real engine. Both follow this file.

## 2. How we work with the contract

1. We write the contract as Pydantic models in `contracts/models.py`. That file is the source of truth.
2. Person B writes one full demo by hand as fixtures in `contracts/fixtures/` (see section 7).
3. The API server in replay mode plays the fixtures with real timing. The UI uses it from hour 1.
4. The server reads one env var: `MIRAGE_MODE=replay|live`. The UI does not change.
5. FastAPI publishes `/openapi.json`. The UI generates its TypeScript types from it (`openapi-typescript`).

Change rules:

- Adding a field: allowed. Tell the other person.
- Renaming or removing a field: both people must agree first.
- Every change updates `models.py`, the fixtures and this file in the same commit.

## 3. State machines

### Run

```
queued → running → completed
            │
            ├─(execution error)→ failed
            │
            ├─(gate trips)→ frozen ─(medium clearance / eligible human unfreeze)→ running
            │                  │
            │                  └─(human: kill)→ killed ─(human: approve restart)→ new run (restarted_from = old id)
            │
            └─(global STOP)→ halted ─(human: resume or resume all; lifts STOP)→ new run (restarted_from = old id),
                                         relaunched by the engine; the task starts over
```

`status`: `queued | running | frozen | completed | failed | killed | halted`

`failed` is terminal for that run: the gateway denies tools and SDK wait returns `failed`.
A human can approve one new queued restart of a killed, halted or failed run.
The engine starts the agent from its registered entrypoint; only a matching agent/task/lineage/full-spec
start claims it, once; queued is not running.
Completion reports never change `frozen`, `killed`, `halted`, or any terminal run.

Human unfreeze needs live ownership and no active proof or confirmed harm. Medium
`checking`/`inconclusive` refuses with 409; only its initial conclusive job can release
the held call once. A later manual freeze of an already-cleared medium run may be
human-unfrozen without repeating that callback. High/hard/escalation stays human.

### Incident

```
open → detonating → false_positive → closed (run unfrozen)
                  └→ confirmed → bisecting → root_caused → fix_pending → fix_verified → pr_open → merged
```

`status`: `open | detonating | false_positive | confirmed | bisecting | root_caused | fix_pending | fix_verified | pr_open | merged | closed`

## 4. Data models

Full field definitions, JSON examples and event payloads:
[4. Data models](docs/contracts/data-models.md#4-data-models).

### RuntimeInfo

[Full definition and rules](docs/contracts/data-models.md#runtimeinfo).

### SandboxJob

[Full definition and rules](docs/contracts/data-models.md#sandboxjob).

### Fleet exposure (M4, additive)

`CreateExposureJob` is `{agent_names: string[], actor: string, reason: string}` (1..8 distinct
nonempty names). POST `/incidents/{id}/exposure-jobs` returns 202 with `ExposureJob`;
GET `/exposure-jobs/{job_id}` reads it, and GET `/exposure-jobs?incident_id={id}` lists newest
first for reload/fleet summaries. GET `/incidents/{id}/exposure-candidates` returns
`ExposureCandidate[]`: `{agent_name, role, status: unassessed | not_applicable |
could_not_evaluate, reason}`. Capability match is unassessed, never vulnerability proof.

`ExposureJob` is `{id, incident_id, agent_names, status: queued | running | completed |
failed, results: ExposureResult[], error: execution_failed | stopped | interrupted | null}`.
State is persisted in existing `agent.message` payloads as `exposure_job`; it does not emit
detonation/verdict events or replace the original incident proof. Job completion means the
assessment finished, including explicit incompatible or unavailable results. Interrupted
jobs fail without resuming; STOP refuses new work and stops starting additional candidates.
Requests log `human.action` with action `assess_exposure`, job target, actor/reason and time.
All work reuses the existing one-worker sandbox queue and its reset/shutdown/epoch fencing;
an isolated status observer emits exposure metadata instead of incident sandbox metadata.
In recording mode POST returns 409, candidate/job lists are empty, and individual jobs 404;
live files and receipts are never presented as part of a selected recording.

`ExposureResult` is `{agent_name, status: vulnerable | blocked | not_applicable |
could_not_evaluate, reason, snapshot_id?, snapshot_revision?, attack_snapshot_revision?,
clean_snapshot_revision?, code_revision?, policy_revision?, replay_kind: scripted |
model_backed | unknown, attack: ExposureObservation | null, clean: ExposureObservation | null}`.
Observation is `{compromised_runs: "0/1" | "1/1", attack_blocked: "0/1" | "1/1",
legit_task_completed: "0/1" | "1/1", completed: boolean, error: replay_failed | tool_error |
null, effects: Effect[]}`. Failed reads/calls or crashes never certify blocked/useful work.
A deterministic prohibited effect already observed still proves vulnerable after a later error.
Blocked requires useful, safe completion of attack and clean variants. Specific captured or
registered absence of `read_calendar` is not_applicable; unsupported adapters/context or
missing exact recordings are could_not_evaluate. Role/tool matching alone is never proof.

The operator supplies `MIRAGE_EXPOSURE_CANDIDATES`, a local JSON array of
`{agent_name, role, tools?, snapshot_path?, snapshot_revision?, code_root?, code_revision?, replay_kind?}`.
Only the controlled `meeting_assistant` adapter executes, with at most one compatible
sibling per job. Browser requests cannot supply paths, snapshots, code or permissions.
The source incident must have a causal calendar input. Only that item is appended to the
sibling's unique matching untrusted read collection. Its own clean items, task, system,
exact tool arguments/read recordings, permissions and trusted completion criteria remain;
both variants clear recorded model replies. Reads/writes still use the existing jailed child.
`run_once(..., repo_root=...)` selects a trusted executable checkout without changing globals.

`snapshot_revision` is SHA256 of the original sibling file bytes; attack/clean/policy
revisions hash canonical JSON (sorted keys, compact separators). `code_revision` is only
published after verifying that the same clean exact-HEAD checkout supplied both children
and remained clean/unchanged afterwards. `replay_kind` is captured operator recording
metadata, never inferred from tool/model matching. Ratios are observed 1/1 only. The
illustrative wire fixture is `contracts/fixtures/exposure_demo.json`, not live-model evidence.

### Run

[Full definition and rules](docs/contracts/data-models.md#run).

### Event (one stream for everything)

[Full definition and rules](docs/contracts/data-models.md#event-one-stream-for-everything).

### GateDecision

[Full definition and rules](docs/contracts/data-models.md#gatedecision).

### Incident

[Full definition and rules](docs/contracts/data-models.md#incident).

### Input (one thing the run read)

[Full definition and rules](docs/contracts/data-models.md#input-one-thing-the-run-read).

### Effect (one action inside Mirage)

[Full definition and rules](docs/contracts/data-models.md#effect-one-action-inside-mirage).

### Detonation

[Full definition and rules](docs/contracts/data-models.md#detonation).

### Verdict

[Full definition and rules](docs/contracts/data-models.md#verdict).

### BisectionRow

[Full definition and rules](docs/contracts/data-models.md#bisectionrow).

### HumanAction

[Full definition and rules](docs/contracts/data-models.md#humanaction).

### ServiceView (Gmail, Calendar, CRM panels)

[Full definition and rules](docs/contracts/data-models.md#serviceview-gmail-calendar-crm-panels).

## 5. HTTP API

Control-plane routes, responses, scheduling and transport rules:
[5. HTTP API](docs/contracts/http-and-replay.md#5-http-api).

### Read

[Full definition and rules](docs/contracts/http-and-replay.md#read).

### Act

[Full definition and rules](docs/contracts/http-and-replay.md#act).

### Demo control (for reliability on stage)

[Full definition and rules](docs/contracts/http-and-replay.md#demo-control-for-reliability-on-stage).

## 6. Coding agent contract (`mirage detonate`)

CLI, HTTP and MCP fix-verification output and pass criteria:
[6. Coding agent contract (`mirage detonate`)](docs/contracts/http-and-replay.md#6-coding-agent-contract-mirage-detonate).

## 7. Fixtures and replay mode

Fixtures, legacy replay and managed recorded-demo behavior:
[7. Fixtures and replay mode](docs/contracts/http-and-replay.md#7-fixtures-and-replay-mode).

### Managed recorded demo (opt-in)

[Full definition and rules](docs/contracts/http-and-replay.md#managed-recorded-demo-opt-in).

## 8. Repo layout

Rule: `web/`, `mcp/` and `agents/` talk to the engine **only over HTTP** (agents through the SDK).
They never import `engine/`. The contract is the only link.

```
contracts/           # shared (A + B agree)
  models.py          # Pydantic models, source of truth
  fixtures/          # recorded demo events and state
sdk/                 # Liam: `mirage-sdk`, the package customer agents install
  mirage/
    core.py          # data plane client: check, hold, record (all decisions in the engine)
    protect.py       # mirage.protect(agent): detects the framework, picks an adapter
    sandbox.py       # run(snapshot, call_tool): the detonation runner for SDK agents
    adapters/
      langchain.py   # LangChain / LangGraph middleware (built for the demo)
      openai_agents.py
      claude_agent.py
engine/              # Gabi: the Mirage service
  api/               # FastAPI: data plane (SDK) + control plane (web, mcp) + SSE, MIRAGE_MODE=replay|live
  gateway/           # check(tool call), freeze/kill, log
  detection/         # hard rules, decision model, policies.yaml (P1–P6)
  store/             # SQLite: agents, runs, events, snapshots
  detonation/        # builds the agent in mirage mode, subprocess + network jail, judge
  bisect.py
  handoff.py         # prompt + report for the coding agent
  cli.py             # mirage detonate
agents/              # Liam: demo agents (the victims): their tools (Gmail, Calendar, HubSpot) + mirage.protect
web/                 # Liam: dashboard (docs/UX.md)
mcp/                 # Liam: MCP server, operator tools + detonate for coding agents
demo/                # Liam: seed scripts, contacts CSV, poisoned invite, pitch, video
docs/UX.md           # screens, interactions, MCP verbs
```

Current source uses synthetic tools; Gmail/Calendar/HubSpot rows describe intended integrations.
Processes during the demo:

```
agents/run_demo_fleet.py (4 runs) ──tools──▶ synthetic in-memory services (only after gate admission)
        └──SDK/HTTP──▶ engine ──▶ detonation subprocess (agent in mirage mode, no keys, no real tools)
web (React) ──HTTP/SSE──▶ engine ◀──HTTP── mcp server ◀── Claude / Codex
```

## 9. Sync points

| When | Both people check |
|---|---|
| Sat +1h | `contracts/models.py` and first fixtures pushed. Server runs in replay mode. |
| Sat evening | First real run shows in the UI (`MIRAGE_MODE=live`). Gate freezes it. |
| Sat night | Detonation and verdict real in the UI. |
| Sun 09:00 | Full demo on real backend. Bisection and handoff work. Record backup video. |
| Sun 11:00 | Two full rehearsals. No new features. |
| Sun 12:00 | Hard freeze. |

## 10. Tech stack

Rule: everything runs on one laptop. AWS is used only for Bedrock.

### Engine (Person A)

| Layer | Choice |
|---|---|
| Runtime | Python 3.12, `uv` |
| API | FastAPI + uvicorn, `sse-starlette` for `/stream` |
| Contract | Pydantic v2 in `contracts/models.py` |
| Demo agents | LangGraph for the demo (`create_agent` + `langchain-aws` `ChatBedrockConverse`, temperature 0), wrapped by `mirage.protect`. The SDK is framework-agnostic (section 11). |
| SDK | `mirage-sdk`: adapters for LangGraph, OpenAI Agents SDK, Claude Agent SDK; talks to the engine with `httpx` |
| Concurrency | One thread per run in the agents process. Freeze: the SDK waits on `GET /runs/{id}/wait` inside that run's tool call. Only that thread pauses. Global STOP is one engine flag. |
| Gmail + Calendar (demo agent tools, `agents/`) | `google-api-python-client` + `google-auth-oauthlib` |
| CRM (demo agent tools, `agents/`) | HubSpot free CRM via its REST SDK |
| Storage | Python's built-in `sqlite3` (WAL): agents, runs, event log, snapshots |
| Mirage mode | The SDK answers tool calls from the snapshot. No Docker. No real tools. |
| `mirage detonate` | `argparse` CLI + HTTP route. One function. The MCP tool in `mcp/` calls the HTTP route. |
| Decision model + judge | `gpt-oss-safeguard-20b` / `-120b` via Converse (fallback: `InvokeModel`) |
| Tunnel for cloud coding agents | `cloudflared` |
| Tests / lint | `pytest`, `ruff` |

### Experience (Person B)

| Layer | Choice |
|---|---|
| Framework | Vite + React + TypeScript |
| Style | Tailwind + shadcn/ui, `lucide-react` icons |
| Animation | Motion |
| Data | TanStack Query (REST), native `EventSource` (`/stream`) |
| Types | `openapi-typescript` from `/openapi.json` |
| PR diff view | `react-diff-viewer-continued` |
| MCP server | TypeScript, `@modelcontextprotocol/sdk`, reuses the generated types. Stretch: MCP Apps card. |
| UI mockups | Google Stitch (prompts in `docs/UX.md`) |

## 11. SDK: how an agent joins Mirage

Adapter hooks, data plane, snapshot/replay and sandbox seam:
[11. SDK: how an agent joins Mirage](docs/contracts/sdk.md#11-sdk-how-an-agent-joins-mirage).

### Where each adapter plugs in

[Full definition and rules](docs/contracts/sdk.md#where-each-adapter-plugs-in).

### Data plane API (SDK → engine)

[Full definition and rules](docs/contracts/sdk.md#data-plane-api-sdk--engine).

### Snapshot and replay

[Full definition and rules](docs/contracts/sdk.md#snapshot-and-replay).

### Sandbox seam (engine ↔ SDK mirage mode)

[Full definition and rules](docs/contracts/sdk.md#sandbox-seam-engine--sdk-mirage-mode).

## 12. MCP server (operator interface)

Operator tools and human-action rules:
[12. MCP server (operator interface)](docs/contracts/mcp-and-chat.md#12-mcp-server-operator-interface).

## 13. Ask Miragio operator chat (additive, Person B)

Chat routes, events, sessions, limits and capability handling:
[13. Ask Miragio operator chat (additive, Person B)](docs/contracts/mcp-and-chat.md#13-ask-miragio-operator-chat-additive-person-b).
