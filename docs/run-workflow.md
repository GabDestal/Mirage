# Run activity workflow

The run page groups recorded actions into a compact set of activity areas. An area can be revisited: connectors show related work, not a planned one-pass sequence. The expandable full activity list preserves request chronology and numbers every action. Unknown tools remain visible under Other activity with readable tool-name captions.

Choosing an area or action pins its call ID. New events update outcomes and the overview without replacing that selection, stealing focus, closing its technical disclosure, or scrolling the page. Return to current activity resumes following the area containing the latest call. Navigating to another run resets selection.

A gate allow means awaiting a result, not success. An actual result establishes completed activity; an error establishes Needs attention. A completed run with a missing action result says Result not recorded. Blocked history is retained in the trace helper while an authoritative resume or subsequent result updates the displayed action state. Human audit events bind to their payload target; an unrelated run's unfreeze cannot release this action. The containment sentence applies only to the held action.

The existing trace helper remains in `pages/trace.tsx`, with its original type fields intact and two optional evidence fields (`resultRecorded`, `released`). No engine, SDK, contracts, incident route, fleet, avatar, global token, stream or API client changes are required. The run page keeps Fleet/chat's light appearance even on a dark OS theme, and disables motion for reduced-motion preferences.

## Validation

From `web/`:

```sh
npm run typecheck
npm run build
npm run lint
node src/lib/workflow.selfcheck.mjs
```

All pass. The self-check has 24 assertions covering permission without result, null result, error, missing result, paused/stopped states, interleaving/repetition, unknown tools, out-of-order replay evidence, duplicate requests, target-bound unfreeze, authoritative resume and 26 calls retained in four activity areas. It executes the actual trace fold using the already installed TypeScript compiler, without loading React or CSS in Node or adding a test framework.

Lint reports six existing Fast Refresh warnings in avatars-preview, avatars, actions and command-menu; none concern changed files. Build reports the existing bundle-size warning.

A local synthetic HTTP/SSE backend was served on loopback port 8018, with Vite on 5178. 39 native Chromium checks cover desktop 1440×900 and mobile 390×844, completed outreach, running and frozen meeting activity, ordinary email text, closed raw disclosure, keyboard Enter/Space activation, chronological action coverage, SSE result/error/status append without reload, pinned call/disclosure/focus/scroll, returning to a revisited current area, all six empty run statuses, loading, API error/retry, not found, target-bound resume and safe plain-text rendering. These checks use synthetic data only; they do not send real emails or call live providers.

## Local evidence

Screenshots and the browser check report are in `/tmp/mirage-workflow-qa/` on the implementation host:

- `outreach-desktop.png`, `outreach-mobile.png`
- `outreach-email-desktop.png`, `outreach-email-mobile.png`
- `outreach-26-actions-desktop.png`
- `frozen-desktop.png`, `frozen-mobile.png`
- `running-desktop.png`, `running-mobile.png`
- `running-pinned-desktop.png`, `running-current-desktop.png`
- `browser-check-results.json`

The local QA scripts (`backend.py`, `browser-check.mjs`, `resume-check.mjs`) remain beside the evidence. They are test fixtures, not product endpoints or production dependencies.

## Realtime limits

Activity uses the existing event cache, updated on receipt of SSE events. Existing run invalidation is batched at 120 ms; existing polling fallback runs at one second if the stream closes. The view says Watching current activity, not Live connected, because the client does not expose connection health. No new transport or timer is added. Provider-live timing, actions outside the SDK tool boundary, and production deployment were not tested by this UI change.
