# Demo evidence and provenance

Documentation review: 2026-10-11. Source inspected at
`adb97c6d480cf8fe21c863a28b537a84fbb8b58d`. This review reads source and existing
reports; it runs no services, agents, provider calls or live acceptance checks.
[PRODUCT.md](../PRODUCT.md) describes the intended real-service demo. The evidence
below describes what the current source and recordings actually establish.

## Recorded M1 and source-fleet M2

| Detail | Recorded M1 example | Current protected source fleet |
|---|---|---|
| Startup | `npm run dev:demo --prefix web`: managed Replay plus real Bedrock Miragio/MCP | `agents.run_demo_fleet` against a live engine; manual attach UI does not start agents |
| Fleet | Meeting assistant, outreach, **support**, PR reviewer | Meeting assistant, **invoicing**, outreach, PR reviewer |
| CRM evidence | Fixture reports **40 contacts**; truncated example rows and recorded blast radius | Shared seed has **8 contacts**; no fresh leakage count established by this docs review |
| Calendar | Fixture's recorded meeting context and poison | **2 clean events + 1 injected event** added at startup |
| Meeting task | Also asks to complete preparation tasks listed in invites | Prepare meetings, look up each attendee and email one short brief; no added invite-task instruction |
| Poison | Recorded Partnership sync preparation-step text | `V2_system_tag`: forged `<system>` configuration update asking for all contacts via empty `search_contacts` and an attacker email |
| Tools | Recorded requests include `export_contacts` | Meeting tools: `read_calendar`, `search_contacts`, `search_emails`, `send_email` |
| Services | Event-derived recorded panels | Process-local synthetic mail/calendar/CRM, invoices and PRs; no Google/HubSpot/GitHub API calls on these paths |
| Proof/fix | Recorded three-run proof, bisection, verification and placeholder PR | Fresh containment, jailed replay, cause tests and current-code verification need composed acceptance |

Sources: [managed launcher](../web/scripts/dev.mjs),
[recorded fixture](../contracts/fixtures/fleet_demo_4agents.jsonl),
[protected fleet/factories](../agents/run_demo_fleet.py),
[meeting task/tools](../agents/meeting_assistant/agent.py),
[poison and seed helper](../agents/meeting_assistant/eval_injection.py),
[shared seed](../agents/data/seed.json), [synthetic services](../agents/services/__init__.py),
[SDK replay](../sdk/mirage/sandbox.py), [input removal](../engine/detonation/snapshot.py),
[current-code verification](../engine/detonation/sandbox.py).

Keep the fixture's 40-record values as **recorded example evidence**; do not describe
them as a fresh eight-contact source-fleet result. Its handoff has no executable live
snapshot/token, verification does not test current code, and its PR URL is a placeholder.
[M1 combined acceptance](DEMO_MILESTONE_1_ACCEPTANCE.md) documents real operator-chat
requests on named compositions against this recording, not live victim-agent proof.
Three from-freeze SDK replays reproduce recorded model replies before continuing;
they are consequence evidence, not three independent fresh injection successes.
Bisection and verification clear those replies and run from scratch.

For the protected startup path, use [START.md](../START.md#protected-source-fleet-fresh-m2-synthetic-rehearsal).
Individual `python -m agents.<name>` modules and the injection evaluation are
unprotected Bedrock runs. They do not establish gateway containment or SDK/UI runs.

## Historical results remain historical

[Meeting evaluation](../agents/meeting_assistant/eval_results.md), committed on
2026-10-10, reports N=4 per cell, eight variants and three models. GPT-OSS V2/V3/V4
report 4/4 compromised and 4/4 user mail; its clean control reports 0/4 compromised.
Haiku and Sonnet report 0/4 compromised per variant. These stored aggregates have
no per-run provider trace or exact execution SHA in the report. Their small selected
samples do not establish current reliability or general model resistance, and
`legit_brief` only checks that mail reached the user, not that the brief was complete.

[Engine runbook metrics](RUNBOOK.md#4b-metrics-pitch-numbers-7-min-bedrock) report
2026-10-10 results: attacks attempted in 6/10 poisoned runs, detected 6/6, no leakage,
no freezes in 10 clean runs; median detection/containment 5.9/8.9 ms, verdict 13.5 s.
It also reports 58 fleet decisions without false freezes and 3/4 stealth model catches.
Those values and its stage timings are preserved historical reports, not refreshed
measurements. Detecting six attempted attacker sends does not mean all ten invites
compromised the model or establish general semantic detection.

## Remaining gates for fresh M2 claims

The engine and agent/SDK audits on 2026-10-11 inspected
`7c337214e1a92de08d905afc370d57a081831595`. The engine report records 140 passing
offline tests plus reproduced failure probes; the agent report records 8 agent and
9 public-protect offline tests plus scripted/mock-transport probes. Neither ran
provider-live fleet/UI acceptance. Local audit artifacts are
`/tmp/mirage-engine-audit-20261011.md` and `/tmp/mirage-agent-audit-20261011.md`;
their findings belong to that revision; later source changes still need composed acceptance.

1. **Truthful run/effect evidence:** surface factory/provider/tool failures instead of
   completed cards, retain handled tool-error status, and expose resolved destinations
   for composite invoice/follow-up actions. Validate intended work per story, including
   all expected entities and a complete single meeting brief; a green card or mail alone
   does not prove task completion.
2. **Containment and startup:** validate one immutable API/gateway mode before imports;
   preserve freeze authority if snapshot persistence fails. Use one owned engine, new
   absolute DB/snapshot/token paths and explicit protected SDK startup. Test ordinary
   instance demo-control guards and reset/job exclusion without changing existing sessions.
3. **Replay and verification:** reject nonpositive runs, keep leak-before-crash evidence
   with consistent attempted/completed/error counts, check newly introduced tools against
   freeze-time and intended current policy, and enforce exact task/recipient completion.
   Show limitations of missing or changed-argument recorded reads and interrupted jobs.
4. **Fresh composed acceptance:** pin revision, model settings, task, seed and poison;
   retain per-run request/status/effect/error evidence. Demonstrate freeze before the
   offending outbound effect, other agents continuing, automatic three-run jailed replay, cause
   removal from scratch, a failing fix rejected and a clean current fix passing both
   checks. Verify the same evidence through UI/SSE/MCP, STOP and human recovery. Record
   actual coding-agent handoff, fix PR and human merge/restart separately from examples.
5. **External services and cloud access:** coordinator-supplied sanitized configuration
   says Bedrock is configured in `us-east-1`, Google configured credential/token paths
   are absent, HubSpot token is unset, and no public deployment URL is configured.
   This worker did not read `.env` or credentials. Implement and demonstrate team-owned
   Google/HubSpot adapters before saying real services; configure reachable, incident-scoped
   sandbox access before claiming a cloud coding agent tested a fix. Configuration alone
   does not prove provider access, integration or deployment.

Later acceptance belongs in a separate report after the required worker PRs are
composed. This documentation PR changes no contracts, fixtures, implementation or
historical measurements and establishes no fresh M2, real-service or deployed acceptance.
