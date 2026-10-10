# Miragio review

The final mascot implementation and all four browser combinations were checked on code SHA `036a4b04d15d5672e0aa256499ba2da1b15472f6`, based on `974a188`. Delivery rebases onto latest main; the PR records the delivered SHA and any difference from this browser-tested composition. Screenshots predate main's subsequent Fleet icon restoration.

- [Approved source beside SVG](source-comparison.png) and [320px static portrait](portrait.png).
- Welcome: [desktop light](desktop-light.png), [desktop dark OS](desktop-dark.png), [phone light](phone-light.png), [phone dark OS](phone-dark.png).
- Reduced motion: [desktop light](desktop-light-reduced.png), [desktop dark OS](desktop-dark-reduced.png), [phone light](phone-light-reduced.png), [phone dark OS](phone-dark-reduced.png).
- Static reply avatars: [desktop light](desktop-light-replies.png), [desktop dark OS](desktop-dark-replies.png), [phone light](phone-light-replies.png), [phone dark OS](phone-dark-replies.png).
- [Animation preview](animation.webm) shows pointer/reading, real blink and ripple motion, then preference changes and synthetic replies. [Browser assertions](results.json) record the four combinations.

The chat keeps its existing light surface under either OS theme. Desktop is 1440 × 1000; phone is 390 × 844. The approved raster is retained byte-for-byte (1296 × 1213); the SVG crops to the pale square tile without its outer white presentation margin.

Validation uses the existing fake sign-in and existing local synthetic chat SSE harness, plus read-only fleet GETs from the demo API. No approval submission, control-plane action, Bedrock call or production write was exercised. This is UI and synthetic transport evidence, not provider-live acceptance. Automated checks cover independent head/gaze, blink compression, changing ripples, reading pose, full pixel equality under reduced motion while typing/moving the pointer, hidden stillness, cleared timers/listeners, static reply instances, repeated unique IDs, two streamed turns, overflow and browser exceptions. Pixel comparison pins the portrait to integer screen coordinates so mobile composer resizing cannot change screenshot crop rounding.

`npm run typecheck`, `npm run build` and `npm run lint` pass. Existing Vite chunk-size warning and eight lint warnings in avatars-preview, agent avatars, actions and command-menu remain unrelated. The manual Impeccable detector ran exactly once on the mascot and two changed chat files: no findings.

To repeat locally with an existing external Playwright install (no project dependency changes):

```sh
PORT=8026 node web/tests/chat-harness.mjs
cd web
MIRAGE_CHAT_API=http://127.0.0.1:8026 npm run dev -- --host 127.0.0.1 --port 5186
MIRAGE_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs MIRAGE_CHROMIUM_EXECUTABLE=/absolute/path/to/chromium node tests/miragio-browser.mjs
```

Run the two servers in separate terminals; the demo API supplies read-only fleet context on port 8000. Playwright video recording also needs its external FFmpeg helper. Native phone touch hardware and production chat/model behavior are outside this scoped check.
