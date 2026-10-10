# Start Mirage manually

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
