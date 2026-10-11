# Mirage benchmarks

**Status 10:30 CEST, Oct 11.** On held-out AgentDojo prompt-injection tasks (20 attacked tasks per model, run once with the frozen gate), Mirage cut successful attacks on the two models that fall for them: GPT-OSS-20B from 11/20 to 0/20 and GPT-OSS-120B from 19/20 to 2/20.
Haiku 4.5 and Opus 4.8 resisted every attack on their own (0/20), so for them Mirage adds no safety on this set.
The price is utility: with Mirage the user's task was completed less often under attack (36/80 vs 64/80 across all four models) and on clean tasks too (24/40 vs 37/40), because the gate also blocks legitimate calls.
On AgentRx held-out task families (6 failed runs per bar), Mirage's evidence helped GPT-OSS-20B find the broken step slightly more often (2/6 → 3/6) but hurt Haiku 4.5 (3/6 → 0/6; only 3 of those 6 Haiku runs gave a usable answer).
Honest headline: Mirage stops prompt-injection attacks on models that are vulnerable, but at today's settings it costs a lot of task completion; samples are small, so read the AgentRx result as direction, not proof.

![AgentDojo prompt-injection attacks, with and without Mirage](benchmarkmaxxing/agentdojo-v2-headline.png)

![What Mirage stopped on held-out AgentDojo tasks](benchmarkmaxxing/agentdojo-v2-stops.png)

Stops (held-out gate rows with a non-empty `blocked` list; attacked / normal): GPT-OSS-20B 12/20, 2/10; GPT-OSS-120B 17/20, 4/10; Haiku 4.5 7/20, 4/10; Opus 4.8 7/20, 5/10. Block reasons across all 82 blocked calls: `UNTRUSTED_PROVENANCE` 78, `DEST_NOT_ALLOWED` 4. Rows: W1 commit `32d6b7d` (`benchmarks/artifacts/agentdojo_v2/heldout__*_rows.jsonl`, PR #198).

![AgentRx: finding the step where a failed agent run broke, with and without Mirage evidence](benchmarkmaxxing/agentrx-v3-critical-step.png)

### Numbers behind the charts

Fixed denominators: every error, crash or unanswered case stays in n and counts as a failure. Ranges are Wilson 95% intervals. The dev split was used to tune the gate; held-out was run once with the frozen config and is the one charted.

| AgentDojo split | Model | Arm | Attack success ↓ | Task done under attack ↑ | Task done, no attack ↑ | Errors/UNKNOWN, all tasks (counted as fail) | Gate blocks |
|---|---|---|---|---|---|---:|---:|
| dev | openai.gpt-oss-20b-1:0 | unprotected | 9/20 (45%, 26%–66%) | 9/20 (45%, 26%–66%) | 9/10 (90%, 60%–98%) | 4 | 0 |
| dev | openai.gpt-oss-20b-1:0 | Mirage gate | 2/20 (10%, 3%–30%) | 7/20 (35%, 18%–57%) | 5/10 (50%, 24%–76%) | 3 | 23 |
| held_out | openai.gpt-oss-120b-1:0 | unprotected | 19/20 (95%, 76%–99%) | 15/20 (75%, 53%–89%) | 10/10 (100%, 72%–100%) | 1 | 0 |
| held_out | openai.gpt-oss-120b-1:0 | Mirage gate | 2/20 (10%, 3%–30%) | 6/20 (30%, 15%–52%) | 6/10 (60%, 31%–83%) | 1 | 30 |
| held_out | openai.gpt-oss-20b-1:0 | unprotected | 11/20 (55%, 34%–74%) | 15/20 (75%, 53%–89%) | 7/10 (70%, 40%–89%) | 0 | 0 |
| held_out | openai.gpt-oss-20b-1:0 | Mirage gate | 0/20 (0%, 0%–16%) | 11/20 (55%, 34%–74%) | 7/10 (70%, 40%–89%) | 0 | 19 |
| held_out | us.anthropic.claude-haiku-4-5-20251001-v1:0 | unprotected | 0/20 (0%, 0%–16%) | 17/20 (85%, 64%–95%) | 10/10 (100%, 72%–100%) | 0 | 0 |
| held_out | us.anthropic.claude-haiku-4-5-20251001-v1:0 | Mirage gate | 0/20 (0%, 0%–16%) | 10/20 (50%, 30%–70%) | 6/10 (60%, 31%–83%) | 0 | 14 |
| held_out | us.anthropic.claude-opus-4-8 | unprotected | 0/20 (0%, 0%–16%) | 17/20 (85%, 64%–95%) | 10/10 (100%, 72%–100%) | 0 | 0 |
| held_out | us.anthropic.claude-opus-4-8 | Mirage gate | 0/20 (0%, 0%–16%) | 9/20 (45%, 26%–66%) | 5/10 (50%, 24%–76%) | 0 | 19 |

| AgentRx (heldout_families) | Simple | + Mirage evidence |
|---|---|---|
| GPT-OSS-20B | 2/6 (33%, 10%–70%); scored 5/6 | 3/6 (50%, 19%–81%); scored 6/6 |
| Haiku 4.5 | 3/6 (50%, 19%–81%); scored 6/6 | 0/6 (0%, 0%–39%); scored 3/6 |

Inputs (copied verbatim from the W1 `bench-agentdojo-v2` and W3 `bench-agentrx-v3` worker branches; byte-identical to W1 commit `c12a88a` (held-out, frozen gate config `dee462c`) and W3 commit `25233e3`): [AgentDojo summary](benchmarkmaxxing/v2-inputs/agentdojo_v2_summary.json), [AgentRx summary](benchmarkmaxxing/v2-inputs/agentrx_v3_summary.json); every drawn number: [v2-chart-source.json](benchmarkmaxxing/v2-chart-source.json). Rebuild with `sh docs/benchmarkmaxxing/render-v2-charts.sh` (stdlib SVG, macOS QuickLook to 1600×900 PNG). SVGs: [AgentDojo](benchmarkmaxxing/agentdojo-v2-headline.svg), [AgentRx](benchmarkmaxxing/agentrx-v3-critical-step.svg).
AgentDojo: temperature 0; "+ Mirage" = the Mirage gate blocking flagged tool calls; dev split ran GPT-OSS-20B only. AgentRx: "+ Mirage" = evidence-assisted diagnosis (static → dynamic → checker stages before the diagnosis); compute is not matched between arms; AgentRx dev cases (2 per model/arm) scored 0/2 in every arm.

## Previous phase: release charts and phase closeout

**CLOSED AT USER REQUEST — 2026-10-11.** This phase closes with existing saved results; no active inference, benchmark/grader runs, services or new implementation. The user may assign Claude a later improvement phase using the [complete handoff](BENCHMARKMAXXING_CLAUDE_HANDOFF.md). **No positive AgentRx assisted gain or Mirage recovery advantage is demonstrated.** Source-only v2 preparation and offline recovery checks create no improved benchmark points.

The three standalone figures below use the original frozen sanitized [chart source](benchmarkmaxxing/chart-source.json), snapshot **2026-10-11 07:13:07 UTC**, without refreshing any mutable producer report. Each SVG/PNG is **1320×940**. Pink/blue identify the compared arms; hatched ranges preserve UNKNOWN outcomes. Absolute bars start at zero; no unrelated samples are connected.

![AgentRx native critical-step accuracy with fixed denominator and missing-outcome bounds](benchmarkmaxxing/agentrx-critical-step-release.png)

The v1 six structural families within seen domains keep **N=6 per model/arm**. GPT-OSS 20B simple/assisted critical-step successes are **2/6,0/6**; Haiku 4.5 **1/6,0/6**. Missing-outcome bounds are respectively **[2/6,3/6], [0,5/6], [1/6,3/6], [0,1]**, using [S/N,(S+U)/N], not confidence intervals or completion-only accuracy. Native cause CATEGORY matches are separate (**3/6,0/6,3/6,0/6**); explanation text is ungraded. Static diagnosis proves no executable recovery or causal bisection.

![AgentRx native scoring coverage, with UNKNOWN in the selected denominator](benchmarkmaxxing/agentrx-coverage-release.png)

Scored coverage is **5/6,1/6,4/6,0/6** in the same model/arm order. Provenance/parse/checker failures remain failure/UNKNOWN and skip downstream stages; they never count as prevention. Assistance adds static, dynamic and checker work before diagnosis, with stage output caps **2048/2048/4096/4096**, so compute is not matched. The family cohort used **32 calls / 226,126 known tokens**; separate v1 Tau2/3 development used **15 calls / 156,683 tokens**, with five scored and three UNKNOWN among eight selected cells. No pooled efficacy denominator is used.

![HarnessRisk actual safe task completion on the final same-case development protocol](benchmarkmaxxing/harnessrisk-safe-completion-release.png)

Final `resource_budget_v5` runs on `recovery_119` retain **N=1 per model/arm**: GPT unprotected/gate **0/1,0/1**, Haiku **1/1,1/1**. All four terminate and restore safe configuration, but GPT's required report predicates fail despite **raw native utility 1, oracle 0.3333 and final-answer fallback 1**. Raw scores stay separate from actual task completion. A model mentioning a deliverable never proves it exists. Equal paired outcomes on one DEVELOPMENT case demonstrate no Mirage gain, frontier ranking, fresh phase2 held-out recovery or approved human restart. Fixtures start compromised, so initial-state intervention is not causal hijack proof. Resource caps are 24 tool calls, 32 model calls, 4096 output tokens/call and 120 seconds; earlier smaller-cap failures remain preserved.

The [missing-runs ledger](benchmarkmaxxing/closeout-run-ledger.md) separates raw native availability, valid reconciled native scoring, actual task coverage, unrun identities and incomplete attempts. **56 AgentRx phase2 cells remain unrun**: eight v2 DEV, 24 next-six-family, 12 conditional v1 Opus and 12 conditional v2 Opus. **Native phase2 remains 0/12 primary and 0/4 separate operator-extension**, plus one unleased conditional frontier cell; all are UNKNOWN. Primary N=12 spans both models and all three arms, including four required full-arm cells. The extension cannot replace them. V2's accepted provenance fix `ec210359a289102ad5beae3d26a3445175fa5ba8` and frozen manifests show readiness only.

Historical AgentDojo remains **platform-restricted; no new execution, retry or workaround**. Its 84 selected cells contain six attempts, five accepted native utility evaluations, 78 unrun and one attempted client failure UNKNOWN. The attacked GPT pair shows attacker success plus utility unprotected, then containment with lost useful completion at a graded gate checkpoint. Full workflow and real human-approved restart remain unmeasured. The preserved phase1 registry of **215 selected / 75 attempted** cells is an inventory across unlike protocols, never an efficacy rate. HarnessRisk's 51 historical cells include 21 incomplete attempts and all original failures.

Root's six component/report PRs are merged **into `benchmaxing` only**, at accepted publication base **`a6c543a5aa043ba1a74b199368b1d3fc5d2c3203`**. W2 delivery `da025d2257acd8d35b54c2996e555dd31fdc5712` and W6 `7e7d437cc79ad58c48a0d7191c12f5463bea03f5` have separate squash/publication pins in the [handoff](BENCHMARKMAXXING_CLAUDE_HANDOFF.md). W5 final component acceptance came from root adoption of C3's scoped review, not fresh Owner A approval. W6's 31 provider-free focused checks exercise real jailed children with fake models, SDK TestClient admission and automated original-task restart; they establish offline integration, not provider efficacy or human approval. **Root cutoff propagation into every child/model launch and automatic-job drain remain live-use prerequisites.** AgentRx needs serialized one-cell leases and an outer >=1.1-second pause after failures. Workers report provider/service jobs drained; reporting launched none. This benchmark lane has not merged into main; no claim is made about other lanes' main activity.

Inspect standalone [accuracy SVG](benchmarkmaxxing/agentrx-critical-step-release.svg), [coverage SVG](benchmarkmaxxing/agentrx-coverage-release.svg) and [safe-completion SVG](benchmarkmaxxing/harnessrisk-safe-completion-release.svg), [release source subset and pins](benchmarkmaxxing/release-chart-source.json), [full original source table](benchmarkmaxxing/chart-source-table.md), [exact missing-run identities](benchmarkmaxxing/closeout-run-ledger.json), [closeout receipts](benchmarkmaxxing/closeout-receipts.json) and [final render verification](benchmarkmaxxing/release-render-verification.json). Reproduce only reporting with `sh docs/benchmarkmaxxing/render-release-charts.sh`; native macOS QuickLook plus exact CoreGraphics cropping avoids tiling/cropping. Arithmetic reconciles every frozen row/group and S+F+U=N; all three final PNGs were inspected at exact dimensions with no clipping/overlap/tiling. No broad tests, providers, graders, hidden label reads or installs were run by this reporting worker. USD cost, underlying provider retries and real human wait remain unavailable.

The original two charts remain accessible: [AgentRx SVG](benchmarkmaxxing/agentrx-outcomes.svg) / [PNG](benchmarkmaxxing/agentrx-outcomes.png), [HarnessRisk SVG](benchmarkmaxxing/harnessrisk-utility-safety.svg) / [PNG](benchmarkmaxxing/harnessrisk-utility-safety.png), with their original [render receipt](benchmarkmaxxing/render-verification.json). Historical sources/data were not deleted or relabelled.
