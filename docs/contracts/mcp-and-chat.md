# MCP and Miragio chat reference

[Canonical overview](../../CONTRACTS.md).
[contracts/models.py](../../contracts/models.py) remains the wire-shape source of truth.

## 12. MCP server (operator interface)

A second front end, like `web/`. It calls the control plane API. It never imports the engine.

| Tool | Kind | Does |
|---|---|---|
| `list_runs` | read | Runs and their status. |
| `get_incident` | read | Headline, attack chain, verdict, cause, `next_action`. |
| `get_audit` | read | Human actions for a run or incident. |
| `detonate` | act | Same as the dashboard button. Also used by coding agents. |
| `find_cause` | act | Start bisection. |
| `unfreeze` | act | Resume a frozen run. |
| `kill` | act | End a frozen run. |
| `resume` | act | Resume a halted run (`POST /runs/{id}/resume`); lifts STOP if it is on. |
| `resume_all` | act | Lift STOP and resume every halted agent (`POST /resume-all`). Lists which runs resume and which are skipped before asking for the phrase `resume all`. |
| `send_fix` | act | Create the handoff for a coding agent. |

Rules:

- Read tools are on by default. Containment/recovery/handoff actions ask for confirmation/reason
  (MCP elicitation); baseline detonation and cause search do not require that approval.
  Human-requested actions log the actor/client and reason; engine system clearance is not human approval.
- All checks run in the engine, not in the MCP server.
- No tool merges a PR.

## 13. Ask Miragio operator chat (additive, Person B)

Node HTTP/SSE service in `mcp/`, bound to `127.0.0.1:8001`. Engine stays on
`localhost:8000`. It uses Bedrock ConverseStream in `us-east-1`, model from
`BEDROCK_CHAT_MODEL_ID` → `BEDROCK_AGENT_MODEL_ID` → `BEDROCK_MODEL_ID`, and the
short-term `AWS_BEARER_TOKEN_BEDROCK` key. Root `.env` loads before client construction.
There is no synthetic model fallback. Startup: `cd mcp && npm ci && npm run build && npm run chat`.

The existing `createServer` is connected to an MCP SDK `Client` with paired in-memory
transports. `listTools` supplies the ten-tool catalogue; `callTool` executes the
existing handlers. Elicitation is presented to the human as one plain-language sentence
with Decline and Approve; the click is the confirmation. On Approve the service answers the
MCP form itself with the phrase and reason the tool put in the request's `_meta["mirage/confirm"]`
(the model-supplied reason or the tool default), so the browser cannot inject content. External
MCP clients (Claude Code, Codex) keep the typed phrase, which fails closed. Engine guards, actor audit labels and untrusted
fences remain authoritative. No merge/restart tools are added.

| Method | Path | Contract |
|---|---|---|
| POST | `/chat/turn` | `ChatTurn` `{session_id?: string, message: string, actor: string}` → SSE |
| POST | `/chat/approvals/{approval_id}` | `ChatApproval` `{action: "accept" \| "decline"}` (any other field → 400) → `{accepted: true}` |
| GET | `/chat/handoffs/{handoff_id}` | Human-click prompt download, `text/plain` attachment; unavailable/expired → 404 |
| GET | `/chat/sessions/{session_id}/events` | SSE of automatic follow-up turns for that session; unknown/expired → 404 |

SSE uses unnamed events: `data: <JSON>\n\n`. Each JSON is `ChatEvent` from
`contracts/models.py`, discriminated by `type`:

| Type | Fields |
|---|---|
| `session` | `session_id` (server-generated UUID, first event) |
| `text_delta` | `text` |
| `tool_start` | `call_id`, `tool`, `args` |
| `tool_progress` | `call_id`, `message` |
| `tool_result` | `call_id`, `tool`, `result` (sanitized MCP CallToolResult: `content`, optional `structuredContent` / `isError`) |
| `approval_required` | `approval_id`, `call_id`, `message` (plain sentence), `schema` (always `{"type":"object","properties":{}}`: nothing to fill) |
| `follow_up` | `title` (session stream only: opens an automatic turn, followed by its usual events and `done`/`error`) |
| `done` | no additional fields |
| `error` | `code`, `message` (sanitized; also used for pre-stream HTTP errors) |

`done` terminates success; `error` terminates failure. Do not automatically retry turns
or action calls. SSE comments are keepalives. The original stream stays open during
approval. `{accepted: true}` means the decision was received, not that the engine
action succeeded; its `tool_result` is authoritative. Declines, expiry and disconnects fail closed.
Stale, repeated or disconnected approval IDs return 409. Approval expires after 120s.

Detonation and bisection do not block the chat. The service calls `detonate` / `find_cause`
with `wait: false` (MCP default stays `wait: true` for coding agents): the tool returns at
once with `structuredContent` `{status: "started", incident_id, after}` and the model says
it is monitoring. The service follows engine `/events` after that cursor (15 min max) for
`verdict.ready` / `bisection.completed` / `detonation.failed`, then runs one automatic turn:
`follow_up`, a scripted read-only `get_incident` tool card, the model's summary, `done`.
Automatic turns cannot start effects, run one at a time, and wait while the session has a
live turn (`POST /chat/turn` meanwhile → 409 `SESSION_BUSY`). The web keeps the session
stream open (one listener per session; a new one replaces the old). A follow-up with no
open stream still lands in history but is not replayed.

Session IDs, approval IDs and handoff IDs are unpredictable server-generated UUIDs.
History is server-owned; requests containing client tool results/history are rejected.
A session retains its original actor, permits one live turn and expires after 30 idle
minutes. Limits: 32 sessions, 4 active turns, 16 KiB JSON body, 8000-character input,
40 history messages / 64 KiB across completed turn groups, 6 model rounds, 12 tool calls,
60s per model response, 185s per tool call, 10 minutes per turn, 64 KiB per tool result,
32 KiB per model stream. Effects cannot repeat for the same tool/target within a turn.
Stopping/disconnecting aborts model continuation and declines pending approvals.
Already-started engine actions may continue: stopping generation never means STOP ALL.

Capability tokens are stripped from tool cards and model continuation. `send_fix`
returns `structuredContent.handoff_url`, a relative user-only URL for its original prompt,
and optionally safe `claude_code_url` / `codex_url`. The UI fetches the full prompt only after the
human clicks Hand off to coding agent, never at the model's request. Prompt/download URL are kept
out of model continuation. Handoffs are held only in memory (max 8 per session), expire
with the conversation, and disappear on service restart. Synthetic fixture:
`contracts/fixtures/chat_demo.jsonl` (wire examples, not a Bedrock fallback).

Only JSON POSTs are accepted. Cross-site browser requests and non-loopback Host headers
are rejected; browser Origin must be in `MIRAGE_CHAT_ORIGINS` (defaults include loopback
Vite on 5173 and chat on 8001). CLI requests without Origin are accepted. There is no
CORS response. Vite proxies `/chat` to `MIRAGE_CHAT_API` (default `http://localhost:8001`).
This is a single-laptop prototype: actor is an audit label, not remote authentication;
do not publish this chat port through a tunnel.

## Verified rollout and useful clean recovery (M2)

A confirmed compromised task uses a fresh restart after a human merges its verified
repair PR into `special-improvements`; `/resume` still refuses confirmed incidents.
The trusted local supervisor prepares and registers the complete merged factory before
the operator approves the existing `/runs/{original}/restart` action. Actor strings are
audit labels; report authority is the same direct private loopback connection and
`MIRAGE_REPAIR_SUPERVISOR_TOKEN` as repair-job reports. Public/tunnel/forwarded access is refused.

| Method | Path | Body / response |
|---|---|---|
| GET | `/incidents/{id}/recovery/provenance` | Private supervisor only: `RecoveryProvenance` with current full `agent_spec`, effective `policy` and canonical `policy_digest`, minimal effective `config` and `config_digest`. |
| POST | `/incidents/{id}/recovery/report` | Private supervisor only: `RecoveryReport` → prepared `RecoveryState`. No approval or launch occurs here. |
| GET | `/incidents/{id}/recovery` | `RecoveryState`; 409 when no verified rollout is prepared. Completion is derived from the linked run and successful tool ledger. |

`RecoveryReport` binds `repair_job_id`, `original_run_id`, `agent`, `task`, the actual
GitHub `pull_request` receipt (`url`, `number`, `baseRefName`, `headRefOid`, `isDraft`,
`state`, `mergeCommit: {oid}`), `merged_sha`, `candidate_tree`, `merged_tree`,
`verified_sha`, `snapshot_digest`, the registered full `agent_spec`, `policy_digest`,
`config`, `config_digest`, and the SHA-256 raw-byte `checkpoint_digest`. The source job
must already have verified attack blocking/useful completion `3/3` and a clean
counterpart `1/1`. Its PR/head must match the observed merged receipt.

Unchanged candidate/merged trees and unchanged effective policy reuse the verified
candidate. Changed code or policy requires `verified_sha = merged_sha` with complete
`verification: RepairCommandEvidence` and `clean_control: RepairCleanControl` receipts.
The engine applies M1's deterministic proof checks and checks every successful effect
against the prepared effective policy. Raw proof ledgers are excluded from recovery
state events; the accepted report retains revision/digest links and null proof fields.

The configuration map is exactly `{MEETING_ASSISTANT_MODEL_ID, DEMO_USER_EMAIL}`.
The selected model is the first nonempty role model, `BEDROCK_AGENT_MODEL_ID`, then
`BEDROCK_MODEL_ID`; it must match the original snapshot's model. Both config and policy
digests use recursively sorted JSON with compact separators and unescaped Unicode,
as in M1's `repair.digest`. The launcher preserves the explicit original synthetic
service checkpoint; recovery does not seed/reset services or relaunch other agents.

`MIRAGE_RECOVERY_CHECKPOINT` defaults to `<dirname of MIRAGE_SNAPSHOTS>/recovery-checkpoint.json`
(else `<repo>/data/`), the seeded service state the demo fleet writes at start before any write.
The model configuration defaults to the snapshot's model and legit recipient.
For the baseline's explicit `ScriptedModel` capture only, the operator may configure
`MIRAGE_RECOVERY_CONFIG_SOURCE` to its original trusted M0 nonsecret receipt. The engine
checks the receipt's raw `original_snapshot_sha256`, original agent/task/factory/legit,
effective model/recipient and nonsecret environment, clean source revision, fixed region
and temperature. It also binds `original_services_sha256` to the reported checkpoint.
The receipt's canonical `config_source_digest` is exposed in provenance and pinned in
the report, approval and claim. It resolves the scripted class label to the actual
recorded continuation configuration; it never edits the source snapshot. Ordinary
real-model snapshots still require model equality and a null `config_source_digest`.

This MVP only admits an original with zero successful outward task writes. The engine
joins that original's production `tool.requested` and successful `tool.result` records;
failed attempts, blocked calls, sibling runs, and sandbox effects do not count. An
outstanding admitted write also prevents preparation. General partial-write replay
and payment/message idempotency are unsupported and recovery refuses such tasks.

`RecoveryState` carries `incident_id`, `report`, the prepared `policy`, `prepared_at`,
`approval: HumanRequest | null`, `approved_at`, `new_run_id`, `useful_task_completed`,
and a controlled `error`. Its `status` is `prepared`, `queued` (human approved),
`running` (SDK claimed), `completed` (useful task proven), or `failed`. Preparation and
approval emit `recovery.prepared` and `recovery.approved`; preparation records the
incident's real merged status without clearing its confirmed verdict. Existing human
approval and run events preserve actor/reason/time and original/new-run lineage.

Approval rechecks snapshot, full registration, policy/config and successful prior writes.
The queue pins the same full spec and policy; later registration changes refuse claim.
A later Rules activation can affect new runs while the approved queue keeps its policy
copy. The claim rechecks the source snapshot/config and prior-write condition. The
original remains killed/halted/failed, and its token never admits new effects.

Ordinary SDK `/complete` behavior remains unchanged. Recovery success additionally
requires an actual completed invocation, the approved full spec and task identity,
a complete grounded legitimate-task declaration, exactly one successful outward brief,
safe effects, and `contracts.completion.matches_requirements` over successful new-run
request/result pairs. Empty/failed/duplicate briefs fail recovery even if invocation
returned. Synthetic wire example: `contracts/fixtures/recovery.json`; it is not provider proof.
