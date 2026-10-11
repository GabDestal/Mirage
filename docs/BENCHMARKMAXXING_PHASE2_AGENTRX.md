# AgentRx phase2: bounded native-derived NL development protocol

Status: offline protocol frozen and pushed, awaiting conceptual review and an explicit root provider lease. No provider calls have been made. This work serves incident root-cause explanation; it changes no Mirage runtime or contracts.

The adapter is an **adaptation, not a complete native AgentRx reproduction**. It reuses released IR conversion, schema literals, generic NL rubric definitions and external native grading at source `7a18c79708e7671be15124460f4f7296107c2a55`. No Azure client, new dependency, generated Python execution, native source modification or service is needed.

## Fixed comparison

Two already exposed development traces, Tau tasks 2 and 3, on environment model IDs `MEETING_ASSISTANT_MODEL_ID` (gpt-oss 20B) and `BEDROCK_AGENT_MODEL_ID` (Haiku 4.5). Each case/model has one simple diagnosis and one assisted diagnosis: **8 cells, at most 20 calls**. Each stage gets one call, no automatic provider retry and no rerun until pass.

| Arm / stage | Input | Maximum output tokens | Maximum constraints |
|---|---|---:|---:|
| Simple diagnosis | Complete trace, instruction, released policy/schema | 4096 | — |
| Assisted static generation | Released policy/schema only | 2048 | 4 |
| Assisted one-shot dynamic generation | Same complete information, native-derived IR, static constraints | 2048 | 4 |
| Assisted batched NL checker | Same complete information, generated constraints, generic native rubric definitions | 4096 | 8 checks |
| Assisted diagnosis | Same complete information plus cited constraint/checker evidence | 4096 | — |

Both final diagnoses use the exact existing `benchmarks.agentrx.SYSTEM_PROMPT` and model-specific `parameters()` values: temperature zero except Opus, and gpt-oss reasoning effort low. Both receive the same underlying complete trace/instruction/policy/schema without truncation. The assisted arm adds three model calls; **compute is not matched**. This protocol has no Opus cells: any conditional same-case Opus comparison requires a separately approved frozen extension and root lease.

Provider execution requires a lease naming the grant, exact frozen model/cases/arms/stages, total call cap, stage output caps and UTC deadline. Root owns the global 1 request/second budget. New inference stops by 09:40 UTC; hard freeze is 10:00 UTC. Reading environment model IDs is not a lease.

## Selection and annotation boundaries

Before inspecting any fresh annotation values, freeze the complete considered raw Tau/Magentic trace inventory and structural eligibility. Then extract only annotation record identifiers to record availability. Selected Tau 2/3 remain in the denominator even if a record or metric is missing; there are no replacement cases.

Families use conservative whole-domain groups. Every task variant in the same domain stays in one split; numeric-normalized instruction hashes are descriptive audit keys, never a reason to split related variants. Both supported domains were already exposed in phase1. **No fresh whole-domain held-out cohort remains.** This block is development re-evaluation and supports no held-out generalization claim. Flash is unsupported by this adapter; `magentic_dataset_whowhen` is a derived annotated variant collection and canonical raw Magentic traces are used instead. Every considered record retains its included/excluded/missing status and reason.

The model input boundary contains only released instruction, policy, tool schema, complete trace and derived IR/constraint evidence. Trace envelope labels, rewards, objectives and records are stripped by the existing message allowlist; actual tool content is preserved. Case IDs, filenames, source SHAs, annotation values and expected answers remain artifact/scorer metadata only. Generation and checker prompts contain no solution/example blocks. Native ground-truth-dependent judge templates and native generated invariants are not used.

## Native reuse and deviations

| Released component | Reuse / deviation |
|---|---|
| `trajectory_ir.py`: `tau_bench_ir`, `magentic_ir`, `validate_ir` | Unchanged AST-loaded functions, no Azure imports. The complete original trace also remains available, preserving native IR omissions of tool wrapper metadata. Synthetic trajectory ID is removed before model input. |
| `domain_registry.py` | Unchanged literal Tau/Magentic tool schemas, without domain examples. |
| Dynamic generator `RUBRIC_EVALUATION_ALGORITHM` | Reuse native CLEAR_FAIL/CLEAR_PASS/UNCLEAR definitions. Replace aggregation: UNCLEAR remains UNKNOWN; it never becomes PASS. |
| Static / one-shot dynamic generation | Explicit small NL-only prompts; native Python generation, iterative loops, solutions and example blocks are omitted. |
| Native checker | Disclosed single batched model checker, requiring a check per constraint and actual 1-based message citations. No 0-based `step_pos` citation mapping. |
| `analyze_metrics.py`: `normalize_category`, `load_ground_truth`; `judge.py`: `analysis` | Unchanged functions through existing `agentrx.score()`, external to model inputs. Critical-step and category scoring remain independent. |
| `benchmarks/report.py` | Reuse fixed-denominator reconciliation and missing-outcome bounds; phase1 adapter/report are byte-immutable. |

Every attempted stage saves exact prompts/hashes, raw provider response and model text, parameters, source/code SHA, calls, actual usage, input characters, latency, stop reason and explicit errors. Nonterminal/truncated responses, malformed JSON, missing/invalid citations and downstream skipped stages remain visible. Failed assistance does not silently fall back to simple diagnosis. Missing labels or predictions stay UNKNOWN per metric. Costs remain UNKNOWN because no reliable price was pinned.

Fixed denominators retain all eight cells. Report paired wins/losses/ties only on the same selected case/model; missing pairs are explicitly UNKNOWN. Bounds are missing-outcome bounds, not confidence intervals. Static trace diagnosis establishes no executable replay, counterfactual bisection, repair, recovery or frontier equivalence.

## Offline commands and evidence

Run from this worktree with the existing Python environment; no installation is needed:

```sh
python3 -m benchmarks.agentrx_phase2 self-check
/Users/liamszefner/Business/hacks/Mirage/.venv/bin/python -m benchmarks.agentrx_phase2 prepare --model-env MEETING_ASSISTANT_MODEL_ID --model-env BEDROCK_AGENT_MODEL_ID
python3 -m benchmarks.agentrx_phase2 verify
python3 -m benchmarks.agentrx_phase2 report
```

All new raw artifacts are under `/tmp/mirage-benchmaxing/run_1d89fe10e4c5/phase2/agentrx`: `selection-frozen.json`, `eligibility-ledger.json`, `phase1-immutable.json`, `manifest.json`, per-stage records, lease records, external native scores and `report.json`. Exact native function/schema/file and adapter/report/system hashes are frozen in the manifest. Phase1 original 215 selected / 75 attempted cells and their registry are preserved.

The frozen ledger contains 88 considered records (29 Tau and 59 Magentic): 87 are structurally eligible, one is unsupported, and 15 Magentic records lack an annotation record. Both selected development cases have annotation record identifiers; no annotation metric values were opened during selection. Tau 2 has 32 messages and Tau 3 has 34. The original adapter, report, result documents and 94 existing phase1 artifact files match the frozen hashes. [The separate phase2 report](BENCHMARKMAXXING_PHASE2_AGENTRX.json) currently retains all eight cells with zero attempts, UNKNOWN metrics and bounds [0,1].

Manifest SHA256: `ec2767dc2c5593c8487d6194c15a7c00de96ef0522993cdbd8e0d855a4f305a8`; implementation commit: `7f1d8e425b51142049b9a7d9a0d96991e21dffab`. Native parsing emits existing invalid-escape SyntaxWarnings; the focused checks pass without changing native source.

Synthetic self-checks exercise JSON parsing, strict constraint fields, complete checker coverage, all three evidence statuses, missing/duplicate/0-based/out-of-range/boolean citations, native 1-based IR, model-boundary leakage stripping with legitimate tool data preserved, hash rejection and fixed-denominator bounds. Provider behavior remains untested until an explicit lease is granted. PR166 stays unmerged against `benchmaxing`.
