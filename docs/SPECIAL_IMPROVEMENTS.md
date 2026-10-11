# Mirage special improvements proposal

Status: authorized implementation in progress, 2026-10-11. Integration branch: `special-improvements`; M5 starts from exact integrated base `a407ce039970668defbfdb50cf136c28c8dcf38b`. The user has authorized all four features and their integration on this branch. The proposal below preserves the full scope; the delivery receipts distinguish implemented slices from the remaining end-to-end gates. Provider execution and the product coding-worker launch are serialized by the root coordinator. Policy activation, repair-PR merge and clean restart remain separate explicit operator decisions.

## Key rule: integrate only on special-improvements

**Every worker branches from `special-improvements`, every PR targets it, and nobody merges or pushes these changes to `main`.** The user explicitly chose `special-improvements` as the integration branch. This instruction overrides repository workflow defaults that target or update main after a feature merge.

- Every improvement worker branches from the current reviewed `special-improvements` tip, using an Orca-managed worktree with an explicit base branch. The integration worktree remains independent, with no parent in main.
- Every feature PR and the Mirage demo's generated repair PR targets `special-improvements`. Put the base branch and exact base SHA in every coordinator/worker brief; never accept the GitHub default base implicitly.
- A human may merge approved PRs into `special-improvements`. Coordinators and workers do not merge into `main`, open a delivery PR targeting `main`, or enable auto-merge.
- Rebasing `special-improvements` onto `origin/main` is allowed when requested. It brings engine changes into this branch; it does not authorize delivery back to main. Coordinate before rewriting the shared integration tip, then give active workers the new exact base.
- After a human-authorized feature merge, update the integration checkout with `--ff-only`, verify the reviewed feature head and clean up settled worktrees through Orca. Leave the main checkout untouched.

Implementation is now authorized and underway. Keep every implementation checkout independent and Orca-managed, with an explicit reviewed `special-improvements` base SHA; publication of this proposal does not itself execute a provider job or operator decision.

## The experience we want

One incident should improve the whole fleet. The operator watches Mirage contain a compromised run, prove the cause, write a tested repair, preserve the lesson, assess other agents and safely return work to service.

The proposed four features form one journey:

1. Mirage coordinates the coding agent and opens a verified repair PR.
2. The incident becomes a permanent regression case and a proposed prevention rule.
3. Mirage checks whether the vulnerability applies to the rest of the fleet.
4. The human rolls out the verified fix and approves clean restarts.

The Rules tab and Miragio chat support this journey. They are not a separate policy-discovery project. Mirage does not discover the permissions a company should grant.

These four feature definitions are the approved product extension. PRODUCT.md describes the original copy/open handoff; this extension adds Mirage's local supervision while the actual coding worker still writes and verifies the fix. An approved feature is not a delivered acceptance result. Existing engine fixes and the working demo remain prerequisites.

## Delivery receipt index

This checkpoint records evidence available at M5 admission, not final journey completion. Receipt paths are operator-local artifacts; fixtures and scripted recordings are labelled separately from fresh model execution. Protected tools currently use synthetic process-memory services. No receipt here establishes external Gmail, Calendar or HubSpot acceptance, production deployment or remote operator authentication.

| Gate | Observed evidence | Remaining acceptance |
|---|---|---|
| M0 original containment and negative control | [Baseline receipt](/tmp/mirage-special-baseline-rugw8sgc/ACCEPTANCE.md): frozen `run_001`, `inc_001`, deterministic from-freeze harm `3/3`; fresh unrepaired attack blocked `0/1`, useful `1/1`, CLI exit 1. The actual supervisor's later [fresh unrepaired baseline](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-repair-JVBxFJ/baseline-receipt.json) shows harm `3/3`, attack blocked `0/3`, useful `3/3`, passed false and no effect errors. Controlled/scripted capture precedes provider-backed continuation and fresh replay. | Preserve the original evidence and digest throughout repair, exposure and recovery. The later parsed baseline file does not itself retain the process exit status. |
| M1 clean counterparts | Corrected [clean recording](/tmp/mirage-special-controls-v2-rugw8sgc/snapshots/inc_special_clean.json) uses `agents.run_demo_fleet:meeting_assistant`; [fresh clean receipt](/tmp/mirage-special-controls-proof-rugw8sgc/inc_special_clean.receipt.json) and [fresh sibling clean receipt](/tmp/mirage-special-controls-proof-rugw8sgc/inc_special_sibling.receipt.json) each show blocked/useful `1/1`, exit 0, no effect errors. | The repaired committed candidate still needs its own original attack `3/3`, useful `3/3` and clean `1/1`. |
| M1 repair integration | Baseline #162, repair backend #163, supervisor/experience #167 and same-factory guard #170 are merged to `special-improvements`; exact GitHub heads/merge commits are below. Actual [dashboard start receipt](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m1-product-pIhgxY/ui-repair-started.json) and [HTTP job readback](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m5-http-1cv1zoiq/repair-start-readback.json) identify `repair_af57f917e8ea446f9db3c3bb881a2bcf`, pinned base `4813f26c44ff58e3ca831031d1e640c0da4658ca`. Root reports actual coding worker `ctx_1f8727d89b21` in independent `mirage-repair-repair_af57f917e8ea446f9db3c3bb881a2bcf`, supervised by operator Run `run_8685b7eb4572`. Latest [HTTP progress receipt](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m5-http-1cv1zoiq/repair-progress-readback.json) is failed/`verification_failed` at `2026-10-11T04:37:42.013399Z`, with no candidate SHA, verification or PR. | Owner investigation is required. Durable regression, exact tested candidate and independently read OPEN draft PR receipt remain pending; startup and worker launch are not repair acceptance. |
| M2 recovery | Engine #161 and launcher/experience #168 are merged. [Owner's report](/tmp/mirage-m2-recovery-report.md): web/MCP builds, 92 focused MCP checks, 14 SDK/launcher checks and five UI state assertions passed; actual guarded preparation/launch routes are mounted. [Nonsecret configuration](/tmp/mirage-special-baseline-rugw8sgc/m2_nonsecret_config.json) and [original service checkpoint](/tmp/mirage-special-baseline-rugw8sgc/original_services.json) preserve the task, full spec and empty outbox before containment. | Actual merged code/config/policy/checkpoint preparation, explicit restart, fresh useful completion and exactly one expected brief. |
| M3 Rules | Engine #159 and experience #160 are merged. [HTTP/gateway/MCP receipt](/tmp/mirage-m3-experience.tmx2kY/handler-proof.json), [desktop](/tmp/mirage-m3-experience.tmx2kY/desktop.png) and [mobile](/tmp/mirage-m3-experience.tmx2kY/mobile-proof.png) show durable create/preview/explicit activation, audit reason, old run retaining null revision and new run pinning `fb7c5383034e8126e4ef669ad99e2cc27dbf971fa78da9a0461dfad15950e725`. The final replay head `c7b8bcb5d22f63b77cc854237b8d8bec9b240383` passed builds and 72 focused MCP/Miragio checks; owned Rules UI/helper sources match the browser-tested `cee726427a081699ac2694e245aeab4cc36ad32f` composition. Engine includes immutable revisions and trusted verifier `--policy-file`. | Final complete journey readback. Allowed/forbidden calls in the browser receipt are scripted gateway checks with no model or real callback; they do not prove fresh task completion. |
| M4 sibling exposure — complete within declared coverage | Engine #169 and experience #164 are merged. [Actual model receipt](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-special-exposure-1557e2mq/receipt.json) and [job effects](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-special-exposure-1557e2mq/model_exposure_job.json) show independent sibling job `det_001_f0fa71e4b205`: own context at pre-fix `74afe5b633a80755d202022696f985771457fecd`, copied `in_03`, attack compromised/useful `1/1`, clean blocked/useful `1/1`, no errors. [Final engine report](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m4-composition-im5rbf0p/M4_COMPOSITION.md) records 195 focused checks including healthy-run HTTP/gateway completion during scripted exposure. After actual original bisection, [mounted shared MCP receipt](/tmp/mirage-exposure-ui/M4_MOUNTED_TRANSPORT.json) and [independent HTTP readback](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m5-http-1cv1zoiq/mounted-exposure-receipt.json) show job `det_001_ee6e477a4756` completed: invoicing `not_applicable`, named unavailable control `could_not_evaluate`, one audit, original confirmed `3/3` and unchanged snapshot/checkpoint. | The mounted runtime's sibling remains unassessed; its separate accepted model proof is not transplanted into that job. Healthy continuation is scripted concurrency evidence. None of these observations replaces original candidate repair `3/3` or proves external-service coverage. |
| M5 runtime startup | Historical containment #175, visible reason #174 and Orca repository resolution #176 are merged. The [ordinary runtime receipt](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m1-product-pIhgxY/runtime.json) pins `4813f26c44ff58e3ca831031d1e640c0da4658ca` in independent checkout `mirage-operator-446a24e5`. [M5 actual GET-only readback](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m5-http-1cv1zoiq/receipt.json) confirms `run_001` failed with the explicit owner-not-restored reason, one system retirement event, confirmed verdict and unchanged raw snapshot/checkpoint bytes. | The earlier bootstrap failed with `repo_not_found` before services/providers; corrected startup is now observed. Recovery returned 409 at the startup checkpoint; the separate later repair-start readback above is running. Actual repair/PR/merge/restart and final readback remain pending. |

Immutable original raw-file SHA256: `4c8b351894bb898fcae23aa3d9811d2152aba069fa0504357f878a7776a9da1f`. Corrected clean raw-file SHA256: `5f6f74229e16fd65b92e712213ea6cc7dcd1855e11e476fcb91760cfd303b54f`; sibling: `0dff6618bb1c37459bb0329c7fb9a65c217deed6c7ed1a13052b093a91a88d48`. These raw-file hashes are distinct from the API's canonical sanitized snapshot/policy digests. Earlier failed controls, including controls-v1, are excluded from acceptance.

GitHub readback confirms these feature receipts. A merged feature is implementation delivery, not final candidate/provider/restart acceptance:

| PR, all targeting `special-improvements` | Reviewed feature head | Actual squash merge |
|---|---|---|
| [#162 baseline](https://github.com/GabDestal/Mirage/pull/162) | `74afe5b633a80755d202022696f985771457fecd` | `d1e812ab963c8287ac69b98801d662bdf076ff75` |
| [#163 repair backend](https://github.com/GabDestal/Mirage/pull/163) | `d0c5fd22e235df313df234819bc3ae81c7795eb0` | `a407ce039970668defbfdb50cf136c28c8dcf38b` |
| [#167 repair supervisor/experience](https://github.com/GabDestal/Mirage/pull/167) | `46335850452f982ce8987270c210f93066a746b2` | `a3f2c45292896301313b642d18138587a2620a77` |
| [#170 same-factory control](https://github.com/GabDestal/Mirage/pull/170) | `7d2a6c15663d715b773cc3fcdaa300be774f5f4f` | `0e590ffacc7f02e17e950170a225dd06cbd5aa9b` |
| [#159 Rules engine](https://github.com/GabDestal/Mirage/pull/159) | `996a611656b67d613e5b56496d5b7d39fec3ba6d` | `0f13abce21888133367f6f5d511813aec3fdeb4a` |
| [#161 recovery engine](https://github.com/GabDestal/Mirage/pull/161) | `92a4def0197ba7b1d670654adf35a7a9c0b7d1cf` | `f1312cbf0cb9603162a4e867f329da774b94995a` |
| [#160 Rules experience](https://github.com/GabDestal/Mirage/pull/160) | `c7b8bcb5d22f63b77cc854237b8d8bec9b240383` | `096f1d3f66c9b78365929f88452f45c2cd5b8238` |
| [#169 exposure engine](https://github.com/GabDestal/Mirage/pull/169) | `f19b232029914027a326f773f4f7a6e491135783` | `0e7e77d2b61c6e00059cc15100de73d8c599a77f` |
| [#168 recovery launcher/experience](https://github.com/GabDestal/Mirage/pull/168) | `6cb9fc1343c1ad9d35674ed3bc8aff2dbf95835e` | `90d74ef4838f92b2d677374198e0025eb23ec1c0` |
| [#164 exposure experience](https://github.com/GabDestal/Mirage/pull/164) | `6d1168a9fc3acb75e95a4dc8c1f23b6e748e6c48` | `83d4991984542991637276d0e8708b01624e7fcd` |
| [#174 containment reason visibility](https://github.com/GabDestal/Mirage/pull/174) | `dfd3ff299954427d91eefb7f7b2195d94d06fb6e` | `c51db572bf352ca6248b31cd8d235e24bd015d6a` |
| [#175 ownerless original containment](https://github.com/GabDestal/Mirage/pull/175) | `24f5b7c433ad1752ac73bfc36add3fa938d7e64d` | `cc636f4f6590010ebc6302f29c53814c2dfc2b79` |
| [#176 managed repository resolution](https://github.com/GabDestal/Mirage/pull/176) | `275f393a1b7599857459ad37a4d9df48d9409423` | `4813f26c44ff58e3ca831031d1e640c0da4658ca` |
| [#177 explicit failed-repair retry](https://github.com/GabDestal/Mirage/pull/177) | `498c71d785cfe900f12e8ec3727f15e4747a831d` | `e463fe91a829b9c79135911aff1ef2a998742e2c` |

The M2 owners' focused trusted-config-source checks pass. The merged launcher accepts an identical private checkpoint copy while independently checking the recorded original; the earlier path-identity mismatch is resolved in source and focused checks. Final runtime HTTP provenance and actual restart remain pending. The original recording still identifies `ScriptedModel`, and its raw bytes remain immutable.

Actual repair-job canonical sanitized snapshot digest: `e771a17714a9ccc49ef8fd0c61118dec8b69e00ba8c47667f767b384dd319442`; original harmful-ledger digest: `46ec0c05e63a3888dc637fc591bb52868d82da88705363c79df14cae25aa49a3`. The original raw-file SHA above remains separate. These identify the actual job's exported evidence, not a repaired result.

The first actual worker committed prompt-only candidate `c586b86daf9dbe9a6eb0da5c4b114ccb10349e4a`. Its [actual fresh candidate command receipt](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-repair-JVBxFJ/candidate-e771a17714a9.json) failed: exit 1, attack blocked `1/3`, useful `3/3`, passed false, no effect errors. It produced no repair PR and no rollout/restart acceptance. Merged #177 adds an explicit new repair request after failure and validated private failure evidence for the next worker; root reports 11 focused checks and actual private failed-seed import. Root/owner is refreshing the runtime with the same retained state before the actual UI retry; the failed attempt stays recorded. Source delivery and seed import do not establish a successful retry.

The [actual original-factory bisection receipt](/var/folders/nt/ctb1fvf572x6g8b36l50_qqm0000gn/T/mirage-m1-product-pIhgxY/bisection-receipt.json) used unchanged `4813f26c44ff58e3ca831031d1e640c0da4658ca`, five untrusted inputs and one fresh replay per input. Only removal of `in_03` gave zero harm with no effect errors. Each other removal retained harm `1/1`; the two email-removal cases also recorded `LookupError`s, which did not erase the harmful effects. Original confirmed baseline `3/3` remains unchanged. This is the observed causal gate for the mounted fleet assessment, not a new repair verification.

### One HTTP-only operator acceptance journey

Use the root-owned loopback engine and the exact integrated checkout it supplies. Read `/openapi.json`, `/runtime`, `/runs`, `/incidents/inc_001` and `/events?after=0` through HTTP to establish current mode/identity and available contracts; audit evidence is the relevant `human.action` events. Do not import engine modules into a demo or HTTP runner. Keep private context/capabilities in the trusted supervisor; public receipts contain only safe progress, references and counts. Never reset the baseline database or launch another fleet to manufacture a clean result.

For the pinned runtime receipt above, API is `http://127.0.0.1:57208`, chat is `http://127.0.0.1:57209` and dashboard is `http://localhost:55110/incidents/inc_001`. These are owned temporary ports, not permanent service addresses. A fresh rehearsal uses the new trusted runtime receipt's URLs and exact code revision. Minimal readback commands for this instance:

```sh
mirage_acceptance_api='http://127.0.0.1:57208'
curl --fail --silent --show-error "$mirage_acceptance_api/runtime"
curl --fail --silent --show-error "$mirage_acceptance_api/incidents/inc_001"
curl --fail --silent --show-error "$mirage_acceptance_api/repair-jobs/repair_af57f917e8ea446f9db3c3bb881a2bcf"
curl --fail --silent --show-error "$mirage_acceptance_api/events?after=0"
```

1. **Freeze and confirm.** Read the original incident, run and ledger through HTTP. Match the immutable snapshot and original freeze/harmful proof; the old run must remain contained. After its recorder exited, startup may append the explicit system reason retiring only that ownerless confirmed original to `failed`; read that reason and unchanged verdict/snapshot rather than presenting it as a currently owned frozen process. Keep the baseline negative result visible: attack blocked `0/1`, useful `1/1`. A replay recording alone is not a fresh fix check.
2. **Explicit repair.** In the installed operator runtime, the operator submits `{incident_id: "inc_001", actor, reason}` to the chat service's `POST /chat/repairs` once (or approves MCP `start_repair`). The trusted supervisor creates the engine job with `POST /incidents/inc_001/repair-jobs` and launches the worker; calling that engine route alone only creates queued state. Poll the engine's `GET /repair-jobs/{job_id}` and incident job list; require root's actual launch receipt for a coding worker in an independent Orca worktree at the pinned `special-improvements` base. A failed job permits a new explicit request through the same route, with trusted private failure evidence validated against the unchanged incident and baseline; keep the old failed job visible. A 202/queued response is not proof of launch or repair. Do not retry a lost create response blindly.
3. **Exact candidate and real PR.** Read public job progress through HTTP; privately the supervisor exports the original/clean recordings, runs the installed CLI from the clean committed repair checkout, and imports evidence with `POST /repair-jobs/{job_id}/report`. Require CLI exit 0, no replay errors, attack blocked `3/3`, useful `3/3`, clean blocked/useful `1/1`, durable regression files and the actual GitHub receipt: OPEN draft, base `special-improvements`, `headRefOid == candidate_sha`. A candidate verified by another loaded checkout, a fixture URL or `queued` status fails this gate.
4. **Manual merge and prepare.** Wait for the operator's repair-PR merge into `special-improvements`. Read the real merged commit, then explicitly call the chat service's `POST /chat/recovery/{job_id}/prepare` with `{}` (or MCP `prepare_recovery`). The trusted supervisor prepares the actual merged checkout and full factory registration, reads private `GET /incidents/inc_001/recovery/provenance` and submits `POST /incidents/inc_001/recovery/report`, binding merged code, full spec, nonsecret configuration/source digest, exact original service checkpoint, task/criteria and effective policy. Read public `GET /incidents/inc_001/recovery` and require `prepared`; preparation neither approves nor launches. Compare candidate/merged trees and policy; reverify with the trusted `--policy-file` copy if relevant content changed. The original checkpoint has no prior outward task write; preserve it rather than resetting shared services.
5. **Explicit restart and useful completion.** Record the operator's `POST /runs/run_001/kill` decision where needed, then separate `POST /runs/run_001/restart` approval with `{actor, reason}`. Take the returned queued run ID and explicitly submit `{queued_run_id}` to the chat service's `POST /chat/recovery/inc_001/launch` (or approve MCP `launch_approved_recovery`). Require a fresh SDK run with `restarted_from` linking the original, actual merged-code launch, transition to running/completed, no execution errors and exactly one nonblank brief to the demo user covering both expected meetings and times. Read the public run/events/recovery outcome over HTTP; confirm old-run authority cannot create effects. Approval or a queued run alone is not recovery. Never use `/resume` to bypass confirmed-incident containment.
6. **Rules create, preview and activate.** Read `GET /rules/agents`, create one narrow named-agent draft with `POST /rules` and `{agent, allow}`, then `POST /rules/{version}/preview` for its readable restriction and digest. Read `GET /rules/{version}` after refresh; the draft must remain inactive. Explicit operator `POST /rules/{version}/activate` with `{actor, reason}` records activation. Through HTTP compare an existing run's admitted revision with a new run's active revision; show an outside-recipient action refused and the useful authorized action permitted. UI and Miragio use the same durable store, and the SDK continues tool checks against that HTTP enforcement service. No second local evaluator or silent activation.
7. **Isolated sibling exposure and healthy continuation.** Read `GET /incidents/inc_001/exposure-candidates` and bounded job state through `GET /exposure-jobs/{job_id}` or `GET /exposure-jobs?incident_id=inc_001`. An explicit operator assessment uses `POST /incidents/inc_001/exposure-jobs` with `{agent_names, actor, reason}` and returns 202/queued, not results. Match the real sibling's own task/recordings/policy/code plus copied causal input, actual attack/clean effects and honest `vulnerable`, `blocked`, `not_applicable` or `could_not_evaluate` labels. Preserve original hashes/verdict; cite the separate healthy-run HTTP/scripted concurrency receipt. During the repair provider slot, root tests mounted transport using only `invoicing` and `synthetic_unavailable_meeting_control` from the trusted manifest; these provider-free statuses do not replace the accepted actual sibling replay. No source-service write or healthy-run pause is authorized by evaluation.

Root alone holds the provider slot and ordinary operator-shell startup for the coding worker. This acceptance worker may consume supplied HTTP state and receipts; it does not start provider, repair, activation, merge or restart actions independently. Final readback must bind the same integrated feature composition and exact candidate/merged/run identities, with remaining gates stated plainly.

The immutable recording's `model_id` is `ScriptedModel`; recovery must use the explicit trusted configuration source in `m2_nonsecret_config.json`, bound to the original raw snapshot SHA, for the actual effective `openai.gpt-oss-20b-1:0` model. Preserve that full provenance manifest separately from the minimal selected nonsecret configuration map. Never edit/resnapshot the original recording to hide this distinction. Root starts the installed supervisor from the ordinary operator shell using `/tmp/mirage-m1-operator-runtime.mjs`; a dispatched coding worker cannot launch a nested worker as a substitute.

## What changed on main, and what we can now reuse

This is a historical source comparison from the original proposal's base, `6cfea0e`, to reviewed main `1e6052e073886abf36f54af10c48e8c521f4b86e`. No services, tests or providers were run for that review. These findings describe source behavior at that revision; the delivery index above records the current `special-improvements` implementation evidence. The approved feature/milestone definitions below specify the intended behavior, not additional completion claims.

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

At the reviewed main revision, current-code verification already runs from scratch, evaluates freeze-time and current permissions, and requires useful task completion. Those main merges strengthened its inputs and failure handling; they did not create a coding supervisor, a real PR, a Rules editor, a fleet assessment job or a merged-revision launcher.

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

Original baseline: `GET /policies` is read-only, agent allowlists are supplied at registration, and the default policy is defined in `engine/detection/policies.yaml`. Versioned storage and human-approved activation are the approved addition; the delivery index records the implemented Rules slices and their actual receipts.

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

The original two-hour estimate guides commit cadence; implementation has started and all four authorized features remain required. The priority is one working local journey: **confirmed incident → coding worker → durable regression → verified real PR → human merge → approved clean restart → useful task completed**, with Rules and fleet applicability accepted on that composition. Report a time overrun or blocked gate honestly; it does not remove a feature from scope.

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

The approved M1 contract now uses `POST /incidents/{id}/repair-jobs`, `GET /repair-jobs/{job_id}`, and the private loopback supervisor route `POST /repair-jobs/{job_id}/report`. States remain `queued`, `running`, `verifying`, `pr_open`, `failed`; public progress carries safe evidence references rather than terminal transcripts. Reuse `fix.verified` and `/incidents/{id}/pr` where possible. A local trusted supervisor is sufficient here; distributed worker authentication and signed attestations are deferred.

**Commit checkpoints:** save regression/job contract; show a real queued/running worker; return parsed verification evidence; show the actual PR. Each is a coherent working commit, approximately every 10–15 minutes. Only the directly relevant check is required at each checkpoint.

**Acceptance:** before-fix evidence reproduces harm; the final committed candidate reports blocked `3/3` and legitimate task completed `3/3`; one clean counterpart also completes; the real PR head matches the candidate. Use the original unrepaired candidate as the negative check rather than manufacturing another bad fix. Allow one repair retry, then report failure and keep the run contained.

### M2: launch the merged repair, finish the task

**A worker scope:** the restart/rollout HTTP seam, event linkage and shared shapes in `engine/api/` and contracts. Reuse the existing restart and run-admission checks. **B worker scope:** extend the same installed local supervisor with a merged-revision launcher and wire the existing clean-restart control to the resulting run. No cloud deployment service and no new agent framework.

1. The human reviews and merges the repair PR into `special-improvements`. The supervisor fetches the PR's `baseRefName`, `state` and `mergeCommit` via GitHub CLI, confirms the integration target, and materializes that exact merged revision in an Orca-managed checkout. It does not switch or reset the user's main checkout.
2. Compare the verified candidate's code tree with the merged tree. If identical, reuse the verification evidence. If relevant content changed, run the existing verification once against the final merged candidate before continuing. Track both commit IDs; squash merge need not preserve the candidate SHA.
3. Build/register the repaired factory with the intended permissions and legitimate-task declaration **before** restart approval. The existing engine guard rejects registration changes after approval; do not approve first and then silently install a different spec.
4. For the original frozen compromised run, use the existing human kill decision, then human clean-restart approval. Launch the registered factory from the merged checkout with fresh model context and the exact approved task. Do not use `/resume` to bypass its confirmed-incident refusal. The SDK's normal start claims the single matching queued restart.
5. Show the resulting `restarted_from` run actually entering `running` and finishing its legitimate task. Keep the old run contained. Queue creation alone is not completion.

For this prototype, select an incident where the original run has not completed any required outward task write before containment. Check its per-run ledger and preserve the synthetic service state when starting the repaired task. Confirm exactly one expected brief is produced after restart. If earlier partial writes exist, stop this recovery path and choose explicit remaining work; general payment/message idempotency is deferred. Never relaunch the whole fleet or reset shared services just to restart this agent.

**Commit checkpoints:** read merge identity and resolve checkout; register then claim approved restart; show actual completion with incident/PR/run links. **Acceptance:** merged code is the launched code, the old run cannot start new tool effects, the exact approved task completes, and the expected brief is not duplicated. One focused restart integration check plus the actual task run is enough; reuse the engine's existing identity tests.

By the original minute-75 checkpoint, this is the intended end-to-end result. If it is not working, C0 prioritizes the repair/recovery blocker and coordinates M3/M4 without dropping their authorized scope. Missing features are reported pending rather than represented by success badges.

### M3: a small Rules tab, one authoritative revision

**A worker scope:** rule revision/activation HTTP and event folding; the policy overlay in `engine/gateway/`; the same restrictions in sandbox verification; contracts/fixtures. **B worker scope:** one Rules page/nav entry and a readable Create/Preview/Activate form, plus Miragio's rule proposal. Reuse installed UI controls and existing HTTP clients.

The first rule type is deliberately narrow: restrict named tools and exact allowed recipients for a named demo agent. Derive its readable sentence from typed fields. Use existing `Allowlist` shapes, a content digest as version, and the engine's existing durable event store for draft/activation history. No arbitrary predicates, YAML-first editing, company permission discovery or mutable P1–P6 text editor.

Approved HTTP surface: list revisions/drafts, create a draft, preview and activate a selected revision with `{actor, reason}`. A/B aligned the models and routes in the Rules contract; the delivery index and HTTP journey identify the implemented names. The Rules page and Miragio both use that same store. The default canonical policy, registered role allowlist and activated restriction intersect; a rule can narrow the role's permissions, not expand them.

Extend the existing admission-time policy copy with the active rule revision, preserve it in the snapshot and verification evidence, and expose it in HTTP responses. The local SDK continues sending tool checks to the engine; there is no need to implement a second local policy evaluator or bundle cache in this sprint. The versioned HTTP policy-to-harness contract remains the design; the engine is the single-laptop harness's enforcement service. A separate authenticated bundle pull remains for a later standalone harness.

Human activation affects new runs. Existing runs retain their admitted copy, including a restart already approved under an earlier revision. A failed or false-positive case must not silently activate a denial. This is an explicit product extension to the original predefined-policy demo, to align before implementing it.

**Commit checkpoints:** persist/list a draft and revision; preview and activate from the UI; demonstrate a new run's pinned version. **Acceptance:** one real activation, one refused action outside the restriction, and the legitimate task still permitted. A single focused check that old/new runs use their own policy copies suffices. Use the same existing hard-rule evaluator for gate and verification; do not create UI safety logic.

### M4: assess one sibling, label the rest accurately

**A worker scope:** a small exposure job and a calendar input-copy adapter in `engine/detonation/`/`engine/api/`, plus its contracts/fixtures. **B worker scope:** candidate selection and per-agent results on the incident/fleet surface, with Miragio summarizing those results. No fleet scheduler or broad scanner.

Use the original recorded attack and one compatible meeting-assistant sibling with its **own** task/context/recordings and captured pre-fix code revision. The current invoicing, outreach and PR-reviewer roles are not automatically compatible with a calendar attack. If there is no compatible sibling recording, explicitly prepare one controlled synthetic sibling; do not transplant the incident snapshot or declare every source agent exposed.

Copy only the malicious calendar item into the sibling's matching untrusted result, clear recorded model replies and run one isolated attack replay plus one clean counterpart. Preserve that agent's permissions and legitimate-task declaration. Report its code/policy/snapshot revisions, effects and `1/1` observations; reserve `3/3` for the original final repair verification. Never start a live tool during this evaluation.

Results distinguish `vulnerable` (the compatible replay attempts prohibited effects), `blocked` (the compatible replay completes useful work without the attack effect), `not_applicable` (a specific missing capability/input path), and `could_not_evaluate` (missing recordings, tool errors or unsupported context). Mere capability matching is exposure information, not a confirmed result. Keep live healthy agents running; pausing an agent is a separate human decision.

**Commit checkpoints:** produce a per-agent result using existing sandbox helpers; show it in UI/chat. **Acceptance:** one actual compatible result and clean counterpart, one explicit incompatible/unsupported result, no original incident overwrite and no real service writes. If this exceeds 15 minutes, report the blocker and keep unassessed states honest while finishing the scoped execution; do not substitute the original agent's proof for the sibling's.

### M5: ten minutes to make the journey usable

Walk through the incident, launched repair worker, saved regression, actual PR, activated rule if delivered, fleet result if delivered, human merge/restart and completed new task. Read the receipts already produced by that same code composition. Repeat provider verification only when relevant code, policy or snapshot changed; do not run another model matrix for presentation edits.

Run the builds/typechecks for changed experience packages once, and only the focused engine/SDK checks for changed seams. Fix a broken control or wrong result label immediately. Defer polish, broad refactors, expanded CI, fuzzing, load tests, enterprise authentication and distributed rollout. Freeze feature scope at minute 110.

Record exact feature PR heads, merged/active revision, verified repair head, snapshot/policy versions, observed replay counts and the final restart result. Separate pending PRs and queued jobs from completed work. The final story must be runnable with documented local commands and must never depend on a fabricated GitHub link or recorded success presented as fresh proof.

### Worker brief and delivery cadence

Every coordinator sends a worker: the milestone goal and demo step; owned files; `special-improvements` as base and PR target, the exact dependency/base SHA and shared shapes; the no-main-merge rule; the smallest permitted implementation; one observable acceptance check; a 10–15-minute commit checkpoint; and the time at which to report a blocker. Workers own review, validation, commits, pushes and PRs. Coordinators own product review and composition, not implementation takeovers.

After the user authorizes implementation/pushes, commit each working step and push at least every 20 minutes or on a dependency handoff. Open a draft feature PR against `special-improvements` as soon as the first coherent slice works; update it as commits arrive. No full-suite rerun on every small commit. The product-generated repair PR opens once its final candidate is verified; ordinary feature PRs may be drafts sooner. Human merges into `special-improvements` use squash/rebase only. After an authorized merge, the coordinator verifies the reviewed tip, updates the integration checkout with `--ff-only`, releases the settled worker and removes only clean, inactive, fully delivered feature worktrees through Orca. No main merge or main checkout update is part of delivery.

Special Improvements remains an independent integration/documentation worktree. Authorized workers are implementing and pushing scoped feature PRs against `special-improvements`; this proposal's publication does not itself execute operator actions. Root supplies each worker's exact integration base and owns final composition acceptance.

## Reference points

- [PRODUCT.md](../PRODUCT.md) sections 3, 5 and 6: incident flow, bisection and the existing coding-agent handoff.
- [CONTRACTS.md](../CONTRACTS.md) sections 1, 3, 5, 6, 8, 11, 12 and 13: ownership, run lifecycle, APIs, CLI verification, HTTP boundaries, SDK, MCP and Miragio.
- [docs/UX.md](UX.md): incident story and human controls.
- [Protected fleet startup](../START.md#protected-source-fleet-fresh-m2-synthetic-rehearsal): local source-fleet path, separate from managed recording.
- [GitHub CLI pull request creation](https://cli.github.com/manual/gh_pr_create): reuse available GitHub tooling for the coding worker.
- [GitHub CLI pull request JSON](https://cli.github.com/manual/gh_pr_view): actual PR head, state and merged commit identity.
- [OWASP excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/): enforce scoped permissions at execution boundaries.

The receipt index above is the current delivery status; the historical main comparison is design context. Rules and fleet assessment are accepted within their declared coverage. The real coding worker and vulnerable baseline ran; the first candidate failed and its substantive bounded retry, real verified PR and actual merged-code recovery remain open. Admission-time policy and restart-identity authority must be reused. General side-effect deduplication is deferred under M2's no-prior-task-write condition. All four feature implementations are authorized; activation, repair-PR merge and restart remain explicit operator decisions.
