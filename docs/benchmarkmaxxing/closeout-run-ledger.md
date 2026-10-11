# Frozen execution and missing-runs ledger

Coverage counts only: unlike cohorts, models and metrics are never pooled into efficacy. Exact case/model/arm/protocol identities, missing reasons and source hashes are in [JSON](closeout-run-ledger.json). Historical failed attempts remain immutable; unrun v2/reference/native cells are separate.

Attempted = a recorded model/client call, not proof of successful provider HTTP execution. Native scored = reconciled known step for AgentRx, reconciled utility for HarnessRisk/AgentDojo. Raw available separately includes incomplete executions and client-failure fields; it never proves useful completion. Incomplete/invalid = attempted without a completed or graded frozen terminal checkpoint; completed rows can still lack native labels. Actual final-state task coverage is separate.

| Lane | Benchmark / cohort / split | Selected | Attempted | Raw native task available | Native scored | Actual task scored | Unrun | Attempted incomplete/invalid |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| phase1_preserved | AgentRx / diagnosis / development | 8 | 4 | 2 | 2 | — | 4 | 2 |
| phase1_preserved | AgentRx / diagnosis / heldout | 24 | 0 | 0 | 0 | — | 24 | 0 |
| phase1_preserved | AgentRx / diagnosis_native_schema_v2 / development | 12 | 4 | 4 | 4 | — | 8 | 0 |
| phase1_preserved | AgentRx / diagnosis_native_schema_v2 / heldout | 36 | 36 | 21 | 21 | — | 0 | 4 |
| phase1_preserved | HarnessRisk / native_recovery / development | 6 | 2 | 2 | 0 | 0 | 4 | 2 |
| phase1_preserved | HarnessRisk / clean_control / development | 6 | 0 | 0 | 0 | 0 | 6 | 0 |
| phase1_preserved | HarnessRisk / frontier_reference / development | 1 | 1 | 1 | 0 | 0 | 0 | 1 |
| phase1_preserved | HarnessRisk / native_recovery / held_out | 12 | 8 | 8 | 0 | 0 | 4 | 8 |
| phase1_preserved | HarnessRisk / clean_control / held_out | 12 | 0 | 0 | 0 | 0 | 12 | 0 |
| phase1_preserved | HarnessRisk / frontier_reference / held_out | 2 | 2 | 2 | 0 | 0 | 0 | 2 |
| phase1_preserved | HarnessRisk / development_mapping_v2 / development | 2 | 2 | 2 | 0 | 0 | 0 | 2 |
| phase1_preserved | HarnessRisk / development_serialization_v3 / development | 2 | 2 | 2 | 0 | 0 | 0 | 2 |
| phase1_preserved | agentdojo / clean / dev | 15 | 4 | 4 | 3 | 3 | 11 | 1 |
| phase1_preserved | agentdojo / attack / dev | 15 | 2 | 2 | 2 | 2 | 13 | 0 |
| phase1_preserved | agentdojo / clean / heldout | 27 | 0 | 0 | 0 | 0 | 27 | 0 |
| phase1_preserved | agentdojo / attack / heldout | 27 | 0 | 0 | 0 | 0 | 27 | 0 |
| phase1_preserved | HarnessRisk / development_budget_v4 / development | 4 | 4 | 4 | 0 | 0 | 0 | 4 |
| phase1_preserved | HarnessRisk / resource_budget_v5 / development | 4 | 4 | 4 | 4 | 4 | 0 | 0 |
| phase2_agentrx | AgentRx / agentrx-native-derived-nl-phase2-v1 / development | 8 | 8 | 5 | 5 | — | 0 | 3 |
| phase2_agentrx | AgentRx / within_seen_domain_unseen_task_families_v1 / within_seen_domain_heldout_task_families | 24 | 24 | 10 | 10 | — | 0 | 14 |
| phase2_agentrx | AgentRx / within_seen_domain_families_opus_reference_v1 / within_seen_domain_heldout_task_families | 12 | 0 | 0 | 0 | — | 12 | 0 |
| phase2_agentrx | AgentRx / within_seen_domain_unseen_task_families_provenance_v2_development / development_same_case_v2 | 8 | 0 | 0 | 0 | — | 8 | 0 |
| phase2_agentrx | AgentRx / within_seen_domain_unseen_task_families_provenance_v2_families / within_seen_domain_heldout_task_families_v2 | 24 | 0 | 0 | 0 | — | 24 | 0 |
| phase2_agentrx | AgentRx / within_seen_domain_provenance_v2_opus_reference / within_seen_domain_heldout_task_families_v2 | 12 | 0 | 0 | 0 | — | 12 | 0 |
| phase2_native | HarnessRisk / phase2_native_primary / development | 6 | 0 | 0 | 0 | 0 | 6 | 0 |
| phase2_native | HarnessRisk / phase2_native_primary / held_out | 6 | 0 | 0 | 0 | 0 | 6 | 0 |
| phase2_native | HarnessRisk / phase2_native_operator_extension / development | 2 | 0 | 0 | 0 | 0 | 2 | 0 |
| phase2_native | HarnessRisk / phase2_native_operator_extension / held_out | 2 | 0 | 0 | 0 | 0 | 2 | 0 |
| phase2_native | HarnessRisk / phase2_native_conditional_frontier / held_out | 1 | 0 | 0 | 0 | 0 | 1 | 0 |

The preserved phase1 registry is 215 selected / 75 attempted cells. AgentDojo: 84 selected / six attempted / five native utility-scored / 78 unrun, with one attempted client failure UNKNOWN. Historical HarnessRisk: 51 selected / 25 attempted / 25 raw-utility fields / four reconciled native-utility-scored / four actual-task-scored; 21 attempted incomplete and 26 unrun or unsupported. Known native/state safety outcomes in incomplete runs remain in the JSON; they never establish missing task completion.

AgentRx phase2 v1: eight development plus 24 structural-family cells, all attempted, respectively five and ten native-scored per metric. The 56 genuinely unrun AgentRx phase2 cells are eight v2 development, 24 v2 untouched families, 12 conditional v1 Opus and 12 conditional v2 Opus. Native phase2 adds 12 primary, four separate operator-extension and one conditional frontier cell, all unrun UNKNOWN. Phase2 primary N=12 covers both models and all three arms; four of those cells require the full engine, rather than all twelve being full-arm executions.

Native clean controls lack released counterparts: the prospective same-case 12-cell clean comparison is unsupported UNKNOWN and is not an executed or selected attack row. Eight additional structurally eligible native cases remain unselected; they are not promised runs. IDs are recorded in JSON without fixture contents.

Historical raw scores, proof flags and independent code SHAs remain in [the original registry](../BENCHMARKMAXXING_RESULTS.json), [chart source table](chart-source-table.md) and their pinned publication sources. New-code source acceptance and offline tests do not create provider or human-approval evidence.
