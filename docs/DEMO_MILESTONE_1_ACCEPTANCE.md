# Milestone 1 combined acceptance

Rehearsal: 2026-10-11, isolated Orca acceptance checkout. M1 uses recorded background
agents and engine evidence with **real Bedrock Miragio, real MCP handlers and human
decisions**. This report does not establish live victim-agent, real-service, sandbox
execution, repair, pull-request creation, merge or clean-restart acceptance.

## Exact composition

Common base: `289a6968539d3d4d2eadf5a72354f7e6a2c5882f`.
Provider/integration/browser tested composition: `c37811a648a37aeb3cd999de77d165f29cfecad8`.
Final presentation composition: `fefbf94339ef643c3f426716102b21652cfa25dd`, retained
locally as `validation/m1-demo-composed`. Source ranges were cherry-picked from
the coordinator-confirmed heads, including follow-ups:

| Dependency | Exact source head |
|---|---|
| [PR109: real Miragio / recorded labels](https://github.com/GabDestal/Mirage/pull/109) | `6d81b769aaac834554e0e24df46e649621fb8712` |
| [PR110: recorded engine](https://github.com/GabDestal/Mirage/pull/110) | `41eb5c97ef510ba986dc108918820abb43669bd9` |
| [PR111: isolated launcher](https://github.com/GabDestal/Mirage/pull/111) | `cff4e13dd0f543b72beeb5a79b3eb1851ad5d0f0` |

Provider rehearsal used PR109's preceding `6f051dd018e7899df50a89ae3f1d4ef8acc3339d`.
The final amendment changes only the demo drawer access sentence and its focused
browser assertions. Engine, MCP/provider, launcher and owned selfcheck files are
identical between tested compositions. Per coordinator instruction, rebuilt web
and rechecked the actual drawer through approved recorded HTTP/dashboard handoff
without additional Bedrock requests. Documentation updates do not alter runtime.

This acceptance PR owns only `mcp/scripts/demo-e2e.mjs` and this report. Companion
implementation commits belong to their PRs and must land before running this script
on main. No dependencies, package scripts, contracts or implementation were added.

## Reproduce

From the composed repository root:

```sh
npm ci --prefix mcp
npm run build --prefix mcp
npm ci --prefix web
npm run build --prefix web
uv sync
```

Then in `web/`, start the existing launcher:

```sh
MIRAGE_CHAT_ENV_FILE=/absolute/server-side/path/to/.env MIRAGE_REPLAY_SPEED=10 npm run dev -- --mode demo
```

The rehearsal used `/Users/liamszefner/Business/hacks/Mirage/.env` server-side only.
The launcher owned web5174, engine8010, chat8011 and disposable state; no control
requests were sent to 5173/8000/8001. The engine and Vite receive no provider key.
Speed 10 is finite, within the launcher limit, and preserves observable sequencing.
Normal demo defaults to speed 2.

From the repository root, run each explicitly:

```sh
node mcp/scripts/demo-e2e.mjs
node mcp/scripts/demo-e2e.mjs --live
```

Both commands mutate/reset **only the managed recording on the fixed dedicated
ports**. They check recorded agent specs before mutations. Default mode creates an
ephemeral HTTP chat service using the existing synthetic `ModelProvider` seam;
the engine, HTTP/SSE, MCP SDK transports, catalogue and handlers are real.
`--live` uses the launcher's actual chat service and never substitutes a provider,
automatically retries effects, or mocks handlers. Human decisions in the selfcheck
are explicit authorized rehearsal inputs to the actual approval endpoint, not
claims that a person clicked the browser. The separate browser exercise did click
the actual Approve control.

## Observed checks

| Check | Result |
|---|---|
| Baseline without initial detonation POST | Freeze precedes automatic three-replay start, effects, completion and confirmed verdict, observed over real engine SSE |
| Completion/effects | Recorded verdict `3/3`, nine effect rows, observed run indices 1–3; script compares the verdict ratio against actual completion fields |
| Healthy agents | Outreach, support and PR reviewer execute/complete after the meeting assistant freezes; four runs, only meeting assistant frozen |
| Service evidence | Nonempty production outbox/calendar/CRM and Mirage outbox via actual HTTP views |
| Guards | Premature handoff/verify and wrong replay count refused with 409; missing target 404; confirmed unfreeze 409; no ledger change |
| STOP/resume | Recording cursor stops; actual MCP `resume_all`, elicitation and HTTP handler restore playback; compromised run remains frozen |
| Real read turn | Actual `list_runs` and `get_incident`; Miragio identifies all four background agents as recorded and distinguishes itself as real |
| Cause | Actual human-requested `find_cause`, actor audit and automatic `get_incident` follow-up; removed poisoned calendar input gives recorded `0/2`, four other rows `2/2` |
| Human decisions | Actual `send_fix` approval event; decline gives refusal/no ledger effect; stale approval ID 409; new explicit request plus fresh acceptance succeeds |
| Handoff | Human-only download succeeds; recorded-only prompt says no usable live snapshot/token/capability and no fix written; no capability token in tool cards |
| Fix/PR evidence | Authorized HTTP recorded verification reports observed blocked `3/3`, legitimate completion `3/3`; only `example.invalid/recorded-demo/pr/42` accepted; no real PR42 created or repaired |
| Reset | Selfcheck removes previous incident/cause/fix/PR/audit; separate UI-owned restart removes previous incident link and returns four working runs, Frozen 0, then starts new recorded playback |

Sandbox-only cause finding deliberately follows the existing Level 0 contract,
without extra elicitation. Decline/approve checks apply to existing Level 1 handoff
and resume controls. The coordinator corrected the initial acceptance brief to
match this contract; no new approval policy was implemented.

## Provider-live versus synthetic evidence

Final selfcheck passed in both modes. Synthetic mode made **nine scripted model
rounds**, including automatic cause follow-up, and made **zero Bedrock requests**.
This proves repeatable transport/handler integration, not model reliability.

The live selfcheck completed four requested turns plus one automatic follow-up:
**nine actual Bedrock ConverseStream requests, nine HTTP200 responses, zero provider
failures**. The model read current tools, described recorded background, requested
cause tests, summarized recorded bisection and handled declined/newly approved
handoffs. Read response explicitly identified recorded background and a real
Miragio; approved handoff response explicitly said no live snapshot/token and no
fix made. Evidence came from tool results, not a synthetic answer substituted for
the provider.

Separate actual browser chat QA added six Bedrock requests: two incident-reading
turns and a subsequent explicit handoff request/approval continuation. Total:
**15 requests, 15 HTTP200 responses, zero failures**; minimum measured spacing
**1804ms**. A temporary Node preload wrapped the existing AWS client's `send` solely
to append request timestamps/status codes in `/tmp`; it called the original SDK,
logged no request/response bodies or credentials, and was never committed. HTTP200
alone is not proof of a finished turn; the selfcheck also required terminal SSE
`done` and actual expected tool results.

## Browser evidence

Used the documented Orca browser CLI, snapshots, DOM evaluation and screenshots;
no independent browser runtime was created. Desktop viewport was 907px wide;
supported iPhone16 emulation reported actual `innerWidth=393`, `innerHeight=852`,
pixel ratio 3. Incident text wrapped and document had no horizontal overflow.

- Fleet showed recorded-agent notice, four agent rows, three healthy agents and
  one frozen meeting assistant, with completed sandbox evidence.
- Incident showed recorded-demonstration notice, `3/3`, nine captured effects,
  frozen production, recorded cause rows and safe fix boundary. Navigation and
  browser reload (followed by existing demo sign-in) retained backend proof.
- The real browser chat read current incident evidence, rendered the actual
  `Your approval is needed` form with Decline/Approve, and recorded
  `You approved this action` after clicking Approve. The real handoff handler
  produced the human handoff button and the recorded-only prompt drawer.
- Clicking `Restart demo recording` in Fleet removed the old incident link,
  showed Frozen 0 / Working 4 / reset tool activity, and displayed
  `Restarted the recorded demo` before new timed events arrived.

Local screenshot samples: `/tmp/m1-incident-mobile.png` and
`/tmp/m1-chat-approval-final-shot.json` and `/tmp/m1-final-drawer-shot.json`;
these are temporary QA material, not
portable repository artifacts. The repeatable checks and observed values above
are the durable evidence.

## Validation commands

| Command | Observed result on confirmed composition |
|---|---|
| `npm run build --prefix mcp` | Passed |
| `npm run build --prefix web` | Passed; existing large-bundle warning remains |
| `npm test --prefix mcp` | 61 tests passed |
| `npm run demo:selfcheck --prefix web` | Passed launcher precedence/isolation/readiness/owned cleanup checks |
| `uv run pytest tests/test_managed_replay.py tests/test_replay.py tests/test_demo_control.py tests/test_auto_detonation.py tests/test_crash_safety.py tests/test_verify.py -q` | 44 passed |
| `node mcp/scripts/demo-e2e.mjs` | Passed, synthetic model explicitly labeled |
| `node mcp/scripts/demo-e2e.mjs --live` | Passed, actual provider/HTTP/SSE/MCP |

## Isolation, cleanup and limitations

Original main remained at `289a6968539d3d4d2eadf5a72354f7e6a2c5882f`, with clean
status. Its four existing data files matched the pre-rehearsal content-free
SHA256 manifest exactly:
`8a5a77d0bcc17140b769e785945958b6667a8af444ae69b7a743e84563636903`.
No original service was started, stopped or reset; no `.env` was copied or read
into terminal/browser/report output. Only the acceptance launcher owns its child
processes and disposable state. Signaled only launcher PID50632; launcher/engine/
chat/Vite PIDs50632/50644/50652/50653 all exited, dedicated ports5174/8010/8011 had
no listeners, and owned temporary directory `mirage-demo-Ib8AaC` disappeared.
Closed only the acceptance browser tab. Main/data checks still matched after
shutdown; the local validation branch remains for exact-composition review.

The browser-discovered drawer access claim was corrected by PR109's owner at the
final head above. Final actual drawer text: “This prompt is a recorded example.
It does not grant live incident access.” The earlier scoped-access claim was
absent, and the prompt still explicitly supplied no live capability. No companion
implementation was edited by this acceptance worker.

Known limitations:

1. An external/API reset can leave an already-open dashboard with an old SSE
   cursor/cached state until reload. UI-owned restart passed. Epoch propagation
   is explicitly outside this M1 claim; use UI restart or reload after external reset.
2. A browser wording such as “request my approval first” can make the real model
   ask a conversational question before calling the actual handoff tool. A new
   explicit request produced the genuine approval card; the extra question is
   model behavior, not an extra implemented approval gate.
3. Unsupported stories, epoch/reconnect/failure UX, live integrations, fresh
   sandbox proof, real fix validation, merges and clean restarts were not accepted
   by this rehearsal. Recorded success ratios/PR42 are examples only.
