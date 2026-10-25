---
name: claudex-plan
description: "Gather requirements and write an execution plan with acceptance criteria and verification commands. Use for planning without launching agent review or implementation; claudex-loop composes this with claudex-review when a full workflow is requested."
---

# Claudex Plan

The current agent owns requirements and plan authoring. This stage does not depend on a particular reviewer, builder, or agent pair; Claude Code, Codex and DeepSeek Harness can host it. Use the shared [planning reference](../claudex-loop/references/planning.md); install the sibling `claudex-loop` skill for its references.

Preserve `plan` / `PLAN_FILE` and `log` / `LOG_FILE`. Defaults are `docs/exec-plans/active/<date>-<slug>.md` and its sibling `<date>-<slug>.review-log.md`. Resolve both once. Add a numeric suffix when a generated default already exists; use an explicit path as supplied. Preserve existing content and authorization when revising a plan.

Inspect the project, settle material requirements, and write the plan with acceptance criteria, risks, a verification contract and actionable progress checkboxes. Derive proof commands from the repository. Prove behavior on the real output of the program that produces its input, not only hand-written samples; when replacing code, run the old and new versions on the same inputs. Research is proportionate to the task; `research=deep` requires explicit opt-in, and a runner panel requires a supported actual host and its own dry-run approval.

Finish with the plan and log paths, key decisions and remaining uncertainties. An authored plan has no independent approval. If review was also requested, pass those exact paths, proof commands, authorization and any explicit role/model choices to [claudex-review](../claudex-review/SKILL.md) with `kind=plan`. If the full development loop was requested, return that handoff to [claudex-loop](../claudex-loop/SKILL.md). Otherwise stop after authoring.
