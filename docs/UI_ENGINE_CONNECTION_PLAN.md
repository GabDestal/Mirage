# Mirage UI and engine connection plan

Historical plan, 2026-10-10, with M1 notes from 2026-10-11.
For present behavior and validation, read [current workflow and validation](CURRENT_WORKFLOW_AND_VALIDATION.md).
Full rehearsal is on hold until the user tells the coordinator to start.

The [complete original plan](https://github.com/GabDestal/Mirage/blob/5c9e2df8a996efab41562a697c0bb20cc3e87525/docs/UI_ENGINE_CONNECTION_PLAN.md) remains pinned to its immutable source.
It includes the original endpoint matrix, source index, runtime observations,
configuration reproduction, options, rollout briefs and test proposals. Those
observations and proposals are historical; they do not accept later source or
create new sprint requirements. This short index keeps the original section anchors.

## 0. Milestone 1 startup implementation and scope

M1 uses recorded agents/engine proof with real Bedrock Miragio and MCP handlers.
The managed launcher owns its dedicated children, ports and temporary paths.
Use [START](../START.md#run-the-m1-demo) for commands and [M1 acceptance](DEMO_MILESTONE_1_ACCEPTANCE.md)
for its tested compositions. Recorded fixes cannot verify current agent code.

## 1. Outcome and boundaries

Connect the dashboard to containment, automatic proof, cause search and external
repair. Preserve the [Person A/B split](../CONTRACTS.md#1-team-split) and HTTP boundary.
The current medium workflow and human recovery rules supersede the old blanket
requirement that every replayed run wait for human release; see the current record.

## 2. What is working today

“Today” in this original heading means the pinned historical audit, not final main.
The [original section](https://github.com/GabDestal/Mirage/blob/5c9e2df8a996efab41562a697c0bb20cc3e87525/docs/UI_ENGINE_CONNECTION_PLAN.md#2-what-is-working-today) preserves the reported facts.

### 2.1 Coordinator runtime observation

The original audit's PIDs, ports, event counts, stale-import diagnosis and dotenv
reproduction remain attributed to that session. Final loaded revisions need a fresh packet.

### 2.2 “Live,” “synthetic” and “offline” mean different things

Live engine/models, synthetic tool backends and fixture replay are separate facts.
The source fleet has four protected agents and in-memory tools; recorded M1 uses a
different support/40-contact example. See [demo provenance](DEMO_EVIDENCE.md).

### 2.3 Process and data flow

Web calls engine HTTP/SSE and proxies chat. Miragio uses Bedrock and existing MCP
handlers. Protected agents use SDK/HTTP; sandbox tools use recorded reads/captured writes.

### 2.4 Core architecture decision: separate demo ownership from engine ownership

Dedicated ports must also use separate state paths. The broader scenario-controller
migration remains a historical proposal; it is not required by this documentation task.

## 3. Current endpoint and consumer matrix

The original matrix is preserved in the pinned plan. Current canonical routes and
wire shapes are in [CONTRACTS](../CONTRACTS.md#5-http-api) and [models](../contracts/models.py).

## 4. Why detonation can be invisible

The original diagnosis separated stale imports, fixture stepping, queue visibility,
reconnect and restored ownership. Later repairs expose typed runtime/jobs and
persistent proof. The current record distinguishes source delivery from browser acceptance.

## 5. Startup mode taxonomy (proposal)

Implemented managed `demo` is recorded engine plus real chat. Plain `live` attaches
Vite to existing services. An offline provider and managed live launcher remain deferred.

### 5.1 Proposed launch and precedence

Current launcher options and precedence are in [START](../START.md#m1-launcher-details-and-options).
The original proposal does not authorize a hidden fallback or a new startup profile.

### 5.2 Child lifecycle and readiness

Readiness is a service check, not provider access. Managed launch stops only its
own children; fresh live rehearsal needs an explicitly owned isolated engine.

## 6. Smallest reuse-based options

The approved path reused native SSE, REST, Query cache, Replay and a Node stdlib
launcher. The pinned original retains the options, estimates and open-source review.
No dependency choice or implementation is added by this index.

## 7. Additive contract proposal

The original proposed fields are not a current schema. [Models](../contracts/models.py)
remain authoritative, with [CONTRACTS](../CONTRACTS.md) as the canonical overview.

### 7.1 Runtime metadata

Delivered runtime metadata reports mode, instance, epoch, high-water mark, loaded
revision and owned run IDs; it does not establish real-service integration.

### 7.2 Queue and job identity

Typed sandbox job purpose/status/count/error is separate from the incident's proof.
Recorded or restored jobs do not imply an active executor.

### 7.3 Epoch-aware transport

Runtime SSE frames and the events epoch header let readers discard old generations.
The final browser incident/reconnect rehearsal remains unrun on user hold.

## 8. Reconnect, reset and stale-state handling (proposal)

The delivered transport uses read-only recovery and stale-response fencing.
Reset remains destructive and refuses active proof work. Do not retry control POSTs
or infer live owners from old events. Full historical requirements remain in the pinned plan.

## 9. Demo lifecycle parity and human decisions

### 9.1 Baseline replay in the proposed demo profile

Managed M1 automatically plays recorded baseline proof; legacy replay retains its
own stepping. Neither starts production agents or live engine proof jobs.

### 9.2 Same proof story on Fleet, Incident and Chat

Existing baseline proof can persist across views without a model turn. External
handoff, bad/clean current-code fixes and human recovery still need fresh acceptance.
Service evidence and Engine approvals panels were intentionally removed from Fleet;
Miragio operator approvals remain distinct from protected tool-call mediation.

## 10. Current commands versus proposed commands

Use [START](../START.md) for executable setup. The old commands remain historical
examples, not authorization to start or reset the user's current session.

### Current attach workflow

Plain dev attaches; launching services alone does not launch a protected fleet.

### Current isolated recorded-engine workflow

Use the managed M1 route with dedicated ports and isolated temporary paths.

### Proposed convenience workflow

The broader convenience/offline proposals are deferred. The fresh live UI route
is in the [unrun reproduction checklist](CURRENT_WORKFLOW_AND_VALIDATION.md#reproduction-route--not-run).

## 11. Rollout: one feature, one Orca worktree, one PR

The original rollout table is historical. Source repairs and their validation are
accounted for in the current record; old proposed slices are not new dispatches.

## 12. Acceptance and validation plan

The original 26-test report, UI selfchecks and transport observations retain their
historical source and scope. They do not establish the final UI/provider rehearsal.
Current documentation checks cover links, anchors, line counts, accuracy and diff scope.

## 13. Risks and decisions to settle

Current limits include synthetic services, process-local jobs/pacing, external
fixer access and incomplete fresh rehearsal evidence. Broader authorization,
real-service adapters, hosting and controller migration remain deferred.

## 14. Document self-review and limitations

This update shortens the index and points to current facts. It changes no engine,
SDK, schema, fixture or runtime, and executes none of the original test proposals.

## Source index

The [original complete source index](https://github.com/GabDestal/Mirage/blob/5c9e2df8a996efab41562a697c0bb20cc3e87525/docs/UI_ENGINE_CONNECTION_PLAN.md#source-index) retains every immutable
code/documentation reference used by that audit. Current source holders and evidence
attribution are linked in [current workflow and validation](CURRENT_WORKFLOW_AND_VALIDATION.md).
