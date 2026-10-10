---
name: atomic-worktree
description: >
  Start, commit, push and ship one small feature in its own git worktree as one
  atomic PR. Use whenever you start a new feature or fix in Mirage, and when you
  are ready to commit, push, or open a PR.
---

# Atomic worktree

One feature = one worktree = one branch = one PR. Keep it small: a few hours of work at most.

## Start

From the main checkout, with `main` up to date:

```bash
git -C ~/Business/hacks/Mirage pull --ff-only
git -C ~/Business/hacks/Mirage worktree add ../Mirage-<feature> -b <prefix>/<feature> main
cd ../Mirage-<feature>
cp ../Mirage/.env .env   # .env is gitignored, copy it in
```

Branch prefixes:

| Prefix | Use |
|---|---|
| `engine/` | Person A: agents, gateway, Mirage, detonation, API |
| `ui/` | Person B: UI, mock server, demo assets |
| `contract/` | Changes to `contracts/` or `CONTRACTS.md` (both people agree) |
| `fix/` | Bug fix |

Feature names are short kebab-case: `engine/gate-hard-rules`, `ui/production-lane`.

## Commit often

- Commit each time something works, even if small. Do not wait for the feature to be done.
- One idea per commit. Message: imperative, short (`Add canary rule to gate`).
- Never commit `.env`, keys, tokens or real personal data.
- Run the code (or its test) before each commit.

## Push often

- Push after every few commits, and at least every 30 minutes.
- First push: `git push -u origin <prefix>/<feature>`.

## Open the PR

When the feature works end to end:

```bash
git fetch origin && git rebase origin/main   # resolve conflicts, rerun
git push --force-with-lease
gh pr create --fill --base main
```

PR description:

- What it does, in 1 to 3 lines.
- Which demo step it serves (from `PRODUCT.md`).
- The `align-first` proposal, if there was one.
- How you tested it (command and result).

Rules:

- One feature per PR. If the PR does two things, split it.
- A `contract/` PR needs the other person to approve.
- **Never merge, only rebase.** Update the branch with `git rebase origin/main`, never
  `git merge`. Land the PR with **Rebase and merge** (`gh pr merge <n> --rebase`): no squash,
  no merge commits. Each commit lands on `main` as is, so keep commits clean.
- Keep `main` working at all times.

## Clean up

After the PR lands:

```bash
git -C ~/Business/hacks/Mirage worktree remove ../Mirage-<feature>
git -C ~/Business/hacks/Mirage branch -D <prefix>/<feature>   # -D: rebase-merge gives new SHAs
git -C ~/Business/hacks/Mirage pull --ff-only
```
