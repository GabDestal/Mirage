# Ask Mirage operator chat

Ask Mirage now streams the real operator service response and its MCP activity into the existing light chat layout. It serves the full demo operator path: review runs, inspect evidence and audit, detonate, find the cause, resolve false positives, end a run, and hand an incident to a coding agent. The page accepts all eight tool names (`list_runs`, `get_incident`, `get_audit`, `detonate`, `find_cause`, `unfreeze`, `kill`, `send_fix`) through the shared event contract; it does not implement their handlers or send engine mutations directly.

## Run

Start the engine using the repository's existing engine instructions, on localhost:8000. Then, with the operator chat backend and visual primitive PRs available:

```sh
cd mcp
npm ci
npm run build
npm run chat
```

In another terminal:

```sh
cd web
npm ci
npm run dev -- --host 127.0.0.1 --port 5194
```

The backend must allow the preview origin `http://127.0.0.1:5194` through its chat-origin configuration. Vite proxies `/api` to `MIRAGE_API` (default http://localhost:8000) and `/chat` to `MIRAGE_CHAT_API` (default http://localhost:8001). The chat proxy keeps the `/chat` prefix. Credentials remain on the backend; none are sent to the browser in the chat configuration. Use the existing demo sign-in screen.

## Behavior and boundaries

- POST `/chat/turn` sends only `{session_id?, message, actor}`. Server-generated sessions own bounded model history; the UI sends no tool results or conversation history. The demo actor is `liam`, matching existing shell actions.
- `session`, `text_delta`, `tool_start`, `tool_progress`, `tool_result`, `approval_required`, `done`, and `error` SSE events drive the transcript. Text is appended as received. Activity reflects received events or pending network response; there is no fabricated reasoning, verdict, or percentage progress.
- The fetch stream handles fragmented UTF-8, CRLF, comments, and multiple frames. EOF without `done` preserves partial output and explains the interruption. HTTP/non-SSE/protocol errors retain the draft for explicit recovery. Retries are operator initiated because a prior tool action may already have started.
- Approval forms receive the exact server schema and POST only the decision to the corresponding server approval ID. Duplicate clicks are fenced. Failed acknowledgments retain form values for retry while the stream remains active. An acknowledged decision remains accurate if the stream finishes before the approval HTTP response.
- Stop response aborts this turn's connection. The backend is responsible for aborting model continuation and declining unresolved approvals on disconnect. Already-started engine actions may continue. New chat also disconnects the current turn and resets its client session reference; asynchronous returns cannot refill a newly reset draft. Global Stop all remains in the shell and is a separate action.
- Follow-scroll stops when the operator scrolls away. Jump to latest anchors directly to the latest output. Expanded evidence and viewport changes are observed. The transcript is keyboard focusable; the shared composer owns Enter/Shift+Enter, IME composition and multiline autosizing.
- Assistant prose supports plain paragraphs, lists, inline strong/code and fenced code. React escapes content; no raw HTML or executable links are rendered. Large code/results wrap and scroll within the transcript. Credential-shaped fields and common credential strings are redacted from expandable results and general response/result clipboard actions.
- `send_fix` may expose a server-generated `structuredContent.handoff_url`. Only an internal `/chat/handoffs/<safe-id>` path is accepted. Copy prompt / Download prompt fetch plaintext on an explicit operator click, reject redirects, and never insert the sensitive prompt into the transcript or model context. The operator is told the prompt contains a scoped incident token. The backend controls handoff lifetime/access.
- Chat and its shell explicitly use light colors regardless of OS theme. Existing layout, typography, welcome text, suggestions, sidebar and global STOP are preserved. Motion is quiet, honors reduced-motion preferences and only reveals content that has arrived.

## Reuse and sources

The user approved refining the existing Opereit-like composition and using the shared visual worker module, with no further approach approval required. This is Person B experience work; engine, MCP handlers, Pydantic contracts and dependency ownership remain outside this PR. The page consumes `ChatComposer`, `ChatActivity`, `ChatToolCard` and `ChatApprovalCard` from the separately owned component module.

Reference files were read without modification:

- `/Users/liamszefner/Opereit/obsydian/apps/dashboard/src/app/agent/components/chat-input.tsx`
- `/Users/liamszefner/Opereit/obsydian/apps/dashboard/src/app/agent/components/chat-container.tsx`
- `/Users/liamszefner/Opereit/obsydian/apps/dashboard/src/app/agent/components/message-bubble.tsx`

Installed Motion is reused for restrained streaming text reveal and the latest-output control. Shared visual primitives use the approved Libraries.dev packages. Public [Transitions.dev](https://transitions.dev/) recipes informed [text state swap](https://transitions.dev/studio.html?lib=text-states-swap), [panel reveal](https://transitions.dev/studio.html?lib=panel-reveal), [skeleton reveal](https://transitions.dev/studio.html?lib=skeleton-loader-and-reveal), and streaming reveal behavior. No Pro purchase or additional renderer dependency was introduced by this feature. [Libraries.dev](https://libraries.dev/) and the component module's own README document the selected visual libraries.

## Reproduce synthetic UI checks

These checks use a scripted local SSE service, not Bedrock, MCP or engine mutations. Every scripted response explicitly says it is synthetic. The existing engine may supply read-only fleet context to the shell; the harness never calls it.

```sh
node --test web/tests/chat-client.test.ts
node web/tests/chat-harness.mjs
```

Run the UI on a separate test port:

```sh
cd web
MIRAGE_CHAT_API=http://127.0.0.1:8016 npm run dev -- --host 127.0.0.1 --port 5176
```

With an external Playwright installation and its Chromium browser, from the repository root:

```sh
MIRAGE_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node web/tests/chat-browser.mjs
```

The optional `MIRAGE_UI_URL` and `MIRAGE_QA_DIR` select the harness-backed UI and evidence destination. The script is deliberately separate from package dependencies and must run only against `chat-harness.mjs`. It checks 1440×1000 desktop and 390×844 mobile, both with dark OS preference; suggestion focus, Enter/Shift+Enter/IME; server session continuity; all eight tool cards; redacted expandable evidence; click-only handoff retrieval; approval validation/retry/accept/decline and acknowledgment race; model error/draft recovery; stop/new-chat fencing; long-content safe rendering; scroll preservation/jump; offline state; reduced motion; and uncaught runtime errors.

## Validation and remaining limits

See [CHAT-VALIDATION.md](CHAT-VALIDATION.md) for the final checks, screenshots, acceptance scope and preview URL. Browser screenshots of synthetic harness responses establish UI/transport behavior only. Live acceptance is reported separately; no production mutation is required by these checks.

The conversation and draft are intentionally memory-only: navigation away or reload ends the stream and discards local transcript/draft. There is no persisted conversation list. Rich Markdown tables/links are not part of the lightweight formatter. The shared visual libraries increase the existing single bundle; Vite's >500 kB warning remains visible. Human approval of a clean restart and GitHub merge remains outside chat tools.
