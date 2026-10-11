# HTTP, coding-agent verification and replay reference

[Canonical overview](../../CONTRACTS.md).
[contracts/models.py](../../contracts/models.py) remains the wire-shape source of truth.

## 5. HTTP API

Base URL: `http://localhost:8000`. JSON in, JSON out.
All POST bodies with a human action carry `{actor, reason}`.

### Read

| Method | Path | Returns |
|---|---|---|
| GET | `/runs` | `Run[]` |
| GET | `/runs/{id}` | `Run` |
| GET | `/runtime` | `RuntimeInfo` |
| GET | `/events?after={seq}` | `Event[]`, with `X-Mirage-Stream-Epoch` from the same atomic read |
| GET | `/stream` | Named `runtime` frame before business `Event` messages; supports `Last-Event-ID` |
| GET | `/incidents` | `Incident[]` |
| GET | `/incidents/{id}` | `Incident` |
| GET | `/services/{service}?env=prod\|mirage` | `ServiceView`, folded from the event log. prod outbox: sent emails (`normal`) + frozen/blocked ones (`blocked`, never sent). mirage outbox: what the main detonation would have sent (`malicious` if it broke a rule). calendar/crm: what the agents read (mirage: the frozen run's inputs). The proven cause is `malicious`. |
| GET | `/policies` | policy pack (read-only) |

### Act

| Method | Path | Does |
|---|---|---|
| POST | `/stop` | Global STOP. All runs halted, all tokens revoked, agents relaunched by resume terminated. |
| POST | `/stop/lift` | Lift the global STOP (204). Logged as `lift_stop`, emits `global.stop_lifted`. Halted runs stay halted. Kept for scripts; the dashboard and MCP use `/resume-all`. |
| POST | `/runs/{id}/freeze` | Freeze one run. |
| POST | `/runs/{id}/unfreeze` | Resume an eligible live frozen run. 409 for active proof, confirmed harm or medium checking/inconclusive. A historically cleared medium incident permits later manual unfreeze without repeating the released call. |
| POST | `/runs/{id}/kill` | End a frozen run. |
| GET | `/approvals` | Legacy `Approval[]`, oldest first; live returns `[]`. Medium (`MIRAGE_GATE_REVIEW` 0.4 ≤ p < threshold 0.7) now uses automatic incident proof. |
| POST | `/approvals/{call_id}/approve` | Legacy body `{actor, reason}` and `Run` response; logged as `approve` in stepped recordings. No live approval exists; unknown/current medium IDs return 404. |
| POST | `/approvals/{call_id}/reject` | Legacy body `{actor, reason}`, logged as `reject` in stepped recordings. No live approval exists; use explicit Kill for live containment recovery. |
| POST | `/runs/{id}/restart` | Approve a clean restart of a `killed`, `halted` or `failed` run (else 409; STOP also refuses). Returns the new `Run`, `queued`, with `restarted_from`. The engine then launches the agent from its registered entrypoint (as resume does); its matching agent/task/lineage/full-spec `POST /runs` claims it once. Without an entrypoint, the agent's owner must start it. A confirmed compromised original instead requires an accepted prepared verified rollout (below); the engine does not launch it, the trusted recovery launcher claims it. Duplicate/ambiguous/changed-spec claims refuse; queued stays queued until admission. |
| POST | `/runs/{id}/resume` | Resume a `halted` run: a clean restart the engine launches. 409 unless `halted`, 409 if its incident is confirmed compromised or detonating (same rule as unfreeze). If STOP is on it is lifted first (logged `lift_stop`, `global.stop_lifted`). Logged as `resume`. Returns the new `queued` `Run` (`restarted_from` = old id) and relaunches the agent from its registered `entrypoint` (`factory().invoke` with the same task, `MIRAGE_URL` = this engine); that start takes over the queued run. Without an entrypoint the run stays queued for its owner to start (`run.started` carries a `note`). |
| POST | `/resume-all` | Lifts STOP if it is on (one `lift_stop`), then resumes every `halted` run with no restart yet (no run has `restarted_from` = its id), like `/runs/{id}/resume` (one `resume` each). Returns `ResumeAll {resumed: Run[], skipped: [{run_id, reason}]}`; `skipped` holds halted runs refused as compromised or detonating. A second call resumes nothing new. Replay: advances the recording, returns empty lists. |
| POST | `/incidents/{id}/detonate` | Explicit retry or operator replay (initial gate-incident replay is automatic). Returns `{detonation_id}`. Results come as events. |
| POST | `/incidents/{id}/bisect` | Start bisection. Results come as events. |
| POST | `/incidents/{id}/handoff` | Optional body `{actor, reason}`. Needs a confirmed verdict (409). Returns `{prompt, claude_code_url, codex_url, mirage_token, report}`: the prompt for a coding agent (facts, fenced untrusted input, where the code is, the check command), the report (markdown), a token for this incident only (never logged). Incident → `fix_pending`. |
| POST | `/incidents/{id}/pr` | Body `PullRequest` `{url}`. The fix PR (coding agent or human). Emits `pr.opened`. Incident → `pr_open`. CLI: `engine.cli pr --incident X --url Y`. |
| POST | `/incidents/{id}/verify` | Run the fix check. Same output as `mirage detonate`. With `MIRAGE_PUBLIC=1` (API exposed through a tunnel) it needs `Authorization: Bearer <mirage_token>`. |
| POST | `/incidents/{id}/repair-jobs` | Required `{actor, reason}`; returns a queued `RepairJob` (201). Requires a confirmed incident and original harmful ledger. Duplicate active jobs return 409. Replay refuses (409). |
| GET | `/repair-jobs` | Public `RepairJob[]` in creation order; the supervisor finds open repair PRs to refresh. |
| GET | `/repair-jobs/{job_id}` | Public `RepairJob` progress, folded from the existing event store. |
| GET | `/incidents/{id}/repair-jobs` | Public `RepairJob[]` in creation order, for restoring incident progress after refresh. |
| GET | `/repair-jobs/{job_id}/context` | Private supervisor only: `RepairJobContext {job, snapshot, clean_snapshot, baseline_effects, snapshot_json, clean_snapshot_json, baseline_json, policy_digest, incident, report}`. Never included in chat or SSE. |
| POST | `/repair-jobs/{job_id}/report` | Private supervisor only: `RepairJobReport` imports external candidate CLI/GitHub evidence; returns the updated job. No shell launch, merge or restart. |
| POST | `/repair-jobs/{job_id}/pull-request` | Private supervisor only: a fresh `gh pr view` `RepairPullRequest` for a `pr_open` job. Same url/number/base and `headRefOid == candidate_sha` (409 otherwise). Records `OPEN → MERGED | CLOSED` (or reopen) as `repair.job.updated`; MERGED is final; an unchanged receipt is a no-op. |

### Repair job contract (special-improvements, M1)

`RepairJob` pins `{id, incident_id, repository, base_branch: "special-improvements", base_sha,
snapshot_digest, baseline_digest, status, created_at, updated_at}` and adds nullable
`{candidate_sha, verification, pull_request, pr_url, error}`. Commit SHAs are full lowercase
40-character hex; content digests are SHA256 of UTF-8 JSON with sorted keys, compact separators
and Unicode preserved (`ensure_ascii=False`). The baseline digest covers the original full detonation's effects list.
States: `queued → running → verifying → pr_open`, or any active state → `failed`.
On engine restore, active jobs fail with `interrupted`; they never automatically relaunch.
Creation is unsafe to retry after a lost response; query incident events for the existing job
before launching. A duplicate active create returns 409 and never launches another worker.

The engine takes `MIRAGE_REPAIR_REPOSITORY` (`owner/repo`) and `MIRAGE_REPAIR_BASE_SHA` from
trusted process configuration, never operator/model parameters. Private context/report require
an actual loopback client, no `Forwarded`/`X-Forwarded-*` headers, `MIRAGE_PUBLIC != 1`, and
`Authorization: Bearer <MIRAGE_REPAIR_SUPERVISOR_TOKEN>` from the local supervisor environment.
Missing configuration returns 503, wrong token 401, nonlocal/proxy/public access 403.
This local supervisor trust seam is not a distributed attestation service.
The clean counterpart is derived from the incident snapshot: the bisection-proven cause item's
description/body/notes/text become neutral text everywhere it appears and recorded model replies are
cleared. Without a found cause, repair creation returns 409. `MIRAGE_REPAIR_CLEAN_SNAPSHOT` optionally
overrides it with a trusted file. Either way context validates it against the original and returns it privately.
The engine redacts credential/capability fields and current process secret values from private
copies while preserving synthetic `FLAG{team26-...}` canaries. Digests bind the sanitized copies.
Hash the returned `snapshot_json`/`baseline_json` UTF-8 bytes directly and copy `snapshot_json`
and `clean_snapshot_json` to the private CLI recordings; do not reserialize with Node (its
number formatting can differ). Parsed strings match the accompanying objects. `policy_digest`
binds the exported freeze-time policy. See `repair_canonical.json` for Unicode/float examples.

`RepairJobReport`: `{status, snapshot_digest, baseline_digest, candidate_sha?, verification?,
clean_control?, pull_request?, error?}`. `verification` is `{exit_code, result: DetonateResult,
replay_errors}` from the final committed candidate's actual CLI process. `clean_control` adds
`snapshot: Snapshot` to that same wrapper. Clean control must retain the original task,
permissions, trusted completion declaration, meeting record and exact recorded reads, replacing
only one calendar/email/web/attachment input's untrusted text consistently in input and tool
result (the proven cause when available). CRM records and the user task cannot be replaced. Recording IDs,
timestamps, run identity, model calls and entrypoint may differ; current-code verification clears model calls.

`pull_request` is the supervisor's actual `gh pr view` receipt:
`{url, number, baseRefName, headRefOid, isDraft, state}`. `pr_open` requires exit 0, no replay
errors, attack blocked `3/3`, useful task completion `3/3`, clean control blocked/useful `1/1`,
and an OPEN draft in the configured repository with base `special-improvements` and
`headRefOid == candidate_sha`. The engine reuses deterministic effect/completion checks;
forged counts, empty ledgers, blanket refusals and harmful effects fail. It records summary
`verification: {attack_blocked, legit_task_completed, clean_task_completed, clean_snapshot_digest}`
and the PR receipt; raw report evidence stays private. Passing reports emit existing
`fix.verified` and `pr.opened`; the original incident verdict is preserved and the run stays
contained. Mismatches return 409 without certifying success; supervisor must report failure.
`verifying` requires the committed candidate SHA; final `pr_open` must match that latest SHA.
An explicit repeated `verifying` update may bind a new committed retry before its CLI runs.
After `pr_open` the job status stays `pr_open`; `pull_request.state` is the live PR state. The
operator supervisor re-reads every OPEN repair PR (`MIRAGE_REPAIR_PR_POLL_MS`, default 15 s) and
reports changes through `/pull-request`. A CLOSED (unmerged) PR lets the operator start a new job.
Controlled errors: `interrupted | launch_failed | worker_failed | verification_failed |
evidence_mismatch | pr_failed | context_changed`. Failed is terminal.

### Rules (Special Improvements M3)

The engine owns durable typed restrictions and previews. The first type names one registered
agent, a subset of its allowed tools and exact allowed email recipients. `RuleDraftRequest` is
`{agent, allow: Allowlist}`; `allow.url_hosts` must be empty because this type does not edit hosts.
Tool names must be both registered and allowed; recipients must already fit the role's baseline.
The draft never activates itself, including after a false positive or failed preview.

| Method | Path | Body → response |
|---|---|---|
| GET | `/rules?agent=&offset=0&limit=100` | `RuleRevision[]`, newest drafts first; optional agent filter, limit 1–100 |
| GET | `/rules/agents` | Registered `AgentSpec[]`, sorted by name; no canonical aliases |
| POST | `/rules` | `RuleDraftRequest` → `RuleRevision`; same normalized content returns the existing revision |
| GET | `/rules/{version}` | `RuleRevision` |
| POST | `/rules/{version}/preview` | Optional `RulePreviewRequest` `{tool?, args?}` → `RulePreview` |
| POST | `/rules/{version}/activate` | `HumanRequest` `{actor, reason}` → `RuleRevision` |

`RuleRevision` is `{version, agent, allow, status, created_at, activated_at}`. Version is the
SHA256 digest of normalized agent/allow content; the content cannot be edited. Status is `draft`,
`active` or `superseded`; each agent has at most one active revision. Activation requires nonblank
actor and reason, revalidates the current registered baseline, logs `human.action` (`activate_rule`)
before `rule.activated`, and survives engine reload. Repeating activation of the active revision
returns it without another audit event. Activating a superseded revision is a new explicit decision.

`RulePreview` is `{version, summary, effective_allow: Allowlist, decision: GateDecision|null,
authoritative: true}`. Omitting `tool` previews scope only; supplying a tool evaluates its known
call with the same engine hard rules. No model, tool execution, event or policy activation occurs.
`decision.call_id` is `preview` and grants no execution authority.

An activated rule intersects the registered allowlist and any exact matching canonical role;
the legacy `assistant` role and its destinations are never aliased to unrelated fleet roles.
URL host matching, canary detection, bulk export detection and P1–P6 remain unchanged.
The engine copies the effective policy and `rule_revision` at run admission, including approved
queued restarts. Later activation affects only later admissions. Restart claims compare the
original registered spec independently of the overlay. Frozen snapshots retain their policy;
verification checks it conjunctively with a policy copied once at verification start.

The SDK continues using HTTP checks and cannot supply a rule revision or policy authority in
`RunStart`. No second SDK evaluator, bundle cache or standalone bundle-pull service is added.
Writes use the existing trusted local operator boundary and return 403 when `MIRAGE_PUBLIC=1`;
actor labels are audit metadata, not authentication. Replay reads use visible fixture events;
replay writes return 409. Unknown agents/versions return 404, invalid or broadened restrictions
return 422. `rules_demo.jsonl` and `rules_http.json` are synthetic contract examples, not live proof.

### Demo control (for reliability on stage)

| Method | Path | Does |
|---|---|---|
| POST | `/demo/start` | Optional body `DemoStart {scenario}` (default `calendar`; others 501, not built). Live: `/demo/reset`, then launches `agents.run_demo_fleet` (Liam's 4 agents) as its own process, `MIRAGE_URL` = this engine. Replay: restarts the recording. |
| POST | `/demo/reset` | Live: stops the demo agents process, clears runs, agents, event log, snapshots and handoff tokens, lifts a global STOP. Also terminates agents relaunched by resume. Replay: restarts the recording. |

Long actions (detonate, bisect, verify) return at once. Progress comes as events.

SSE runtime frames have `event: runtime`, JSON `RuntimeInfo` data and no business `id`.
The first frame is always runtime metadata, including on reconnect with a stale `Last-Event-ID`;
later metadata changes are sent before the next business batch. Epoch changes reset the
business cursor. Polling consumers compare the events response's epoch header, discard stale
history on change, and fetch from zero; API failures must not be projected as successful jobs
or active control. Runtime frames are not new `EventType` values or persisted business events.

In live mode, a newly opened gate incident automatically queues three detonation replays
**after** its snapshot is persisted and its production run is frozen. The SDK/HTTP gate and
the in-process dev gate use the same scheduler; no operator action or UI polling triggers it.
Repeated `RUN_FROZEN` checks, manual freezes without an incident/snapshot, restore and replay
fixtures do not schedule live work. The automatic queue is logged with `run.status`
(`from: frozen`, `to: frozen`, `actor: system`, reason naming automatic detonation);
`detonation.started` means execution has begun, not just reservation. No automatic action
is recorded as a `human.action`. Completion/failure use the existing lifecycle events.

One shared, thread-safe runtime reservation covers automatic/manual detonate, bisect and
verify. Jobs run one at a time across incidents, retaining the sandbox's existing sequential
replay pacing by default. Failed work leaves production frozen and needs an explicit manual
retry through `/incidents/{id}/detonate`; retry/verify/bisect cannot grant automatic release.
Only the initial medium job may release its exact original call, once, after three complete
error-free useful baselines capture it without harm, stronger validated SAFE classifications
cover held/outbound calls, and current authority matches. Other recovery stays human.
STOP rejects new jobs and cancels queued jobs when they reach execution;
an already active sandbox job can finish but cannot release production.

`/demo/reset` and `/demo/start` return 409 while a sandbox job is active, **before** changing
agents, events, snapshots or tokens; wait for completion and retry. When idle, reset excludes
new reservations, cancels queued jobs and clears data atomically relative to the scheduler.
Graceful shutdown cancels queued work and drains active sandbox work before exit.
Reservations are process-local: stop standalone dev/CLI processes before resetting shared
data, and use the SDK/API fleet for the dashboard demo. Replay mode retains fixture stepping.

Detected external file replacement restores registrations and STOP from the replacement log,
revokes old in-memory owners, and fences proof-job emissions to their reserved store epoch.
Old active work may drain, but its verdict/effects/lifecycle cannot enter the replacement log;
new same-ID reservations survive old-job cleanup and execute on the existing single-worker queue.
This also covers nested sandbox worker threads. Epoch visibility does not establish distributed
production-control authority: standalone processes must still be stopped before shared resets,
and cross-process live STOP append synchronization is outside this prototype's control guarantee.

## 6. Coding agent contract (`mirage detonate`)

Fix output below belongs to CLI `detonate` (default current-code verification) and HTTP
`/verify`. MCP `detonate` calls HTTP `/detonate` for baseline proof, not current-code verification.

```
mirage detonate --incident inc_007 [--runs 3] [--remove-input in_cal_03] [--json]
mirage detonate --incident inc_007 --policy-file /private/effective-policy.json --json
# today: uv run python -m engine.cli detonate ...
```

```json
{
  "incident_id": "inc_007",
  "attack_blocked": "3/3",
  "legit_task_completed": "3/3",
  "passed": true,
  "effects": [ "Effect", "..." ],
  "policy_revisions": []
}
```

`passed` is true only if both values are `3/3`.
`policy_revisions` lists sorted unique rule digests checked from the frozen policy and, for
verification, the effective policy copied at verification start. Legacy policies have no rule digest.
Activation during a verification cannot change that proof's policy. Rebuilt factory permissions
are additional baseline constraints; they cannot broaden the frozen or verification-start policy.

For a private standalone repair/recovery checkout, the trusted local operator may pass
`--policy-file` with the direct effective-policy JSON from authenticated engine provenance.
The CLI validates the existing policy shape and snapshot agent, then copies that policy once
before verification children run. The original snapshot file and frozen restrictions remain
unchanged and conjunctive; changing the source policy file mid-proof cannot change the copy.
This flag is verify-only: `--from-freeze` and `--remove-input` reject it. Invalid or unavailable
files return exit code 2 before proof starts. No browser/data-plane policy override or new policy
language is exposed; the existing HTTP gate remains production authority.

## 7. Fixtures and replay mode

- `contracts/fixtures/calendar_demo.jsonl` holds one `Event` per line, in order, with real timing (`ts`).
- `contracts/fixtures/state/` holds `runs.json`, `incidents.json`, `services_*.json` at the end of the demo.
- `execution_failure.jsonl` and `execution_snapshot.json` are synthetic contract examples for
  failed completion/results/effects and story declarations; they are not the default demo recording.
- `runtime_metadata.json` contains synthetic `RuntimeInfo` and `SandboxJob` wire examples;
  legacy demo fixtures retain a null job projection without guessing state from text.
- With `MIRAGE_MODE=replay`, the real API server plays the `.jsonl` file over `/stream` and `/events`.
  Same endpoints, same OpenAPI. There is no separate mock server, so nothing can drift.
- POST actions in replay mode move the replay forward (example: `/incidents/{id}/detonate` plays the detonation events).
- Person B writes the first fixtures by hand in hour 1. Later, Person A replaces them with a real recorded run.
- Starter fixture: `contracts/fixtures/sample_demo.jsonl` (story 1, valid against `models.py`). The server
  plays `calendar_demo.jsonl` when it exists, else the sample. Override with `MIRAGE_FIXTURE=<path>`.
- Speed: `MIRAGE_REPLAY_SPEED=10` plays 10x faster (UI work, tests).
- How POSTs move the replay: the fixture is cut into one segment per operator step: detonate, find the cause
  (bisection, including its own detonations), handoff, check a fix, and each other `human.action` (kill,
  unfreeze, restart...). Any POST action plays the next segment. `/demo/start` and `/demo/reset` restart.
- Record a real run as the fixture: run the demo live, then `uv run python -m engine.cli export-fixture`
  (writes `contracts/fixtures/calendar_demo.jsonl` and lists the replay steps).
- `/runs` and `/incidents` are folded from the events played so far, including `next_action`.
- Data plane routes (§11) answer `409` in replay mode.

### Managed recorded demo (opt-in)

`MIRAGE_MODE=replay MIRAGE_REPLAY_MANAGED=1` enables the managed calendar story, defaulting to
`contracts/fixtures/fleet_demo_4agents.jsonl` (override with `MIRAGE_FIXTURE`). `MIRAGE_REPLAY_SPEED` controls
timing (`inf` shows each unlocked stage immediately). Legacy replay without the managed flag
keeps the operator-driven behavior above. Launcher state paths (`MIRAGE_DB`, `MIRAGE_SNAPSHOTS`,
`MIRAGE_TOKENS`) are isolated absolute paths; managed replay never reads or writes their stores.

- Recorded production activity, freeze, baseline three-run detonation and verdict play automatically.
  Healthy outreach, support and PR-review runs remain running when the meeting assistant freezes;
  their final tools, results and completions continue during baseline detonation, before its verdict.
  Fixture timestamps and sequence order form one contiguous stream across these parallel runs.
  No production agent, job, model, provider tool or sandbox subprocess is started. Real Miragio and
  MCP handlers may call this real HTTP API; their model execution belongs to the caller.
- `/bisect`, `/handoff`, `/verify`, then `/pr` unlock only the matching next stage for the matching
  incident, after the previous stage finishes playing. Unknown targets return `404`; wrong actions,
  premature or repeated actions return `409` without advancing. Requested run counts must match
  the recorded evidence (baseline/verification three, bisection two). Reads never unlock stages.
- Bisection returns `{incident_id, status: "bisecting"}` and verification returns
  `{incident_id, status: "verifying"}`. Completion events remain visible through `/events` and
  `/stream`, so MCP `wait:false` callers can follow their cursor. Handoff returns the existing prompt
  and coding-agent URL fields immediately. Accepted bisection, handoff and verification record the
  actual actor, reason and decision timestamp in `human.action` (missing bodies are `unknown`).
- Handoff explicitly describes recorded evidence, with no usable live snapshot, token or capability.
  It writes no fix. Verification shows recorded example evidence, not a test of current code. PR
  evidence uses `https://example.invalid/recorded-demo/pr/42`, never a real repository PR; `/pr` only
  acknowledges the fixture's exact placeholder URL after verification, and creates no GitHub PR.
  Legacy replay `/pr` returns `409` rather than writing the live store.
- `/stop` pauses the recording clock and blocks incident-stage actions; `/stop/lift` and `/resume-all`
  resume the clock from that position, without unlocking an incident stage. These actions log actual
  actor/reason in the replay event stream (`global_stop` / `lift_stop`). `/resume-all` returns the existing
  `ResumeAll` shape with `resumed: []` and `skipped: []`: no runs or models are launched or restarted. Either
  resume route returns `409` without changing evidence when the recording is not paused. While paused,
  active recorded runs are returned as `halted`; resume restores their prior recorded states, including
  the compromised production run remaining `frozen`. This is a synthetic pause, not live token
  revocation or a clean agent restart. Historical evidence stays
  intact. Per-run controls and approval decisions explicitly return `409`; confirmed
  harmful runs specifically reject unfreeze. `/policies` supplies recorded registrations (derived
  from fixture activity if registration events are absent), without live entrypoints.
- `/demo/start` (calendar only) and `/demo/reset` restore the original recording, clear replay-only
  decisions and lift its pause. They do not launch agents or touch ordinary SQLite/snapshot/token data.
  Fixture event timestamps retain recorded timing; `human.action.payload.ts` is the real decision time.
