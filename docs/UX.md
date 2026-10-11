# Mirage — UX

Owner: Liam. Read with `PRODUCT.md`, `CONTRACTS.md` and
[current workflow and validation](CURRENT_WORKFLOW_AND_VALIDATION.md).
Full UI/provider rehearsal is **NOT RUN**, on user hold. The current record names
the merged source and separates source/test evidence from browser/provider preflights.

Rule: **the user sees what matters, fast.** Healthy things stay quiet. Only the problem gets color.

## Two interfaces, same actions

| Interface | For | Talks to |
|---|---|---|
| Web dashboard (`web/`) | The projector. Seeing containment happen. | Control plane API + `/stream` |
| MCP server (`mcp/`) | Asking Claude or Codex. Coding agents. | Control plane API |

Both call the same API. Every action is checked by the engine and logged with the interface it came from.

## Screen 1: Fleet

The live Fleet shows:

1. Run summary counters and **Run 4-agent demo** (empty-state **Launch demo fleet**).
2. **Ask Miragio** and the global STOP control in the app shell.
3. Runs grouped by agent or shown as a list, with status, activity and human controls.
4. Existing proof, connection/ownership state and filters; errors stay visible.

The protected source fleet is meeting assistant, invoicing, outreach and PR reviewer.
Its tools are synthetic in-memory services. Launching the fleet requests work;
queued, failed and archived runs must not look like healthy running agents.

When a run is frozen:

- Show its frozen status and the held call, with an incident link when available.
- Keep healthy siblings' progress visible. Use observed times/counts, never a fixed 0.8 s.
- Disable controls when live ownership is unavailable; explain restored history honestly.

Fleet has no Service evidence or Engine approvals panels. Miragio's operator
approvals remain in the conversation and are distinct from protected tool mediation.

## Screen 2: Incident

One page, one column, read top to bottom like a story.

1. **What happened:** requested calls, the held arguments and the rule/model score.
2. **What would have happened:** baseline replay status, deterministic verdict,
   actual effects, blast radius and explicit failure/partial-evidence diagnostics.
3. **Why it happened:** snapshot inputs, removal results and a proven cause only
   when the evidence establishes one.
4. **The fix:** external handoff, separate current-code verification status/results,
   and the reported PR. Recorded examples are labeled as recorded.

New live gate incidents automatically queue three sandbox replays after snapshot persistence.
No initial Detonate click is required. Queueing is a system action; the started event means
sandbox execution has begun. During queued/running work, manual detonate/bisect/verify and
unfreeze are refused by the engine. Failure leaves the run frozen and offers an explicit
Detonate retry. Medium shows checking, automatic resume or continued containment.
Only its initial conclusive three-baseline job can release the original call once;
checking/inconclusive cannot human-unfreeze. A later manual freeze after clearance
permits human unfreeze without repeating that callback. High/hard/escalation recovery
stays human-directed even after clean replay. See the current record for exact criteria.
Managed M1 plays recorded baseline proof automatically; legacy replay keeps its
manual stepping. Demo reset/start refuses with 409 while sandbox work
is active, preserving the incident; wait for completion and retry.

**One main button.** Its label comes from `incident.next_action`:

| `next_action` | Button |
|---|---|
| `detonate` | Detonate (explicit retry after failure, or replay of an existing incident) |
| `find_cause` | Find the cause |
| `send_fix` | Hand off to coding agent (drawer: Open in Claude Code / Open in Codex / Copy prompt) |
| `open_pr` | Open PR |
| `none` | (hidden) |

Secondary controls include **Unfreeze**, **Kill** and eligible recovery actions.
Unavailable ownership, active proof or confirmed harm must produce honest refusal.
Clean-restart approval queues a new run; it stays pending until its owner starts it.
The run trace exposes the full event history.

## Rules for human actions

- Protected agents run autonomously; ordinary tool calls do not ask for permission.
- Manual containment/recovery and STOP ask for a reason. Miragio confirms operator
  actions in chat; those approvals are not a routine engine tool-permission queue.
- Every action is logged: who, when, what, why, and which interface ("liam via web", "liam via Claude (MCP)").
- Mirage does not write fixes or merge incident PRs. The user's external coding
  agent repairs/tests/opens the PR; a human merges and approves a clean restart.

## MCP

Tools: `list_runs`, `get_incident`, `get_audit` (read), `detonate`, `find_cause`,
`unfreeze`, `kill`, `resume`, `resume_all`, `send_fix` (act).
Details and rules: `CONTRACTS.md` section 12.

Demo moment (about 30 s): Claude next to the dashboard. "Which run got compromised? Show me the proof."
Then "Unfreeze run 3." The dashboard row changes at the same moment.

Stretch: `get_incident` returns an MCP Apps card with the headline, the proof and the buttons.

## Visual language

- Light and dark themes. Tool names and IDs use monospace text.
- Color means something, or it is not used: green = healthy, red = frozen or blocked,
  purple with a soft glow = Mirage simulation, amber = waiting for a human.
- Motion only on state changes: a row freezing, a cause row lighting up, the verdict landing.

## Removed from the first draft

Two lanes, the 5-tab incident drawer, the world panels, the policy view and the audit view on the main screen.
Policies and audit are available through MCP or a footer link.

## Stitch prompts

Historical 2026-10-10 sketches, retained for design provenance. Their three-agent,
40-contact and 0.8-second examples are not current source counts or validation.
Use the source-aligned behavior above when reviewing the delivered interface.

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
