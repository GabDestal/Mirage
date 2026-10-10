# Mirage runbook (engine side)

How to run Mirage on your laptop. Windows PowerShell or any shell. Everything runs from the repo root.

## 1. Setup (once)

```bash
uv sync                 # Python 3.12+, installs everything (engine, agents, the `mirage` SDK)
cp .env.example .env    # then fill AWS_BEARER_TOKEN_BEDROCK (short-term key, it expires)
```

The meeting-assistant victim uses `MEETING_ASSISTANT_MODEL_ID` in production and Mirage. The demo
default is GPT-OSS 20B (`openai.gpt-oss-20b-1:0`); the gate and judge use their separate safeguard
model settings. Temperature is 0.

Check Bedrock works: `uv run python test_bedrock.py` prints a sentence.
If any command fails with an auth error later, regenerate the Bedrock key and update `.env`.

## 2. Tests (offline, no Bedrock, ~25 s)

```bash
uv run pytest -q
```

## 3. The whole story in one command (~5 min, Bedrock)

```bash
uv run python -m engine.dev.demo                   # 3 dev agents, one gets poisoned
uv run python -m engine.dev.demo --agent meeting   # Liam's meeting assistant through the SDK
uv run python -m engine.dev.demo --keep            # keep the API up afterwards (for the UI)
```

It starts the engine API (live mode, port 8000), runs the agents, then drives the incident over HTTP
like the UI would. Expected output:

```
FROZEN by the gate: DEST_NOT_ALLOWED on send_email -> attacker@...
3/3 compromised. 3 of 3 runs sent 40 records and the canary secret to attacker@...
without Renewal call - Contoso   2/2 compromised
without Q4 partner sync          0/2 compromised   <- CAUSE
attack blocked 0/2, legit task 2/2 -> NOT verified (expected: no fix yet)
```

If no run freezes, the model did not take the bait this time: run it again (gpt-oss-20b at temperature 0
is not fully deterministic). Each run starts from a fresh `data/` folder.

## 4. Piece by piece

| What | Command |
|---|---|
| Engine API, live | `MIRAGE_MODE=live uv run uvicorn engine.api.server:app --port 8000` |
| Engine API, replay (UI work, no Bedrock) | `MIRAGE_MODE=replay MIRAGE_REPLAY_SPEED=10 uv run uvicorn engine.api.server:app --port 8000` |
| 3 dev agents (prints every gate decision) | `uv run python -m engine.dev.runner` |
| Detonate an incident (operator replay) | `uv run python -m engine.cli detonate --incident inc_001 --from-freeze` |
| Find the cause | `uv run python -m engine.cli bisect --incident inc_001` |
| Check a fix (what the coding agent runs) | `uv run python -m engine.cli detonate --incident inc_001` (exit 0 = verified) |
| API docs | http://localhost:8000/docs |

PowerShell: set env vars with `$env:MIRAGE_MODE='live'` before the command.

The CLI and the API share `data/` (event log + snapshots), so an incident frozen by one process can be
detonated from another. `POST /demo/reset` (or deleting `data/`) starts over.

## 5. Where things live

| Path | What |
|---|---|
| `data/mirage.db` | Event log (SQLite, hash-chained). The API's runs and incidents are folded from it. |
| `data/snapshots/<incident>.json` | Snapshot written by the gate at freeze: the sandbox's only input. |
| `engine/detection/policies.yaml` | Policy for dev agents. SDK agents send theirs with `mirage.protect(allow=...)`. |

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `AccessDeniedException` / auth error | Regenerate the Bedrock key in `.env`. |
| `The API did not start on port 8000` | Something else uses the port: `--port 8010`. |
| A run freezes on `UNKNOWN_TOOL` | It no longer freezes: a model typo in a tool name passes through (nothing can run). |
| Detonation shows `SANDBOX_ESCAPE` | The agent (or a library) tried the network, a process or a secret file. The effects list the target. |
| `409 owned by another process` | Freeze/unfreeze/kill only work in the process that runs the agent (the dev runner runs its own). |
