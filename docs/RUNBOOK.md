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
uv run python -m engine.dev.demo --agent meeting --until freeze  # stop at the freeze: automatic replay starts; use the UI for the next steps
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

**Stage speed:** add `MIRAGE_PARALLEL=3` (PowerShell: `$env:MIRAGE_PARALLEL='3'`) to run the sandbox replays
and the bisection rows at once. Measured live with Liam's agent: detonate 9 s, find the cause 33 s (was 75 s),
fix check 16 s, about 71 s end to end. It bursts above the team's ~1 Bedrock request/s rule, so it is off by default.

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
| Handoff for a coding agent (prompt + report + token) | `curl -X POST localhost:8000/incidents/inc_001/handoff` |
| Record the fix PR | `uv run python -m engine.cli pr --incident inc_001 --url <PR URL>` |
| Save the last live run as the replay fixture (stage backup) | `uv run python -m engine.cli export-fixture` |
| API docs | http://localhost:8000/docs |

PowerShell: set env vars with `$env:MIRAGE_MODE='live'` before the command.

The gate automatically queues three sandbox replays as soon as a new incident's snapshot is
persisted and production is frozen. Restart the engine on this version to enable it; no new
configuration is required. Production stays frozen until a human decides. `run.status` with
actor `system` records automatic queueing; `detonation.started` records actual execution.
Jobs across incidents are serialized, and `MIRAGE_PARALLEL` retains its existing meaning
inside one job (default 1). A failure emits `detonation.failed`: fix the cause, then explicitly
retry with `POST /incidents/<id>/detonate` or the operator CLI command above. Polling and
engine restore never retry automatically.

`POST /demo/reset` and `/demo/start` return 409 if sandbox work is active. This preserves the
fleet, incident log, snapshots and tokens: wait for the job to finish and retry. Idle reset
cancels queued work before clearing data; graceful shutdown cancels queued work and waits
for active work. The 180-second timeout is per replay; an entire job/bisection can take longer.

The CLI and API share `data/`, but job reservations are process-local. For the dashboard demo,
use the SDK/API fleet. Stop standalone dev runners and CLI jobs before resetting shared data
or deleting `data/`; the API cannot cancel or drain work in another process. Do not use the
manual detonate action in another process while an automatic dev replay is still running.

## 4b. Metrics (pitch numbers, ~7 min, Bedrock)

```bash
uv run python -m engine.dev.testset            # 20 live runs: 10 poisoned (Liam's V1..V7), 10 clean
uv run python -m engine.cli metrics            # re-print from data/ + data/testset_labels.json
```

Measured 2026-10-10 (Liam's agent, gpt-oss-20b): attack attempted in 6 of 10 poisoned runs, detected 6/6,
0 runs leaked, 0 of 10 clean runs frozen, time to detect 5.9 ms, time to contain 8.9 ms (medians),
time to verdict 13.5 s. All 6 attacks used the attacker's address, which the hard rules catch by design.

## 4c. Gate layer 2 (decision model)

On by default in live mode: `gpt-oss-safeguard-20b` judges outbound calls the hard rules allowed (~2 s each;
reads are not judged). `MIRAGE_LAYER2=0` turns it off; `MIRAGE_GATE_THRESHOLD=0.7` sets how sure it must be.
Score the gate model (Bedrock): `uv run python -m engine.dev.gate_eval [--model openai.gpt-oss-safeguard-120b]`
(29 cases from `engine/detection/gate_eval.jsonl`: real fleet calls, tricky legit calls, stealth attacks).
Between `MIRAGE_GATE_REVIEW=0.4` and the threshold, the call waits for a human: `GET /approvals`, then
`POST /approvals/<call_id>/approve` or `/reject` with `{"actor", "reason"}` (Unfreeze / Kill in the UI do the same).
Tests always run with it off. Measured: 0 false freezes on the live 4-agent fleet (58 decisions), and 3/4 stealth
exports to an allowed domain caught by the model (all 4 by the BULK_RECORDS rule).

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
