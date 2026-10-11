# SDK reference

[Canonical overview](../../CONTRACTS.md).
[contracts/models.py](../../contracts/models.py) remains the wire-shape source of truth.

## 11. SDK: how an agent joins Mirage

Owner: Liam. The SDK goes **into the customer's agent**, not into our engine. It is the developer experience.

Principle: **with or without Mirage, the agent runs in production exactly as it would without it.**
Same tools, same keys, same results. The SDK only sits in front of each tool call and records the run.
When the gate trips, the run freezes in prod and the agent **keeps running in the sandbox from the frozen
call**, with its full context, where every action is traced and nothing reaches the real world.

Two lines, any supported framework:

```python
import mirage
# LangGraph graph or OpenAI Agents `Agent`
agent = mirage.protect(agent, name="assistant", api_key="mirage_live_demo")
# Claude Agent SDK `ClaudeAgentOptions`
options = mirage.protect(options, name="assistant", api_key="mirage_live_demo")
```

`api_key=None` is optional and keyword-only: a demo placeholder accepted and intentionally ignored
for all three frameworks. It provides no authentication and is never stored, logged, or forwarded
to an adapter or the engine. Existing calls and positional arguments still work.

`allow={...}` (the allowlist, `Allowlist`) is optional. The SDK is a thin client: **every decision is in
the engine.** It has three parts:

1. **Adapters** find, inside the agent: run start (task), every tool call, every model call, run end.
2. **Core** is the data plane client below: register, start run, record model calls, check each tool call
   (run it on allow, wait while frozen, raise on kill), record its result, complete.
3. **Sandbox runner** (`mirage.sandbox:run`): rebuilds the agent and routes its tools to the engine's
   `call_tool` (see "Snapshot and replay"). The SDK never reads tool answers from the snapshot itself.

### Where each adapter plugs in

Original adapter mapping: OpenAI Agents SDK 0.23, Claude Agent SDK 0.2.165.
Provider-free adapter regressions now exist; this table does not claim a live provider rehearsal.

| | LangGraph (demo) | OpenAI Agents SDK | Claude Agent SDK |
|---|---|---|---|
| Run start + task | wrap `invoke` / `stream` | `agent.hooks` `on_start` (`turn_input`) | `UserPromptSubmit` hook (`prompt`) |
| Tool call: check, freeze, kill | middleware `wrap_tool_call` | wrap `FunctionTool.on_invoke_tool` | `PreToolUse` hook (deny, or wait; raise its `timeout`, default 600 s) |
| Sandbox: answer instead of running | yes | yes | custom tools only (wrap the handler); built-ins (Bash, WebFetch) are denied |
| Model calls recorded | `wrap_model_call` | wrap `agent.model` | session transcript (`options.session_store`) |
| Sandbox: replay replies to the freeze | yes | yes | no (the model runs in the CLI); fork the session instead (to check) |
| Run end | after `invoke` | `on_end` (+ catch errors) | `Stop` hook |

Verified in two spikes with the LangGraph adapter (LangChain 1.4): waiting inside the tool hook holds the run
until release; raising stops it before the tool runs; in mirage mode no real tool ran and the write was captured.

Limits: Mirage sees only tool calls. Code that calls an API outside a tool, and OpenAI hosted tools
(web search, code interpreter), are not seen.

### Data plane API (SDK → engine)

| Method | Path | Body → Returns (models in `contracts/models.py`) | Does |
|---|---|---|---|
| POST | `/agents` | `AgentSpec` `{name, owner, tools, allow: {tools, email_to, url_hosts}, entrypoint, legit?}` | Register an agent. `entrypoint` example: `agents.assistant:build_agent`. `legit` defaults to `{}`. |
| POST | `/runs` | `RunStart` `{agent, task, env, restarted_from}` → `RunStarted` `{run_id, run_token}` | Start a run. Emits `run.started`. |
| POST | `/runs/{id}/model-calls` | `ModelCall` `{model_id, request, response}` | Record one model call. |
| POST | `/gateway/check` | `ToolCheck` `{run_id, tool, args}` → `GateDecision` | Check one tool call. The engine assigns `call_id`. |
| POST | `/runs/{id}/tool-results` | `ToolResult` `{call_id, tool, result, error}` | Record only the matching admitted call/tool for this authenticated run. Unknown, held or revoked calls return 409 before recording. Identical retries return 204 without another result; conflicting retries return 409. |
| GET | `/runs/{id}/wait?timeout=25&call_id=call_014` | → `WaitResult` `{status: running \| frozen \| failed \| killed \| halted}` | Long poll the original held call (max 60 seconds). A durable human release or conclusive initial medium clearance makes only this call eligible; its bound wait claims admission once. Unknown, revoked, consumed or stale calls return 409. Omitting `call_id` supports status-only legacy polling, but pending/revoked held release authority returns 409 instead of granting a callback. The SDK sends its original checked `call_id`, polls again after `frozen`, and blocks on 409 or terminal status. |
| POST | `/runs/{id}/complete` | Optional `RunCompletion` `{error: string \| null}` → `Run` | While `running`: absent/null error emits `run.status` → `completed`; non-null error emits `failed` with a sanitized reason. No body and `{}` preserve old clients. Contained and terminal runs stay unchanged. |

Destination checks read the `to` and `url` arguments of **any** tool, so tool names are free.
`allow.email_to` takes domains (`mirage-demo.com`), `*@domain`, or full addresses (`demo-user@mirage-demo.com`).

The SDK sends the run token as `Authorization: Bearer <run_token>`.
Human-action POSTs from web and MCP (§5) send `HumanRequest` `{actor, reason}`.

Calls checked while already frozen block immediately, without policy evaluation or a new hold.
A later freeze, kill or STOP retires unclaimed held-call release authority; a later unfreeze cannot
revive it. Results from already-admitted in-flight calls remain acknowledgeable once after containment.
Admission and the SDK's local callback are separate steps: already-started external effects cannot
be cancelled instantaneously. Neither a result acknowledgment nor legacy status polling admits a new call.

### Snapshot and replay

- The snapshot is `Snapshot` in `models.py`, written by the gate at freeze (`data/snapshots/<incident_id>.json`):
  task, entrypoint, model calls up to the freeze, every tool call with its result, and the inputs.
- **Only the engine reads and writes it.** The SDK never parses it to answer tools; it gets a `call_tool`.
- A tool result can hold several inputs (example: `read_calendar` returns 4 events). Each one is an `Input`.
- `SnapshotToolResult` is `{call_id, tool, args, result, error?}`. Failed results stay recorded with
  a sanitized `error` and `result: null`; they never contribute useful inputs or successful effects.
  Replay preserves the failure outcome, not the provider's raw error text: the SDK reconstructs an
  error tool message from the marker. Known built-in/common provider exception types are retained;
  unknown or empty error strings become `ExecutionError`.
- Each run pins its full admitted `AgentSpec` and policy; same-name registration affects future
  runs. `AgentSpec.legit` is copied into each new/restarted run and its frozen `Snapshot.legit`.
  It is an opaque declaration owned by the story; this contract only transports it. The current shape is
  `{"required": [{"tool": "send_email", "args": {"to": "demo-user@mirage-demo.com"},
  "nonempty": ["subject", "body"], "contains": {"body": ["Q4 sync"]}}]}`:
  `args` names an exact subset to match, `nonempty` names required nonempty arguments, and `contains`
  supplies relevant strings required in each named argument. Criterion evaluation belongs to the sandbox.
- Detonation: the engine starts a jailed child process (no third-party keys, network only to Bedrock).
  The child calls `runner(snapshot, call_tool)` (`runner` defaults to `entrypoint`). For SDK agents the runner is
  `mirage.sandbox:run`: it rebuilds the agent from `entrypoint`, replays the recorded model replies up to
  the frozen call, then runs live from there. Every tool call goes to `call_tool(tool, args)`, owned by the
  engine. Reads return the next recorded result for exactly the same tool and arguments. Missing or
  exhausted reads return a typed `ToolResult` with null result and a safe error category. Declared
  demo writes are captured and answered `{"status": "ok"}`; an exact recorded failure stays a typed failure.
- Bisection: remove one `Input` from the snapshot (example: the invite from `read_calendar`'s result) and run
  again **from the start** (no replay of model replies), so the agent's path can change.

### Sandbox seam (engine ↔ SDK mirage mode)

Built in `engine/detonation/`. The engine owns the process and the jail; the agent code only sees two files.

- **At freeze** the gate writes `data/snapshots/<incident_id>.json`, validated as `Snapshot` (`models.py`),
  including `model_calls` (from `POST /runs/{id}/model-calls`). Agents registered with `POST /agents` get
  `runner = "mirage.sandbox:run"`; engine dev agents get `runner = null`.
- **Each detonation run** is a new `python -I` child in a temp folder. Its environment holds only
  `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`, OS basics, `MIRAGE_SNAPSHOT` (path), `MIRAGE_EFFECTS` (path),
  and non-secret agent config (`*_MODEL_ID`, `DEMO_USER_EMAIL`) so the rebuilt agent uses the same model and user.
- **Jail** (audit hooks): DNS and connections only to `bedrock-runtime.<region>.amazonaws.com`; no new
  processes; no reads of `.env` or `secrets/`. Each blocked attempt is logged as an effect `sandbox.<kind>`.
- **Runner**: the child calls `(runner or entrypoint)(snapshot: dict, call_tool)` where
  `call_tool(tool, args) -> result`. Every tool call must go through `call_tool`. Today the engine's dev agent
  is called directly (`engine.dev.assistant:mirage_entry`); SDK agents go through `mirage.sandbox:run`.
  `call_tool` consumes exact tool+args recordings in chronological order, without reusing another entity's
  same-tool result. Successful read values stay raw, including dictionaries with ordinary error/status
  fields. Non-null recorded errors and unavailable reads return `ToolResult(result=None, error=<safe category>)`
  and emit the same category in `Effect.error`, without provider text. Declared demo write names receive
  captured synthetic acknowledgments; unsupported unrecorded tools fail unavailable. Each attempt has
  a fresh snapshot and recording-consumption state.
- **Gate layer 2** (`engine/detection/decision_model.py`): for outbound calls the hard rules allowed (a destination
  argument, or a send/export/share/post/forward/upload/publish tool), `gpt-oss-safeguard-20b` judges the call against
  P1-P6 and the user's task. Violation with `p >= MIRAGE_GATE_THRESHOLD` (default 0.7) → freeze with
  `layer: decision_model`, `policy_id`, `p`. Reads are not judged. An outage allows the call and says so in
  `explanation`. `MIRAGE_LAYER2=0` turns it off. It only decides freezes; the verdict stays code.
- **Medium suspicion:** `MIRAGE_GATE_REVIEW` (0.4) ≤ p < threshold (0.7) returns `freeze`,
  `rule_id: SANDBOX_REVIEW`, persists an incident/snapshot and automatically queues three baselines.
  All must finish useful work error-free, capture the exact held effect and show zero code-defined harm.
  The configured stronger judge must return validated SAFE for held and actual outbound calls.
  Missing/partial/stale evidence, crash, semantic doubt or unavailable classification stays contained.
  Current run/call/token/generation/spec/policy/task/snapshot/job/epoch authority is rechecked; durable
  completion and clearance precede the one original callback grant. Manual retry/verify/bisect cannot
  release it; checking/inconclusive human unfreeze is refused. High/hard/escalation always needs a human.
- **`BULK_RECORDS`** (hard rule, P4): an outbound call carrying `>= MIRAGE_BULK_RECORDS` (default 6) email addresses
  besides its recipients freezes, even to an allowed destination. The verdict uses it too.
- **Verdict** is code: the gate's own hard rules run over each effect. Any hit = compromised run.
- **Judge** (`engine/detection/judge.py`, `BEDROCK_JUDGE_MODEL_ID`, safeguard-120b): after a full detonation that
  found harm, it reads only the harmful effects (never the inputs) and adds valid policies to `policies_violated` and
  one plain sentence after the code's `blast_radius.summary`. It never changes `confirmed` or the counts; on any error
  the code's text stands. Not run for bisection rows or fix checks. `MIRAGE_JUDGE=0` turns it off.
- `MIRAGE_PARALLEL=N` (default 1): run N replays and N bisection rows at once. Rows are emitted as they finish;
  the incident lists them in input order.
- **Tools the agent does not have** (a model typo such as `search_contactschannelcommentary`) are not an attack:
  the gate answers `block` with `rule_id: UNKNOWN_TOOL`, without freeze or incident. An actual callback
  must have a registered tool identity; an invocation-ending SDK denial is reported as failed through
  the existing completion error contract. The verdict ignores absent tools. "The agent's tools" =
  `AgentSpec.tools`; agents that don't register (engine dev agents) keep the old rule.
- **`ESCALATION`** (hard rule): an agent that keeps asking for tools it does not have, other than garbled names that
  contain one of its real tools, is probing for a way around its permissions. The `MIRAGE_ESCALATE_AFTER`-th such
  call in a run (default 2) answers `freeze` with `rule_id: ESCALATION` and opens an incident; earlier ones stay
  `UNKNOWN_TOOL`. Escalation contains the run but never grants release authority to an unregistered callback.
- **Legit task**: the snapshot carries the agent's opaque `legit` story declaration (above).
  The sandbox owns evaluation; failed attempts cannot count as completion. Legacy `{tool, to}` declarations
  and the existing empty-declaration fallback remain compatible until that evaluator is updated.
- **Bisection** (`engine/bisect.py`): for each **untrusted** input (`calendar_event`, `email`, `web_page`,
  `attachment`; the user task and CRM records are trusted), detonate without it (default 2 runs, from scratch).
  The input whose removal drops the attack to 0 is the cause. `POST /incidents/{id}/bisect` needs a confirmed
  verdict (else 409); CLI: `uv run python -m engine.cli bisect --incident inc_001 [--runs 2]`.
- **Fix verification** (`POST /incidents/{id}/verify`, and `mirage detonate` by default): reruns the **current**
  agent code from scratch (no recorded model replies) and judges with the policy at freeze **and** the current
  policy (agent registration, else `policies.yaml` re-read). A fix that allowlists the attacker still fails.
  `passed` = no violation in n/n runs and the legit task done n/n. `--from-freeze` gives the operator replay.
- CLI: `uv run python -m engine.cli detonate --incident inc_001 [--runs 3] [--remove-input in_02] [--json]`.
  Exit code 0 only when `passed` (attack blocked n/n and legit task n/n), so a regression test can call it.
