# Mirage — Design system

Status: draft, 2026-10-10. Owner: Liam. `docs/UX.md` says **what** each screen shows.
This file says **how it looks, moves and feels**. If they disagree on look and feel, this file wins.

## 1. North star

**Security that feels like Linear, not like a SOC.**
Vercel made hosting feel calm. Linear made project tracking feel fast. Mirage does the same for
agent security, for a 10-person company with no security team.

The person using Mirage should:
- know in **one second** whether everything is fine;
- understand an incident **without security vocabulary**;
- take the right action in **one click**, and feel safe doing it.

Simple is not plain. The screen is quiet, the details are precise: spacing, type, motion,
and the small moments (a run freezing, a cause lighting up) are where the quality shows.

## 2. Principles

1. **Calm by default, loud only when it matters.** Healthy = grey and quiet. Color appears only for
   a state that needs attention. If everything is colored, nothing is.
2. **One thing per screen, one main button per screen.** The engine's `next_action` picks the button.
3. **Show the flow, not the log.** What the agent did is a workflow you can see (n8n style),
   not a wall of JSON. Raw data is one click away, never in the way.
4. **Plain words.** "Frozen", "Would have sent 40 contacts", "Caused by: calendar invite".
   Never "IOC", "TTP", "exfiltration vector". Framework IDs (OWASP ASI01, MITRE) are small grey tags.
5. **Every action is reversible or confirmed.** Unfreeze, Kill, STOP ALL ask for a reason
   (2–3 ready-made reasons + free text). The UI says what will happen before it happens.
6. **Fast is a feature.** Optimistic UI on human actions, no spinners under 300 ms, keyboard first.
7. **Friendly agents.** Each agent has a small, cute, custom icon. Agents are coworkers you
   protect, not threats you hunt.

## 3. Layout

```
┌────────────┬──────────────────────────────────────────────────────┐
│ ◐ Mirage   │  Fleet                      3 running · all healthy ●│
│            │──────────────────────────────────────────────────────│
│ ▸ Fleet    │                                                      │
│   Incidents│   [agent rows / trace / incident story]              │
│   Approvals│                                                      │
│   Agents   │                                                      │
│            │                                                      │
│  AGENTS    │                                                      │
│  🐙 assist │                                                      │
│  🦉 support│                                                      │
│  🐝 invoice│                                                      │
│            │                                                      │
│ ⌘K Search  │                                                      │
│ ■ STOP ALL │                                                      │
└────────────┴──────────────────────────────────────────────────────┘
```

- **Sidebar, 240 px, always visible** (collapses to 56 px icons under 1100 px).
  Top: logo. Then 4 nav items with 16 px icons. Then the list of agents with their avatars and
  a 6 px status dot. Bottom: ⌘K search and **STOP ALL** (always reachable, red outline, never hidden).
- Nav items show a count badge only when non-zero (`Incidents 1`, `Approvals 2`). Zero = no badge.
- **Header, 48 px:** page title left, status sentence right. No other chrome.
- **Content:** max width 1080 px for lists, 880 px for the incident story. Generous empty space.
- **Side sheet** (right, 480 px) for details: a tool call, an input, the full log. Never a new page
  for a detail. `Esc` closes.
- Desktop first (1440×900, the projector). Must not break at 1280.

## 4. Color

Monochrome base, one brand accent, semantic colors only for state. Dark theme first (projector,
"console" feel); light theme from the same tokens.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0A0A0B` | `#FFFFFF` | Page |
| `--bg-subtle` | `#111113` | `#F7F7F8` | Sidebar, cards |
| `--bg-hover` | `#18181B` | `#F0F0F2` | Hover, selected row |
| `--border` | `#232326` | `#E6E6E9` | 1 px borders, dividers |
| `--text` | `#EDEDEF` | `#111113` | Primary text |
| `--text-muted` | `#8A8A93` | `#6B6B74` | Secondary text, labels |
| `--text-faint` | `#5A5A63` | `#9A9AA3` | Timestamps, IDs |
| `--accent` | `#7C7CFF` | `#5E5CE6` | Focus ring, links, primary button (indigo, Linear-like) |
| `--ok` | `#3DD68C` | `#18A058` | Healthy dot only (never a big surface) |
| `--danger` | `#FF5C5C` | `#E5484D` | Frozen, blocked, STOP ALL |
| `--warn` | `#F5A524` | `#D97706` | Waiting for a human |
| `--mirage` | `#B07CFF` | `#8B5CF6` | Simulation: anything that happened in Mirage, not in production |

Rules:
- Semantic colors appear as **a dot, a 2 px left border, a pill, or text**. Never as a filled card.
- Tints for pills: the color at 12 % opacity as background, full color as text.
- `--mirage` always comes with the same treatment: dashed borders and a soft glow
  (`box-shadow: 0 0 24px -8px var(--mirage)`). It means "this is a simulation, nothing real happened".
- Text contrast ≥ 4.5:1 for body, ≥ 3:1 for large text and icons.

## 5. Type

- **Inter** (variable) for UI, **JetBrains Mono** for tool names, IDs, arguments.
  Turn on `font-feature-settings: "cv11", "ss01"` and tabular numbers (`tnum`) for counts and times.
- Scale (px / line-height / weight):

| Role | Size | Weight | Example |
|---|---|---|---|
| Incident headline | 24 / 32 | 600, tracking −0.02em | "Run 2 tried to send 40 contacts to attacker@…" |
| Page title | 15 / 20 | 600 | "Fleet" |
| Body | 14 / 20 | 400 | Row text, descriptions |
| Label | 13 / 18 | 500 | Buttons, nav |
| Meta | 12 / 16 | 400, muted | Timestamps, IDs, framework tags |
| Mono | 12.5 / 18 | 400 | `send_email`, `run_002` |

- Sentence case everywhere. No ALL CAPS except the tiny sidebar section label (`AGENTS`, 11 px, +0.04em).

## 6. Space, shape, depth

- 4 px grid. Common steps: 4, 8, 12, 16, 24, 32, 48.
- Radius: 6 px (buttons, pills, inputs), 10 px (cards, nodes, sheets), full (dots, avatars).
- Borders do the work, not shadows. 1 px `--border` everywhere.
- Shadows only on floating layers (menus, ⌘K, sheet): `0 8px 32px rgb(0 0 0 / 0.4)` dark,
  `0 8px 24px rgb(0 0 0 / 0.08)` light.
- Rows: 48 px tall, 16 px horizontal padding, hover = `--bg-hover`, no border between rows
  inside a card (Linear style), a divider only between groups.

## 7. Icons and agent avatars

- **UI icons:** `lucide-react`, 16 px, stroke 1.5, `currentColor`. One icon per meaning, used
  the same way everywhere (Snowflake = frozen, Shield = gate, FlaskConical = Mirage, GitPullRequest = fix).
- **Agent avatars:** custom inline SVGs in `web/src/agents/avatars.tsx`, one per demo agent.
  - 20 px in lists, 32 px in headers, 48 px on the agent page.
  - Style: rounded square (radius 6) with a soft pastel fill, a simple friendly creature or object
    in 1.5 px stroke on top. Two colors max. Cute, not childish.
  - Proposed set: assistant = owl, support = octopus (many arms, many tickets), invoicing = bee,
    outreach = paper plane, PR reviewer = fox.
  - State shows **on** the avatar: a 6 px dot bottom right (grey idle, green running, red frozen,
    amber waiting). Frozen: the avatar gets a 1 px `--danger` ring and a tiny snowflake.
  - Unknown agents fall back to a generated geometric avatar from the agent name (deterministic hash
    → color + shape), so every new agent still looks intentional.

## 8. The trace: a workflow, not a log

The core visual of Mirage. Every run is drawn as a left-to-right flow, like an n8n workflow.

```
 [📅 Calendar invite] ──▶ [🦉 assistant] ──▶ [crm_export] ──▶ [send_email → attacker@…] ✕
      input (red)            model             tool ok          BLOCKED by gate
```

- **Nodes:** 10 px radius cards, 200 × 56 px. Icon + name (mono) + one line of meta
  ("40 rows", "0.3 s"). Kinds: input (calendar, email, CRM record, attachment), model step, tool call.
- **Edges:** 1.5 px, `--border`. The active edge shows a small dot travelling along it while the
  run is live (CSS `offset-path`, linear, 1.2 s loop). Stops when the run stops.
- **States:** done = neutral; running = subtle pulse on the border; blocked = `--danger` border +
  ✕ badge + the rule that fired as a pill under the node; malicious input = `--danger` left border.
- **Mirage overlay:** the detonation draws the path that *would have happened* after the blocked
  node, in `--mirage`, dashed, with the glow. Production stops at the red ✕; Mirage continues past it.
  This one image is the pitch: "here is what we stopped".
- **Bisection:** input nodes get a small result chip: "removed → clean" (grey) or
  "removed → still compromised". The cause input lights up (one-time 400 ms glow) and keeps a label
  "Cause".
- Click a node → side sheet with arguments, result, timing, policy hits. Raw JSON is a collapsed
  section at the bottom of the sheet.
- **Where it appears:** a compact version (nodes as 8 px dots + label, no pan/zoom) in each Fleet row;
  the full version on the run and incident pages.
- **Library:** `@xyflow/react` (React Flow) for the full view: pan, zoom, minimap off, read-only,
  nodes are our own React components. Layout is computed by us (a run is mostly a line:
  `x = index * 240`), no layout engine. The compact Fleet version is plain flexbox, no React Flow.

## 9. Motion

Crisp and fast, like Linear. Motion explains state changes; it never decorates repeated actions.

Tokens:
```css
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);     /* enter, most UI */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1); /* things moving on screen */
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);  /* side sheet */
--dur-press: 120ms;  --dur-fast: 160ms;  --dur-base: 220ms;  --dur-sheet: 320ms;
```

| Moment | Animation |
|---|---|
| Button press | `scale(0.97)` on `:active`, 120 ms |
| Hover (rows, nav) | background color only, 120 ms `ease`; gated by `@media (hover: hover)` |
| Menu / popover / tooltip | opacity + `scale(0.96 → 1)` from the trigger, 160 ms ease-out |
| Side sheet | `translateX(100%) → 0`, 320 ms ease-drawer; exit 200 ms |
| New tool call in a trace | node fades in + `translateX(-8px → 0)`, 220 ms; edge draws in |
| **Freeze (hero moment)** | the blocked node shakes once (2 × 4 px, 240 ms), its border turns red, the row's left border grows 0 → 2 px, the avatar gets its snowflake, the status sentence counts to "1 frozen". Other rows keep moving. |
| Mirage replays | three ghost runs stack in with 60 ms stagger, purple glow fades in |
| Verdict lands | the number ("40 records") counts up in 600 ms, once |
| Cause found | 400 ms glow on the cause node, then steady |

Never animate: ⌘K open/close, keyboard navigation, page switches from the sidebar, list sorting.
Only `transform` and `opacity` (plus color). Exits faster than enters.
`prefers-reduced-motion`: keep fades and color, drop all movement, shake and travelling dots.
Use CSS transitions for UI state; Motion (`motion/react`) only for the trace enter/stagger and the count-up.

## 10. Components (shadcn/ui, restyled with the tokens)

- **Button:** primary (accent fill, 1 per screen), secondary (border), ghost (text), danger (red
  outline; fills only on hover). Height 32 px, label 13/500. Shortcut hint on hover tooltip.
- **Status pill:** dot + word ("Running", "Frozen 0.8 s", "Waiting"). Tinted background.
- **Agent row:** avatar · name + task (muted) · compact trace · pill · time. Frozen = 2 px red left border + "Open incident" ghost button.
- **Reason dialog:** title says the effect ("Unfreeze run_003? It will resume sending emails."),
  2–3 reason chips, free-text field, confirm button with the action verb. Enter confirms.
- **Toast** (Sonner via shadcn): bottom right, one line, an Undo when possible.
- **⌘K command menu** (`cmdk` via shadcn): jump to agent/run/incident, run actions
  (Unfreeze, Kill, Detonate, STOP ALL). Every action in the UI is also in ⌘K.
- **Empty states:** one line + one action. "No incidents. Your agents are behaving." with the
  agents' avatars in a row.
- **Mirage badge:** `FlaskConical` icon + "Mirage", purple, dashed border, glow. Only on simulated data.

## 11. Voice

- Talk like a calm colleague. Short sentences, active voice, numbers instead of adjectives.
- Headline formula: **who** + **what they tried** + **outcome**.
  "assistant tried to email 40 contacts to attacker@evil-corp.com. Blocked."
- Explain each security idea once, inline, in a tooltip: "Mirage = a copy of production where
  nothing real happens. We let the agent continue there to see what it would have done."
- Times relative ("12 s ago"), exact on hover.

## 12. Keyboard

`⌘K` command menu · `G F` Fleet · `G I` Incidents · `J/K` move in lists · `Enter` open ·
`Esc` close sheet · `U` unfreeze · `⇧⌘.` STOP ALL (still asks for a reason).

## 13. Don't

- No charts on the main screens, no gauges, no "threat level" meters, no world maps.
- No red or green big surfaces. No gradients except the Mirage glow.
- No more than one primary button per screen.
- No raw JSON in the default view.
- No modal for something a side sheet can show.
- No spinner when a skeleton or optimistic update works.

## 14. References

- Linear (sidebar, density, ⌘K, motion), Vercel dashboard (calm status, deployment timeline,
  monochrome), n8n (workflow trace), Raycast (instant keyboard actions), Sonner (toasts).
- Motion rules from the `emil-design-eng` skill (Emil Kowalski). Audit with `web-design-guidelines`
  and `review-animations` before the demo.

## 15. Open questions

1. Dark first (projector, console feel) or light first (friendlier for small companies, Linear and
   Vercel both default to the OS)? Proposal: dark for the demo, light works from the same tokens.
2. Agent avatars: the animal set above, or simple objects (calendar, ticket, invoice…)?
3. React Flow (`@xyflow/react`) for the full trace: OK as a new dependency?
4. `docs/UX.md` says "no sidebar with many items". This file adds a sidebar with 4 items + the agent list.
   OK to update UX.md to match?
