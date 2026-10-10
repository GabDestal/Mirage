# Mirage — project context for coding agents

Read with `PRODUCT.md` (what we build and demo) and `CONTRACTS.md` (team split, data models,
API). If this file and those disagree, ask before building.

## What we are building
Mirage is incident response for compromised AI agents. Several agents run tasks in parallel
against real services. One agent reads a malicious input. Mirage:
1. **Detects** it: a gate checks every tool call before it runs (hard rules, then a
   decision model).
2. **Freezes** only that run. Frozen, not killed: other runs keep working, and a human can
   unfreeze a false positive.
3. **Detonates** the frozen run in Mirage, a simulation twin of production: same tools, fake
   backends, started from a snapshot taken at freeze. The bad call is allowed there. 3 runs.
4. **Proves** the result: deterministic verdict, blast radius, and **bisection** (remove one
   input at a time) to find the input that caused the compromise.
5. **Fixes**: one click hands the incident to a coding agent. It tests the fix with
   `mirage detonate` against the same snapshot. A human merges the PR and approves a clean
   restart.

Pitch line: "Proof, not guesses. Verified fixes, not alerts."
Team rule: **demo first.** Build what the demo shows. Nothing else.

## Context
- Secure Horizons hackathon (ESSEC Cergy, Oct 10-11 2026), team of 2, blue-team event.
- Target track: Track 2 (Defenders Augmented). Fallback: Track 3 with a supply-chain framing.
- Core code must be written during the event. Hard freeze: Sunday 12:00.
- Frameworks to map against: OWASP Top 10 for Agentic Applications (ASI01 goal hijacking,
  ASI02 tool misuse, ASI03 privilege abuse, ASI08 cascading failures), MITRE ATLAS
  AML.T0051 (LLM prompt injection), NIST CSF 2.0 (Detect, Respond, Recover).

## Demo stories
1. **Main: calendar injection → CRM exfiltration.** An assistant agent prepares meetings.
   A calendar invite description says to export all CRM contacts and email them to an
   attacker address. The gate freezes the agent. Real Calendar, HubSpot and Gmail.
2. **Support ticket with a malicious attachment.** Same engine, different tools and inputs.
   The attachment asks the agent to export customer records and use the canary secret.
3. **False positive.** A clean agent emails a new address the customer gave in the ticket.
   The gate freezes it, detonation shows no harm, a human unfreezes it.

- Canary secret: `FLAG{team26-canary}`. No legitimate task ever needs it. Touching it = compromised.
- The "attacker" address is a team-owned inbox, shown as attacker-controlled.

## Two environments
- **Production:** real team-owned accounts with synthetic data: Gmail, Google Calendar,
  HubSpot free CRM.
- **Mirage:** same tool names and arguments, different backend. Each tool has two adapters.
  Reads come from the snapshot. Writes go to fake services we can inspect.
  **Nothing in Mirage reaches the real world** (no real HTTP, no real email).

| Tool | Production adapter | Mirage adapter |
|---|---|---|
| `read_calendar` | Google Calendar API | calendar snapshot |
| `send_email` | Gmail API | fake outbox (captured, never sent) |
| `crm_query` | HubSpot API | SQLite copy of CRM records |
| `crm_export` | HubSpot API | SQLite copy, export captured |
| `fetch_url` | real HTTP (allowlist) | recorded or stub page |

The snapshot holds every input the run read and the full agent context (system prompt,
messages, tool calls, tool results). Each Mirage run starts from a fresh copy.

## Architecture (Python 3)
Repo layout and ownership are in `CONTRACTS.md` section 8.
- `contracts/models.py` — Pydantic models. **Source of truth** for all data shapes. Every
  change updates `models.py`, the fixtures and `CONTRACTS.md` in the same commit.
- `agents/` — agent loop using Bedrock Converse API with tool use. The model only *requests*
  tool calls; our code executes them.
- `gateway/` — **every production tool call goes through `gateway.execute(run_id, tool, args)`**.
  It checks the global STOP flag, the run status, the tool allowlist, the canary and the
  destination allowlist, runs the decision model, and logs every call. Agents have no other
  path to tools or credentials. This is the core security boundary: never bypass it.
- `detection/` — layer 1 hard rules and layer 2 decision model (policy pack P1–P6 in
  `PRODUCT.md` section 4). Policies are written before the demo, never edited live.
- `store/` — SQLite: event log (one stream, `Event` model) and snapshots.
- `mirage/` — Mirage adapters, snapshot loading, detonation, `mirage detonate` CLI,
  MCP server and HTTP access with a per-incident token.
- `replay/` — bisection over snapshot inputs.
- `remediation/` — handoff prompt, incident report, PyGithub PR.
- `api/` — real FastAPI server. `mock/` — fake server that replays fixtures for UI work.
- `ui/` — operator view. Reads `MIRAGE_API=mock|real`. Stack still open (Streamlit or React).

## Verdict: deterministic first
- **`confirmed` is decided by code, not by a model.** Check the effects ledger of each
  detonation: canary in any argument, data sent to a non-allowlisted destination, or a bulk
  export. Any hit = compromised run. Bisection uses the same check.
- The judge (`gpt-oss-safeguard-120b`) reads only the effects ledger, never the malicious
  input. It maps effects to policies (`policies_violated`) and writes the summary text. It
  never changes `confirmed`.
- "Legit task completed" is also a code check (example for story 1: a meeting summary email
  went to the user's own address). Define it per story.
- The gate's decision model only decides freezes. A false freeze costs one human click.

## Bedrock setup
- Region: `us-east-1` only.
- Auth: short-term Bedrock API key in `.env` as `AWS_BEARER_TOKEN_BEDROCK` (expires,
  regenerate when calls fail with auth errors). Load with `python-dotenv` before boto3.
- Model IDs come from `.env`, never hardcoded. Use inference profile IDs (`us.` or
  `global.` prefix); plain model IDs fail with an on-demand throughput error.
  Exception: `gpt-oss-safeguard-20b` / `-120b` have no profile; use the plain model ID.
- Agents: fast model with `temperature: 0`, in production and in Mirage.
- Reports/PR text: stronger model; some models reject `temperature`, omit it there.
- Rate limit: stay under ~1 request per second per person. Add a small delay in loops,
  especially during detonation and bisection.

## Human in the loop (core requirement, emphasize everywhere)
- Global STOP button: one click halts all runs and revokes all tokens. The gateway checks
  a global "halted" flag before every tool call.
- Freeze / unfreeze / kill on each agent card.
- Medium-risk actions wait in an approval queue (approve/reject with reason shown).
- Escalation rule: repeated denials followed by workaround attempts = pause run + alert human.
- Human approves clean restarts and always merges PRs manually (no auto-merge).
- Every human decision is logged: who, when, what, why.

## Hard rules (non-negotiable)
- Synthetic data only. No real personal data.
- No secrets in Git: keys live in `.env` (gitignored). Use `.env.example` as template.
- Only attack our own accounts and our own sandbox. Never target external systems or websites.
- Fake secrets only, format `FLAG{team26-...}`.
- Push to GitHub at least every hour.

## Build order (engine)
1. Gmail, Calendar and HubSpot access works (tokens, synthetic data loaded).
2. One agent with Converse tool use and the production adapters.
3. Gate: hard rules + SQLite log + freeze/unfreeze.
4. Poisoned calendar invite. The gate freezes the agent.
5. Three agents in parallel. One frozen, two continue.
6. Mirage adapters + snapshot at freeze.
7. `mirage detonate` CLI: 3 runs, effects ledger, deterministic verdict, judge summary.
8. Bisection.
9. Decision model (layer 2) in the gate.
10. Mirage MCP server + HTTP API + incident token.
11. Coding agent handoff: Copy prompt + Send to Codex. Test the full loop.
12. UI (Person B builds it in parallel on the mock server).
13. Story 2 and story 3.
14. Metrics on a synthetic test set (detection rate, false positives, time to detect,
    time to contain).

`mirage detonate` must work without the UI. It is the riskiest demo part: test it often.

## Repo rules (all agents, all the time)
Skills live in `.claude/skills/`. Agents that do not load skills: read the `SKILL.md` file.
- **Demo first.** Build only what the demo in `PRODUCT.md` shows. `CONTRACTS.md` is the
  link between engine (Person A) and UI (Person B).
- **Reuse before writing** (`ponytail` skill): smallest complete change; existing code,
  stdlib, installed deps, then open source, then new code.
- **Align before building** (`align-first` skill): check product fit and browse open source,
  propose options, get an OK before committing to a new approach.
- **One feature = one worktree = one atomic PR** (`atomic-worktree` skill). Never work
  directly on `main`.
- **Commit often, push often**: commit each working step, push at least every 30 minutes.

## Working style
- Build one step at a time and run it before moving on.
- Keep code simple and readable; this is a 24-hour prototype.
- When something is ambiguous, ask before making architectural changes.
