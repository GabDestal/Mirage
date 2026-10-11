# Demo agents

The agents Mirage protects in the demo. They are the "customer" side: normal LangGraph agents
with their own tools. The protected fleet in `agents.run_demo_fleet` wraps them with
`mirage.protect` (see `CONTRACTS.md` section 11). Individual module commands do not.

The source fleet is **meeting assistant, invoicing, outreach and PR reviewer**. Its
services are process-local synthetic fakes, not Google, HubSpot or GitHub integrations.
The shared seed has eight contacts and two clean calendar events; fleet startup adds
one poisoned invite. The recorded M1 fixture instead includes support and a 40-record
example. See [demo evidence](../docs/DEMO_EVIDENCE.md) for the task/poison differences
and limits of historical results.

## Current structure

- One folder per agent: `agents/<name>/`.
- `agents/<name>/agent.py` exposes:
  - `build_agent(model=None, middleware=())` → a `create_agent` graph. `model=None` uses `chat_model()`.
    The fleet's module-level protected factories supply importable replay entrypoints.
  - Each factory uses its own override: `MEETING_ASSISTANT_MODEL_ID`, `INVOICING_MODEL_ID`,
    `OUTREACH_MODEL_ID` or `PR_REVIEWER_MODEL_ID`, then `BEDROCK_AGENT_MODEL_ID`, then
    `BEDROCK_MODEL_ID`. Blank overrides fall through. All four reuse `clean_tool_names`
    (`agents/common/model.py`), keep caller middleware, and use temperature 0 in `us-east-1`.
  - Models created by `chat_model()` share one installed LangChain `InMemoryRateLimiter`
    per Python process: one provider model turn per second, capacity one. Recorded SDK
    replies bypass model calls. This does not coordinate separate fleet, gateway, chat
    or sandbox processes, or provider-internal retries; it is no cross-process provider
    rate guarantee. [Repair acceptance](../docs/UI_ENGINE_REPAIR_ACCEPTANCE_20261011.md)
    separates its offline wiring evidence from fresh provider acceptance.
  - `TASK`: the default task string for the demo.
- `python -m agents.<name>` runs `TASK` once with Bedrock **without Mirage protection**
  and prints tool arguments/results (`agents/common/run.py`). It does not create SDK/UI runs.
- `agents/<name>/test_agent.py`: offline tests with `agents.common.testing.scripted(...)`. No Bedrock, no network.
- Tools use the shared fake services in `agents/services/` (mail, calendar, crm). Agent-specific services
  (invoices, pull requests) live in the agent's own folder.
- Every agent reads at least one **untrusted input** (an email, a calendar event, a PR comment, a CRM note).
  That is where a prompt injection can arrive. Fleet startup seeds the poisoned invite
  through `agents/meeting_assistant/eval_injection.py`; standalone modules use the clean shared seed.
- Synthetic data only. Fake secrets only (`FLAG{team26-...}`).

## Run the protected fleet

Follow [protected startup](../START.md#protected-source-fleet-fresh-m2-synthetic-rehearsal)
to create an owned, isolated live engine and connect web/chat to it. Then, from repo root:

```bash
MIRAGE_MODE=live MIRAGE_URL=http://127.0.0.1:8020 uv run python -m agents.run_demo_fleet
```

This uses real Bedrock models with synthetic tools. Use this SDK fleet for visible
gateway decisions and freezes; `npm run dev:demo --prefix web` plays recorded evidence
and starts no source agents. An explicit UI **Start demo** on the owned isolated live
engine is an alternative that resets that instance before launching the same fleet.
Choose one fleet-start path, and retain the runtime until active proof work finishes.

## Standalone development

These commands exercise the agents without the gate, containment or SDK event stream:

```bash
uv sync
uv run pytest agents            # offline
uv run python -m agents.meeting_assistant  # unprotected; needs configured Bedrock credentials/model
```
