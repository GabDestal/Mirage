# Current workflow and validation

2026-10-11. **Draft: final engine handoff pending. Rehearsal is on hold.**
Only the user can tell the coordinator to start the full rehearsal.
This record covers the local synthetic demo, not production acceptance.

Source inspected: `5c9e2df8a996efab41562a697c0bb20cc3e87525`.
The final code SHA, medium-clearance delivery and final accuracy review are pending.
This documentation worker has run no agents, services, controls or provider calls.

## What changed, and why

| Change | How it works | Why it matters |
|---|---|---|
| Protected four-agent fleet | Meeting assistant, invoicing, outreach and PR reviewer use the SDK and HTTP gate. Runs start before factory construction; failures keep a safe reason. | A failed model, factory or tool must not look completed, and healthy siblings can continue. |
| Call authority | A held release belongs to the original run, checked call and containment generation. Its wait claims admission once; results must match the admitted call. | Approving one call cannot authorize an unchecked sibling or revive a retired hold. |
| Failure and task truth | Snapshots retain tool-error markers. Replay matches the exact tool and arguments. Verification checks the required recipient, content and entity inventory. | An empty read, failed send, incomplete brief or partial task cannot count as a useful fix. |
| Proof accounting | Requested counts are positive and bounded. Harm recorded before a crash survives; failed attempts cannot certify a clean result. Parent collection failures retain sibling proof. | Missing or partial work cannot become an invented 3/3 pass. |
| Runtime and transport | HTTP/SSE expose process identity, loaded revision, stream epoch, owners and typed proof jobs. Read-only reconnect discards stale responses. | Restored history is evidence, not a restored live agent or lock. |
| Persistent proof | Fleet, Incident and Miragio can show existing baseline proof without asking a model. Bisection and verification remain separate. | Navigation should not lose the incident or confuse a later test with the initial replay. |
| External repair | The handoff supplies incident facts, agent location, snapshot/state paths and the verification command. The drawer explains local access. | The user's coding agent repairs and opens the PR; Mirage supplies the evidence and test. |
| Fleet simplification | Service evidence and Engine approvals panels were removed. Start demo, Ask Miragio and STOP remain. | The operator can focus on runs and the incident. Miragio's own action approvals remain separate. |

These are source facts or owning-worker reports, not a full browser rehearsal.
Source holders: [fleet](../agents/run_demo_fleet.py), [SDK](../sdk/mirage/core.py),
[gate](../engine/gateway/gate.py), [replay/verifier](../engine/detonation/sandbox.py),
[jobs](../engine/detonation/jobs.py), [runtime API](../engine/api/server.py),
[stream](../web/src/api/stream.ts), [Fleet](../web/src/pages/fleet.tsx),
[proof](../web/src/components/engine-proof.tsx), [handoff](../engine/handoff.py).
[Models](../contracts/models.py) remain the source of truth for wire shapes.

## Workflow and the medium change awaiting delivery

Protected agents act autonomously. The SDK automatically checks each tool call;
normal admitted calls run without asking a person for permission.
Containment suspends the pending tool callback before its production effect.
Other runs have separate owners and can continue.

The user-approved medium workflow below is **pending at the inspected source**:

| Gate outcome | Required behavior |
|---|---|
| Normal | Run the admitted tool and record its result. |
| Medium suspicion, conclusive clean evidence | Hold the original call, save its snapshot, automatically run three sandbox attempts, then admit that exact call once. |
| Medium suspicion, harmful evidence | Keep production contained; show the deterministic proof and human recovery. |
| Medium suspicion, inconclusive evidence | Error, crash, missing/partial/stale evidence or unresolved semantic doubt keeps the call contained. A no-harm count alone is insufficient. |
| High risk, hard rule or escalation | Freeze and prove; recovery always needs a human, even if replay appears clean. |

At `5c9e2df`, medium suspicion still uses `NEEDS_APPROVAL` without an incident.
The final engine feature must replace that behavior before these docs describe it
as delivered. High/hard-rule/escalation recovery, manual Freeze/Unfreeze/Kill,
STOP, fix merge and clean restart remain intentional human decisions.
Miragio approvals concern operator-requested actions, not routine protected tools.

For a new persisted gate incident, the engine automatically queues three sandbox
replays. Reads use the snapshot; writes are captured. Real service tools do not run.
Code decides harm from effects; the judge adds policy labels and explanation.
From-freeze replay reproduces recorded model replies before continuation; it proves
consequences, not three independent fresh injection successes.

Cause search removes untrusted inputs and runs from the start. Fix verification
also runs current agent code from the start, against frozen and current policy,
with the full legitimate-task check. A loosened attacker allowlist cannot pass.
The external coding agent tests and opens the fix PR; a human merges it and decides
on a clean restart. A queued restart stays pending until its protected owner starts.
There is no internal coding engine and no automatic merge.

## What the evidence establishes

| Evidence source | Result | Limit |
|---|---|---|
| Current source and merged repairs | Coordinator accounts for the 16 Person B repair features; owning tests cover their named heads. This draft also inspects merged call binding #154 and parent proof preservation #152. | Test counts from different compositions are not added. Final engine feature/source handoff remains pending. |
| Provider access probe | After key regeneration, six fresh model requests returned HTTP 200. Separate bounded gate/judge usability probes succeeded. | These probes do not establish a fresh four-agent fleet, injection reliability or full UI proof. |
| Actual browser chat | One no-tool browser turn through UI 5180, chat 8041 and Bedrock rendered a reply. Chat build: `d9c5f7744b1d742da03c9910427566ad9c5d0247`, reported PID 68595. | No incident, MCP action, fleet or repair was exercised. |
| Actual empty Fleet | Live attachment accepted on UI `5eef2405cbb3869ea70d124b38ae31b90f318d7c` and loaded engine `c116744767053793662dcbccc49c498f607e10f4`. Panel removal accepted on UI `56fc52e5b9ce7be26825984da07800b6563f1fe9`, same earlier API. | Empty layout/connection checks, not incident or medium-flow acceptance. |
| Provider-free tests and HTTP/SSE checks | Owning workers/coordinator report GREEN at their pinned compositions, including real jailed synthetic children and actual loopback transport checks. | Scripted/mock models, synthetic rendering and wire tests are distinct from browser/provider rehearsal. |
| Recorded M1 | Four recorded agents and recorded proof/fix progression, with real Miragio/MCP against replay. | Different support/40-contact example; no live snapshot capability or current-code fix test. |
| Full fresh UI rehearsal | **NOT RUN: user hold.** | No full UI-started fleet → automatic proof → cause → external fix → bad-fix rejection → clean useful verification → recovery acceptance. |

The engine's reported bounded attachment was PID 51886 on 8040 with an empty
owner list. UI HMR, compiled chat and Python imports had separate revisions.
Disk HEAD and an open port cannot prove what code those processes loaded.
No final shared-source runtime packet has been supplied for this draft.

Current production-lane tools are in-memory synthetic mail/calendar/CRM/invoice/PR
services. The source fleet seeds eight contacts and two clean events plus one
injected event. No real Gmail, Google Calendar or HubSpot delivery is accepted.
Coordinator reports configured Google credential/token paths absent, HubSpot and
`GITHUB_TOKEN` unset, and no hosting target. This worker did not read credentials.

## Reproduction route — NOT RUN

Start only after the user explicitly releases the rehearsal hold. Use the
[protected source startup](../START.md#protected-source-fleet-fresh-m2-synthetic-rehearsal)
on one owned, isolated live engine; do not use the recorded M1 launcher for this check.

Prerequisites: final merged source pinned on all surfaces; installed Python/uv and
Node dependencies; rebuilt chat; working Bedrock agent/gate/judge/chat models in
`us-east-1`; dedicated free ports; new absolute event DB, snapshot and token paths;
UI and chat/MCP targeting that same engine. Keep credentials server-side and retain
the real incident/snapshot for the external coding agent. Do not reset active proof
or run standalone CLI jobs concurrently against the same process-local job stores.

1. Record exact code/model/task/seed/poison and loaded runtime revisions, instance,
   epoch, owner IDs and state paths. Confirm direct engine and UI proxy agree.
2. In the signed-in live UI, click **Start demo** on that owned engine to launch
   `agents.run_demo_fleet`. Observe all four protected runs and truthful failures;
   a start response establishes a launch request, not four completed tasks.
3. Observe the malicious call frozen before its production effect while healthy
   agents continue. Observe snapshot persistence, automatic queued/running proof
   and three attempted replays without clicking initial Detonate.
4. Check the five gate outcomes in the table above with identifiable probes:
   normal, medium clean, medium harmful, medium inconclusive, and high/hard/escalation.
   Record actual callback/effect counts; medium clean may resume the original once,
   while the remaining contained cases must retain human recovery.
5. Inspect real effects/counts, blast radius and cause search. Inconclusive or
   interrupted evidence must stay explicit. Navigate Fleet/Incident/Miragio and
   reconnect; preserve baseline proof and reject stale epoch responses.
6. Hand the actual incident prompt to the user's external coding agent. Confirm
   it can access the named checkout and snapshot. Use the supplied command:
   `uv run python -m engine.cli detonate --incident <actual-id> --runs 3 --json`,
   with the handoff's exact `MIRAGE_SNAPSHOTS` and `MIRAGE_DB` paths.
7. Show a bad current-code fix failing, then a clean fix passing attack blocked
   3/3 and the entire useful legitimate task completed 3/3. Store actual outputs;
   no-op, policy weakening and partial-task fixes are not successful repair evidence.
8. Record the actual fix PR and human merge/restart decisions separately. Confirm
   queued stays queued until the protected owner starts. Exercise STOP and recovery;
   STOP must prevent new protected effects, and confirmed harm cannot auto-release.

The UI route, probes and expected observations above are a checklist for later
execution. This documentation task has executed none of them.

## Deferred limits

This is a laptop prototype. Job reservations and provider pacing are process-local;
already-started external effects cannot be cancelled instantly. Only wrapped tool
calls are observed. Broader authorization, cross-process control, real-service
adapters, hosting and public cloud-fixer access are deferred.
Deterministic task matching checks declared requirements; it does not establish
general semantic grounding or prose quality. No zero-bug claim is made.

## Provenance and documentation checks

Historical repair notes are retained in the
[closed, unmerged #137 draft ledger](https://github.com/GabDestal/Mirage/blob/c84a44d95aab8e16671fd755d3520fde6074a2d2/docs/UI_ENGINE_REPAIR_ACCEPTANCE_20261011.md).
Its source/reviewed heads and owning test summaries remain historical, not final
acceptance. The former audit source was `7c337214e1a92de08d905afc370d57a081831595`;
its removed checkouts are not active test targets. Portable local reports remain:
`/tmp/mirage-engine-audit-20261011.md`, `/tmp/mirage-agent-audit-20261011.md`,
`/tmp/mirage-provider-access-regenerated-20261011.json`, and
`/tmp/mirage-provider-usability-regenerated-20261011.json`.
The draft handoff at `/tmp/mirage-ui-engine-repair-draft-handoff-20261011.md`
predates closure of #137; current coordinator status supersedes its PR/worktree state.

[Demo provenance](DEMO_EVIDENCE.md), [M1 acceptance](DEMO_MILESTONE_1_ACCEPTANCE.md)
and the [connection plan](UI_ENGINE_CONNECTION_PLAN.md) retain their named scopes.
Final documentation validation will record Person A accuracy review, local links
and stable section anchors, every changed document's line count (maximum 299),
and whitespace/scope checks. No redundant code, runtime or provider reruns are planned.
