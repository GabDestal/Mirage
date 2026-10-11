# UI and engine repair acceptance — 2026-10-11

**Status: draft; fresh composed acceptance pending.** Source inspected at
`35e5730428575e4e7e65311f9bdf127c6169f267` after rebasing the documentation draft;
it is the verified remote `origin/main` source. GitHub independently reports the twenty
PRs below merged, with the
listed squash commits. This documentation worker inspected source, merge metadata
and published worker reports; it ran no services, controls, providers or fleets.
Final coordinator source SHA and composed rehearsal evidence have not yet been
supplied. After the user regenerated the key, fresh six-model access and bounded
gate/judge usability checks succeeded, plus one actual browser no-tool chat turn.
Sections 5–6 preserve the earlier denials and the precise limits of this new evidence.

This ledger covers [PRODUCT.md](../PRODUCT.md) steps 0:00–2:40 and the Person A/B
ownership in [CONTRACTS.md](../CONTRACTS.md), using [docs/UX.md](UX.md) for human
actions. [Demo evidence](DEMO_EVIDENCE.md) and [M1 acceptance](DEMO_MILESTONE_1_ACCEPTANCE.md)
retain their historical scope. Recorded M1 is recorded engine evidence plus real
operator chat on its named compositions; it does not accept the current source fleet.
The original [connection plan](UI_ENGINE_CONNECTION_PLAN.md) sections 1+ remain
historical audit/future proposals; its section 0 links this current ledger.

**Current sprint scope (coordinator/user direction):** deliver the P1/P2 protected
demo with core containment, proof, state and integration. Existing P1–P6 and trusted
per-agent allowlists remain unchanged; the completion matcher verifies the task rather
than redefining policy. Known regressions that break this flow remain acceptance
dependencies. Broader authorization work, real-service adapters, deployment and
speculative epoch checks on control POSTs are deferred, not new sprint requirements
or a production roadmap.

## 1. Evidence boundaries

| Evidence | What it establishes | What remains separate |
|---|---|---|
| Source/merge inspection | Code and documentation present at a named Git SHA; GitHub merge state | Loaded process revision or working browser behavior |
| Worker offline/synthetic GREEN | Specified tests at that worker's tested head; scripted models, mocked transports or jailed synthetic children | Provider behavior, actual service integration or final composition |
| Coordinator composed local rehearsal | Only the source/runtime, flows, effects and browser observations actually reported | Repeatable provider reliability and deployed acceptance |
| Provider-live rehearsal | Actual model requests/results at the reported configuration | Google Calendar/Gmail/HubSpot integration when tools remain synthetic |
| Real-service/deployed acceptance | Team-owned service effects or named deployed URL, only when separately demonstrated | Neither is established by this draft |

The two portable audits pin `7c337214e1a92de08d905afc370d57a081831595`:
`/tmp/mirage-engine-audit-20261011.md` (140 passing offline tests plus reproduced
failure probes) and `/tmp/mirage-agent-audit-20261011.md` (8 agent and 9 public-protect
tests plus scripted/mock-transport probes). Their defects and green counts describe
that audited revision. Later repair tests below are attributed worker evidence,
not reruns by this documentation worker or proof of final provider acceptance.
Local `/tmp` artifacts are provenance pointers, not portable hosted evidence;
GitHub PR bodies preserve the published summaries.

## 2. Merged repair ledger

GitHub `state=MERGED`, `mergeCommit.oid`, `headRefOid` and local commit ancestry were
checked for every row. The tested/reviewed worker head differs from the squash SHA;
counts describe the worker's named suite/head and must not be added together.

| PR / owner | Repair and demo implication | Squash on main | Tested/reviewed worker head | Published RED → GREEN; evidence limit |
|---|---|---|---|---|
| [#121](https://github.com/GabDestal/Mirage/pull/121) / B | Overdue selector excludes already-reminded invoices; healthy companion/rerun | `acf02d8f5107c57339c446ff2caaf3349c8d22c2` | `1125ab3921f4e601e1cd8db1c465bdfde21f38a9` | 3 failed/3 passed → 14 agent tests passed. In-memory flags; new process/reset loses them; no atomic send/mark guarantee. |
| [#122](https://github.com/GabDestal/Mirage/pull/122) / B | Invoice/follow-up arguments expose exact recipient/content before gate; containment/effects | `adb97c6d480cf8fe21c863a28b537a84fbb8b58d` | `485d160acb63eb07ae0bcc77294d541b5758197e` | 16 failed/2 passed; missing-resource cases 3 failed → 35 agent tests passed. Scripted SDK callback evidence; no jailed/provider acceptance. Old recordings lack these payloads. |
| [#124](https://github.com/GabDestal/Mirage/pull/124) / A | Freeze authority before fallible persistence; no automatic proof without published snapshot | `43194031651a28c589ce21d24dd3a1ad9db6d778` | `1bffc1a6cd7a0104442341f68363964c5cff854b` | Original HTTP500/running/next-call-allowed probe; 16 regressions fail on parent → 16 focused and 126 engine tests pass. Real jailed synthetic recovery; storage failure can prevent durable diagnostics. |
| [#126](https://github.com/GabDestal/Mirage/pull/126) / A | Failed retry retains last proven stage; bisection replaces stale rows/cause | `fce6f75d9ba852d901b94bb5a8bed703ca6248b3` | `e4af681546e21ff44029ab2bcb15d2b7b1241575` | 13 failing assertions/4 already passing → 91 related cases; 21 focused after rebase. Temporary stores/scripted jobs; reservations stay process-local. |
| [#129](https://github.com/GabDestal/Mirage/pull/129) / B | Eval preserves harm before crash; pure full-inventory completion declarations | `63911d1f51eee7acfb74c0d293756dfa3a09a8f8` | `9ad5e00eb25f1a69a9fceeffbf9a6d367f7c9ddd` | 11 failed/3 passed → 88 agent tests; evaluator selftest passed. Fleet registration/engine matcher still separate; literal grounding is a minimum, not semantic task quality. |
| [#128](https://github.com/GabDestal/Mirage/pull/128) / B | Protected startup and honest recorded/source/historical evidence wording | `8d62b802bb75d54be8d1939f6040da5831cda04e` | `cb7973ea8789ed04199bbbb2429cb23ed4b6e0c2` | Docs checks: 36 links/anchors, 16 shell blocks syntax-only, scope/source checks. No implementation RED or fresh runtime acceptance claimed. |
| [#131](https://github.com/GabDestal/Mirage/pull/131) / A | One validated immutable API/gateway mode after dotenv; automatic proof scheduling | `8f8f81e8761eccd899d7c89c730030f9bc5a7add` | `c7c72945d8d32346940abb44199082411084038e` | 14 failed/2 passed plus original mode probes → 17 startup, 60 related, 179 repository tests pass. Synthetic outside-repo dotenv, provider construction forbidden. |
| [#123](https://github.com/GabDestal/Mirage/pull/123) / A | Leak-before-crash remains evidence; attempted denominator, completed-only task credit | `609e62ca9ab7c65d9023ae46458978b48236df00` | `6879b6d2d749004b03abbbfc6b9019f5db1939a1` | 8 failed/5 passed, then diagnostic and sanitization REDs → 27 tests pass. Real jailed synthetic P3 changes `1/0`, `-1/0` to `1/1`, `0/1`; no provider calls. |
| [#125](https://github.com/GabDestal/Mirage/pull/125) / B | Event-derived services, engine approvals, manual freeze/recovery, human queued restart | `e3eb805b0d0a4ac03643959dd60ea1759f31ea95` | `a38046727043e0a00a193b75ed27ba9556d7b48b` | Server-render RED: Freeze absent; review RED: manual recovery absent → live/demo selfchecks, existing UI checks, typecheck/build/lint pass. Stub fetch/rendering; browser acceptance separate. |
| [#127](https://github.com/GabDestal/Mirage/pull/127) / A | Shared normalized email/URL destinations and decoded payload checks in gate/verdict | `f129e7c02e20ff8d7aa7e22ff3434ca8f56d36dc` | `9065380f1969b6d68297fb020c1ba7274a258e1e` | 45 failed/41 passed plus review REDs → 284 tests, including 101 destination cases. Callback held before unsafe effects; unknown field semantics/tool-internal destinations and semantic P3/P6 remain limits. |
| [#133](https://github.com/GabDestal/Mirage/pull/133) / B | Shared process-local provider-turn cadence, individual overrides and sanitizer for all four factories | `e3a0d019d3b9c3f7b22deec91e8889cd5f4da654` | `6b68321bdbe3e4f9062073fa799bef2a7c6649a0` | 31 failed/7 passed initially → 43 model/config and 131 agent tests. Virtual-clock four-factory/12-turn check at 1-second intervals; no measured provider throughput. |
| [#134](https://github.com/GabDestal/Mirage/pull/134) / A | Layer-2 response validation, sanitized unavailability and shared outbound destinations | `e836fd4a797ec9fbe648f29164d7c4db37954b05` | `d8efa585118709b4f9a6afb4eb4f90fba8ff273c` | 80 failed/13 passed → 264 related tests. Mocks only; outage still intentionally allows after hard rules; semantic P3/P6 acceptance remains open. |
| [#136](https://github.com/GabDestal/Mirage/pull/136) / A | Crash-regression assertion follows sanitized diagnostics while retaining inconclusive-cause guards | `2e7f47c188a4aa1b6af3d94cf2293912521e344f` | `db0e74b53aaff2b18bf383688eca46e828d7bc06` | Exact regression 1 failed/1 passed → 2 passed; 53 focused and 530 full tests. Test-only alignment, no implementation or provider change. |
| [#135](https://github.com/GabDestal/Mirage/pull/135) / A | Integer counts1..10 before loading/scheduling/audit; default detonate/verify3, bisect2 | `47474ee22ec25e6b626092af0342722a7a0d7c41` | `1315ce523a3c43d8dcd03ab3f5e2880db9ba7ad6` | Real zero-child HTTP0/0 false pass; 52 failed/15 passed → 110 count cases and 640 full tests on #136 base. Jailed scripted children; no provider. |
| [#138](https://github.com/GabDestal/Mirage/pull/138) / B | Handoff explains required checkout/snapshot or connected deployment; unavailable/stale prompt actions disabled | `3d657d59840e1f644f0a08c5ff6455890bee2113` | `3662a09a76b4e3e2d7b57448692d66ca85b619be` | 4 RED failures → 10 live-mode and 10 recorded-demo selfchecks; existing controls/build/lint pass. Synthetic drawer/REST/clipboard/window checks; coordinator independently confirms both10-pass runs. No remote fixer or browser workflow acceptance. |
| [#139](https://github.com/GabDestal/Mirage/pull/139) / A | CLI loads shared config before capturing snapshot/store/token paths; same-snapshot fixer verification | `744af9c304e1eb813d0532520eaee1798d85c133` | `ea4c9d06d9ffc83d4a7ef0ff060a122d02602629` | 8 failed/22 passed → 171 related tests. Fresh processes with synthetic dotenv/provider construction forbidden; no actual credential file read or provider call. |
| [#140](https://github.com/GabDestal/Mirage/pull/140) / A with delegated B presentation | Shared `failed`/reason/completion/error/legit contract, snapshot error retention and truthful service/status projection | `d9c5f7744b1d742da03c9910427566ad9c5d0247` | `4e0c1ef2c6700874408483144e27e0bd06ccc8b8` | Synthetic completion/snapshot/service REDs → 74 focused, 668 full Python and 61 MCP tests; web checks and worker synthetic loopback Failed/reason/Healthy0 display. SDK callbacks, jailed typed errors and criteria matcher remain peer work. |
| [#142](https://github.com/GabDestal/Mirage/pull/142) / A | Successful current-tool effects face frozen, registered and rebuilt-factory policy; validated current-spec sidefile and typed unavailable/recorded-error callbacks | `738aa06007207d5d2c2f0f79c9dfd6b7c952400e` | `bc5a90909a7d28422a2d21584909f5d0a33b9b66` | Real-child P4 RED false passes for newly registered/factory attacker writes → 17 catalogue regressions, 29 related and 715 full tests pass. Missing/invalid SDK current metadata fails closed; automatic SDK publication still peer-owned. |
| [#144](https://github.com/GabDestal/Mirage/pull/144) / A | Human containment/STOP precedes fallible audit writes; release/lift persists before authority restored | `66c2bb4087f51d65fbf49ee61732d90de8dbba02` | `8a9326448fc923786eda867b2d516d98572de31c` | 14 failed/6 controls → 20 authority and 718 full tests. Actual protected SDK callback counts, slow-decision races and SQLite faults; original-call/result/startup binding remains separate. |
| [#145](https://github.com/GabDestal/Mirage/pull/145) / A | Validated immutable `0 <= review <= freeze threshold <= 1`; defaults0.4/0.7, bad values refuse startup | `35e5730428575e4e7e65311f9bdf127c6169f267` | `4d88faa06452dbdb9c4015af72d05805d0381cd7` | 9 RED nan/mutation failures including HTTP admission → 209 focused and 756 full passes. Synthetic startup/providers; valid score behavior and intentional outage ALLOW unchanged. |

### Published validation commands and report provenance

These are commands reported by the owning workers, **not executed here**. Python
workers reused the installed root interpreter, disabled dotenv/provider access and
used temporary stores or network-denying wrappers as described in their reports.
The concise commands identify suites; use the original report's environment when
reproducing. This ledger does not ask for a new suite or provider rerun.

| PR | Reported command / result | Existing local report |
|---|---|---|
| #121 | `env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 AWS_EC2_METADATA_DISABLED=true /Users/liamszefner/Business/hacks/Mirage/.venv/bin/python /tmp/mirage-reminder-eligibility-tests-20261011.py agents` → 14 passed | `/tmp/mirage-reminder-eligibility-report-20261011.md` |
| #122 | `PYTHON_DOTENV_DISABLED=1 AWS_EC2_METADATA_DISABLED=true uv run --frozen pytest -q agents` → 35 passed | PR body; SDK `MockTransport`/scripted evidence |
| #124 | `MIRAGE_MODE=live /Users/liamszefner/Business/hacks/Mirage/.venv/bin/python -m pytest tests/test_containment_persistence.py -q --tb=short` → 16 passed; `-m pytest tests -q --tb=short` → 126 passed | `/tmp/mirage-engine-audit-20261011/containment-report.md` |
| #126 | `PYTHON_DOTENV_DISABLED=1 /Users/liamszefner/Business/hacks/Mirage/.venv/bin/python -m pytest tests/test_proof_lifecycle.py tests/test_auto_detonation.py tests/test_bisect.py tests/test_verify.py tests/test_crash_safety.py tests/test_judge.py tests/test_replay.py tests/test_managed_replay.py tests/test_api.py tests/test_audit_and_restore.py tests/test_demo_control.py tests/test_resume.py tests/test_restart.py -q` → 91 passed | PR body |
| #129 | `env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 AWS_EC2_METADATA_DISABLED=true /Users/liamszefner/Business/hacks/Mirage/.venv/bin/python /tmp/mirage-scoring-offline-20261011.py agents` → 88 passed | `/tmp/mirage-scoring-completion-report-20261011.md` |
| #131 | Report gives 17 startup/60 related/179 full passes but does not publish an exact invocation; do not infer it. Relevant suite: `tests/test_startup_mode.py`. | `/tmp/mirage-engine-startup-mode-report.md` |
| #123 | `PYTHON_DOTENV_DISABLED=1 /Users/liamszefner/Business/hacks/Mirage/.venv/bin/python -m pytest tests/test_crash_safety.py tests/test_sandbox_accounting.py tests/test_sandbox.py tests/test_verify.py tests/test_bisect.py -q` → 27 passed | `/tmp/mirage-engine-proof-accounting-report.md` |
| #125 | From `web/`: `node tests/human-controls-selfcheck.mjs`, same with `--demo`, `npm run typecheck`, `npm run build`, `npm run lint` → passed (existing lint/chunk warnings) | PR body |
| #127 | `uv run pytest -q` → 284 passed; `uv run ruff check engine/detection/rules.py tests/test_destination_rules.py` → passed | PR body |
| #133 | `env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 AWS_EC2_METADATA_DISABLED=true PYTHONPATH=/Users/liamszefner/orca/workspaces/Mirage/fix-fleet-model-cadence:/Users/liamszefner/orca/workspaces/Mirage/fix-fleet-model-cadence/sdk /Users/liamszefner/Business/hacks/Mirage/.venv/bin/python /tmp/mirage-model-cadence-tests-20261011.py` → 131 passed | `/tmp/mirage-model-cadence-report-20261011.md` |
| #134 | `/Users/liamszefner/Business/hacks/Mirage/.venv/bin/python -m pytest tests/test_decision_response_validation.py tests/test_layer2.py tests/test_judge.py tests/test_destination_rules.py tests/test_startup_mode.py tests/test_containment_persistence.py tests/test_gate.py tests/test_api.py -q --tb=short` → 264 passed | `/tmp/mirage-decision-response-report.md` |
| #136 | PR reports `test_crashed_bisection_cannot_prove_a_cause` (2 passed), 53 focused and 530 full passes; exact command not published in its body, so not inferred. | PR body; test-only scope |
| #135 | `/Users/liamszefner/Business/hacks/Mirage/.venv/bin/python -m pytest -q --tb=short` → 640 passed on exact `2e7f47c188a4aa1b6af3d94cf2293912521e344f` plus owned count commits | `/tmp/mirage-positive-proof-counts-20261011.md` |
| #138 | From `web/`: `node tests/handoff-ui-selfcheck.mjs` and `node tests/handoff-ui-selfcheck.mjs --demo` → 10 passed each; independent coordinator reruns also10 each | PR body and coordinator report |
| #139 | PR reports 171 startup/count/handoff/verify/sandbox/bisect passes; exact invocation not published, so not inferred. New suite: `tests/test_cli_startup_mode.py`. | PR body |
| #140 | `uv run pytest -q` → 668 passed; MCP build/tests61 and web typecheck/build/existing presentation checks passed | PR body; shared models/fixtures/CONTRACTS/generated schema shipped together |
| #142 | PR reports 17 current-catalogue, 29 catalogue/accounting and 715 full root-venv passes; exact invocation not supplied, so not inferred. New suite: `tests/test_current_catalogue_verification.py`. | PR body; real jailed synthetic children, no provider |
| #144 | Reported root `.venv` with `PYTHON_DOTENV_DISABLED=1 MIRAGE_MODE=live`: 20 `tests/test_authority_boundaries.py` cases and 718 full passes; exact invocation not supplied, so not inferred. | PR body; fault/race/actual-SDK synthetic checks |
| #145 | RED: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/test_gate_threshold_configuration.py -k 'nan or mutation' --tb=short` → 9 failed. GREEN: same environment/interpreter with `-m pytest -q tests/test_gate_threshold_configuration.py tests/test_decision_response_validation.py tests/test_layer2.py tests/test_startup_mode.py tests/test_cli_startup_mode.py` → 209 passed; full suite756. | PR body; fresh synthetic dotenv, provider construction forbidden |

## 3. U1–U5 delivery and open dependencies

| Slice | Current delivery evidence | Acceptance still pending |
|---|---|---|
| U1 — SDK error truth and protected fleet | Shared contract #140 and engine callback/current-policy #142 merged. [#141](https://github.com/GabDestal/Mirage/pull/141) draft at `4fb80d8044407cda05ed30b6a2f57ad608d7ae18`, tested on shared head `4e0c1ef2c6700874408483144e27e0bd06ccc8b8`: 14 initial RED failures/2 normal controls → 50 parent SDK tests pass; pinned jailed error replay was RED before #142. New rebase/test target is `738aa060`. | Final SDK/error-replay GREEN/merge, current metadata publication, fleet factory/start failure surfacing and trusted per-story registration; composed UI evidence. |
| U2 — services and human controls | #125 merged; actual reason/body hooks and encoded REST paths tested with stub fetch/rendering. | Browser-visible service isolation, approval vs chat approval, manual Freeze→Unfreeze/Kill, restored ownership refusal, queued restart, STOP/recovery and no repeated effects. |
| U3 — stream recovery | [#130](https://github.com/GabDestal/Mirage/pull/130) draft at `116258461d6858543ea4c5d888e53dd2ed36690e` on unmerged engine `59dce1b9c755cc6698312eeec3f46001aee4cc78`; latest 8 regression REDs → 24 stream selfchecks. Worker reports 14 actual loopback HTTP/SSE assertion groups through current frontend parsers; 74 related engine tests, typecheck/build/launcher/lint pass. | Runtime contract merge and own-only replay onto exact main; fresh engine8040/UI5180/chat8041 browser recovery/ownership acceptance. Provider-free wire checks are not browser acceptance. |
| U4 — persistent proof | [#132](https://github.com/GabDestal/Mirage/pull/132) draft at `ac50da1198840c1dd7e095c131317d82b9f508df`, consuming optional job contract from `59dce1b9c755cc6698312eeec3f46001aee4cc78`; typed detail/restoration and zero-request live/recorded renders reported green. Shared newest-production-run selector uses timestamp/ID ordering. | Shared job contract merge and final own-only replay; navigate Chat/Fleet/Incident on the composed runtime without a model turn and keep baseline distinct from bisection/verification. Synthetic renders are not browser8040 acceptance. |
| U5 — documentation acceptance | [Draft #137](https://github.com/GabDestal/Mirage/pull/137), these three documentation files; README updated for #133. | Final known source SHA and coordinator rehearsal artifacts, final link/syntax/scope checks, pushed matching PR head. Documentation readiness will not close missing runtime gates. |

Person A's exact legitimate-task matcher, alternate-read fidelity and
runtime/ownership/job metadata remain separate dependencies at the inspected source.
#142 repairs current-tool policy and typed recorded errors on the engine side; #140
supplies the execution-truth contract/projections. SDK/fleet delivery is still open.
[Metadata #143](https://github.com/GabDestal/Mirage/pull/143) is draft at GitHub head
`efa0ef847305ec14a6e176a1fa8e15ddb7d2e683`, stacked on #141: meaningful initial23
RED failures/2 compatibility passes, 25 metadata tests green and 76 SDK passes/1
inherited jailed failure at that composition. Final exact target/rebase and complete
GREEN are pending. #129 supplies pure criteria,
not completed engine/fleet wiring. #133 supplies process-local pacing, not a shared
fleet/gateway/chat/subprocess provider budget. Final PR status must be refreshed before
accepting the composed tree; an open PR or another branch's GREEN is not merged code.

U3 wire provenance: `/tmp/mirage-pr130-runtime-http-results.json` pins the frontend
and engine heads above and records live/replay temporary children with providers
disabled. Current frontend readers consumed actual `/runtime`, `/events` and SSE:
runtime precedes business events, event responses bind their epoch atomically,
reset/reconnect accept lower sequence numbers, and restored history has a new process
identity with no live owners. It reports isolated ephemeral loopback ports, no user
port changes, temporary data deleted and owned processes stopped. There was no
browser, provider/model call or tool execution. Exact HTTP harness command is not
supplied. PR #130 publishes `uv run pytest -q tests/test_runtime_metadata.py
tests/test_demo_control.py tests/test_managed_replay.py tests/test_replay.py
tests/test_services.py tests/test_execution_truth.py` → 74 passed at that stacked
composition; this worker has not rerun it. At 01:48 UTC the coordinator independently
ran `node tests/stream.test.mjs` from the PR #130 worktree's `web/` on exact
`116258461d6858543ea4c5d888e53dd2ed36690e`: 24 passed, 0 failed. This is the tracked
test filename; it accepts neither final main nor a browser workflow.

### Engine invariant and architecture ledger — reserved for Person A

Person A will supply the precise source-pinned engine invariants, findings-to-repair
mapping and exact validation evidence for this section, including remaining provider
and deployment gates. Content is pending; the repair rows above retain their narrower
published scope. Coordinator reports independent78 engine/API/services checks for
#140 and independent160 checks for #139, but exact commands have not been supplied
and are not inferred.

A separately owned provider-free acceptance harness is planned with explicitly
scripted two healthy meeting probes plus one poison probe and causal removal driven
by actual tool responses. It changes neither the normal fleet nor startup. No harness
source/runtime acceptance is yet supplied, and scripted probes will remain synthetic
evidence rather than source-fleet provider proof.

**Additional authority gate (coordinator report, 2026-10-11):** a separate actual-SDK
audit produced 17 RED failures around approval of the original call releasing a
concurrent unchecked call, stale approval/manual freeze, STOP/recovery and result
binding. #144 subsequently fixes fail-closed audit ordering and stale approval after
a failed kill; original-call approval/result identity and run-start/recovery binding
remain peer-owned. Its report explicitly leaves cross-process cancellation and the
SDK ALLOW-to-callback admission window open, and permits already-admitted callbacks
to finish/acknowledge their original result after STOP. Exact original audited
source/report and final remaining-repair evidence are pending; #125 UI controls
alone do not establish approval/recovery authority acceptance.

## 4. Runtime and source identity

| Detail | Current fact / coordinator-owned evidence slot |
|---|---|
| Final composed source | Pending coordinator's known full SHA; draft inspection source is `35e5730428575e4e7e65311f9bdf127c6169f267` |
| Engine | Planned owned loopback `http://127.0.0.1:8040`, Person A; coordinator reports not yet running. Started PID/time/loaded revision/mode/instance/epoch/owned runs pending. |
| Web/proxy | Coordinator reports main UI `http://127.0.0.1:5180`, PID84720, terminal `term_146a8a2b-1ee2-4b95-9d64-9c0bab73eaa1`, source at startup `e3a0d019`; configured `/api`→8040, `/chat`→8041. Read parity/loaded final source pending. |
| Chat/MCP | Coordinator restarted owned `http://127.0.0.1:8041` after main `d9c5f774` build, Node PID68595, same terminal `term_55913927-9c65-4fd4-8984-b9dc1b19ceba`, fresh main configuration selected over inherited bearer/model values. Native-browser no-tool turn through5180/chat8041/Bedrock succeeded; engine8040/MCP actions untested. Earlier PID86841/denial is historical. |
| State isolation | New absolute DB/snapshot/token paths and scheduler identity pending coordinator evidence; a different port alone is insufficient |
| Existing session | User engine8000/UI5173/chat8001 remain untouched and are not acceptance test targets |
| Victim/companions | Four protected source agents: meeting assistant, invoicing, outreach, PR reviewer; coordinator's access probe reports meeting GPT-OSS and shared companion Haiku IDs below, with companion overrides unset. Final fleet user/task/day/seed/poison and request/effect/error evidence pending. |
| Model configuration in source | Individual override→`BEDROCK_AGENT_MODEL_ID`→`BEDROCK_MODEL_ID`; blank overrides fall through; temperature0, region `us-east-1`, all factories use existing sanitizer |
| Cadence | One `InMemoryRateLimiter` per Python process, 1 provider model turn/second, capacity1; recorded replies bypass calls. No cross-process or internal-retry guarantee. |
| Tool backend | Source fleet uses process-local in-memory synthetic mail/calendar/CRM/invoice/PR tools. Eight shared contacts, two clean events plus V2 forged-system invite. No actual Gmail/Calendar/HubSpot on these paths. |

Pin running processes separately from disk HEAD. A changed checkout or refreshed browser
does not activate a new Python import or rebuild a running chat bundle. Runtime metadata
must report the loaded source; compare direct engine, Vite proxy and chat/MCP targets
against that same instance/epoch. Provider readiness requires actual requests, not an
open port or configured model name. This worker performs none of those operations.

Pinned source: [model limiter/fallback][source-model], [four protected factories/startup][source-fleet],
[agent completion declarations][source-completion], [shared synthetic services][source-services],
[current-code verifier][source-verifier], [handoff][source-handoff], [handoff drawer][source-handoff-ui], [CLI][source-cli].

## 5. Browser and incident workflow ledger

Incident workflows await coordinator evidence on the final composed source. The
separate bounded browser-chat result is accepted only on its reported earlier build.
Record observed counts/errors; never replace partial evidence with expected `3/3`.

| Demo / workflow | Observable acceptance | Current result |
|---|---|---|
| Fleet/startup (0:00) | Protected SDK runs on the identified engine; actual task inventory and outcomes, failures visible; services explicitly synthetic/event-derived | Native browser shows honest disconnected Fleet/502 while engine is absent; protected-fleet acceptance pending, no invocation by this worker |
| Containment (0:30) | Offending tool held before its outbound effect, one run frozen while companions continue; exact incident/snapshot; automatic three-run queue without UI Detonate | Pending composed/provider evidence; #124/#131 offline tests only |
| Proof (1:20) | Three jailed attempts, consistent attempted/completed/error/harm counts and deterministic verdict; Production blocked vs Mirage captured effects; no real tools in child | Pending; from-freeze recorded replies prove consequences, not three fresh injection successes |
| Cause | Human Find the cause runs from scratch with removed input; report observed ratios and no cause if interrupted/inconclusive | Pending; #126 synthetic retry/folding evidence only |
| Persistent views | Chat opens after automatic job and reads existing proof without model turn; Fleet/Incident navigation and reconnect preserve baseline; removed-input/verify effects identified separately | Pending U3/U4 composition/browser |
| Failure/retry | Job failure preserves prior proof, leaves production contained, shows sanitized category and explicit retry; missing snapshot/read/tool error cannot become success | Pending; partial repairs merged, remaining fidelity/shared contracts open |
| Human controls | Reason/actor logged for manual freeze/unfreeze/kill, engine approve/reject and STOP/recovery; confirmed compromise refused; restored owner409 honest; no automatic POST retry | Pending browser/engine composition; #125 synthetic hooks/render checks only |
| External handoff (2:00) | Human opens/copies incident report to their external coding agent; same snapshot reachable through local checkout/state or connected deployment; untrusted inputs fenced; tokens excluded from chat/model cards | #138 synthetic/coordinator selfchecks accept truthful drawer wording and prompt readiness; actual external handoff/access remains pending. Mirage does not write or internally generate the repair. |
| Failed fix rejected | External agent's changed current code tested from scratch against same snapshot, freeze/current policy and full legitimate task; bad/no-op/permission-loosening/partial-task fix fails | Pending current-code verification; recorded fixture fix is an example only |
| Clean fix passes | Positive requested runs all finish, attack blocked n/n and entire legitimate task completed n/n; exact user/content/entity inventory, useful brief, no duplicate/forbidden work | Pending engine matcher/fleet wiring and fresh rehearsal; a sent email or completed card is insufficient |
| PR/restart (2:40) | External coding agent opens actual fix PR; human review/merge and explicit clean-restart decision separately recorded; queued stays pending until owner starts | Pending actual product decisions; this docs PR is not an incident fix PR |
| False positive | Clean held action replay shows no harm with completed task; human unfreezes the held call; resumed task completes | Pending fresh scenario, distinct from merely lifting STOP |
| Reconnect/reset/restore | GET-only recovery, epoch/instance match, stale responses excluded; authorized reset cannot erase active proof; restored history does not imply live locks/tokens | Pending final runtime/transport composition and browser evidence |
| Browser operator-chat connection | Actual signed-in browser sends harmless no-tool turn through Vite/chat to real Bedrock; rendered response visible | Accepted at reported chat build `d9c5f774`, PID68595; native Dia AX and screenshot reported. No engine action, tool card, model retry or incident proof. |

Current CLI semantics at the inspected source: the product shorthand `mirage detonate`
is executed as `uv run python -m engine.cli detonate --incident <id> --runs 3 --json`
(root packaging has no installed console-script entrypoint). This defaults to
current-code verification from scratch; `--from-freeze` is the operator consequence
replay. Exit0 requires `passed`; both attack-blocked and legitimate-task n/n are required.
Counts now accept integers1..10 only, with default detonate/verify3 and bisect2, before
loading or scheduling. #142 enforces current-factory policy on the engine side;
automatic SDK metadata and the exact legitimate-task matcher remain pending, so the
interface alone does not establish verified fixes. Use the actual live incident snapshot; the recorded
M1 handoff has no executable snapshot/token and its PR URL is a placeholder.

The current live handoff supplies incident context and local verification paths.
Opening a Claude Code/Codex link does not transfer the checkout/snapshot or connect
Mirage; a copied prompt alone does not grant reachable sandbox access. #138 explains
that requirement, keeps the prompt read-only, and disables unavailable, blank or
error-stale prompt actions. A backend incident token is not proof of deployed access.
Human PR review/merge and clean-restart approval remain explicit product decisions.

#139 now resolves CLI configuration before snapshot/event/token paths are imported;
its fresh-process synthetic probes verify shell precedence, outside-repository dotenv
and invalid-mode refusal without importing the API. #140 provides optional completion
errors, failed status/reason, opaque per-story declarations and retained snapshot error
markers. #142 supplies typed engine error callbacks/current-spec validation, but
final SDK composition is still pending; the earlier jailed RED is not claimed as
revalidated. The earlier parent SDK GREEN deliberately excludes
`sdk/tests/test_detonation.py` and `sdk/tests/test_error_detonation.py`:
`python -m pytest sdk/tests --ignore=sdk/tests/test_detonation.py --ignore=sdk/tests/test_error_detonation.py -p no:cacheprovider --basetemp=/tmp/mirage-sdk-error-parent-green -q`
→ 50 passed in the credential-free environment described by
`/tmp/mirage-sdk-error-truth-20261011.md`.

**Coordinator browser report, 01:11 UTC:** Orca tab handles repeatedly disappeared;
fallback native Dia at `127.0.0.1:5180` reached the dashboard through normal demo
sign-in. Accessibility state exposed the chat turn “What is happening across my
agents?” and a public error that Bedrock denied access to the configured chat model
in `us-east-1`. This is a browser-observed failed chat/provider attempted gate, with
no successful provider/tool completion or incident proof. A ScreenCaptureKit error
followed sign-in, but subsequent accessibility state verified navigation; no screenshot
proof was supplied for this earlier failed capture. Engine8040 was still not started. The observation does not identify
an expired key or establish that other model roles are unavailable.

**Coordinator browser report, 01:16 UTC:** native Dia `/fleet` accessibility state
showed “Can't reach the Mirage engine”, “502 Bad Gateway” and “Try again” while
engine8040 remained absent. This accepts visibility of the disconnected Fleet state
only: no fake agent cards or model retry were observed, and no live attachment,
containment or provider proof is established.

**Coordinator browser report, 01:29 UTC:** owned chat8041 was rebuilt/restarted from
main `d9c5f774` with explicitly selected fresh main configuration; Node PID68595
replaces86841 in the same terminal. A new native Dia tab at `127.0.0.1:5180`, preserving
the user's GitHub tab, completed normal sign-in. Prompt “Reply only: Chat connection
verified. Do not call tools” rendered “Chat connection verified.” Accessibility and
screenshot capture succeeded and were reported in the coordinator conversation;
no portable screenshot path was supplied here. This accepts one real
browser5180→chat8041→Bedrock no-tool turn. There were no tool cards, engine actions or
retries, and engine8040 remained absent. It accepts the chat connection, not fleet,
containment, replay or full MCP/incident workflows.

## 6. Open provider, service and deployment gates

**Coordinator provider-access report, 01:19 UTC:** Person A ran one sequential
no-tool “Reply OK” request per distinct configured model, in `us-east-1`, with at
least1.1s between attempts and retries0. `/tmp/mirage-provider-access-20261011.json`
contains the sanitized configured IDs and categories below; this documentation worker
read that report and made no requests. All six attempts returned `AccessDeniedException`,
with zero nonempty responses. Unset companion overrides were reported without extra
attempts. Exact probe command and code SHA are not supplied; this is access evidence
for the reported configuration, not a protected-fleet or final-composition rehearsal.

| Configured role/key | Reported model ID | Earlier access | Fresh regenerated-key access |
|---|---|---|---|
| Shared companions / `BEDROCK_AGENT_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `AccessDeniedException` | HTTP200, nonempty |
| Fallback / `BEDROCK_MODEL_ID` | `us.openai.gpt-5.6-sol` | `AccessDeniedException` | HTTP200, nonempty |
| Victim / `MEETING_ASSISTANT_MODEL_ID` | `openai.gpt-oss-20b-1:0` | `AccessDeniedException` | HTTP200, nonempty |
| Gate / `BEDROCK_GATE_MODEL_ID` | `openai.gpt-oss-safeguard-20b` | `AccessDeniedException` | HTTP200; no nonempty text in32-token access probe |
| Judge / `BEDROCK_JUDGE_MODEL_ID` | `openai.gpt-oss-safeguard-120b` | `AccessDeniedException` | HTTP200; no nonempty text in32-token access probe |
| Chat / `BEDROCK_CHAT_MODEL_ID` | `us.anthropic.claude-opus-4-8` | `AccessDeniedException` | HTTP200, nonempty |

`INVOICING_MODEL_ID`, `OUTREACH_MODEL_ID` and `PR_REVIEWER_MODEL_ID` are unset in
that reported configuration, so source factory fallback selects the shared agent ID.
These failures do not establish credential expiry, invalid IDs, availability of
unconfigured models, or a root cause.

**Credential-state change, coordinator report at 01:25 UTC:** the user regenerated
the main server key. Person A owns the fresh no-tool window, using the explicitly
selected main configuration rather than a stale inherited token, with at least1.1s
pacing and retries0. The six denials remain real earlier evidence and do not prove
that expiry caused them.

**Fresh access/usability report, 01:29 UTC:**
`/tmp/mirage-provider-access-regenerated-20261011.json` records HTTP200 for all six
same configured IDs, nonempty agent/fallback/victim/chat responses and no nonempty
gate/judge text within the access-only32-token budget. HTTP200 alone is not successful
classification proof. The separate
`/tmp/mirage-provider-usability-regenerated-20261011.json`, pinned to
`d9c5f7744b1d742da03c9910427566ad9c5d0247`, reports isolated direct provider calls
with synthetic inputs and no tool execution: existing gate classification returned
`violates=true`, P5, `p=0.99`, nonempty reason; judge parsed P1/P2/P5 and a nonempty
summary. This clears the reported credential/model access gate and establishes one
bounded gate/judge usability case, not semantic detection performance, a deterministic
incident verdict, or a protected-fleet rehearsal. Exact probe commands are not supplied.
Person A owns those probes; this worker made none. Person B's sole fresh provider
acceptance is the harmless browser chat turn above. No successful live-model incident,
source-fleet task, snapshot, replay or fix verification has been demonstrated here.

Coordinator-supplied sanitized integration configuration: Google configured
credential/token paths are absent; HubSpot token is unset; no deployment URL/target
is configured. This worker has not read/copied `.env`, credentials, raw provider
payloads or incident capabilities.

Even a successful Bedrock fleet/UI rehearsal with these tools would establish a
**local live-model synthetic-service** flow. Actual team-owned Gmail/Calendar/HubSpot
adapters, synthetic seed and safe service effects require separate evidence before the
real-service product claim. A cloud coding agent additionally needs reachable,
incident-scoped sandbox access; local CLI availability is not deployed acceptance.
Historical metrics, selected N=4 eval results and M1 recordings remain unchanged.

## 7. Documentation delivery checks

Draft validation command: `python3 /tmp/mirage-ui-engine-repair-docs-check.py` →
24 local links/anchors, 8 pinned source objects, 20 squash ancestors and 5 shell blocks
(`zsh -n`, syntax only) passed. Exact three-file scope and byte-identical connection-plan
sections 1+ passed; `git diff --check` passed. GitHub PR metadata was fetched, but no
broader external-link crawl or code/provider test rerun was performed.

Final source/evidence refresh, documentation recheck, clean checkout and matching
remote/PR head remain pending. No implementation/config/schema edits, new repository
tests, service restarts, control POSTs, provider calls, credentials or deployments
belong to this task.

[source-model]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/agents/common/model.py
[source-fleet]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/agents/run_demo_fleet.py
[source-completion]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/agents/common/completion.py
[source-services]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/agents/services/__init__.py
[source-verifier]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/engine/detonation/sandbox.py
[source-handoff]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/engine/handoff.py
[source-cli]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/engine/cli.py
[source-handoff-ui]: https://github.com/GabDestal/Mirage/blob/35e5730428575e4e7e65311f9bdf127c6169f267/web/src/components/handoff-drawer.tsx
