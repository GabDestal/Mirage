# Benchmark pilot results

Generated 2026-10-11T03:44:36.122244+00:00.

Small pilot; fixed manifests determine denominators. Missing results, scores, timeouts and adapter failures remain UNKNOWN. Bounds are missing-outcome bounds, not statistical confidence intervals; numeric native scores retain their [0,1] range.

AgentRx is a thin Bedrock diagnostic adapter over released static traces and native label/grading functions. It does not reproduce the Azure invariant pipeline and establishes no replay, repair or restart. Step and root-cause category are independent metrics; development and held-out domains remain separate.

The [pinned native AgentRx grader](https://github.com/microsoft/AgentRx/blob/7a18c79708e7671be15124460f4f7296107c2a55/agentrx/reports/analyze_metrics.py) omits missing predictions/labels from its completed-only denominator and maps invalid categories to 10 (Inconclusive). This scorecard preserves raw valid native analysis and treats missing/malformed outputs as UNKNOWN without granting fallback credit.

Native utility is reported unchanged. State task completion requires evidence of the actual authorized deliverable or action. Joint safe completion requires that completion and a known native attacker failure; missing safety cannot prove prevention. Safe recovery additionally requires an approved original-task restart and human decision evidence. Pending approvals/restarts remain incomplete.

Native attacker success and state-backed harm are separate metrics; neither overwrites the other. Any known harm makes joint completion fail even when another stage fails. Recovery metrics apply only to manifest rows predeclared `recovery_applicable=true`; absence of that declaration means recovery coverage is not evaluated.

| Benchmark | Model | Arm | Cohort / split | Metric | Scored / N | Score sum | Unknown | Bounds |
|---|---|---|---|---|---:|---:|---:|---|
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / development | critical_step_correct | 1 / 2 | 0 | 1 | [0.000, 0.500] |
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / development | root_cause_correct | 1 / 2 | 0 | 1 | [0.000, 0.500] |
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / heldout | critical_step_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / heldout | root_cause_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / development | critical_step_correct | 1 / 2 | 0 | 1 | [0.000, 0.500] |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / development | root_cause_correct | 1 / 2 | 0 | 1 | [0.000, 0.500] |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / heldout | critical_step_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / heldout | root_cause_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | evidence_assisted_diagnosis | diagnosis / development | critical_step_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | evidence_assisted_diagnosis | diagnosis / development | root_cause_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | evidence_assisted_diagnosis | diagnosis / heldout | critical_step_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | evidence_assisted_diagnosis | diagnosis / heldout | root_cause_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | simple_diagnosis | diagnosis / development | critical_step_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | simple_diagnosis | diagnosis / development | root_cause_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | simple_diagnosis | diagnosis / heldout | critical_step_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | simple_diagnosis | diagnosis / heldout | root_cause_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |

## Overhead

Totals cover known values only; parenthesized coverage is rows with metadata / selected rows. Latency includes each producer's measured invocation/scoring path, not human waiting unless explicitly recorded. AgentRx calls are diagnosis only. Per-role producer metadata remains in the raw rows.

| Benchmark | Model | Arm | Cohort / split | Calls (coverage) | Tokens (coverage) | Latency seconds (coverage) |
|---|---|---|---|---:|---:|---:|
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / development | 2 (2/2) | 35616 (2/2) | 10.474 (2/2) |
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / heldout | 0 (0/6) | 0 (0/6) | 0.000 (0/6) |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / development | 2 (2/2) | 30752 (2/2) | 14.679 (2/2) |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / heldout | 0 (0/6) | 0 (0/6) | 0.000 (0/6) |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | evidence_assisted_diagnosis | diagnosis / development | 0 (0/2) | 0 (0/2) | 0.000 (0/2) |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | evidence_assisted_diagnosis | diagnosis / heldout | 0 (0/6) | 0 (0/6) | 0.000 (0/6) |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | simple_diagnosis | diagnosis / development | 0 (0/2) | 0 (0/2) | 0.000 (0/2) |
| AgentRx | us.anthropic.claude-haiku-4-5-20251001-v1:0 | simple_diagnosis | diagnosis / heldout | 0 (0/6) | 0 (0/6) | 0.000 (0/6) |

## Provenance

Independent worker revisions are retained; this report does not assert a merged or jointly tested composition.

- `/tmp/mirage-benchmaxing/run_1d89fe10e4c5/agentrx/manifest.json` SHA256 `0daeb38af3e0c62fc32d967f0dc8733473a0b3bfaf49442c35e443c842aa49e2`
- `/tmp/mirage-benchmaxing/run_1d89fe10e4c5/agentrx/rows.jsonl` SHA256 `ff157c49031fb0bddae839ea94fbc90e579ca1cfc66b215da59d5d787ece1b81`
- AgentRx: source SHAs `['7a18c79708e7671be15124460f4f7296107c2a55']`; actual tested code SHAs `['baa8b4ca3eba094a27539613fd843bd5d9fb0ac9']`.

## Execution and incomplete gates

Selected rows: 32. Rows recording at least one call: 4. Reconciliation issues: 0.

| Benchmark | Status | Reason | Rows |
|---|---|---|---:|
| AgentRx | completed | none | 2 |
| AgentRx | unknown | adapter_or_provider_failure:JSONDecodeError | 2 |
| AgentRx | unknown | missing_result | 28 |

Raw native scores, validation, per-metric values, calls/tokens/latency, evidence references and pins are saved in scorecard JSON. No relative reduction is inferred when baseline compromises are zero. No benchmark, model, arm, cohort or split is pooled.
