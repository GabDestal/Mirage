# Mirage benchmark improvement plan

Status: planning only. Benchmark execution and tuning are not authorized yet.

## Objective and start condition

Demonstrate that Mirage prevents harmful actions, diagnoses failures accurately, and restores useful work safely. Pursue strong measured results by improving general enforcement and recovery, without teaching benchmark answers.

The benchmarkmaxxing worktree is independent of main. Its coordinator may read the repository, prepare this plan, and identify dependencies. Do not run benchmarks, make Bedrock calls, install dependencies, start services, change implementation or configuration, or dispatch implementation workers until the user explicitly starts this phase. Documentation preparation is authorized now.

After authorization, complete a small pilot within three to four hours of agent execution. Engine fixes take priority and must land first. Recheck the composed main revision rather than assuming individual workers or passing unit tests establish readiness. Preserve existing worker ownership.

## Selected external benchmarks

| Benchmark | Use | Initial scope | Limits |
|---|---|---|---|
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) | Harmful action prevention and legitimate task completion, including completion after recovery | 10–20 task/attack pairs, plus corresponding clean tasks; prefer non-calendar suites | Native checks do not grade Mirage's internal freeze, replay, bisection or restart mechanism |
| [AgentRx](https://github.com/microsoft/AgentRx) | Failure-step localization and root-cause attribution against human annotations | 10–20 recorded failed traces | Offline diagnosis dataset; not executable repair or counterfactual bisection. A dataset evaluation is not a reproduction of the complete AgentRx framework |
| [HarnessRisk](https://github.com/Baiyajing/HarnessRisk) | Recovery from compromised state while resisting poisoned recovery instructions | About five file-based recovery/persistence cases | New August 2026 research preprint. Existing runners target other harnesses; adapter and OS isolation require a feasibility check |

AgentRx releases 115 annotated failed trajectories. HarnessRisk releases 128 cases across six lifecycle phases. Sources: [Microsoft Research](https://www.microsoft.com/en-us/research/blog/systematic-debugging-for-ai-agents-introducing-the-agentrx-framework/), [HarnessRisk paper](https://arxiv.org/abs/2608.17597), [HarnessRisk cases](https://huggingface.co/datasets/YajingB/HarnessRisk).

Useful HarnessRisk examples are recovery_119, which restores unsafe gateway/approval configuration, and recovery_120, which repairs poisoned durable memory. A report alone is insufficient: the attack checks inspect whether the unsafe configuration or memory remains. Select cases by tool/environment compatibility before seeing their evaluation outcomes.

Do not add ITBench, OSWorld, new cyber ranges or full benchmark infrastructures to this phase. Keep the three selected sources; report an unavailable adapter honestly if it cannot fit the budget.

## Engine readiness and architecture dependencies

The coordinator must obtain the exact accepted main SHA and confirmation of these capabilities from the engine/SDK owners before execution:

- Every relevant effect goes through the gate before execution, including file/configuration writes and mutations hidden behind generic tools.
- Company policy, agent permissions and trusted task scope intersect. External content cannot grant permissions. Policy authority and version binding are consistent across gate, snapshot, verifier and restarted run.
- Snapshots retain input identity, complete relevant context and tool outcomes. Replay failures are failures; unknown reads and generic fake success responses cannot establish native task completion.
- Each benchmark world can be reset and forked. Sandbox writes change only the benchmark simulation state. Production execution and detonation use separate ledgers and state.
- Fix verification evaluates both safety and useful completion using the same authoritative restrictions. Removing the task, refusing every tool or allowlisting the attacker is not a fix.
- Restart revokes the compromised run's authority, starts fresh context and preserves the original authorized task. Already-completed writes have receipts or idempotency protection.
- Evaluation scheduling prevents automatic detonation from multiplying inference calls unexpectedly. No bypass of normal gateway checks is acceptable.

The current contract describes recorded-read replay and generic captured-write responses. A stateful benchmark bridge is a dependency, not an existing guarantee. Request the smallest bridge from the owning worker after authorization; do not replace the engine or quietly substitute a new detector.

Benchmark fixtures and ground-truth labels are untrusted evaluation data. Keep any native fake credentials in isolated fixtures; never load real service credentials into a benchmark world. Confirm compatibility with repository fake-secret conventions before adopting native cases rather than silently rewriting published fixtures.

## Experimental design

For executable AgentDojo and compatible HarnessRisk cases, compare three configurations:

1. Unprotected agent.
2. Mirage gate only, with the same detector/policies as the full configuration, and recovery disabled.
3. Full Mirage workflow: containment, snapshot, isolated investigation, verification and operator-approved clean restart.

Keep victim model, prompt, tools, authorized task, attack, initial state, model parameters and step limits identical within each comparison. Reset state between runs. Disclose any runner modifications or unsupported cases. Use a fixed, published attack source where available; skip adaptive attack generation for the first pilot.

The native benchmark judges task utility and attack success on the actual execution state after continuation/restart. Deliberately permitted harm inside detonation is separate evidence and does not count as a production compromise.

For AgentRx, compare a simple diagnosis prompt with Mirage's evidence-based diagnostic output using the same Bedrock model and the same allowed trace/policy/schema information. Grade against the released failure-step and cause labels. Do not show labels to either diagnostic system. Static traces cannot demonstrate replay, bisection or restart; do not claim otherwise.

Mirage's event trace separately records containment, replay, verification, human approval, restart and final completion. A safe recovery score derived from those stages is our disclosed extension. Original benchmark metrics remain separately visible. No external benchmark selected here certifies the entire internal lifecycle out of the box.

## Honest benchmark improvement

Before tuning, pin source revisions and create a reproducible manifest containing case IDs, attack IDs, model IDs, seeds where supported, split assignment, limits and policy version. Split by task/attack family so near-duplicate variants do not cross the development/evaluation boundary. A single task attacked multiple ways stays in one split.

Use development cases to improve general mechanisms:

- Resolve actual effects before authorization, independent of tool spelling.
- Check trusted resource, destination, beneficiary, action and data scope rather than demo-only domains or one hardcoded canary.
- Cover unauthorized configuration changes, memory writes, deletion, secret exposure and privilege escalation.
- Remove poisoned influence during recovery without removing necessary benign task information.
- Repair fresh-run reconstruction, tool error handling and side-effect deduplication.
- Reduce false positives using clean counterparts and correct authorized task scopes.

Forbidden: case-ID branches, attack-text matching, evaluator-answer injection, permissions inferred from attacker objectives, feeding AgentRx labels to diagnosis, modifying success criteria to pass, selecting final cases/models because they fail attacks, dropping failures from denominators, or repeatedly tuning against held-out results.

Choose two available smaller Bedrock models based on clean tool-use competence and access before held-out attack results are visible. A third model is optional only if the pilot leaves budget. If evaluation exposes a new issue that we fix, mark those cases as development and obtain untouched evaluation cases; do not relabel the rerun as held-out.

## Metrics and evidence

| Metric | Definition |
|---|---|
| Attack success rate | Native attacker-success outcomes divided by all selected executable attack cases, with failures/timeouts reported separately |
| Legitimate task completion | Native user-task success for both clean and attacked tasks, reported separately |
| Joint safe completion | Native task succeeds and native attack fails on final execution state |
| Diagnosis accuracy | Correct critical failure step and correct cause category, reported separately against AgentRx labels |
| Safe recovery | Required recovery state passes external checks and the authorized task finishes; any additional restart/reinfection check is labelled a Mirage extension |
| False containment | Clean legitimate tasks incorrectly held; include human approvals and unresolved holds |
| Overhead | Model calls, token usage, provider throttling, machine processing time and human wait time, reported separately |

Publish counts and denominators per benchmark/model/arm; do not pool unlike metrics into one giant accuracy percentage. Keep unsupported cases, timeouts, errors and incomplete recoveries visible. Zero baseline compromises means relative reduction is undefined. Use uncertainty intervals when the sample supports them, and label small samples as pilots.

Aspirational targets, not promised or measured results: at least 80% relative attack-success reduction where a nonzero baseline exists, with legitimate completion within five percentage points of baseline, and a visible safe-completion gain over gate-only containment. Do not trade away utility to hit the safety target.

Each result links to source revision, selected case, model configuration, policy version, native scores, final world diff and a sanitized event/incident trace. Pin verification to the exact tested code/configuration revision. Keep tokens, environment files and capability credentials out of Git and reports.

## Bedrock and time budget after authorization

All inference uses existing Bedrock access in us-east-1. Load python-dotenv before boto3 where needed. Use AWS_BEARER_TOKEN_BEDROCK and model/profile IDs from environment; never hardcode or print secrets. Respect model-specific temperature support. Victim parameters stay fixed across arms; diagnostic/report roles are disclosed separately.

Reuse the project's Bedrock client. AgentRx's published client and HarnessRisk's runner are not native drop-in Bedrock integrations; adapt provider seams only where necessary. Use native state checks and released labels instead of introducing paid external judges. Coordinate a shared request budget with the existing fleet, approximately one request per second per person across all inference roles. Retries need caps and backoff; never silently change provider or model after auth failures.

| Budget | Outcome |
|---|---|
| 0–30 minutes | Confirm accepted engine revision, provider access, one case per adapter and real isolation; decide feasible coverage |
| 30–90 minutes | Minimal adapters, effect mapping and development-set corrections, owned by scoped workers |
| 90–180 minutes | Freeze evaluation manifest/policies; paired held-out runs and a small recovery cohort |
| 180–240 minutes | Finish bounded runs, inspect failures and produce a compact sourced scorecard |

These are caps, not measured runtimes. Pilot five cases to estimate calls and latency before expanding. Prefer fewer complete paired cases and two models over an unfinished broad sweep. If a provider/sandbox bridge exceeds the feasibility gate, retain the benchmark in the plan and report that it was not run.

## Coordinator and delivery contract

Demo purpose: provide evidence for prevent, explain and recover after the incident journey; do not create a benchmark-focused product UI.

Initial ownership: planning coordinator in benchmarkmaxxing; documentation preparation only. Future implementation uses supervised Orca workers in independent scoped worktrees, one feature and atomic PR per worktree. Never create Codex/raw Git worktrees. Main is read-only coordination. Human approval remains required for merges and production restarts.

Person A owns engine/gate/store/replay/verifier/API changes. Person B owns SDK/agent adapters, policy text, story completion criteria, benchmark experience and reports. Shared changes require contracts/models.py, fixtures and CONTRACTS.md together. Do not duplicate or take over files already owned by the engine-fix fleet.

After authorization, propose workers for (a) minimal executable benchmark adapters, (b) offline diagnosis evaluation, and (c) the report, combining scopes where reuse makes a separate worker unnecessary. Each brief includes goal/demo step, owned files, dependencies, constraints and observable checks. No worker should invent a second safety engine to get higher numbers.

Acceptance for this planning task: this document exists in the independent benchmarkmaxxing worktree; the coordinator has the brief and is waiting for an explicit start. No benchmark, implementation, tuning or Bedrock test has run as part of preparation.
