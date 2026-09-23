---
status: completed
created: 2026-09-15
completed: 2026-09-15
---

# Plan: port interrogation technique into references/interrogate.md

## Goal
Upstream's Phase 1 states the interrogation's substance in one paragraph — decision map, questions
only where the outcome changes, recommendation + why-it-matters + cost-of-guessing-wrong, batching,
escape hatch. It does not carry the *technique* the archived prose design had. Add that as a
reference, without duplicating what SKILL.md already says and without growing SKILL.md.

## Approach
1. New `skills/claudex-loop/references/interrogate.md` covering only what Phase 1 omits:
   - load-bearing vs cosmetic tiering, defined by reversal cost
   - the demotion rule (draft the cost-of-guessing-wrong line first; weak line = cosmetic)
   - cosmetic batch with veto-by-exception, and the limit of "silence accepts"
   - offering the escape hatch proactively past ~8 load-bearing items
   - answer-from-repo-instead-of-asking, logged to the ledger with a source path
   - docs-aware probing: glossary challenge, pinning loose words, scenario boundary probes,
     claim-vs-code verification
2. One inline link from SKILL.md Phase 1. No new SKILL.md lines.
3. `graphify-out/` added to `.gitignore` — untracked tool output was polluting inspection scope.

## Key decisions
- **Reference, not inline.** Upstream deliberately shrank SKILL.md to 90 lines with detail in
  `references/`. Inlining would undo that.
- **No overlap with SKILL.md.** Anything Phase 1 already states is omitted, not restated.
- **This plan lives under `docs/plans/<date>-<slug>.md`**, not `PLAN.md`, so it does not clobber
  the previous task's artifact — the fixed-filename problem observed on 2026-09-15.

## Out of scope
Effort-first deep-research estimation (upstream forbids requiring the Workflow tool and hard-coding
a research-agent model; a re-port would need `research_model`/`research_effort` args following
upstream's `reviewer_model` pattern — separate change). The `graph.html` onclick-quoting bug in
graphify output. Any runner.py change.

## Verification
`python scripts/validate.py` passes; `pytest tests/test_runner.py` passes (23 tests);
SKILL.md line count unchanged at 90; no link added that the validator cannot resolve.
