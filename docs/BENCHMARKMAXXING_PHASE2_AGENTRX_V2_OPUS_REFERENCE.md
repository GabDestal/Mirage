# AgentRx phase2 v2: optional same-case Opus reference

Status: artifact-only freeze, zero calls. An explicit root lease remains required; rehearsal timing estimates authorize no inference. Selection is conditional only on time, model access and lease availability, never v2 outcomes.

This reference uses exactly the six cases and both arms already frozen for [the v2 family cohort](BENCHMARKMAXXING_PHASE2_AGENTRX_V2.md). Its **12 cells and maximum 30 calls** have a separate denominator from the cheap-model development and family cohorts. The manifest was frozen before any v2 model outputs. The unchanged accepted runner, full trace/policy/schema/instruction, native scoring and final diagnosis system prompt are reused. No whole-domain independence, matched compute, executable recovery or frontier equivalence is claimed.

The existing environment model is `us.anthropic.claude-opus-4-8`. Final `maxTokens=4096` and omitted temperature follow the existing Opus parameters; static2048/dynamic2048/checker4096/diagnosis4096 caps and one call per stage remain fixed. Assistance adds three calls within the same model. Cost stays UNKNOWN without a reliable pinned price.

Raw artifacts: `/tmp/mirage-benchmaxing/run_1d89fe10e4c5/phase2/agentrx/v2/opus-reference`. Manifest SHA256: `cf2175393396ece03dd95f3ee825c23b12e772c275bbdca5ee4fba1e8cb41b96`. Source code remains the accepted `ec210359a289102ad5beae3d26a3445175fa5ba8`; original v1 and phase1 pins, both cheap v2 manifest hashes and the native pins pass. Frozen manifest rows retain the original preparation revision; any actual execution records its current publication SHA separately.

The [independent report](BENCHMARKMAXXING_PHASE2_AGENTRX_V2_OPUS_REFERENCE.json) retains all 12 cells as UNKNOWN, with zero attempted/scored cells and [0,1] per-metric bounds. Reporting uses the unchanged shared `benchmarks.report` CLI with explicit independent destinations. The raw directory contains `RUN_CONTRACT.md`; no adapter edits or cheap-report overwrite are needed. Parse/provider failures and skipped stages remain explicit, without retries or retroactive v1 rescoring.
