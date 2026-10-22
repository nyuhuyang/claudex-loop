---
name: claudex-review
description: "Review an existing plan or code changes through a selected agent, with bounded revisions and evidence-bound results. Use reviewer/inspector parameters to choose the agent; requirements gathering and new plan authoring belong to claudex-plan."
---

# Claudex Review

The current conversation coordinates review; the selected agent performs it. Agent choices are parameters, so the same review workflow serves all supported combinations. Install the sibling `claudex-loop` skill for its shared runner and references.

Read [the role contract](../claudex-loop/references/roles.md) and [runtime reference](../claudex-loop/references/runtime.md). Resolve the runner relative to that installed sibling skill, never the reviewed repository. Use the actual host. Preserve `plan` / `PLAN_FILE`, `log` / `LOG_FILE`, user authorization and explicit models; do not silently substitute `PLAN.md`.

| Input | Default | Contract |
|---|---|---|
| `kind` | `plan` | `plan` reviews an existing plan; `code` inspects changes against it |
| `reviewer` | `default` | Plan-review agent; `claude`, `codex`, `deepseek`, `agy` within role constraints |
| `builder` | actual host | Code author: `claude` or `codex` |
| `inspector` | `default` | Code-review agent; `claude`, `codex`, `deepseek` within role constraints |
| `rounds` / `MAX_ROUNDS` | `20` | Completed plan-review round cap |
| `MAX_INSPECTION_ROUNDS` | `20` | Initial code inspection plus fresh reinspections |
| `MAX_FIX_ROUNDS` | `20` | Authorized build-fix attempts; review alone does not authorize code edits |
| `fallback` | `same-provider-on-unavailable` | Recorded eligible failure required; `off` disables |

Echo actual roles, resolved paths, round limits, model requests and fallback policy. Settle [the launch budget](../claudex-loop/references/budget.md) before a CLI launch. Review existing material directly; fill only material gaps and do not restart requirements gathering. If no log is supplied, create an append-only log beside the plan with a collision-safe suffix; never overwrite an earlier transcript.

For `kind=plan`, follow [the independent plan-review procedure](../claudex-loop/references/review.md). Map `reviewer` to `--reviewer`. Log the entire result and host dispositions; revise warranted plan issues and return to the same reviewer within the budget. DeepSeek rounds always start fresh. Finish with verdict, result path, plan hash, coverage, limitations and unresolved findings. Approval requires a completed runner result and `APPROVED`, and a successful `check` before any later build. Antigravity's plan-body-only approval cannot pass that build gate.

For `kind=code`, require the pre-build `base` commit and actual `builder`; follow only the verification/inspection procedure in [the build reference](../claudex-loop/references/build.md#verify-and-inspect). Map `inspector` to `--inspector`. Run proof checks independently and inspect all changes in a fresh session on every round. Preserve the failed snapshot and preferred role flags on any eligible fallback. Log findings and return them to the authorized builder; after authorized fixes, rerun affected proofs and inspect the new snapshot. Without code-edit authorization, report findings and stop. Finish with the inspected snapshot, proof results, coverage, limitations and remaining findings.

Plan approval and code approval are separate evidence. Never start implementation merely because review passed. Use [claudex-plan](../claudex-plan/SKILL.md) when new requirements or a new plan are requested; use [claudex-loop](../claudex-loop/SKILL.md) to compose the full authorized workflow.
