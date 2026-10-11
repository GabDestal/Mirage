# AgentRx phase2: within-seen-domain task-family cohort

Status: C2 accepted this freeze; the root-leased GPT-OSS family block is scored and drained, with Haiku awaiting its separate lease. This preserves the original whole-domain development/phase1 split. It is a **within-seen-domain cohort of structurally grouped unseen task families**, not an unseen-domain experiment. Lexical grouping does not prove semantic independence of every paraphrase; that limitation must accompany any results.

Before opening new annotation values or model outputs, the source inventory was grouped and written to `families/families-frozen.json`. Only afterward were annotation record identifiers checked and the full `families/eligibility-ledger.json` frozen. Failure values/categories/rewards/outcomes are not grouping inputs. No replacements after outcomes are allowed.

The fixed algorithm normalizes capitalized spans, URLs, quoted spans and numbers in released instructions. Same-domain pairs are connected when token-set Jaccard is at least 0.48, character SequenceMatcher similarity is at least 0.72, or normalized instructions match exactly. Transitive closure keeps all detected variants in one family. Tau is conservatively one family because initial simulator messages underspecify complete intent; the phase1 Tau exposure excludes the entire Tau domain. Attached document contents are excluded from identity grouping only; runtime receives the complete trace/instruction.

Structural eligibility requires a nonempty released instruction and complete payload of at most 100,000 characters. Oversized inputs are excluded before outcomes, never truncated. Annotation record presence is required; missing per-metric values are not inspected during eligibility and remain UNKNOWN after scoring. Any family intersecting the eight phase1-selected cases is excluded. One lexicographically first eligible case represents each family; the first six representatives by case ID form the frozen cohort. Neither family grouping nor selection depends on failure labels.

The ledger covers 88 records and 55 structural families. It identifies 26 eligible families before the six-family cap. Exclusion-reason counts overlap: 35 records in exposed families, 18 oversized payloads, 15 missing annotation records, one unsupported structure, and 21 nonrepresentatives or records outside the fixed family cap.

| Frozen case | Message count | Complete payload characters |
|---|---:|---:|
| `2aa5dd83fbcd0dce9a3dd4592106e5b5edf738008d932e357d477bba80e59ccf` | 5 | 17,610 |
| `2dfc4c37-fec1-4518-84a7-10095d30ad75` | 20 | 25,800 |
| `3af8028c2a59e28ca88baff0e6d91f2a9f170c5ef91003f1c8406755a2760ad4` | 17 | 25,713 |
| `42576abe-0deb-4869-8c63-225c2d75a95a` | 5 | 12,606 |
| `42d4198c-5895-4f0a-b0c0-424a66465d83` | 20 | 33,352 |
| `52f7224e9c79431e7926afe317782711a0028750693e7456cde22ef6f4bd8bd5` | 21 | 38,206 |

All six are Magentic traces. Each is selected on the same two cheap models and two arms as [the development protocol](BENCHMARKMAXXING_PHASE2_AGENTRX.md): **24 fixed cells and at most 60 calls**. The same final diagnosis prompt, model parameters, stage caps and native graders apply. Assisted diagnosis adds three calls; compute is not matched. No Opus cells or calls are authorized by this freeze.

Shared implementation commit: `581193cd70d9967be3e570e7a6554baea408234f`. Development manifest SHA256: `217d5b2a4a2e47754d37274139744562110d4e387f2a1bf6aad48a1b5eb6c942`. Family manifest SHA256: `bd320eb8c5f455c7de6e9f985c642c14ba9e7990349a70fcacd074525cd7a74f`. Root approved the no-call development manifest's code-pins-only advancement for separate output selection and manifest-derived report counts; its prior manifest is archived. Development cases, original whole-domain ledger, final/generation prompts, parameters and stage caps remain unchanged.

All family raw artifacts live under `/tmp/mirage-benchmaxing/run_1d89fe10e4c5/phase2/agentrx/families`. The [separate family report](BENCHMARKMAXXING_PHASE2_AGENTRX_FAMILIES.json) retains 24 fixed cells, including the 12 currently unattempted Haiku cells. No annotation metric values were read before the selection freeze; native scoring opened values only after saving model output. Focused variant-normalization/transitive-grouping checks and shared native/code/selection/phase1 pin checks pass; no broad verification or provider smoke campaign was run.

GPT-OSS attempted all 12 cells with 20 calls and 162,536 total tokens. Simple diagnosis scored 5/6 cells, got 2/6 critical steps and 3/6 categories correct, and retains one UNKNOWN: missing-outcome bounds [0.333,0.5] and [0.5,0.667]. Assisted diagnosis scored 1/6 cells, got 0 correct for either metric and retains five UNKNOWN cells, bounds [0,0.833] each. Five dynamic outputs violated the frozen source enum; one simple output had invalid/missing message citations. All downstream skips remain explicit. The only scored pair ties on incorrect critical step and loses category relative to simple; five pairs remain UNKNOWN. No assistance gain is demonstrated. The synchronous runner exited with code zero, the lease is closed, and no cell was retried or replaced.

```sh
python3 -m benchmarks.agentrx_phase2_families self-check
python3 -m benchmarks.agentrx_phase2 verify --cohort within_seen_domain_unseen_task_families
python3 -m benchmarks.agentrx_phase2 report --cohort within_seen_domain_unseen_task_families
```

Provider runs require the explicit root-approved lease JSON and `--cohort within_seen_domain_unseen_task_families`. Source filenames/benchmark IDs and selection metadata are never injected into runtime prompts. Failures, incomplete stages and absent labels remain explicit; no assisted-stage fallback or retry-until-pass is allowed. This static diagnostic adaptation establishes no executable recovery or frontier equivalence.
