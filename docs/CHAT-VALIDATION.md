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

The captures use the sidebar already landed in main and the shared primitive source at `5dae334d530c6fd5ad036a3daf971f0aac18981c`. Final [desktop](chat-evidence/final-desktop.png) and [mobile](chat-evidence/final-mobile.png) welcome captures were taken after replaying only this feature onto exact merged main `1cb3a1c383e72241ea8e2de85ecc43569583b492`, preserving the approved horizon mark. The synthetic state captures predate that branding-only update.

## Real backend acceptance

**Full live UI/tool-result acceptance remains unconfirmed.** The merged backend was built and started in a dedicated Orca runtime terminal with the authorized preview origin; the real engine was already on localhost:8000. Two strictly read-only `list_runs` UI submissions were made: the originally authorized single turn, then one explicitly approved capture repair. The first evidence collector failed when Chromium could not expose the consumed SSE response body. The second reached completed assistant prose and an enabled Copy response action, then failed on a singleton text assertion because the response had two prose segments around tool activity. No final live tool/result assertion or screenshot was recorded, and no further provider attempt was made under the coordinator's explicit bound. These are evidence-collection failures, not evidence of a passed end-to-end tool sequence. No mutation, detonation, root-cause action or secret-bearing handoff was requested.

The backend worker's own provider smoke is reported separately by that PR and is not re-certified here. The final local client/build and complete synthetic UI acceptance are proven above. A coordinator can inspect the running real preview and authorize a future bounded live verification if needed.

## Preview and startup

Real-service preview: **http://127.0.0.1:5194/** (Vite `/chat` -> localhost:8001, `/api` -> localhost:8000). The backend must allow this origin. Runtime terminals: chat service `term_2ec83412-1a70-4907-9925-c23bde055569`, Vite preview `term_b03d5631-c881-4b4c-87ce-5fb90fd2216c`; these are dedicated runtime previews, separate from the worker agent. The synthetic QA used port 5176 and harness port 8016. Startup commands and source references are in [CHAT.md](CHAT.md).

## Risks / remaining acceptance

The UI's memory-only conversation resets on navigation/reload. The server owns session expiry, action authority, disconnect cancellation, handoff access and model reliability. The formatter intentionally supports paragraphs/lists/code rather than rich Markdown tables or links. The shared visual library bundle warning remains. Full provider-live action/approval/handoff and full production demo acceptance require separate authorized integrated checks; synthetic green UI checks do not establish those. A human remains responsible for merging a coding-agent PR and approving a clean restart outside this chat's eight tools.
