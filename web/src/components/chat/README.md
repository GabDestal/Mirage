# Mirage chat primitives

This Person B feature supports the incident-response demo's Ask Miragio tool activity and human approval step. It refines the incumbent light chat rather than replacing its layout. No engine, MCP, API, page, shell, or contract code changes.

Import `ChatComposer`, `ChatActivity`, `ChatToolCard`, and `ChatApprovalCard` from `@/components/chat-primitives`. The agreed props remain unchanged; the composer also accepts optional `inputRef: Ref<HTMLTextAreaElement>` for page-owned focus. The parent owns draft, submission, busy, stop, real activity labels, and pending approval. It must mark approval pending while a decision is sent. Use a stable request key when rendering multiple approval requests.

The controlled composer submits immediately and leaves clearing the draft to its parent. Enter sends, Shift+Enter inserts a newline, and composing/empty/busy/disabled submissions are ignored. Visual effect siblings never reparent the textarea or functional button. Auto height caps at 200px. The 36px silver send control has a 44px hit area. Error text is associated with the textarea.

The composer uses a plain neutral border and a static blue focus-within border; the decorative beam and its dependency have been removed. Dependencies: `thinking-orbs@0.3.2` (MIT), plus existing Motion. The send/stop control stays icon-only; no Metal overlay or canvas covers its functional icon. The 20px monochrome orb follows actual thinking/tool states only. Effects unmount when idle, offscreen, hidden, or reduced motion is enabled; reduced motion retains static focus styling and Lucide indicators.

Tool results use native `details`/`summary`, with real status and bounded panel/icon transitions. Status text swaps use Motion and the free Transitions.dev recipes with 4px travel and 2px blur; no invented reasoning or staged progress. Approval reveals once when visible, with a 220ms bounded transition.

Approval supports flat string, boolean, number, and integer fields; required fields; enum/const; numeric bounds; string length/pattern; email/URI formats. Unknown constraints or nested schemas fail closed and still allow decline. The actual MCP title `Type "<phrase>" to confirm` makes the phrase mandatory and exact; it is never prefilled. Required text must contain non-whitespace content. Browser validity runs before our constraint check. Content retains scalar types. This is presentation validation; the MCP/backend must enforce authority as before.

## Startup and evidence

```sh
cd web
npm ci
npm run dev -- --host 127.0.0.1 --port 5193 --strictPort
# http://127.0.0.1:5193/src/components/chat/preview.html
npm run build
npm run lint
node --experimental-strip-types src/components/chat/approval-schema.selfcheck.ts
```

The evidence below is historical, from before the composer beam removal; the screenshots and browser assertions do not verify the current composer. No preview or live UI was run for the removal.

The preview is a separate development HTML entry with synthetic examples and explicit controls. It is not imported into the production page. Build/typecheck passes; lint has only eight existing warnings outside this feature. The approval selfcheck passes 16 checks. A separate Vite production build of the preview entry also passes (562.55kB JS, 168.73kB gzip; standard large-chunk warning). The normal app retains its existing large-chunk warning.

Orca browser harness checks passed: 14 composer assertions covering IME/Enter/Shift+Enter, composition form submission, busy/disabled/empty guards, stop, immediate callback, controlled clearing, stable node and selection; seven approval assertions covering pending locks, unsupported-schema refusal, decline, and native required validation. Additional checks verified exact phrase error, valid accept content, reduced-motion zero canvases/beam layers, simulated WebGL2 unsupported with functional textarea/send/status, and no horizontal overflow at 390px with expanded long output. Browser console showed no component errors. The first assertion run stalled on animation-frame waits in the embedded browser; timer-based waits completed, with no code change needed.

Screenshots are **component-harness evidence**, not integrated Bedrock/MCP acceptance. Desktop uses the incumbent 672px column; mobile is 390px with expanded long output. Final connected behavior and provider-live acceptance remain with the page/backend workers. Shader timing/performance on real mobile hardware was not tested.

The composer border/button follow-up passes build/typecheck, lint (the same eight existing warnings), the Impeccable detector, and 17 browser assertions for icon visibility, input/composition guards, stop, focus, selection, and error association. Orca harness geometry matches the full composer perimeter at 1280px and 390px without horizontal overflow; a simulated reduced-motion preference has no beam/canvas and retains static focus and arrow. Orca's media emulation did not change the native media query, and embedded browser timing can stall when its panel is hidden, so harness screenshots alone do not establish native reduced-motion or animation timing acceptance. The coordinator separately verified the untouched preview in native Dia: focused `hey` shows the arrow and the colorful glow travels around the perimeter. No provider calls or real writes were used.

- [Desktop screenshot](evidence/desktop.png)
- [Mobile screenshot](evidence/mobile.png)

## Source references

- Incumbent: `web/src/pages/chat.tsx`, `web/src/pages/chat.css`.
- Opereit reference (read-only): `/Users/liamszefner/Opereit/obsydian/apps/dashboard/src/app/agent/components/chat-input.tsx`; visual direction retained, artificial submit delay omitted as requested.
- Actual MCP elicitation shape: `mcp/src/server.ts`, `confirm()`.
- [Beam docs](https://libraries.dev/beam), [orbs docs](https://libraries.dev/orbs), [MIT source and examples](https://github.com/Jakubantalik/Libraries.dev).
- Free motion recipes: [text states swap](https://github.com/Jakubantalik/transitions.dev/blob/main/cli/free/text-states-swap.md), [panel reveal](https://github.com/Jakubantalik/transitions.dev/blob/main/cli/free/panel-reveal.md), [icon swap](https://github.com/Jakubantalik/transitions.dev/blob/main/cli/free/icon-swap.md). No Pro dependency or purchase.
