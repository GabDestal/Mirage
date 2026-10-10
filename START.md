# Start Mirage

## Milestone 1 — recorded background, real Miragio

Install dependencies once and build the real chat service from this checkout:

```sh
uv sync
cd mcp
npm ci
npm run build
cd ../web
npm ci
npm run dev -- --mode demo
```

`npm run dev:demo` and `MIRAGE_UI_MODE=demo npm run dev` select the same profile.
Open [http://127.0.0.1:5174](http://127.0.0.1:5174). The launcher owns loopback web
**5174**, recorded engine **8010**, and real Bedrock chat **8011**. Each launch uses
absolute `contracts/fixtures/fleet_demo_4agents.jsonl` and a fresh temporary directory
for SQLite, snapshots and handoff tokens. Ctrl+C stops only its children and removes
that disposable state. Startup never attaches to or stops an existing service, and
never sends `/demo/start` or `/demo/reset`.

Configure root `.env` with `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION=us-east-1`, and a
working `BEDROCK_CHAT_MODEL_ID` (see [chat setup](mcp/CHAT.md)). The launcher checks
the file exists without reading credentials. Only chat receives provider credentials;
Replay and Vite do not inherit them, and Replay does not load `.env`. Missing
configuration fails chat startup; invalid credentials or denied model access remain
visible provider errors on a real chat turn. GET readiness does not spend a model call
or establish provider access. There is no scripted provider or automatic fallback.

For Orca rehearsal, use the original checkout's credentials without copying them:

```sh
MIRAGE_CHAT_ENV_FILE=/Users/liamszefner/Business/hacks/Mirage/.env npm run dev -- --mode demo
```

This override must be absolute. Chat keeps shell values ahead of file defaults;
launcher routing and mode are set before loading the file. Never put credentials in
`VITE_*` variables or commit `.env`.

CLI `--mode live|demo` wins over `MIRAGE_UI_MODE`; default `live` is the existing
attach workflow below. Demo sets child `MIRAGE_UI_MODE=demo` and exposes only the
nonsecret `import.meta.env.VITE_MIRAGE_UI_MODE='demo'` UI flag. The engine receives
`MIRAGE_MODE=replay`, `MIRAGE_REPLAY_MANAGED=1` and isolated state paths; chat and Vite
use the same engine URL. Chat allows the actual localhost/127.0.0.1 web origins.

Demo accepts `--port` (web), `--engine-port`, `--chat-port`, and `--open`. Environment
defaults are `MIRAGE_DEMO_WEB_PORT`, `MIRAGE_DEMO_ENGINE_PORT`, `MIRAGE_DEMO_CHAT_PORT`;
CLI ports win. Ports must be distinct and cannot use attach ports 5173/8000/8001.
Every occupied port fails startup. Conflicting mode, proxies, fixture, chat port/origins
or inherited state paths also fail; unset conflicting `MIRAGE_*` values. Other Vite
flags are rejected in demo so they cannot change its host/config. `MIRAGE_REPLAY_SPEED`
defaults to **2** (2× time); finite values >0 through 10 are accepted, instant playback
is rejected. Readiness defaults to 30 seconds per child; `MIRAGE_DEMO_READY_TIMEOUT_MS`
accepts 1–120000 milliseconds.

**M1 evidence:** production agents, detection, containment, detonation, proof and
fix/PR progression are recorded/simulated engine events. Miragio uses real Bedrock,
real MCP handlers and human approvals against that recorded engine. Recorded
handoff/fix evidence does not provide a runnable live snapshot, prove a coding agent
tested a repair, create/merge a real fix PR, or prove Gmail/Calendar/HubSpot integration.
Human merges remain manual.

**Later M2:** actual agents, live gate/containment, snapshot sandbox execution and fresh
deterministic proof require separate acceptance. This launcher implements only M1;
it adds no live engine profile and starts no victim fleet or engine provider/job work.
Managed Replay lifecycle and UI/chat presentation land in companion PRs.

Launcher checks use stub children/disposable paths and make no provider calls:

```sh
cd web
npm run demo:selfcheck
npm run typecheck
npm run build
```

## Existing manual attach workflow

Open three separate terminals and run one block in each. These use the main repo
at `/Users/liamszefner/Business/hacks/Mirage`; adjust that path if your checkout is elsewhere.

Before starting, keep your existing root `.env`. Operator chat needs
`AWS_BEARER_TOKEN_BEDROCK` (your private Bedrock key), `AWS_REGION=us-east-1`, and
`BEDROCK_CHAT_MODEL_ID=us.anthropic.claude-opus-4-8`. Add missing settings without
overwriting the file; never commit the key.

If dependencies are missing, run `uv sync` at the repo root and `npm ci` inside
each of `mcp/` and `web/` once.

## Terminal 1 — engine (8000)

```sh
cd /Users/liamszefner/Business/hacks/Mirage
uv run uvicorn engine.api.server:app --host 127.0.0.1 --port 8000
```

Engine mode comes from the current `MIRAGE_MODE` shell environment and defaults to
`live`; this command does not load the mode from `.env`. To choose explicitly,
prefix the engine command with `MIRAGE_MODE=live` (real engine) or `MIRAGE_MODE=replay`
(recorded fixtures for UI work, no engine Bedrock calls), as in the
[engine runbook](docs/RUNBOOK.md). Operator chat still uses Bedrock in either mode.

## Terminal 2 — operator chat (internal loopback 8001)

```sh
cd /Users/liamszefner/Business/hacks/Mirage/mcp
npm run build && npm run chat
```

Keep chat on its default `127.0.0.1:8001`; the web app proxies chat requests there.

## Terminal 3 — web (5173)

```sh
cd /Users/liamszefner/Business/hacks/Mirage/web
npm run dev -- --port 5173 --strictPort
```

Open [http://localhost:5173](http://localhost:5173). These commands start the
services only; launch demo scenarios manually when ready.

If chat shows **502**, first check that Terminal 2 started successfully and is
listening on port **8001**. More chat setup and troubleshooting: [operator chat](mcp/CHAT.md).

Stop each service with **Ctrl+C** in its terminal.
