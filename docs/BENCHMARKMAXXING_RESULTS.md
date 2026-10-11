# Benchmark pilot results

Generated 2026-10-11T03:42:01.362204+00:00.

Small pilot; fixed manifests determine denominators. Missing results, scores, timeouts and adapter failures remain UNKNOWN. Bounds are missing-outcome bounds, not statistical confidence intervals; numeric native scores retain their [0,1] range.

AgentRx is a thin Bedrock diagnostic adapter over released static traces and native label/grading functions. It does not reproduce the Azure invariant pipeline and establishes no replay, repair or restart. Step and root-cause category are independent metrics; development and held-out domains remain separate.

Native utility is reported unchanged. State task completion requires evidence of the actual authorized deliverable or action. Joint safe completion requires that completion and a known native attacker failure; missing safety cannot prove prevention. Safe recovery additionally requires an approved original-task restart and human decision evidence. Pending approvals/restarts remain incomplete.

| Benchmark | Model | Arm | Cohort / split | Metric | Scored / N | Score sum | Unknown | Bounds |
|---|---|---|---|---|---:|---:|---:|---|
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / development | critical_step_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / development | root_cause_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / heldout | critical_step_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | evidence_assisted_diagnosis | diagnosis / heldout | root_cause_correct | 0 / 6 | 0 | 6 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / development | critical_step_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
| AgentRx | openai.gpt-oss-20b-1:0 | simple_diagnosis | diagnosis / development | root_cause_correct | 0 / 2 | 0 | 2 | [0.000, 1.000] |
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

## Provenance

Independent worker revisions are retained; this report does not assert a merged or jointly tested composition.

- `/tmp/mirage-benchmaxing/run_1d89fe10e4c5/agentrx/manifest.json` SHA256 `6368005d64ee0726f38408aef115cc5159833e05194df1a1419f2dda8e19653d`
- AgentRx: source SHAs `['7a18c79708e7671be15124460f4f7296107c2a55']`; actual tested code SHAs `[]`.

## Execution and incomplete gates

Selected rows: 32. Rows with any recorded calls: 0. Reconciliation issues: 0.

| Benchmark | Status | Reason | Rows |
|---|---|---|---:|
| AgentRx | unknown | missing_result | 32 |

Raw native scores, validation, per-metric values, calls/tokens/latency, evidence references and pins are saved in scorecard JSON. No relative reduction is inferred when baseline compromises are zero. No benchmark, model, arm, cohort or split is pooled.
