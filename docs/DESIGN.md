# Mirage — Design system

Status: v2, 2026-10-10. Owner: Liam. `docs/UX.md` says **what** each screen shows (to be realigned
after V1). This file says **how it looks, moves and feels**. On look and feel, this file wins.
Builders: load the `impeccable` skill (mode: Operate) and `emil-design-eng`. This file is the
committed world; impeccable's craft floor applies on top.

## 1. North star

**Security that feels like Linear and Vercel, not like a SOC.**
Mirage is for a 10-person company with no security team. The owner opens it and knows in one second
that their agents are fine. When one is not, the screen tells the story in plain words and offers
one obvious next step.

Simple is not plain. The screen is quiet; the quality lives in the interactions: how a row responds
under the cursor, how an agent freezes, how the Mirage path appears where production stopped.

## 2. Principles

1. **Quiet when healthy.** A healthy fleet is ink on paper. No color, no markers, no badges.
2. **State is shown by the thing itself**, never by a decoration next to it. The agent's avatar
   reacts, the sentence changes, the trace stops. No status dots, no status pills, no colored stripes.
3. **One main action per screen.** The engine's `next_action` picks it.
4. **Show the flow, not the log.** What the agent did is a workflow you can see (n8n style).
   Raw data is one click away, never in the default view.
5. **Plain words.** "Frozen", "Would have sent 40 contacts", "Caused by the calendar invite".
   Never "IOC", "TTP", "exfiltration vector". Framework IDs (OWASP ASI01, MITRE) live in the detail sheet.
6. **Safe to click.** Unfreeze, Kill, STOP ALL say what will happen and ask for a reason.
7. **Fast.** Optimistic updates on human actions, skeletons instead of spinners, keyboard first.

## 3. Anti-AI-look rules (hard)

From the `impeccable` craft floor plus our own list. A reviewer rejects a PR that does any of these.

- No status dots, no pill badges used as content, no count badges on nav items.
- No colored `border-left` / stripe on rows or cards. No colored glow halos (zero-offset shadows).
- No small uppercase label above a heading (eyebrow). No section numbers (01 / 02).
- No grid of same-size icon + title + text cards. No nested cards. No hero-metric tiles.
- No gradient text, no decorative glass or blur, no grid or noise backgrounds.
- Monospace only for real code and data: tool names, arguments, IDs. Never as "technical" styling.
- No emoji or unicode glyphs as icons. Icons are `lucide-react` or our own SVG.
- No Magic UI eye candy: no Border Beam, Particles, Meteors, Shine Border, Sparkles, Aurora text.
  Magic UI is allowed only where motion carries state (see §9).
- No modal where a side sheet or inline step works. The reason dialog is the one exception.
- No charts, gauges, threat meters or world maps on the main screens.

## 4. Color

Paper, ink, and one brand color: **Mirage aqua**. A desert mirage shows water that is not there;
our color is that water. It marks two things only: the brand, and anything that happened in the
simulation (not in production). Red is the only alarm color.

| Token | Light (default) | Dark | Use |
|---|---|---|---|
| `--paper` | `#FCFCFA` | `#0C0D0D` | Page |
| `--paper-2` | `#F4F4F1` | `#141515` | Sidebar, sheet, hover |
| `--paper-3` | `#EAEAE6` | `#1D1E1E` | Selected, pressed |
| `--line` | `#E3E3DE` | `#262828` | 1 px borders and dividers |
| `--ink` | `#151716` | `#ECEDEA` | Text, primary button fill |
| `--ink-2` | `#5C605E` | `#9DA19F` | Secondary text |
| `--ink-3` | `#8C908E` | `#6E7270` | Timestamps, IDs, placeholders |
| `--mirage` | `#0E8C86` | `#3CC7BE` | Brand, simulated path, Mirage text |
| `--mirage-wash` | `#E3F4F2` | `#0F2826` | Background of simulated areas |
| `--alarm` | `#D93A2B` | `#FF6A5C` | Frozen, blocked, STOP ALL |
| `--alarm-wash` | `#FBE9E6` | `#2A1412` | Background of the blocked node only |

- The primary button is **ink** (black on light, white on dark), Vercel style. Not aqua.
- Waiting for a human has no color: the avatar and the sentence carry it.
- Text contrast ≥ 4.5:1 body, ≥ 3:1 large text and icons. Theme the browser surfaces too:
  `::selection` in `--mirage-wash`, focus ring 2 px `--ink` with 2 px offset, scrollbars in `--line`.

## 5. Type

- **Geist Sans** for everything, **Geist Mono** for tool names, arguments, IDs (npm `geist`, self-hosted).
- Tabular numbers (`font-variant-numeric: tabular-nums`) for counts, times, durations.
- Fixed rem scale, ratio ~1.2:

| Role | Size / line | Weight |
|---|---|---|
| Incident headline | 24 / 32 | 600, tracking −0.02em |
| Page title | 16 / 24 | 600 |
| Body | 14 / 20 | 400 |
| Control label | 13 / 20 | 500 |
| Meta | 12 / 16 | 400, `--ink-3` |
| Mono | 12.5 / 18 | 400 |

- Sentence case everywhere. No uppercase labels.

## 6. Space, shape, depth

- 4 px grid. Steps: 4, 8, 12, 16, 24, 32, 48, 64. Tight inside a group, generous between groups.
- Radius: 8 px controls, 12 px nodes / sheets / menus. Full radius only for avatars' container if round.
- One elevation rule: flat things get a 1 px `--line` border; floating things (menu, ⌘K, sheet,
  toast) get a soft offset shadow `0 12px 32px -8px rgb(21 23 22 / 0.18)` and **no** border.
- Rows: 52 px, full-bleed hover in `--paper-2`, no dividers inside a group.

## 7. Layout

```
┌──────────────┬───────────────────────────────────────────────────────┐
│ Mirage       │ Fleet                    All 3 agents are working.    │
│              │───────────────────────────────────────────────────────│
│ Fleet        │ (owl) Meeting assistant   read_calendar → crm_query → │
│ Incidents    │ (bee) Invoicing           …                           │
│              │ (fox) PR reviewer         …                           │
│ Agents       │                                                       │
│ (owl) Meeting│                                                       │
│ (bee) Invoic.│                                                       │
│ (fox) PR rev.│                                                       │
│              │                                                       │
│ Search    ⌘K │                                                       │
│ Stop all     │                                                       │
└──────────────┴───────────────────────────────────────────────────────┘
```

- **Sidebar, 232 px, always visible**, `--paper-2`. Logo, Fleet, Incidents, then the agents with
  their avatars (the avatar shows state, so the sidebar is a live view of the fleet), then Search ⌘K
  and **Stop all** at the bottom (text button in `--alarm`, always reachable, never hidden).
- **Header, 52 px:** page title left, the status sentence right ("All 3 agents are working." /
  "Meeting assistant is frozen. 2 others keep working."). The sentence is the status. Nothing else.
- **Content:** max 1080 px for lists, 880 px for the incident story.
- **Side sheet** (right, 480 px) for any detail: tool call, input, full log. `Esc` closes.
- Desktop first: 1440×900 projector, must hold at 1280. Under 1100 px the sidebar collapses to avatars.

## 8. Agent avatars (the status system)

Custom SVG characters in `web/src/agents/avatars.tsx`. Crisp geometry, not illustration: built from
circles, rounded rects and a few strokes, two flat colors each, drawn on a 24-unit grid.
Sizes: 20 px (sidebar, rows), 32 px (headers), 64 px (incident headline, empty states).

| Agent | Character | Body color |
|---|---|---|
| Meeting assistant | owl | soft clay |
| Support | octopus | soft rose |
| Invoicing | bee | soft butter |
| Outreach | paper plane | soft sky |
| PR reviewer | fox | soft apricot |
| Unknown agent | geometric blob, color + shape hashed from the name | — |

Each avatar has **states**, drawn by changing the face and adding one element. The avatar plus one
plain word in the row text is the whole status system.

| State | Avatar | Row text |
|---|---|---|
| Working | eyes open, a slow blink every ~6 s | "Working · read_calendar" |
| Idle / done | eyes half closed, still | "Done 2 min ago" |
| Waiting for you | eyes look up at the viewer, small raised hand | "Waiting for your approval" |
| Frozen | encased in a translucent ice block (`--alarm` outline), eyes closed | "Frozen 0.8 s after reading an invite" |
| Killed | desaturated to `--ink-3`, eyes are two short lines | "Stopped by Liam" |
| In Mirage | the character drawn in `--mirage` with the heat-shimmer (§9) | "Replaying in Mirage · 2 of 3" |

Rules: the state change animates (§9), the blink is the only idle motion and stops under reduced motion.

## 9. Motion

Crisp, like Linear. Motion explains a state change; it never decorates a repeated action.

```css
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);     /* enters, most UI */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1); /* things moving on screen */
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);  /* side sheet */
--dur-press: 120ms; --dur-fast: 160ms; --dur-base: 220ms; --dur-sheet: 320ms;
```

**The one authored moment: the heat shimmer.** Anything simulated in Mirage (the Mirage path in the
trace, the avatar in Mirage, the replay counter) is drawn in `--mirage` with a slow horizontal
shimmer: an animated `mask-image` linear gradient (lighter band, 2.4 s, linear, infinite) like heat
over a road. Under reduced motion it is static. Nothing else in the product shimmers.

| Moment | Animation |
|---|---|
| Press (any control) | `scale(0.97)`, 120 ms |
| Hover | background only, 120 ms `ease`, behind `@media (hover: hover)` |
| Menu, popover, tooltip | opacity + `scale(0.96 → 1)` from the trigger, 160 ms ease-out; adjacent tooltips instant |
| Side sheet | `translateX(100%) → 0`, 320 ms ease-drawer; exit 200 ms |
| New step in a trace | node fades + `translateX(-8px → 0)`, 220 ms; its edge draws in (`stroke-dashoffset`) |
| **Freeze** | ice block grows over the avatar (`scale(0.9 → 1)` + opacity, 240 ms), the blocked node turns `--alarm-wash` with a 1 px `--alarm` border, the header sentence crossfades with a 2 px blur bridge. Other rows keep moving. |
| Mirage path appears | edges draw past the blocked node one by one (stagger 80 ms), then the shimmer starts |
| Verdict number | counts up once in 600 ms (Magic UI `NumberTicker`) |
| Cause found | the cause input's border goes `--ink` → `--alarm` and its label appears, 220 ms |

Never animate: ⌘K open/close, keyboard navigation, sidebar page switches, list re-sorts.
Animate `transform`, `opacity`, `mask`, `filter`, colors. Exits faster than enters.
Magic UI allowed: `NumberTicker`, `AnimatedBeam` (only for a live edge, if it beats our own), `BlurFade`
(only for the trace node enter). Nothing else from Magic UI without a reason in the PR.

## 10. The trace (n8n style)

Every run is a left-to-right flow.

```
 [Calendar invite] → [Meeting assistant] → [crm_export] → [send_email to attacker@…]  ✕ Blocked
                                                                └ ─ ─ Mirage: [send_email] → 40 contacts left
```

- **Nodes:** 12 px radius, 208 × 60, `--paper` with 1 px `--line`. Icon (lucide, 16 px) + name
  (mono for tools, sans for inputs and the agent) + one meta line ("40 rows · 0.3 s").
- **Edges:** 1.5 px `--line`. While live, the newest edge carries a short `--ink-3` dash moving along it.
- **Blocked node:** `--alarm-wash` fill, 1 px `--alarm` border, a lucide `ShieldX` icon and
  "Blocked: destination not allowed" as the meta line. No badge.
- **Malicious input:** same treatment once the cause is known.
- **Mirage path:** after a detonation, the path the agent *would have* taken continues past the
  blocked node, dashed, in `--mirage` on a `--mirage-wash` band, with the heat shimmer.
  Production stops; Mirage continues. This image is the pitch.
- **Bisection:** each input node gets a meta line: "Removed → clean" or "Removed → still compromised".
- Click a node → side sheet: arguments, result, timing, rule hit, policies (OWASP / MITRE IDs here).
  Raw JSON in a collapsed section at the bottom.
- **Compact trace** in Fleet rows: tool names in mono separated by `→`, newest last, older ones fade to
  `--ink-3`, the blocked one in `--alarm`. Plain text and flexbox, no React Flow.
- **Full trace** on run and incident pages: `@xyflow/react`, read-only, our own node components,
  layout computed by us (`x = index * 248`), pan on, zoom limited, minimap and controls off.

## 11. Components

shadcn/ui primitives restyled with these tokens.

- **Button:** primary (ink fill, one per screen), secondary (1 px `--line`), ghost (text),
  destructive (text in `--alarm`, wash on hover). 32 px tall, 13/500. Shortcut shown in its tooltip.
- **Agent row:** avatar · name + one-line state sentence · compact trace · relative time.
  Frozen row: the sentence turns `--alarm` and an "Open incident" secondary button appears. Nothing else changes.
- **Reason dialog:** the title states the effect ("Unfreeze Meeting assistant? It will send the
  email it was holding."), 2–3 reason choices as a radio list, free text, confirm button named by the verb.
- **Toast** (Sonner): bottom right, one line, Undo when possible.
- **⌘K** (`cmdk`): jump to any agent, run, incident; run any action. Every action exists here.
- **Empty state:** the avatars in a row, one sentence, one action. "Nothing to look at. Your agents are behaving."
- **Mirage mark:** the word "Mirage" in `--mirage` with the shimmer, used as the label of simulated content.

## 12. Voice

- A calm colleague. Short sentences, active voice, numbers over adjectives.
- Incident headline: **who** + **what they tried** + **outcome**.
  "Meeting assistant tried to email 40 contacts to attacker@evil-corp.com. Blocked."
- Explain each security idea once, in a tooltip: "Mirage is a copy of production where nothing real
  happens. We let the agent continue there to see what it would have done."
- Relative times ("12 s ago"), exact time on hover.

## 13. Keyboard

`⌘K` command menu · `G F` Fleet · `G I` Incidents · `J/K` move · `Enter` open · `Esc` close ·
`U` unfreeze (selected run) · `⇧⌘.` Stop all (still asks for a reason).

## 14. References

Linear (sidebar, density, ⌘K, motion), Vercel (calm status, ink buttons, deployment flow),
n8n (workflow trace), Raycast (instant keyboard actions), Sonner (toasts).
Skills: `impeccable` (craft floor, anti-patterns, detector hook), `emil-design-eng` (motion).
