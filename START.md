# Start Mirage

## Run the M1 demo

M1 has **four recorded background agents and recorded engine evidence**; Miragio
uses **real Bedrock and real MCP tools** against that recorded engine.

### First-time setup

Start at the main repo root below (adjust the path if your checkout is elsewhere).
Keep the existing root `.env`: add missing `AWS_BEARER_TOKEN_BEDROCK`,
`AWS_REGION=us-east-1`, and a working `BEDROCK_CHAT_MODEL_ID` following
[chat setup](mcp/CHAT.md). Use the current configured model, which must support
ConverseStream and tool use; do not overwrite the file or commit credentials.
Have `uv`, Python 3.12+ and Node/npm installed, then install dependencies and build chat once:

```sh
cd /Users/liamszefner/Business/hacks/Mirage
uv sync
npm ci --prefix mcp
npm ci --prefix web
npm run build --prefix mcp
```

### Every run

From the same repo root, use one terminal:

```sh
cd /Users/liamszefner/Business/hacks/Mirage
npm run build --prefix mcp
npm run dev:demo --prefix web
```

Open [http://127.0.0.1:5174](http://127.0.0.1:5174) and click **Sign in** with the
prefilled demo fields (a local demo sign-in; refreshing asks you to sign in again).
The launcher starts web, recorded engine and real chat automatically. The recording
plays production activity, freezes the meeting assistant, and shows the initial
**three-run detonation and proof automatically** while the healthy agents continue;
no initial detonation click is needed. Ask Miragio about the incident; later cause
search, handoff and verification stages advance through operator actions/approvals.

In **Fleet**, click **Restart demo recording** to replay from the beginning; it resets
only recorded evidence and replay decisions, launching no real agents. Stop with
**Ctrl+C** in the launch terminal: it stops only this launch's children and removes
its temporary state. Rerun the commands above for a fresh launch, including after
changing `.env`. Use this managed demo workflow on its own; do not combine it with
the three-terminal manual attach workflow below.

## M1 launcher details and options

From repo root, `npm run dev --prefix web -- --mode demo` and
`MIRAGE_UI_MODE=demo npm run dev --prefix web` select the same profile as `dev:demo`.
The launcher owns loopback web **5174**, recorded engine **8010**, and real Bedrock
chat **8011**. Each launch uses
absolute `contracts/fixtures/fleet_demo_4agents.jsonl` and a fresh temporary directory
for SQLite, snapshots and handoff tokens. Startup never attaches to or stops an
existing service, and never sends `/demo/start` or `/demo/reset`.

The launcher checks the env file exists without reading credentials.
Only chat receives provider credentials; Replay and Vite do not inherit them,
and Replay does not load `.env`. Missing
configuration fails chat startup; invalid credentials or denied model access remain
visible provider errors on a real chat turn. GET readiness does not spend a model call
or establish provider access. There is no scripted provider or automatic fallback.

For Orca rehearsal, use the original checkout's credentials without copying them:

```sh
MIRAGE_CHAT_ENV_FILE=/Users/liamszefner/Business/hacks/Mirage/.env npm run dev:demo --prefix web
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

From repo root, launcher checks use stub children/disposable paths and make no provider calls:

```sh
npm run demo:selfcheck --prefix web
npm run typecheck --prefix web
npm run build --prefix web
```

## Existing manual attach workflow

Open three separate terminals and run one block in each. These use the main repo
at `/Users/liamszefner/Business/hacks/Mirage`; adjust that path if your checkout is elsewhere.

Before starting, keep your existing root `.env`. Operator chat needs
`AWS_BEARER_TOKEN_BEDROCK` (your private Bedrock key), `AWS_REGION=us-east-1`, and
a working `BEDROCK_CHAT_MODEL_ID` (see [chat setup](mcp/CHAT.md)). Add missing settings
without overwriting the file; never commit the key.

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
