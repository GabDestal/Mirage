# Demo agents

The agents Mirage protects in the demo. They are the "customer" side: normal LangGraph agents
with their own tools. Mirage joins them later with one line (`mirage.protect`, see `CONTRACTS.md` section 11).

## Conventions (every agent follows these)

- One folder per agent: `agents/<name>/`.
- `agents/<name>/agent.py` exposes:
  - `build_agent(model=None, middleware=())` → a `create_agent` graph. `model=None` uses `chat_model()`.
    `middleware` is where `mirage.protect(...)` goes later. Do not import the SDK yet.
  - `TASK`: the default task string for the demo.
- `python -m agents.<name>` runs `TASK` once with Bedrock and prints every tool call (`agents/common/run.py`).
- `agents/<name>/test_agent.py`: one offline test with `agents.common.testing.scripted(...)`. No Bedrock, no network.
- Tools use the shared fake services in `agents/services/` (mail, calendar, crm). Agent-specific services
  (invoices, pull requests) live in the agent's own folder.
- Every agent reads at least one **untrusted input** (an email, a calendar event, a PR comment, a CRM note).
  That is where a prompt injection can arrive. Poisoned data is added by `demo/`, not by the agent.
- Synthetic data only. Fake secrets only (`FLAG{team26-...}`).

## Run

```bash
uv sync
uv run pytest agents            # offline
uv run python -m agents.<name>  # needs .env with AWS_BEARER_TOKEN_BEDROCK and BEDROCK_AGENT_MODEL_ID
```
