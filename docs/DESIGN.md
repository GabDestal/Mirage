# Mirage — Design system

Status: v3, 2026-10-10. Owner: Liam. Mode: Operate.

The visual reference is Opereit: the supplied login and dashboard screenshots, the original
Opereit components, and the Mirage login we have just built. This file defines the approved
visual direction. `PRODUCT.md` and `CONTRACTS.md` define product behavior and data;
`docs/UX.md` defines the incident story. On look and feel, this file wins over earlier drafts.
Builders: load `ponytail`, `impeccable` and `emil-design-eng`.

Implementation status: the login and Ask Mirage chat home follow this reference. The existing
Fleet, sidebar and shared controls still use v2 styling; their specifications guide the next UI
iterations. Section 8 records the implemented chat surface and its current read-only scope.

## 1. North star

**Mirage should feel like the same product before and after sign-in.**

A light, calm workspace with the detail and tactility of Opereit: Inter text, white content,
a pale sidebar, compact navigation, soft outlines and dark gradient buttons. The login adds
the blue cursor brush and a translucent panel. Inside the app, space and hierarchy do the work.

The operator should understand the fleet at a glance, see the incident as a story, and find
one clear next action. Keep the evidence and human controls central to that experience.

## 2. Principles

- **Reuse the reference.** Take layout, spacing and control treatment from the actual Opereit
  components before inventing a new pattern. Adapt their content to Mirage.
- **Quiet when healthy.** Healthy runs use neutral text and their agent avatars. A freeze
  changes the avatar, state sentence and blocked call; other runs keep moving.
- **One main action.** The incident's `next_action` determines the primary button.
- **Plain words and visible evidence.** Show the blocked call, simulated effects, cause and fix.
  Put raw arguments, logs and framework IDs in the detail sheet.
- **Safe human actions.** Unfreeze, Kill, Stop all and approvals explain the effect and ask
  for a reason. Preserve every engine check and the human audit trail.
- **Comfortable density.** Compact navigation and controls, generous space around the main task.
  Rows and text lists carry routine information; use a panel when it groups a real interaction.
- **Immediate response.** Keyboard actions, navigation and submission feel instant.
  Motion explains a change or gives press feedback.

## 3. Color and surfaces

Light is the reference. Use neutral greys from Opereit, blue for interaction, and Mirage aqua
for the existing logo and simulated content. Red identifies blocked actions and compromise.
Dark mode needs a matching, separately checked translation of this reference.

| Token | Light target | Use |
|---|---|---|
| `--paper` | `#FFFFFF` | Main workspace, fields, menus |
| `--paper-2` | `#FAFAFA` | Sidebar, quiet hover, composer context strip |
| `--paper-3` | `#E5E5E5` | Selected navigation and pressed surfaces |
| `--line` | `#E5E5E5` | Subtle outlines and separators |
| `--ink` | `#171717` | Main text |
| `--ink-2` | `#525252` | Navigation and secondary text |
| `--ink-3` | `#737373` | Meta text and readable placeholders |
| `--accent` | `#0C55C4` | Links, interactive emphasis, user initials |
| `--focus` | `oklch(0.62 0.186 260.066)` | Focus borders and rings |
| `--accent-wash` | `#E4EEFF` | Selection and subtle interaction backgrounds |
| `--mirage` | `#0E8C86` | Logo, simulated edges and large marks |
| `--mirage-text` | `#0F766E` | Small text identifying simulated content |
| `--mirage-wash` | `#E3F4F2` | Simulated result areas |
| `--alarm` | `#B91C1C` | Frozen/blocked text, errors, destructive actions |
| `--alarm-wash` | `#FBE9E6` | Blocked node background |

The primary action uses a dark neutral gradient, matching the login. Links and focus use blue.
Color is accompanied by a word, icon or shape that explains it.

Body text, labels and placeholders meet 4.5:1 contrast; large text and meaningful icons meet
3:1. Fainter greys are reserved for disabled controls and decoration. Keep readable contrast
in the neutral context strips and tinted simulation areas.

Use the dotted background and translucent surface for login. Fleet, incidents and chat use
plain content backgrounds. A subtle focus ring belongs to a control; a glow surrounding an
entire page or an alert adds no useful information.

## 4. Typography

- **Inter variable**, self-hosted, for app text. The login font already lives at
  `web/public/fonts/Inter/InterVariable.woff2` with its license.
- **JetBrains Mono** is the Opereit reference for code and IDs. Existing Geist Mono can remain
  during the migration; reuse the original font asset if exact matching is needed.
- Use a 16 px root with a 14 px body. Keep component measurements stable when moving from
  Mirage's current smaller root size. The login uses explicit pixel values for this reason.
- Body weight 450, navigation 450, controls 500, prominent incident headings 600.
  Tabular numerals for counts, timestamps and durations.

| Role | Size / line | Weight |
|---|---|---|
| Incident headline | 24 / 32 px | 600 |
| Login or chat welcome title | 20 / 28 px | 500 |
| Page title | 16 / 24 px | 500 |
| Body and navigation | 14 / 20 px | 450 |
| Control and suggestion row | 13 / 20 px | 500 / 450 |
| Meta text | 12 / 16 px | 450 |
| Account email | 11 / 16 px | 450 |
| Code and IDs | 12.5 / 18 px | 400 |

Use sentence case for headings and actions, and restrained tracking (−0.01em for welcome
headings, −0.02em for incident headlines). Compact navigation group captions may follow
Opereit's 10 px uppercase mono style; keep them confined to sidebar groups.

## 5. Space, shape and depth

- Work on a 4 px grid, with small adjustments taken from the reference components:
  6 px icon gaps, 10 px navigation inset, 14 px form gaps.
- Tight spacing within controls and related text; 24–48 px between independent sections.
- Radius: 8 px fields, buttons and navigation; 12 px panels, composers, nodes and sheets;
  16 px for a composer wrapper with its context strip. Circular avatars remain circular.
- Ordinary surfaces use a subtle 1 px outline, sometimes with a tiny downward shadow.
  The Opereit reference deliberately combines those two on fields and composers.
- Floating menus and sheets use a soft offset shadow. Keep their surface white and readable.
- The dark submit button has an inset highlight and a small bottom shadow. This is the
  reference's tactile detail; keep it consistent across primary actions.
- List rows are 48–52 px and use a quiet hover surface. Avoid dividers between every row.

## 6. App shell and sidebar

Use Opereit's workspace structure: a pale, fixed-width sidebar beside a white content area.
The sidebar's hierarchy and account footer remain visible while the content scrolls.

| Part | Target |
|---|---|
| Sidebar | 256 px wide, `--paper-2`, 1 px right separator |
| Brand row | 24 px Mirage mark, 14 px medium name, 14 px inset |
| Navigation | 30–32 px rows, 16 px icons, 10 px icon/text gap, 8 px radius |
| Active item | Soft grey filled row with darker text and icon |
| Groups | Compact caption, 20 px separation; collapsible only when useful |
| Nested items | Indented text, thin neutral guide line, compact spacing |
| Account footer | Top separator; 28 px initials avatar, name and email, menu affordance |
| Header | 48–52 px, page icon/title or breadcrumb left, fleet sentence right |
| Content padding | 24 px normally, up to 64 px on roomy desktop pages |
| Detail sheet | Right side, 480 px wide, capped to viewport width |

Mirage navigation starts with Fleet and Incidents, then the agents. Search and **Stop all**
stay reachable near the bottom, above the account row. The account row uses the demo identity
until authentication is built. Add a chat item when there is a usable chat surface behind it.

Small outlined navigation counts may indicate a real actionable queue, as in Opereit's Claims
row. Use an actual count and a destination that explains it. Run health remains a state sentence
and avatar, rather than a collection of count or status badges.

The header keeps the fleet sentence: “All 3 agents are working.” or “Meeting assistant is
frozen. 2 others keep working.” On an incident page, the title or breadcrumb identifies the
incident. Healthy status stays neutral; frozen status uses `--alarm`.

Lists use a maximum width of 1080 px; incident stories use 880 px. Chat content uses 672 px.
Design for the 1440 × 900 projector and check 1280 px. Below 1100 px the sidebar can collapse
to a 56 px icon rail. At phone widths, use an accessible navigation drawer and keep Stop all
reachable from the visible app header. Sheets fit the viewport and traces can scroll horizontally.

## 7. Login

Match the actual Opereit auth source and the existing Mirage implementation:

- Background `#F4F4F4`, neutral dots `#D4D4D4`, 5 px grid spacing.
- Original blue cursor brush, with spring motion and a slowly drying trail.
  Active dot color mixes the source blue-400 and blue-500 values; glow uses `#DBE8FF`.
- Centred panel, maximum width 384 px, minimum height 404 px, 12 px radius.
  Padding: 56 px top, 32 px sides, 36 px bottom.
- Translucent white gradient, original subtle shadows, 22 px backdrop blur and 1.3 saturation.
- White 52 px logo holder with an 11 px radius and subtle outline; 28 px Mirage mark inside.
- Inter heading, 20 / 28 px, medium, with a 20 px gap below the logo.
- 36 px white fields with 8 px radius, quiet outline, blue focus border and soft focus ring.
- Password visibility control, right-aligned recovery link, and 36 px full-width dark gradient button.
- Match at the same browser zoom. Screenshot pixels are not the source's CSS dimensions.

Reuse `web/src/components/login-background/` for the effect. Preserve its WebGL cleanup,
resize handling, reduced-motion support and static CSS dot fallback.

Current fake login: `liamszefner@gmail.com` / `demo123`, prefilled. Incorrect credentials
show an inline error. Values are neither sent nor stored; refreshing returns to login.
The recovery control displays the demo credentials. Real authentication is separate product work.

## 8. Ask Mirage chat home

`/` opens Ask Mirage; `/fleet` keeps the existing Fleet as a secondary view. The home uses the
supplied Opereit dashboard screenshot and `agent-home.tsx` composition: a centred, left-aligned
column (672 px maximum, 24 px horizontal clearance) on a white workspace.

1. An 80 px Mirage mark above “What needs your attention today?” (20 / 28 px, medium).
2. A white multiline composer with a 12 px radius, subtle outline and small bottom shadow.
3. A neutral context strip with current fleet state, frozen-run count and a relevant text action.
4. Three plain suggestion rows with small icons, 32 px below the composer group. Clicking a
   suggestion fills the draft and focuses the textarea.

The composer uses a real textarea. Clicking its empty interior focuses it. A compact arrow-up
send button sits at the lower right and is disabled when empty or submitting. Enter sends,
Shift+Enter adds a line, and IME composition is respected. Focus uses a blue border and restrained
ring. A failed request shows an inline error and preserves the draft; context-loading errors
provide a retry action.

Sending fetches fresh run and incident data and displays a read-only summary with links to the
Fleet, run and incident views. Each answer carries a “Fleet snapshot at” timestamp. This is a
summary interface, with no natural-language model or chat backend yet; sending has no control
effects. Investigation and human actions remain in the existing incident and control views.

The conversation keeps a stable reading column, quiet user messages and a composer at the bottom.
New answers scroll into view only when the reader is already near the bottom; reading earlier
answers preserves scroll position. New chat clears the displayed conversation.

## 9. Fleet and incident presentation

Fleet remains one row per run: avatar, agent/task, one-line state sentence, compact trace,
relative time. A frozen run exposes **Open incident**, changes its sentence and stops its trace.
Keep the rest of the fleet readable and moving.

The incident is one story column:

- **What happened:** the input, agent and attempted call. Show the gateway rule and blocked outcome.
- **What would have happened:** a clearly labelled Mirage area with the actual replay result and effects.
- **Why:** each removed input and its result, with the proven cause highlighted.
- **Fix:** handoff, PR and verification evidence when those exist.

Use neutral surfaces and clear type hierarchy. A replay result can use `--mirage-wash` with
readable aqua text. The blocked node can use `--alarm-wash` and a thin red outline. Stronger
color belongs to these specific facts, rather than whole-page alert styling.

The primary action follows `incident.next_action`: Detonate → Find the cause → Send fix → Open PR.
Keep Unfreeze and Kill secondary, and respect the engine's allowed state transitions.
The full log opens in a side sheet. Verification shows the deterministic result; clean restart
requires human approval, and a human merges the PR.

## 10. Trace and agent avatars

A trace shows the production path stopping at a blocked call, then the simulated path continuing.
Nodes use white surfaces, 12 px radius, a subtle outline, an icon, the name and one meta line.
A useful starting size is 208 × 60 px, with 40 px between nodes. Edges use a thin neutral stroke.
The simulated continuation is dashed and aqua, labelled “Mirage”.

Clicking a node opens its arguments, results, timing and rule in the detail sheet. Bisection
adds “Removed → clean” or “Removed → still compromised” to the input. Raw JSON is collapsed.
Compact Fleet traces remain text and flexbox. Reuse existing React, CSS and SVG for a linear
trace; consider a graph library only when the actual interaction needs it.

Keep the existing SVG agent characters: owl, octopus, bee, paper plane, fox, and the hashed
fallback. Their shapes and colors provide identity within the neutral workspace.
Sizes: 20 px in navigation and rows, 32–64 px in headers and incident context, up to 80 px
on a chat welcome surface. A state word accompanies each meaningful avatar change.

| State | Presentation |
|---|---|
| Working | Eyes open, subtle occasional blink; “Working · read_calendar” |
| Done | Still avatar; “Done 2 min ago” |
| Waiting | Raised hand; “Waiting for your approval” |
| Frozen | Existing ice treatment; “Frozen after reading an invite” |
| Killed | Desaturated avatar; “Stopped by Liam” |
| In Mirage | Aqua treatment; “Replaying in Mirage · 2 of 3” |

## 11. Shared controls

- **Primary button:** dark neutral gradient, thin dark outline, inset highlight, 8 px radius,
  13 px medium label. 32 px normally, 36 px in forms. Preserve press feedback and clear disabled state.
- **Secondary button:** white, thin neutral outline and tiny downward shadow.
- **Ghost action:** neutral text, quiet grey hover. Links use interaction blue.
- **Destructive action:** readable red label; neutral or subtle red hover. The label names the effect.
- **Field:** white, 8 px radius, neutral outline, blue border/ring on focus.
  An error adds a readable red message associated with the field.
- **Reason dialog:** state what happens, present 2–3 reason choices plus free text, and name
  the confirmation by its verb. Preserve keyboard focus and escape behavior.
- **Menu/sheet:** white surface, restrained depth, compact rows. Avoid wrapping every subsection in a card.
- **Toast:** Sonner, bottom right, short sentence and an available recovery action.
- **Command menu:** existing `cmdk`, instant keyboard navigation and access to the same human actions.
- **Empty state:** one avatar/mark, a plain sentence, one useful action. Borrow the chat welcome's
  spacing when it helps the user start a task.

Use Mirage's installed React, Radix, Motion, Lucide, Sonner and `cmdk` before adding dependencies.
Opereit's Base UI components are styling and behavior references; adapt them to the installed primitives.

## 12. Motion and interaction

The login's blue cursor trail is the expressive moment. In the workspace, keep motion short
and tied to interaction or state. Preserve the original spring effect rather than rebuilding it.

| Moment | Treatment |
|---|---|
| Press | `scale(0.97)`, 100–120 ms; reduced motion can stay static |
| Hover | Color/background, 100–150 ms; mouse hover media query |
| Focus | Border and ring, up to 150 ms |
| Sidebar group | Height and opacity, 150 ms enter / 100 ms exit |
| Menu/tooltip | Small opacity/scale change, 160 ms; adjacent tooltips appear immediately |
| Detail sheet | Slide, up to 320 ms enter / 200 ms exit |
| New trace step | Short fade/translation, 220 ms |
| Freeze | Existing avatar ice transition, about 240 ms; blocked node and sentence change together |
| Replay progress | Update the actual progress text and simulated edges as results arrive |
| Cause found | Thin outline and label change, about 220 ms |

Navigation, keyboard selection and command-menu opening are immediate. Submitting a chat message
must not wait for decorative effects. Honor reduced motion, stop idle rendering when settled,
and release animation frames/listeners when a surface unmounts. Keep the app free of recurring
page glows, particle effects and mandatory number-counting animations.

## 13. Copy, accessibility and restraint

Use short, active sentences. An incident headline states who, what they tried and the outcome:
“Meeting assistant tried to email 40 contacts to an external address. Blocked.” Show the exact
destination in the evidence. Explain Mirage once: a copy of production where actions are simulated.
Relative times are useful; exact time remains available in an accessible detail or tooltip.

All controls need a name, visible keyboard focus and useful hover/disabled/error states. A compact
icon button still needs a usable hit target. Keep loading skeletons, actionable empty states and
errors with a recovery step. Status updates are announced politely; errors use an alert.

Avoid gradient text, metric-tile grids, repeated nested cards, colored stripes beside every row,
security jargon as headings, and ornamental graphs. Use mono for code, IDs and the compact
sidebar captions described above. Use the pinned login effect and surface treatment intentionally.

## 14. Keyboard

Keep `⌘K` command menu, `G F` Fleet, `G I` Incidents, `J/K` selection, Enter to open,
Esc to close, `U` to request unfreeze and `⇧⌘.` to request Stop all. Every action preserves
its reason and authority checks. Shortcuts stay inactive while typing in a field or textarea.

## 15. Source references

The reference checkout is `/Users/liamszefner/Opereit/obsydian/apps/dashboard/src/`.
Start with these source files when adapting the next surface:

| Pattern | Opereit source |
|---|---|
| Global type, neutral/brand tokens | `index.css` |
| Login layout and panel | `app/auth/components/auth-layout.tsx` |
| Original cursor effect | `app/auth/hooks/use-dot-grid-background.ts`, `dot-grid-motion.ts`, `dot-grid-renderer.ts` |
| Fields, password toggle, submit | `app/auth/components/auth-text-field.tsx`, `auth-password-toggle.tsx`, `auth-submit-button.tsx` |
| Workspace | `ui/layout/layout.tsx`, `ui/layout/page-layout.tsx` |
| Sidebar, nesting and active rows | `ui/layout/sidebar/sidebar.tsx`, `sidebar-section.tsx` |
| Account footer | `ui/layout/sidebar/user-menu.tsx` |
| Screenshot's composer, context and suggestions | `app/agent/components/agent-home.tsx` |
| Conversation presentation | `app/agent/components/chat-container.tsx`, `message-bubble.tsx` |
| Tactile buttons and fields | `ui/components/button-v2.tsx`, `input.tsx` |

Use the supplied screenshots to judge visual fidelity and these files to recover exact styling.
Reuse Mirage's domain, avatars and API contracts when adapting the reference. The screenshots'
logistics navigation, counts and copy are replaced by the relevant Mirage content.
