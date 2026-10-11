# Mirage special improvements proposal

Status: proposal only. No feature implementation, API change, model execution or deployment is authorized by this document.

## The experience we want

One incident should improve the whole fleet. The operator watches Mirage contain a compromised run, prove the cause, write a tested repair, preserve the lesson, assess other agents and safely return work to service.

The proposed four features form one journey:

1. Mirage coordinates the coding agent and opens a verified repair PR.
2. The incident becomes a permanent regression case and a proposed prevention rule.
3. Mirage checks whether the vulnerability applies to the rest of the fleet.
4. The human rolls out the verified fix and approves clean restarts.

The Rules tab and Miragio chat support this journey. They are not a separate policy-discovery project. Mirage does not discover the permissions a company should grant.

These are future proposals. PRODUCT.md currently says Mirage hands the incident to the user's coding agent and does not write the fix itself; this document proposes extending that experience. Approve the product/contract change before implementation. Existing engine fixes and the working demo remain prerequisites.

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

After reviewing the PR and simulation evidence, the human merges the change. Mirage shows which agent revisions are ready, asks for the restart decision and confirms that the original legitimate task finishes under the repaired version.

### Smallest complete implementation

For the demo, deployment means updating the approved local agent/configuration to the merged revision and relaunching its authorized task. Reuse existing PR linkage, fix verification, run restart/resume APIs and SDK execution. Do not build a general cloud deployment platform.

Bind evidence to exact code, configuration and policy versions. Confirm the merged revision matches the verified candidate or verify the final merged tree. A green PR alone does not establish the running agent's identity.

The human approves the clean restart. Revoke the old run's authority and use fresh model context; do not continue the compromised conversation. Pin the new task and policy scope, use `restarted_from` to link the runs, and distinguish queued restart approval from actual running/completed SDK execution.

Preserve receipts and idempotency for writes that completed before containment so a fresh task does not resend messages, duplicate payments or replay irreversible effects. If the original context cannot be reconstructed safely, remain contained and request a new authorized task rather than claim recovery.

Start with the repaired run. Broader fleet rollout follows the exposure evidence and separate explicit human approval. Halt rollout on verification or execution failure. A rollback also uses an approved revision and keeps suspect runs contained; it must not simply widen permissions or reactivate the compromised context.

### Feasibility and acceptance

Doable for one controlled local demo agent. Arbitrary hosting, distributed package rollout, automatic merge and automatic restart are deferred.

Accept when the approved version is actually running, the old token cannot perform effects, the legitimate task completes without duplicate writes, and the audit links incident, PR head, merged revision, policy version, restart approval and resulting run. A queued run, fixture replay or deployment button click alone is not acceptance.

## Delivery order and scope

| Order | Increment | Dependency | Effort estimate after engine fixes |
|---|---|---|---|
| 1 | Durable regression artifact and clean control | Trustworthy snapshot and verification | Small: roughly 1–2 hours |
| 2 | Integrated coding job to draft PR | Regression artifact, bounded runtime/GitHub access | Medium: roughly 2–4 hours |
| 3 | Two or three-agent exposure assessment | Per-agent snapshots and compatible replay | Medium: roughly 2–4 hours |
| 4 | Verified local rollout and clean restart | Merged revision, restart authority and receipts | Medium: roughly 1–3 hours |

These are planning estimates, not promises or additive work that must fit the benchmark budget. Build one complete incident journey before adding a second agent class. The Rules editor follows the policy-authority dependency; a structured preview can demonstrate the concept before activation is implemented, clearly labelled as a proposal.

Reuse engine proofs, HTTP/SSE and Miragio's existing operator flow. Avoid separate safety logic in the UI, invented live evidence or fake GitHub links. `contracts/models.py` remains the source of truth. Each approved implementation increment gets its own Orca-managed worktree and atomic PR; Special Improvements holds this proposal only.

The proposed user journey is: confirm the incident, coordinate a verified repair, preserve its regression, assess fleet exposure, review and merge the PR, then explicitly restart the selected agent. Every badge and progress step must link to the evidence behind it.

## Reference points

- [PRODUCT.md](../PRODUCT.md) sections 3, 5 and 6: incident flow, bisection and the existing coding-agent handoff.
- [CONTRACTS.md](../CONTRACTS.md) sections 1, 3, 5, 6, 8, 11, 12 and 13: ownership, run lifecycle, APIs, CLI verification, HTTP boundaries, SDK, MCP and Miragio.
- [docs/UX.md](UX.md): incident story and human controls.
- [GitHub CLI pull request creation](https://cli.github.com/manual/gh_pr_create): reuse available GitHub tooling for the coding worker.
- [OWASP excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/): enforce scoped permissions at execution boundaries.

Open dependencies: accepted engine revision; policy authority/versioning; compatible per-agent replay; a bounded coding runtime; exact revision verification; restart launch truth; and side-effect deduplication. This proposal does not authorize implementing any of those changes yet.
