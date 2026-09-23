---
status: completed
created: 2026-09-15
completed: 2026-09-15
---

# Plan: pre-flight research estimate + dated plan/log defaults

## Goal
Before a multi-agent research fan-out runs, show the user its *shape* — how many launches, at what
configuration — and bind execution to what they approved. Upstream's Phase 0 gates research depth
(`none` / `web` / `deep`) but says nothing about how much work `deep` will actually do.

## Constraints this must respect
- SKILL.md line 45: *"Do not require a proprietary Workflow tool or hard-code a research-agent
  model."* The estimate must be provider-agnostic and name no model.
- SKILL.md line 21: *"Report requested and observed model information separately; report an
  unresolved CLI default honestly."*
- SKILL.md stays terse; detail lives in `references/`.

## Approach
1. New `skills/claudex-loop/references/research.md`:
   - **Estimate before launch**: launches per stage x rough output per launch, printed with the
     resolved configuration, at the opt-in the tier already requires. No new approval step.
   - **Bands are uncalibrated guesses**, labelled as such. Output-only, with input excluded and
     said so.
   - **A cost figure only when the model is actually resolved.** When the CLI default is
     unresolved, print launches and tokens and state why no cost is given — per line 21.
   - **Sign-off binds the shape**: approval covers those counts; edits reprint; exceeding them
     stops and re-presents.
   - **Effort before architecture**: published guidance is to sweep effort on the current model
     before adding a cheaper second model. Cited as a reason to try effort first, not as a
     prediction about any workload.
   - **Coverage discipline**: >= 2 distinct agents on distinct angles per question, a bounded
     retry allowance printed with the estimate, no loop-until-dry.
2. One inline link from SKILL.md Phase 0. No new SKILL.md lines.
3. **Dated plan/log defaults.** Change the documented defaults of `PLAN_FILE` and `LOG_FILE` from
   the fixed `PLAN.md` / `PLAN-REVIEW-LOG.md` to `docs/plans/<date>-<slug>.md` and
   `docs/plans/<date>-<slug>-review-log.md`. Observed 2026-09-15: a second loop run overwrote the
   first run's plan and its full review transcript, recoverable only from git history.
   `runner.py`'s `--plan` argparse fallback is NOT changed — it cannot know the date, the host
   always passes `--plan` explicitly, and no test asserts on it.

## Key decisions
- **No model named anywhere.** The archived design's Sonnet/Opus tiering is dropped entirely, not
  relocated — upstream forbids hard-coding a research-agent model and the user has dropped the
  `research_model` arg proposal.
- **No Workflow-tool API.** No `agent()` opts, no `budget` object, no JS. The estimate is a
  reporting and sign-off discipline that works with any fan-out mechanism.
- **No cost prediction for a configuration that will not run**, and none at all when the model is
  unresolved. Four review rounds established that every such prediction in the archived design was
  unfounded.

## Out of scope
`research_model` / `research_effort` arguments (dropped by the user). Any runner.py change. Any
change to the `research` tunable's values. The graphify `graph.html` quoting bug.

## Verification
`scripts/validate.py` passes; `pytest tests/test_runner.py` passes (23 tests, unchanged — the
runner is not touched); SKILL.md still 90 lines; reference contains no model name, no
`agent(`/`budget.`, and none of bound/ceiling/maximum.
