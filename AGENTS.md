# Mirage — project context for Claude Code

## What we are building
Mirage is incident response for compromised AI agents. Several agents run tasks in parallel.
One agent gets compromised by a malicious input. Mirage:
1. **Detects** it (hard rules first, optional model-based risk score).
2. **Contains** only the affected run: revoke its access, other runs keep working.
3. **Replays** the compromised run in an isolated environment with recorded inputs and
   recorded tool responses, then **bisects** inputs (remove one at a time) to prove which
   input caused the compromise.
4. **Recovers** the legitimate task in a fresh, clean run.
5. **Reports** the root cause and opens a **one-click GitHub PR** with the fix
   (tool allowlist, permission policy, regression test), verified by re-running the replay.

Pitch line: "Proof, not guesses. Verified fixes, not alerts."

## Context
- Secure Horizons hackathon (ESSEC Cergy, Oct 10-11 2026), team of 2, blue-team event.
- Target track: Track 2 (Defenders Augmented). Fallback: Track 3 with a supply-chain framing.
- Core code must be written during the event. Hard freeze: Sunday 12:00.
- Frameworks to map against: OWASP Top 10 for Agentic Applications (ASI01 goal hijacking,
  ASI02 tool misuse, ASI03 privilege abuse, ASI08 cascading failures), MITRE ATLAS
  AML.T0051 (LLM prompt injection), NIST CSF 2.0 (Detect, Respond, Recover).

## Demo scenario (customer support)
- 3 support runs process tickets in parallel (synthetic customers and orders).
- Each agent has tools: `lookup_order`, `read_attachment`, `send_customer_message`,
  plus a dangerous `export_records` it should never need for a normal ticket.
- One ticket has a malicious attachment instructing the agent to export customer records
  to an external address and to use the planted secret.
- Canary secret: `FLAG{team26-canary}`. No legitimate task ever needs it. Touching it = compromised.

## Architecture (Python 3)
- `agents/` — agent loop using Bedrock Converse API with tool use. The model only *requests*
  tool calls; our code executes them.
- `gateway/` — **every tool call goes through `gateway.execute(run_id, tool, args)`**.
  It checks the agent's tool allowlist, blocks the canary, blocks unknown destinations,
  checks whether the run is revoked, and logs every call. Agents must have no other path
  to tools or credentials. This is the core security boundary: never bypass it.
- `store/` — SQLite event log. Each event: run_id, agent, timestamp, event_type, tool,
  args, result, decision (allow/approve/quarantine/block), prev_hash, hash.
- `detection/` — hard rules decide containment. Optional model risk score only for
  ambiguous calls (medium = ask human approval, high = quarantine).
- `replay/` — re-run a recorded run with recorded inputs and recorded tool responses
  (no real tools), then bisection to find the causal input. Replay verdict must be
  deterministic (canary touched or not), never model-based.
- `remediation/` — model writes root cause + incident report; PyGithub opens the PR.
- `ui/` — Streamlit operator dashboard: runs, alerts, containment, replay, PR button.
- `tests/` — synthetic test set (about 20 runs, half poisoned) to compute detection rate,
  false positives, time to detect, time to contain.

## Bedrock setup
- Region: `us-east-1` only.
- Auth: short-term Bedrock API key in `.env` as `AWS_BEARER_TOKEN_BEDROCK` (expires,
  regenerate when calls fail with auth errors). Load with `python-dotenv` before boto3.
- Model IDs come from `.env`, never hardcoded. Use inference profile IDs (`us.` or
  `global.` prefix); plain model IDs fail with an on-demand throughput error.
- Agents: fast model that accepts `temperature: 0` (for reproducible replays).
- Reports/PR text: stronger model; some models reject `temperature`, omit it there.
- Rate limit: stay under ~1 request per second per person. Add a small delay in loops,
  especially during replay bisection.

## Hard rules (non-negotiable)
- Synthetic data only. No real personal data.
- No secrets in Git: keys live in `.env` (gitignored). Use `.env.example` as template.
- Only attack our own sandbox. Never target external systems or websites.
- Fake secrets only, format `FLAG{team26-...}`.
- Push to GitHub at least every hour.

## Build order
1. One support agent with Converse tool use and mocked tools.
2. Gateway + SQLite logging + canary/allowlist/destination rules.
3. Malicious attachment scenario, blocked by the gateway.
4. Three concurrent runs with separate run IDs and tokens.
5. Containment: revoke one run, others finish.
6. Replay with recorded responses + input bisection.
7. Root-cause report + one-click PR (fix + regression test), verified by replay.
8. Streamlit operator view.
9. Metrics on the test set.

## Working style
- Build one step at a time and run it before moving on.
- Keep code simple and readable; this is a 24-hour prototype.
- When something is ambiguous, ask before making architectural changes.