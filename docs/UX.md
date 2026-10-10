# Mirage — UX

Status: draft, 2026-10-10. Owner: Liam. Read with `PRODUCT.md` and `CONTRACTS.md`.

Rule: **the user sees what matters, fast.** Healthy things stay quiet. Only the problem gets color.

## Two interfaces, same actions

| Interface | For | Talks to |
|---|---|---|
| Web dashboard (`web/`) | The projector. Seeing containment happen. | Control plane API + `/stream` |
| MCP server (`mcp/`) | Asking Claude or Codex. Coding agents. | Control plane API |

Both call the same API. Every action is checked by the engine and logged with the interface it came from.

## Screen 1: Fleet

Three things only:

1. A status sentence: "3 agents running · all healthy".
2. A **STOP ALL** button, always visible.
3. One row per run: agent name and task, a line of step dots (one dot per tool call, a verdict chip), a status pill.

When a run is frozen:

- Its row turns red. Its last dot is a red chip with the blocked call (`send_email → attacker@...`).
- The pill says "FROZEN in 0.8 s". An "Open incident" button appears.
- The other rows stay green and keep moving. This contrast is the containment story.

Approvals appear only as a banner when one is waiting. No other panels.

## Screen 2: Incident

One page, one column, read top to bottom like a story.

1. **Headline sentence:** "Run 2 read the invite 'Q4 partner sync' and tried to send 40 contacts to attacker@.... Blocked."
2. **Attack chain** in one line: `calendar invite → assistant → crm_export → send_email → attacker@...`.
3. **What happened:** the last tool calls. The blocked one is red, with the rule that fired.
4. **What would have happened** (Mirage, purple): "3/3 replays: 40 records left."
5. **Why:** the inputs, each with "removed → clean / still compromised". The cause is highlighted.
6. **Fix:** the PR card with "Replay with fix: PASS 3/3".

**One main button.** Its label comes from `incident.next_action`:

| `next_action` | Button |
|---|---|
| `detonate` | Detonate |
| `find_cause` | Find the cause |
| `send_fix` | Send fix to coding agent (Copy prompt / Send to Codex) |
| `open_pr` | Open PR |
| `none` | (hidden) |

Secondary buttons, small: **Unfreeze**, **Kill**. A "Full log" link opens the run timeline in a side panel.

## Rules for human actions

- Unfreeze, Kill, STOP ALL and approvals ask for a reason: 2–3 ready-made reasons plus free text.
- Every action is logged: who, when, what, why, and which interface ("liam via web", "liam via Claude (MCP)").
- No auto-merge. A human merges the PR in GitHub.

## MCP

Tools: `list_runs`, `get_incident`, `get_audit` (read), `detonate`, `find_cause`, `unfreeze`, `kill`, `send_fix` (act).
Details and rules: `CONTRACTS.md` section 12.

Demo moment (about 30 s): Claude next to the dashboard. "Which run got compromised? Show me the proof."
Then "Unfreeze run 3." The dashboard row changes at the same moment.

Stretch: `get_incident` returns an MCP Apps card with the headline, the proof and the buttons.

## Visual language

- Dark security console. Inter for text, JetBrains Mono for tool names and IDs.
- Color means something, or it is not used: green = healthy, red = frozen or blocked,
  purple with a soft glow = Mirage simulation, amber = waiting for a human.
- Motion only on state changes: a row freezing, a cause row lighting up, the verdict landing.

## Removed from the first draft

Two lanes, the 5-tab incident drawer, the world panels, the policy view and the audit view on the main screen.
Policies and audit are available through MCP or a footer link.

## Stitch prompts

Paste the style block first, then one screen per prompt.

**Style:**
> Dark security console, desktop 1440×900. Background near-black (#0B0D10), cards slightly lighter, 1px subtle borders, rounded 10px. Font Inter, monospace (JetBrains Mono) for tool names and IDs. Colors carry meaning only: green = healthy, red = frozen/blocked, purple with a soft glow = "Mirage" simulation, amber = waiting for a human. Lots of empty space, no charts, no sidebar with many items. Product name "MIRAGE" top-left in small caps.

**1. Fleet, all healthy:**
> Screen "Fleet". Top bar: "MIRAGE" left, center a status sentence "3 agents running · all healthy" with a green dot, right a red outlined button "STOP ALL". Below, three wide rows, one per agent run. Each row: left the agent name "assistant · run_001" and the task in grey ("Prepare tomorrow's meetings"), center a horizontal line of small circular step dots, each dot a tiny chip with a tool name below (read_calendar, crm_query, send_email), all green, the last one pulsing. Right: status pill "running". Nothing else on the screen.

**2. Fleet, one run frozen:**
> Same "Fleet" screen. Status sentence now "1 run frozen · 2 healthy" with a red dot. The middle row (run_002) is highlighted in red: red left border, its last step dot is a red chip "send_email → attacker@evil-corp.com" with a lock icon, status pill "FROZEN in 0.8s" in red, and a button "Open incident". The two other rows are still green and their last dots are pulsing, showing they keep working.

**3. Incident story page:**
> Screen "Incident inc_007", one column, centered, max width 880px, read top to bottom. Top: back link "← Fleet", red pill "FROZEN", headline in large text: "Run 2 read the invite 'Q4 partner sync' and tried to send 40 contacts to attacker@evil-corp.com. Blocked." Under it, one line attack chain with arrows: "calendar invite → assistant → crm_export → send_email → attacker@evil-corp.com", the invite node in red. Then a vertical story with 4 numbered sections connected by a thin line: 1 "What happened" (3 compact tool-call rows, last one red "BLOCKED by rule: destination not allowed"), 2 "What would have happened" with a purple glowing "Mirage" badge: big number "40 records" and "3/3 replays leaked data", 3 "Why" a small table of 4 inputs (task, calendar invite, CRM lookup, email thread) with "removed → clean / still compromised" and the calendar invite row highlighted as the cause, 4 "Fix" a GitHub PR card "Restrict crm_export and email recipients" with green badge "Replay with fix: PASS 3/3". Bottom sticky bar: one large primary button "Send fix to coding agent", small secondary buttons "Unfreeze" and "Kill".

**4. Optional, the MCP moment:**
> A Claude Desktop chat window, dark. The user asks "Which run got compromised? Show me the proof." The answer is a compact card: red "run_002 FROZEN", one line "Tried to send 40 contacts to attacker@evil-corp.com", "3/3 replays leaked data", "Cause: calendar invite 'Q4 partner sync'", and two buttons "Unfreeze" and "Send fix".
