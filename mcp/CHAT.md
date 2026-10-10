# Ask Mirage backend delivery

Goal and demo step: make the natural-language operator interface cover incident inspection,
detonation, deterministic proof, bisection, false-positive unfreeze, kill and coding-agent
handoff (`PRODUCT.md` demo 1:00–2:40). Person B owns this HTTP/MCP experience; engine
implementation and guards remain Person A's. No `engine/`, `web/` or `PRODUCT.md` edits.

## Approach and sources

Reuse the existing [`createServer`](src/server.ts), with official MCP SDK in-memory
transports and `Client.listTools/callTool`. The service does not duplicate tool handlers.
Use Node's HTTP server, environment loader, abort signals and UUIDs, plus the official
AWS SDK `ConverseStreamCommand`; no HTTP framework or synthetic model fallback.
The coordinator/user authorized this approach and the additive user-only handoff endpoint.

- [AWS SDK v3 Bedrock streaming examples](https://docs.aws.amazon.com/sdk-for-javascript/v3/developer-guide/javascript_bedrock-runtime_code_examples.html)
- [Bedrock API key authentication](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html)
- [MCP TypeScript SDK v1](https://github.com/modelcontextprotocol/typescript-sdk/tree/v1.x)
- Shared source of truth: `CONTRACTS.md` §13, `contracts/models.py`,
  `contracts/fixtures/chat_demo.jsonl` (updated together).

## Startup and wire

From repo root, configure the gitignored `.env` with a short-term
`AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION=us-east-1`, and `BEDROCK_CHAT_MODEL_ID`.
An empty chat ID falls back to the existing agent ID, then generic model ID. IDs are
never hardcoded. The model must support ConverseStream and tool use.

```sh
cd mcp
npm ci
npm run build
npm run chat
```

Chat binds `127.0.0.1:8001`; existing engine stays on `localhost:8000` (`MIRAGE_API`).
Frontend owns the same-origin Vite `/chat` proxy (`MIRAGE_CHAT_API` defaults to
`http://localhost:8001`). `MIRAGE_CHAT_ORIGINS` lists explicit browser origins forwarded
through that proxy. No CORS. Non-loopback Host and cross-site requests are rejected.

`POST /chat/turn` sends `{session_id?, message, actor}` and receives the dispatched
SSE events. Only the server owns history/tool results. `POST /chat/approvals/:id`
submits `{action: "accept" | "decline", content?}`; `{accepted:true}` acknowledges receipt,
while the eventual tool result confirms engine outcome. The original stream remains
open through the dynamic MCP form. Typed confirmations, decline, wrong phrase and blank
reason retain the existing MCP semantics. Approval expires in two minutes; duplicate,
stale and disconnected submissions return 409.

`send_fix` returns a sanitized tool result with `structuredContent.handoff_url`.
The frontend fetches `GET /chat/handoffs/:id` only after the human clicks Copy/Download.
It returns the original prompt as a plaintext attachment. Prompt, capability token and
download URL are kept out of model continuation; prompt/token are absent from tool cards.
A safe plain Codex URL may be shown to the user. Human merge and clean restart remain
outside the tool catalogue.

Stopping generation cancels the model, declines pending approvals and stops continuation.
It does **not** undo already-started engine actions. Read current status before another
action. The service never automatically retries Bedrock or effect calls, and blocks
same-tool/same-target repeat effects within a turn. Bounds and expiry are in §13.

## Evidence (2026-10-10)

- `cd mcp && npm run build`: passed.
- `cd mcp && npm test`: 29 tests passed across three files. Real local HTTP/SSE and actual
  MCP server/client transport; model streams and engine HTTP replies are mocked.
  Covers eight-tool parity/execution, progress, fences/audit labels, wrong/declined/blank
  approval, timeout, stale/double submit, cancellation before/after an engine action,
  malformed/rejected args, guard refusal, bounded rounds/history/sessions/active turns,
  JSON/body/origin/Host checks, provider/in-stream errors and handoff isolation/download.
- Official AWS SDK middleware test substitutes only HTTP transport: bearer signing,
  `us-east-1` endpoint, configured model fallback, ConverseStream/tool serialization and
  no retry are verified without provider traffic.
- `uv run python mcp/scripts/validate-chat-contract.py`: all nine wire examples and request
  trust-boundary assertions passed; all eight event types covered.
- `uv run pytest tests/test_contract_models.py -q`: five tests passed.
- `git diff --check`: passed.
- Provider-live: one corrected read-only `npm run chat:smoke` passed using existing local
  credentials/model. Output: `{"ok":true,"provider":"Bedrock ConverseStream","region":"us-east-1","catalogue":8,"textChars":101,"toolCalls":0}`.
  No real engine actions or destructive service calls were made. The first attempt stopped
  locally in SDK auth selection (full scheme name instead of `httpBearerAuth`); this was
  corrected, regression-tested, and the coordinator approved the single follow-up.

## Review and remaining acceptance

Reviewed tool catalogue reuse, engine-only HTTP boundary, server-owned session history,
context trimming in whole turn groups, typed approval path, cancellation races, origin/Host
checks, redaction, handoff lifetime and request/time/resource bounds. The SDK defaults to
SigV4 first, so the explicit `httpBearerAuth` preference is necessary for the short-term key.
The service reports sanitized fixed error messages and never logs raw provider exceptions,
prompts, tokens or tool arguments.

This is a loopback, single-user laptop prototype: actor is an audit label, not account
authentication; IDs are temporary capabilities. Handoffs/history are in memory and disappear
on restart; handoffs expire with their idle session. Long-running engine operations may
outlive chat cancellation. Provider keys expire and model permissions may change.

Not checked here: the frontend composition or a complete live operator demo with real engine
detonation/bisection/actions. Those are coordinator acceptance after this backend PR and
the frontend PRs are composed. No merge or deployment was performed by this worker.
