# Ask Mirage delivery evidence

Goal: connect the existing polished, light Ask Mirage surface to server-owned Bedrock/MCP operator chat for every demo operator step, while preserving the incumbent welcome and typography. Scope: page/transcript, SSE client/session lifecycle, exact-ID/schema approvals, explicit-click handoff, Vite proxy and chat-route shell theme. No engine/MCP/contracts/dependency implementations are owned by this feature.

## Local and synthetic acceptance

- `node --test web/tests/chat-client.test.ts`: **7 passed**. Fragmented UTF-8/CRLF SSE, event schema validation, interrupted streams, service errors, exact approval IDs/acknowledgment, abort propagation, and credential redaction.
- `cd web && npm run build`: **passed** with the final shared primitives and current sidebar composition. Vite reports its >500 kB single-bundle warning (~937 kB before gzip in this composition).
- `cd web && npm run lint`: **passed**, with eight existing warnings in avatars, avatar preview, command-menu and actions; no new warning in the changed feature files.
- `git diff --check`: **passed**.
- Impeccable static scan of `web/src/pages/chat.tsx` and `chat.css`: **no findings**. This is not a substitute for the browser checks.
- `MIRAGE_PLAYWRIGHT_MODULE=<external Playwright>/index.mjs node web/tests/chat-browser.mjs`: **18/18 checks passed** across 1440×1000 desktop and 390×844 mobile. Both emulate a dark OS preference, while chat and its chrome remain light. See [machine-readable results](chat-evidence/chat-browser-results.json).

The browser harness serves true HTTP SSE through the Vite `/chat` proxy, with visibly synthetic scripted replies and tool results. It never calls Bedrock, MCP or an engine mutation. The shell's engine read-only context remains independent. The matrix covers welcome, suggestion focus, multiline/Enter/Shift+Enter/IME, server session continuity, all eight tool cards, expandable redacted results, explicit-click handoff copy, required/exact schema confirmation, transient approval retry, accept/decline, HTTP acknowledgment after SSE completion, error/draft recovery, stop/new-chat fencing, long content and HTML escaping, scroll preservation/jump, offline draft, reduced motion and runtime errors (none).

The first inspection found missing accessible naming on Copy response and a long-distance smooth-scroll delay. The correction batch added explicit accessible naming, a direct latest-output anchor, pending decision acknowledgment fencing, a content resize observer, offline abort, and removed welcome-exit layout interference. The one complete confirmation matrix passed, and every final evidence screenshot was opened and inspected. The initial transient approval screenshots were replaced with settled captures; no old welcome, blurred status or overlapping status label remains. Vite had to restart after dependencies changed during integration; this was an initialization failure before that confirmation matrix, not a passing render claim.

## Screenshots

These are actual app captures using the explicitly synthetic SSE harness:

| State | Desktop | Mobile |
| --- | --- | --- |
| Welcome / dark OS preference | [desktop](chat-evidence/desktop.png) | [mobile](chat-evidence/mobile.png) |
| Tool evidence / handoff | [desktop](chat-evidence/desktop-tools.png) | [mobile](chat-evidence/mobile-tools.png) |
| Server schema approval | [desktop](chat-evidence/desktop-approval.png) | [mobile](chat-evidence/mobile-approval.png) |
| Failure / preserved draft | [desktop](chat-evidence/desktop-error.png) | [mobile](chat-evidence/mobile-error.png) |
| Long reply / scroll position preserved | [desktop](chat-evidence/desktop-long.png) | [mobile](chat-evidence/mobile-long.png) |

The captures use the sidebar already landed in main and the shared primitive source at `5dae334d530c6fd5ad036a3daf971f0aac18981c`. A concurrent branding-only main update can replace the favicon without changing the tested chat behavior.

## Real backend acceptance

Pending the coordinator-owned backend service on localhost:8001. This section will record the single approved read-only composed UI turn separately from synthetic acceptance. No mutation, detonation, root-cause action or secret-bearing handoff is included in the live validation scope.

## Preview and startup

Real-service preview: **http://127.0.0.1:5194/** (Vite `/chat` -> localhost:8001, `/api` -> localhost:8000). The backend must allow this origin. The synthetic QA preview uses port 5176 and harness port 8016. Startup commands and source references are in [CHAT.md](CHAT.md).

## Risks / remaining acceptance

The UI's memory-only conversation resets on navigation/reload. The server owns session expiry, action authority, disconnect cancellation, handoff access and model reliability. The formatter intentionally supports paragraphs/lists/code rather than rich Markdown tables or links. The shared visual library bundle warning remains. Full provider-live action/approval/handoff and full production demo acceptance require separate authorized integrated checks; synthetic green UI checks do not establish those. A human remains responsible for merging a coding-agent PR and approving a clean restart outside this chat's eight tools.
