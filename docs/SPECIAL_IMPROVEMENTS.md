# Mirage special improvements proposal

Status: planning proposal, 2026-10-11. Integration branch: `special-improvements`, based on `origin/main` at `1e6052e073886abf36f54af10c48e8c521f4b86e`. Branch and documentation publication are authorized; the user will say when to start implementation and pushing code. This document authorizes no feature implementation, API change, model execution, policy activation or deployment.

## Key rule: integrate only on special-improvements

**Never merge these changes into `main`.** The user explicitly chose `special-improvements` as the integration branch. This instruction overrides repository workflow defaults that target or update main after a feature merge.

- Every improvement worker branches from the current reviewed `special-improvements` tip, using an Orca-managed worktree with an explicit base branch. The integration worktree remains independent, with no parent in main.
- Every feature PR and the Mirage demo's generated repair PR targets `special-improvements`. Put the base branch and exact base SHA in every coordinator/worker brief; never accept the GitHub default base implicitly.
- A human may merge approved PRs into `special-improvements`. Coordinators and workers do not merge into `main`, open a delivery PR targeting `main`, or enable auto-merge.
- Rebasing `special-improvements` onto `origin/main` is allowed when requested. It brings engine changes into this branch; it does not authorize delivery back to main. Coordinate before rewriting the shared integration tip, then give active workers the new exact base.
- After a human-authorized feature merge, update the integration checkout with `--ff-only`, verify the reviewed feature head and clean up settled worktrees through Orca. Leave the main checkout untouched.

Creating/publishing this branch and plan does not start the implementation milestones. Wait for the user's start instruction before launching implementation workers or pushing feature code.

## The experience we want

One incident should improve the whole fleet. The operator watches Mirage contain a compromised run, prove the cause, write a tested repair, preserve the lesson, assess other agents and safely return work to service.

The proposed four features form one journey:

1. Mirage coordinates the coding agent and opens a verified repair PR.
2. The incident becomes a permanent regression case and a proposed prevention rule.
3. Mirage checks whether the vulnerability applies to the rest of the fleet.
4. The human rolls out the verified fix and approves clean restarts.

The Rules tab and Miragio chat support this journey. They are not a separate policy-discovery project. Mirage does not discover the permissions a company should grant.

These are future proposals. PRODUCT.md currently says Mirage hands the incident to the user's coding agent and does not write the fix itself; this document proposes extending that experience. Approve the product/contract change before implementation. Existing engine fixes and the working demo remain prerequisites.

## What changed on main, and what we can now reuse

This is a source comparison from the original proposal's base, `6cfea0e`, to `1e6052e`. No services, tests or providers were run for this review. The engine is materially stronger; these findings describe merged source behavior, not a new live rehearsal.

| Change | How it works now | Consequence for special improvements |
|---|---|---|
| Run and tool failures remain failures: #141, #143 | SDK completion forwards invocation errors; LangGraph records handled tool errors instead of treating their messages as successful results. See [SDK core](../sdk/mirage/core.py) and [adapter](../sdk/mirage/adapters/langchain.py). | Reuse existing error/status reporting for repair progress. Do not build another success detector from agent prose. |
| Full task requirements reach the snapshot: #143, #147 | `mirage.protect(..., legit=...)` carries trusted requirements; the fleet freezes requirements derived from clean inventories before execution. Checks cover the complete meeting brief and the required entities for other stories. See [fleet](../agents/run_demo_fleet.py) and [completion declarations](../agents/common/completion.py). | The repair must complete the actual meeting task. Reuse these criteria rather than inventing a second evaluator. |
| Replay returns exact recorded reads: #150 | The child consumes results for identical tool names and arguments, once per recording, in order. A missing read is a typed unavailable result, rather than another contact's answer or a fake success. See [child](../engine/detonation/child.py). | Fleet evaluation requires compatible recordings. Changed queries can legitimately make a candidate unevaluable; plan for that small demo constraint. |
| Human release belongs to one checked call: #154 | Held calls carry their identity, generation and admission state. A human release admits only the original call once. Results require that admission; identical result retries do not duplicate the ledger. See [gateway](../engine/gateway/gate.py) and [API](../engine/api/server.py). | Preserve the gateway and use its controls. Repair/recovery should not release the old compromised callback. |
| Harm survives replay collection failures: #152 | Parent failures, malformed later ledger lines and failed sibling futures retain earlier effects. Errors do not earn a clean verification count. See [sandbox](../engine/detonation/sandbox.py). | Reuse `DetonateResult`, its exit code and its effects. Keep failed attempts visible without adding an extensive verification service. |
| Policy and factory metadata are pinned: #155 | `LiveRun` deep-copies its admitted `AgentSpec`, allowlist and legitimate-task declaration. Freeze uses those copies. Fix verification also obtains the rebuilt factory's current spec and checks effects under freeze-time and current restrictions. | Much of the policy-authority prerequisite is already present. Add only explicit rule revisions/activation and visibility. There is still no versioned Rules product or remote operator authentication. |
| Restart claims identify the approved work: #157 | Approval creates one queued restart for a killed, halted or failed run. Claiming it requires the same agent/task and unchanged full registration; duplicate approvals and ambiguous claims are refused. | Reuse restart approval. Add the missing launch of the merged code and task outcome; the existing `/restart` route still only queues work. |
| Useful fallback and quieter UI: #151, #153 | [Scripted acceptance probes](../demo/acceptance_fleet.py) exercise SDK/HTTP/jailed replay without a model provider; Fleet no longer includes the service-evidence and engine-approval panels. | Use the probes for wiring if necessary, labelled scripted. Put repair progress on the incident/chat surface and keep Fleet quiet. |

Current-code verification already runs from scratch, evaluates freeze-time and current permissions, and requires useful task completion. The new merges strengthen its inputs and failure handling; they do not create a coding supervisor, a real PR, a Rules editor, a fleet assessment job or a merged-revision launcher.

Two important integration details remain. HTTP `/verify` executes the code loaded from the engine's own checkout; it does not automatically test a separate repair worktree. Also, restart queues an approved run while `/resume` refuses confirmed compromised runs. The plan below handles both explicitly instead of rebuilding the engine.

The two-hour version uses the protected meeting assistant and current synthetic services: eight seeded contacts, two clean meetings and the injected invite. Google/HubSpot integration, the recorded fixture's 40-record claim and a general deployment platform are outside this increment. The four feature sections retain the wider proposal; the milestone plan defines the smaller implementation target.

## 1. Mirage coordinates a coding agent and opens a PR

### Demo moment

The operator says, "Fix this and prove it." Miragio starts a bounded repair job, shows progress and returns a real GitHub PR with the original incident, the change, the regression test and the verification result.

### Smallest complete implementation

Reuse the existing incident handoff, incident-scoped verification access and a local coding-agent runtime. Mirage owns orchestration and progress; the coding runtime owns edits in an isolated Orca-managed worktree. The user should not have to copy context between applications for the integrated demo path.

Launch from a trusted local supervisor with an allowlisted repository and base revision. Supply the authorized repair scope, sanitized incident facts, marked untrusted evidence and an incident-limited verification capability. Keep GitHub credentials in the supervisor/runtime, outside model continuation and detonation. Use the installed coding runtime and GitHub tooling before introducing a new coding framework.

The worker makes a small repair, adds the regression case, verifies the same frozen incident with current code from scratch, commits, pushes and opens a draft PR. Verification must show both attack prevention and useful task completion. A repair that refuses everything, relaxes policy or depends on the injected text fails acceptance.

The controlled repair loop may retry a bounded number of times using development evidence. Each candidate is verified against the same incident and clean control; a failed attempt remains visible. If repair fails or expires, the run stays contained and Miragio explains the blocker. Do not present a best-of-many lucky replay as a reliable repair.

### Existing seams and proposed changes

Reuse `engine/handoff.py`, `engine/cli.py`, `POST /incidents/{id}/verify`, `POST /incidents/{id}/pr` and the Miragio/MCP experience. The existing engine constructs a handoff prompt and records a reported PR; it does not create that PR or supervise a coding process.

Proposed contract addition: a repair-job ID with queued/running/verifying/pr_open/failed states, exact repository/base/head revisions, verification evidence and a PR URL. Name endpoints and events only during contract alignment. Event progress must describe real work, not scripted success.

Person B owns operator UX, coding-runtime/GitHub integration and the repair prompt. Person A owns authoritative incident/job linkage and verification APIs. Contract models, fixtures and CONTRACTS.md change together.

### Feasibility and acceptance

Doable as a bounded local integration after the core replay path works. Building an entire Bedrock-native coding IDE, arbitrary shell agent or cloud fleet of repair workers is outside the hackathon version. A model must not get an unrestricted shell just to make the demo shorter.

Accept when a real draft PR exists, its head revision matches the tested candidate, the original attack is blocked and the legitimate task completes in three of three fresh verification runs. A deliberately bad fix must fail. No automatic merge or production restart.

## 2. An incident becomes a regression case and proposed rule

### Demo moment

Miragio says, "This incident is now a regression test. I also propose this rule for future invoice tasks." The operator sees a plain-language rule preview, its scope and its effect on a clean workflow, then explicitly activates it.

### Smallest complete implementation

A confirmed incident produces a durable regression artifact: a sanitized snapshot or reference, reproduction command, immutable policy/code references and legitimate-task criterion. Preserve it through the repair PR and the existing `mirage detonate` path (currently invoked as `uv run python -m engine.cli detonate --incident <incident_id>`). Keep capability tokens and real credentials out of the artifact. Bedrock-backed CI requires an intentional credential boundary; do not expose provider keys to untrusted PR code.

Separately, Miragio proposes a structured rule. The rule expresses a general permission boundary, such as emailing only the trusted billing contact for the authorized invoice. It must not memorize the attack's recipient, text or case ID. Automatically preserve confirmed regression evidence; require human approval for policy activation. A false positive becomes a clean regression case, not a permanent denial rule.

Add a small Rules tab with Create rule, a readable form/preview, scope, status, version and Activate. Miragio may draft the same typed rule from conversation. YAML is an advanced export/editor representation of the canonical policy, not the product's main interface and not a separate policy source.

### How rules reach the local harness

Current behavior: `GET /policies` is read-only, agent allowlists are supplied at registration, and the default policy is defined in `engine/detection/policies.yaml`. Versioned policy storage and human-approved activation below are proposed additions.

Use one authoritative engine policy store and the existing HTTP boundary. Company policy, agent role permissions and trusted task scope intersect. A model proposes actions; deterministic checks enforce permissions. External content cannot expand them.

For the proposed single-laptop prototype, the local engine serves the validated active policy version and the SDK sends tool checks to that engine. The harness does not need another policy language or direct imports from `engine/`. If local execution needs a copy, it pulls an authenticated, versioned policy bundle at run start and pins its digest; it never polls untrusted instructions into live authority.

Pin the policy version to each run, snapshot and repair verification. Activating a new version affects new runs; older runs either finish under their pinned version or are explicitly paused and restarted under the new one. Do not silently change authorization beneath a paused call. Gate and verifier use the same effect restrictions and must reject policy-widening fixes.

Policy registration/activation must be bound to a trusted operator/owner. Audit actor labels and the current SDK placeholder `api_key` are not authentication. This is a dependency on the engine policy-authority work, not a reason to create a second policy store in `web/` or the SDK.

### Feasibility and acceptance

The incident regression artifact is a near-term extension of existing verification. The rule UI and policy activation are a second scoped increment once authority/versioning exist. Automatic discovery of company permissions is deferred.

Accept when an incident reproduces before the fix and passes after it, a clean control still succeeds, the operator sees the policy diff, unauthorized policy updates fail, and the local harness/gate/verifier identify the same pinned version. All new contracts require models, fixtures and CONTRACTS.md together.

## 3. Check whether the vulnerability applies to the fleet

### Demo moment

The operator says, "Could this happen to my other agents?" Mirage evaluates compatible agents in simulation and reports, for example, vulnerable, blocked, not applicable or could not evaluate. The healthy live agents continue their work.

### Smallest complete implementation

First identify candidates using actual capabilities, exposed input channels and policy scope. A shared model alone does not establish vulnerability. An agent that cannot reach the sensitive resource or effect may be not applicable; missing context is could not evaluate, not safe.

For a small compatible set, fork each agent's own context and state, insert the attack into an appropriate untrusted input surface and execute in isolated Mirage mode. Preserve that agent's task and permissions; do not transplant the compromised agent's entire snapshot into another role. Compare a clean counterpart. All writes remain simulated.

Use the same effect checks and legitimate-task criteria as the original incident. Report the exact agent/code/policy revision tested, reproduction counts, task completion and coverage limits. "Shared exposure" from capability matching and "confirmed vulnerable" from replay are different findings.

Reuse registration metadata, snapshots, detonation and the effects ledger. The likely engine addition is a bounded multi-agent exposure job with per-agent results, cancellation and artifact references. Do not overload the original incident verdict or count an evaluation error as prevention.

Person A owns compatible-context reconstruction, isolated execution and per-agent evidence. Person B owns fleet selection, exposure results and Miragio summaries. Align the result schema before UI work. Start with two or three compatible demo agents; defer an arbitrary enterprise-wide vulnerability scanner.

### Feasibility and acceptance

Doable as a small fleet demonstration if each selected agent has a usable snapshot and replay adapter. A universal proof about every agent is not feasible from one incident.

Accept when an exposed agent is correctly reproduced as vulnerable, a restricted agent is shown blocked or not applicable with evidence, and an unsupported agent remains unassessed. No evaluation sends real email, changes a real service or freezes healthy runs. Any decision to pause an exposed live agent is a separate human action.

## 4. Roll out the verified fix and restart safely

### Demo moment

After reviewing the PR and simulation evidence, the human merges the change into `special-improvements`. Mirage shows which agent revisions are ready, asks for the restart decision and confirms that the original legitimate task finishes under the repaired version.

### Smallest complete implementation

For the demo, deployment means updating the approved local agent/configuration to the merged revision and relaunching its authorized task. Reuse existing PR linkage, fix verification, run restart/resume APIs and SDK execution. Do not build a general cloud deployment platform.

Bind evidence to exact code, configuration and policy versions. Confirm the merged revision matches the verified candidate or verify the final merged tree. A green PR alone does not establish the running agent's identity.

The human approves the clean restart. Revoke the old run's authority and use fresh model context; do not continue the compromised conversation. Pin the new task and policy scope, use `restarted_from` to link the runs, and distinguish queued restart approval from actual running/completed SDK execution.

Preserve receipts and idempotency for writes that completed before containment so a fresh task does not resend messages, duplicate payments or replay irreversible effects. If the original context cannot be reconstructed safely, remain contained and request a new authorized task rather than claim recovery.

Start with the repaired run. Broader fleet rollout follows the exposure evidence and separate explicit human approval. Halt rollout on verification or execution failure. A rollback also uses an approved revision and keeps suspect runs contained; it must not simply widen permissions or reactivate the compromised context.

### Feasibility and acceptance

Doable for one controlled local demo agent. Arbitrary hosting, distributed package rollout, automatic merge and automatic restart are deferred.

Accept when the approved version is actually running, the old token cannot perform effects, the legitimate task completes without duplicate writes, and the audit links incident, PR head, merged revision, policy version, restart approval and resulting run. A queued run, fixture replay or deployment button click alone is not acceptance.

## Two-hour milestone plan

The clock starts when the user says to start. The priority is one working local journey: **confirmed incident → coding worker → durable regression → verified real PR → human merge → approved clean restart → useful task completed**. Rules and fleet applicability extend that working journey. They must not consume the time needed to finish it.

Use the installed Orca/coding runtime, GitHub CLI, existing Node/Python standard libraries, existing HTTP/SSE, event store and sandbox. No new framework, database, queue, coding IDE, policy DSL or deployment platform. One local operator, one repair job at a time, one named demo repository and one agent story are sufficient. Serialize sandbox/provider proof jobs through the local supervisor and retain the existing sequential pacing; implementation workers can edit in parallel without running overlapping replay loops.

### Schedule and coordinator ownership

| Milestone | Elapsed time | Lead coordinator | Delegated workers | Observable exit |
|---|---|---|---|---|
| M0: lock the demo and shared shapes | 0–10 min | C0: overall coordinator | One Person A contract/engine worker; Person B checks the local integration prerequisites | One usable synthetic incident, exact base and file ownership, agreed small request/result shapes |
| M1: integrated repair and regression | 10–50 min | C1: repair coordinator | A: incident/job evidence; B: local coding supervisor and incident/chat UI | Click starts a real coding worker; durable regression is in a real PR; tested head is reported accurately |
| M2: merge-aware local recovery | 50–75 min | C2: recovery coordinator | A: reuse restart authority and record rollout; B: merged-checkout launch and restart UI | Human merge and approval lead to an actual new run that completes the meeting task |
| M3: minimal Rules tab and activation | 75–95 min | C3: policy coordinator | A: restrictive policy revisions; B: Rules form/preview and chat proposal | Human activates one scoped rule; a subsequent run uses that revision; existing runs keep their pinned policy |
| M4: one compatible fleet assessment | 95–110 min | C4: exposure coordinator | A: isolated replay of a compatible sibling; B: results on incident/fleet and chat | One compatible agent has replay evidence; incompatible/unsupported agents have honest explicit statuses |
| M5: finish the single journey | 110–120 min | C0: overall coordinator | Existing workers fix only blockers in their owned slices | One coherent operator walkthrough, real links and run results, final commit heads and limitations recorded |

C0 owns scope, dependencies and human communication. C1–C4 own the named milestone's acceptance and worker briefs. Use supervised Orca orchestration for dependencies, worker questions, progress and completion reports. These are delegation roles, not five always-running planning agents. Activate only the current milestone lead; reuse coordinator sessions when useful. Keep at most one overall coordinator, one milestone lead and two implementation workers active. The integrated product's repair agent occupies a worker slot while it runs.

Coordinator agents remain read-only for implementation in the integration checkout and main. Workers implement, validate, commit, push and open/update PRs in isolated Orca-managed worktrees based on `special-improvements`, with PRs targeting that branch. Each backend or experience slice is a separate atomic feature PR; frequent commits stay within that PR. Person A owns engine behavior/APIs and the shared-contract edits; Person B owns SDK/demo execution, coding-runtime/GitHub integration, MCP/chat and UI. Both agree shared shapes before consumers build. `contracts/models.py`, fixtures and `CONTRACTS.md` travel together in the engine slice that introduces a shape.

Start backend and experience workers together after a five-minute contract sketch, with replay examples for the experience worker. The coordinator gives dependents the exact reviewed/merged `special-improvements` base SHA. A worker reports a blocker after five minutes; the coordinator cuts optional scope or reassigns it rather than opening a new architecture exercise. Human merges remain human decisions. If a merge is pending, code can be checked in an explicit local composition, but integration/rollout must not be reported delivered. Nothing in this plan is delivered to main.

### M0: freeze the choices, not another audit

Choose the meeting assistant, one synthetic incident and the existing completion declaration. Record the snapshot digest, task, admitted permissions, code base and model setting. Ensure the recording includes the exact reads needed for the complete legitimate brief: strict replay will not invent missing attendee context. If necessary, the demo worker captures a fresh controlled recording with those safe reads before containment; do not weaken the replay engine.

Once execution is authorized, check the owned live engine's loaded revision and use fresh isolated data paths, not the managed recording, for real repair evidence. Confirm the installed coding runtime and GitHub access are usable. `orca`, `codex`, `gh` and `uv` were found during this planning review; authentication and provider execution were not checked. Reuse the existing scripted probes for transport debugging if needed, while labelling them scripted. A fresh model-backed repair is a different claim.

Person A's worker settles only the shapes required immediately: repair job identity/progress, an evidence wrapper around existing `DetonateResult`, exact code/snapshot references and the PR URL. Do not define a universal job system. Rule/exposure shapes are settled when their milestones begin.

Exit with one-page worker briefs and no open question about which repository, snapshot, task or tool path the repair is using. This ten-minute checkpoint is a setup check, not a new benchmark or exhaustive engine review.

### M1: real repair job, real PR, saved regression

**A worker scope:** incident/job linkage and evidence reporting in `engine/api/`, `engine/handoff.py`, the existing event store/fold, and shared contracts/fixtures. Reuse handoff and proof lifecycle; add a small helper only if the current modules cannot hold the focused change. Do not change gateway decisions or the sandbox judge.

**B worker scope:** the local supervisor in `mcp/`, MCP/chat tool wiring, and the incident/handoff UI. Reuse the existing approval and progress-card components. A proposed `repair_incident` action obtains the handoff through HTTP and privately sends it to the coding runtime. Keep the full prompt and capability out of Miragio's model continuation, as the current handoff already does.

The proposed workflow is concrete:

1. One explicit operator action creates a repair job and launches one coding worker in its own Orca worktree, on the recorded `special-improvements` base. Keep the existing copy-prompt handoff available as a fallback.
2. Preserve the synthetic snapshot, clean counterpart and trusted task requirements in `tests/regression/`, with a small reproduction command/test. Sanitization removes credentials and capabilities while retaining the attack text as marked untrusted data.
3. The worker commits the regression artifact, makes the smallest prompt/code repair, then commits the candidate before final verification. The coding worker's repair scope is the demo agent and its regression files; it cannot fix the demo by changing the engine's verdict, relaxing permissions or replacing the attack input.
4. Run `uv run python -m engine.cli detonate --incident <id> --runs 3 --json` from the repair checkout. Give it private copies of the required snapshot/state paths. Its sandbox therefore rebuilds the candidate code. Do not call a main-checkout HTTP `/verify` endpoint and claim it tested the worker's code.
5. The trusted local supervisor reads the command's exit status and JSON output, records the snapshot digest and clean checkout SHA, and sends that evidence to the engine over HTTP. The private verification process must not append directly to the running engine's shared database. Person A's narrow report path records the evidence on the original incident without rerunning main's code.
6. The worker pushes and creates a draft PR with the incident, regression and verification output. Use `gh pr create --base special-improvements --draft --body-file ...`; the supervisor reads its real URL, `baseRefName` and `headRefOid` with `gh pr view --json ...`. A terminal sentence saying “done” is not the PR receipt. The observed base must be `special-improvements` and the head must equal the tested commit. [GitHub CLI creation](https://cli.github.com/manual/gh_pr_create) and [PR JSON fields](https://cli.github.com/manual/gh_pr_view) cover these operations.

Draft contract names for alignment, not existing routes: `POST /incidents/{id}/repair-jobs`, `GET /repair-jobs/{job_id}`, and a loopback supervisor report route `POST /repair-jobs/{job_id}/report`. Keep states to `queued`, `running`, `verifying`, `pr_open`, `failed`; reports carry an error or artifact reference rather than terminal transcripts. Reuse `fix.verified` and `/incidents/{id}/pr` where possible. A local trusted supervisor is sufficient here; distributed worker authentication and signed attestations are deferred.

**Commit checkpoints:** save regression/job contract; show a real queued/running worker; return parsed verification evidence; show the actual PR. Each is a coherent working commit, approximately every 10–15 minutes. Only the directly relevant check is required at each checkpoint.

**Acceptance:** before-fix evidence reproduces harm; the final committed candidate reports blocked `3/3` and legitimate task completed `3/3`; one clean counterpart also completes; the real PR head matches the candidate. Use the original unrepaired candidate as the negative check rather than manufacturing another bad fix. Allow one repair retry, then report failure and keep the run contained.

### M2: launch the merged repair, finish the task

**A worker scope:** the restart/rollout HTTP seam, event linkage and shared shapes in `engine/api/` and contracts. Reuse the existing restart and run-admission checks. **B worker scope:** extend the same installed local supervisor with a merged-revision launcher and wire the existing clean-restart control to the resulting run. No cloud deployment service and no new agent framework.

1. The human reviews and merges the repair PR into `special-improvements`. The supervisor fetches the PR's `baseRefName`, `state` and `mergeCommit` via GitHub CLI, confirms the integration target, and materializes that exact merged revision in an Orca-managed checkout. It does not switch or reset the user's main checkout.
2. Compare the verified candidate's code tree with the merged tree. If identical, reuse the verification evidence. If relevant content changed, run the existing verification once against the final merged candidate before continuing. Track both commit IDs; squash merge need not preserve the candidate SHA.
3. Build/register the repaired factory with the intended permissions and legitimate-task declaration **before** restart approval. The new engine guard will reject registration changes after approval; do not approve first and then silently install a different spec.
4. For the original frozen compromised run, use the existing human kill decision, then human clean-restart approval. Launch the registered factory from the merged checkout with fresh model context and the exact approved task. Do not use `/resume` to bypass its confirmed-incident refusal. The SDK's normal start claims the single matching queued restart.
5. Show the resulting `restarted_from` run actually entering `running` and finishing its legitimate task. Keep the old run contained. Queue creation alone is not completion.

For this prototype, select an incident where the original run has not completed any required outward task write before containment. Check its per-run ledger and preserve the synthetic service state when starting the repaired task. Confirm exactly one expected brief is produced after restart. If earlier partial writes exist, stop this recovery path and choose explicit remaining work; general payment/message idempotency is deferred. Never relaunch the whole fleet or reset shared services just to restart this agent.

**Commit checkpoints:** read merge identity and resolve checkout; register then claim approved restart; show actual completion with incident/PR/run links. **Acceptance:** merged code is the launched code, the old run cannot start new tool effects, the exact approved task completes, and the expected brief is not duplicated. One focused restart integration check plus the actual task run is enough; reuse the engine's existing identity tests.

By minute 75, this is the required end-to-end result. If it is not working, C0 keeps the remaining time on repair/recovery and defers M3/M4. All four features remain in the proposal; missing features are reported pending rather than represented by success badges.

### M3: a small Rules tab, one authoritative revision

**A worker scope:** rule revision/activation HTTP and event folding; the policy overlay in `engine/gateway/`; the same restrictions in sandbox verification; contracts/fixtures. **B worker scope:** one Rules page/nav entry and a readable Create/Preview/Activate form, plus Miragio's rule proposal. Reuse installed UI controls and existing HTTP clients.

The first rule type is deliberately narrow: restrict named tools and exact allowed recipients for a named demo agent. Derive its readable sentence from typed fields. Use existing `Allowlist` shapes, a content digest as version, and the engine's existing durable event store for draft/activation history. No arbitrary predicates, YAML-first editing, company permission discovery or mutable P1–P6 text editor.

Proposed HTTP surface: list revisions/drafts, create a draft and activate a selected revision with `{actor, reason}`. These names and models are aligned by A/B at the milestone start. The Rules page and Miragio both use that same store. The default canonical policy, registered role allowlist and activated restriction intersect; a rule can narrow the role's permissions, not expand them.

Extend the existing admission-time policy copy with the active rule revision, preserve it in the snapshot and verification evidence, and expose it in HTTP responses. The local SDK continues sending tool checks to the engine; there is no need to implement a second local policy evaluator or bundle cache in this sprint. The versioned HTTP policy-to-harness contract remains the design; the engine is the single-laptop harness's enforcement service. A separate authenticated bundle pull remains for a later standalone harness.

Human activation affects new runs. Existing runs retain their admitted copy, including a restart already approved under an earlier revision. A failed or false-positive case must not silently activate a denial. This is an explicit product extension to the original predefined-policy demo, to align before implementing it.

**Commit checkpoints:** persist/list a draft and revision; preview and activate from the UI; demonstrate a new run's pinned version. **Acceptance:** one real activation, one refused action outside the restriction, and the legitimate task still permitted. A single focused check that old/new runs use their own policy copies suffices. Use the same existing hard-rule evaluator for gate and verification; do not create UI safety logic.

### M4: assess one sibling, label the rest accurately

**A worker scope:** a small exposure job and a calendar input-copy adapter in `engine/detonation/`/`engine/api/`, plus its contracts/fixtures. **B worker scope:** candidate selection and per-agent results on the incident/fleet surface, with Miragio summarizing those results. No fleet scheduler or broad scanner.

Use the original recorded attack and one compatible meeting-assistant sibling with its **own** task/context/recordings and captured pre-fix code revision. The current invoicing, outreach and PR-reviewer roles are not automatically compatible with a calendar attack. If there is no compatible sibling recording, explicitly prepare one controlled synthetic sibling; do not transplant the incident snapshot or declare every source agent exposed.

Copy only the malicious calendar item into the sibling's matching untrusted result, clear recorded model replies and run one isolated attack replay plus one clean counterpart. Preserve that agent's permissions and legitimate-task declaration. Report its code/policy/snapshot revisions, effects and `1/1` observations; reserve `3/3` for the original final repair verification. Never start a live tool during this evaluation.

Results distinguish `vulnerable` (the compatible replay attempts prohibited effects), `blocked` (the compatible replay completes useful work without the attack effect), `not_applicable` (a specific missing capability/input path), and `could_not_evaluate` (missing recordings, tool errors or unsupported context). Mere capability matching is exposure information, not a confirmed result. Keep live healthy agents running; pausing an agent is a separate human decision.

**Commit checkpoints:** produce a per-agent result using existing sandbox helpers; show it in UI/chat. **Acceptance:** one actual compatible result and clean counterpart, one explicit incompatible/unsupported result, no original incident overwrite and no real service writes. If this exceeds 15 minutes, keep the exposure list with honest unassessed states and defer execution; do not substitute the original agent's proof for the sibling's.

### M5: ten minutes to make the journey usable

Walk through the incident, launched repair worker, saved regression, actual PR, activated rule if delivered, fleet result if delivered, human merge/restart and completed new task. Read the receipts already produced by that same code composition. Repeat provider verification only when relevant code, policy or snapshot changed; do not run another model matrix for presentation edits.

Run the builds/typechecks for changed experience packages once, and only the focused engine/SDK checks for changed seams. Fix a broken control or wrong result label immediately. Defer polish, broad refactors, expanded CI, fuzzing, load tests, enterprise authentication and distributed rollout. Freeze feature scope at minute 110.

Record exact feature PR heads, merged/active revision, verified repair head, snapshot/policy versions, observed replay counts and the final restart result. Separate pending PRs and queued jobs from completed work. The final story must be runnable with documented local commands and must never depend on a fabricated GitHub link or recorded success presented as fresh proof.

### Worker brief and delivery cadence

Every coordinator sends a worker: the milestone goal and demo step; owned files; `special-improvements` as base and PR target, the exact dependency/base SHA and shared shapes; the no-main-merge rule; the smallest permitted implementation; one observable acceptance check; a 10–15-minute commit checkpoint; and the time at which to report a blocker. Workers own review, validation, commits, pushes and PRs. Coordinators own product review and composition, not implementation takeovers.

After the user authorizes implementation/pushes, commit each working step and push at least every 20 minutes or on a dependency handoff. Open a draft feature PR against `special-improvements` as soon as the first coherent slice works; update it as commits arrive. No full-suite rerun on every small commit. The product-generated repair PR opens once its final candidate is verified; ordinary feature PRs may be drafts sooner. Human merges into `special-improvements` use squash/rebase only. After an authorized merge, the coordinator verifies the reviewed tip, updates the integration checkout with `--ff-only`, releases the settled worker and removes only clean, inactive, fully delivered feature worktrees through Orca. No main merge or main checkout update is part of delivery.

Special Improvements remains an independent integration/documentation worktree. Publishing `special-improvements` and this plan starts no coordinators/workers and changes no implementation. Implementation and feature-code pushes wait for the user's start instruction.

## Reference points

- [PRODUCT.md](../PRODUCT.md) sections 3, 5 and 6: incident flow, bisection and the existing coding-agent handoff.
- [CONTRACTS.md](../CONTRACTS.md) sections 1, 3, 5, 6, 8, 11, 12 and 13: ownership, run lifecycle, APIs, CLI verification, HTTP boundaries, SDK, MCP and Miragio.
- [docs/UX.md](UX.md): incident story and human controls.
- [Protected fleet startup](../START.md#protected-source-fleet-fresh-m2-synthetic-rehearsal): local source-fleet path, separate from managed recording.
- [GitHub CLI pull request creation](https://cli.github.com/manual/gh_pr_create): reuse available GitHub tooling for the coding worker.
- [GitHub CLI pull request JSON](https://cli.github.com/manual/gh_pr_view): actual PR head, state and merged commit identity.
- [OWASP excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/): enforce scoped permissions at execution boundaries.

Remaining dependencies at the reviewed main revision: a usable complete recording; local coding/GitHub/provider access; the small job/result HTTP seam; explicit rule versioning; one compatible sibling recording; merged-revision launch; and the operator's merge/restart decisions. Admission-time policy and restart-identity authority now exist and should be reused. General side-effect deduplication is deferred under M2's no-prior-task-write condition. This proposal does not authorize implementing any of these changes yet.
