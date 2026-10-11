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
