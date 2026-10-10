---
name: align-first
description: >
  Check product fit and browse open source before committing to an approach.
  Use before starting any new component, library choice, integration, or
  architecture change in Mirage (gateway, Mirage adapters, detonation, UI,
  MCP server, Gmail/Calendar/HubSpot access). Not needed for small fixes inside
  an approach already agreed.
---

# Align first

Do not build until the approach is aligned. Time box: 10 minutes for steps 1 to 3.

## 1. Product alignment

Read `PRODUCT.md` and `CONTRACTS.md`. Answer in one line each:

- Which demo step does this serve? (See the demo script in `PRODUCT.md`.)
- Does it change the contract? If yes, both people must agree first (`CONTRACTS.md`, section 2).
- Is it Person A (engine) or Person B (experience) work?

If it serves no demo step, stop and say so.

## 2. Browse open source

Look for something that already does it. Search before you design.

- `gh search repos "<topic>" --sort stars --limit 10`
- `gh search code "<api or function name>" --limit 10`
- Web search for official SDKs, MCP servers and examples (Google APIs, HubSpot, Bedrock, FastAPI SSE, etc.).

Keep only candidates that are maintained, have a permissive license, and fit Python 3 / our stack.
Read the README and one real example of each candidate. A search snippet is not enough.

## 3. Propose

Write a short proposal to the user:

```
Goal: <one line, the demo step>
Options:
  A. <reuse X> — <link> — <cost in hours>, <risk>
  B. <build small> — <cost in hours>, <risk>
Recommendation: <A or B>, because <one line>
Contract impact: none | <fields/endpoints that change>
```

Prefer reuse (see the `ponytail` skill). Building is the fallback.

## 4. Get the OK

Wait for the user to confirm before you write code. Then use the `atomic-worktree` skill to start.
Put the proposal (goal, choice, links) in the PR description.
