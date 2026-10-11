# AgentRx phase2 v2: typed provenance and new fixed cohorts

Status: distinct offline implementation and both protocols frozen, no v2 inference. Root/C2 approved typed sources after development showed a provenance-format mismatch. V1 executable files, prompts, raw outputs, native scores and denominators remain byte-identical and runnable for the separately leased Opus reference. No old cell is retried, rescued or regraded.

The only model behavior change is provenance representation. Static constraints derive from the supplied policy/schema; dynamic constraints derive from supplied instruction/trace/policy/schema. Both prompts request nonempty arrays of unique canonical source literals. The parser accepts those arrays or one canonical literal, preserves the original representation, and rejects unknown/label sources, duplicates, empty arrays, wrong types and free-text compound strings. It performs no splitting or coercion. Strict fields/IDs, actual 1-based citations, complete checker coverage, stage caps, final diagnosis prompt, model parameters and external native grading are unchanged.

Implementation lives only in `benchmarks/agentrx_phase2_v2.py`. It reuses the unchanged v1 IR/schema, bounded runner, native scoring and report reconciliation/metrics/bounds. Per-process setup selects the separate output, parser and frozen prompts. The report writer directs only the publication destination to v2 documents and verifies v1 preservation hashes; no legacy report is written into a v1 destination.

Two separately frozen cohorts are required before provider outputs:

- Same-case development: Tau 2/3 x GPT-OSS20B/Haiku4.5 x simple/assisted, eight new cells/max20 calls. Compare v1/v2 native accuracy and parser coverage as development evidence, without modifying v1 outcomes.
- New structurally held-out task families within the seen Magentic domain: six new cases x the same two models/arms, 24 cells/max60 calls. The entire original 88-record family/eligibility ledger remains visible; every phase1-exposed family and every v1 family/variant is excluded. Same grouping, complete-payload<=100000character rule, record-availability eligibility and lexicographic representative order. C2 independently found 20 remaining eligible groups and fixed the next six before annotation values/outcomes. No replacement after results.

The new cases are `557e78eceec08ca8b0da5f9fdaca6e1c7ec6140a8ce600983ee716327dab005e`, `56137764-b4e0-45b8-9c52-1866420c3df5`, `57d9dc6935e8a40b02e7f8ec81768fe70e68a0c05f6866927c9fda38db38a486`, `5d0080cb-90d7-4712-bc33-848150e917d3`, `6b06d186921b8b390c65aebd0d16f09f60a47d2f1288ebe36953f734e84c0a3c`, and `6e3be83d1949fa52cba03fb1ce4b5b3bf7e37a83fd7d67694b10b2e439d90cf8`. Selection metadata/IDs never enter prompts. The predecessor label-blind ledger SHA256 is `fbcf19608a74e9387510d43431a6f7a65f2cc998ba0f07e61f88c8fefb5b49aa`.

V2 raw artifacts stay under `phase2/agentrx/v2/development` and `phase2/agentrx/v2/families`. Each has its own manifest, complete ledger, v1-preservation receipt, stage records and native scores. Prices remain UNKNOWN. UNKNOWN criteria never grant PASS; malformed/truncated/provider-failed stages remain explicit with skipped downstream stages, no fallback/retry. Extra assisted compute is counted, so this is not matched compute. Static diagnosis establishes no executable recovery or frontier equivalence; lexical grouping does not establish universal semantic independence.

A focused compatibility check uses the exposed saved development dynamic output, plus a synthetic typed representation of the preserved failed Haiku static output. The original compound raw output remains rejected; no runtime rewrite or scoring occurs. The check accepts actual supplied provenance and rejects labels, unknowns, wrong types, empty/duplicate sources and invalid indices. V1 source/output preservation and independent next-six selection are checked at freeze.

```sh
python3 -m benchmarks.agentrx_phase2_v2 self-check
python3 -m benchmarks.agentrx_phase2_v2 prepare --cohort development
python3 -m benchmarks.agentrx_phase2_v2 prepare --cohort families
python3 -m benchmarks.agentrx_phase2_v2 verify --cohort development
python3 -m benchmarks.agentrx_phase2_v2 verify --cohort families
```

Provider hold remains until positive user-session drain and an exact root lease naming model/cases/arms/stages/caps/deadline. Estimated rehearsal time is not authorization. No model calls are authorized by these offline commands or by environment IDs. PR166 remains open against `benchmaxing`.

Implementation commit: `ec21035` (isolated v2 module; original v1 code pins still match). Development manifest SHA256: `a8fddd846ac6150b6c8a04bd5abfe3180fbfa7a7c517c1724ef4aee9457a0947`. New-family manifest SHA256: `0e73ac32af009763d0ff063f787f26d3c14d83efc07fce47152659ceb7582917`. Both source/native/selection/phase1/v1 pin checks pass, including 79 v1 source/raw-result files per preservation receipt. Family cases independently match C2's next-six selection exactly. The initial no-call family freeze is archived after a development-ledger availability fix; prompts/cases/caps did not change. The failed offline development preparation is recorded with zero calls.

Separate zero-attempt fixed-denominator reports: [development](BENCHMARKMAXXING_PHASE2_AGENTRX_V2_DEV.json) and [new families](BENCHMARKMAXXING_PHASE2_AGENTRX_V2_FAMILIES.json). All selected metrics currently remain UNKNOWN with [0,1] bounds. Run uses the existing venv Python with `-m benchmarks.agentrx_phase2_v2 run --cohort development` or `--cohort families`, plus the exact root-assigned `--lease` JSON. Static/dynamic/checker/diagnosis caps are 2048/2048/4096/4096, one call per stage, maximum ten calls per development model block or 30 per new-family model block.
