---
status: completed
created: 2026-10-31
completed: 2026-10-31
---

# Plan: Clean up the merged branches on the fork

## Goal

Remove the remote branches in `nyuhuyang/claudex-loop` whose work is already on `main`, leaving the repository with only the branches that still matter. Never rewrite history; every deleted branch must be fully contained in `main` first.

## Context

- `fork` → `nyuhuyang/claudex-loop`; `origin` → `chaseai-yt/claudex-loop` (upstream, not touched).
- Before this task the fork had 9 branches: `main`, the active `agent/LOC-84`, and seven feature/archive branches.
- This follows the previous task, which merged every branch into `main` (`ffd8c65`); deleting them removes refs, not commits: all commits stay reachable from `main`.

## Findings (2026-10-31, before deleting)

- `git fetch fork --prune` showed `fork/main` = `ffd8c65` = the local tip.
- All eight non-main branches had 0 commits not in `main` (`git rev-list --count fork/main..<branch>`), so no unique work could be lost.
- `gh pr list --state open` returned `[]`; the three historical PRs are merged.
- The seven old branches and their tips:
  - `archive/prose-design` — `6978dbb`
  - `claude-only-fallback` — `b50fff2`
  - `docs/ccfa-research-skills` — `d632073`
  - `feat/agy-provider` — `0b1d4be`
  - `feat/deepseek-reviewer` — `95641c9`
  - `feat/exec-plan-format` — `3308a1c`
  - `fix/fallback-provider-classification` — `c930a65`
- `agent/LOC-84` is the active task branch and was identical to `main`; it is kept until this task lands.

## Acceptance criteria

- [x] Pre-delete check: no branch has commits missing from `main` — all eight non-main branches showed 0
- [x] No open pull request depends on the branches — `gh pr list --state open` was empty
- [x] Seven merged branches deleted on `fork` — `git push fork --delete ...` printed `[deleted]` for each
- [x] Deleted tips recorded for restore — SHAs above; the local branches still hold them
- [x] Remaining remote branch refs are exactly `main` and `agent/LOC-84`, both at `ffd8c65` — `git ls-remote fork refs/heads/*`
- [x] `python3 scripts/validate.py` passes — "Skill metadata, references and manifests passed."
- [x] `python3 -m unittest discover -s tests -v` passes — 141 tests, OK (1 skipped)
- [x] Plan archived, committed, and pushed; remote `main` re-read at the final tip

## Steps

1. Fetch and verify every non-main branch is contained in `main`; confirm no open PRs.
2. Delete the seven fully merged branches on `fork`; re-read the remaining refs.
3. Run the repository checks, archive this plan with its review log, and push branch and `main`.

## Non-goals

- Deleting `main`, the active `agent/LOC-84` branch, tags, or PR refs.
- Deleting the user's local branches, which live in the shared Git directory and are outside this task.
- Deleting branches on `origin` (the upstream project).

## Restore

A deleted branch can be restored with `git push fork <sha>:refs/heads/<branch>`, using the recorded tip.
