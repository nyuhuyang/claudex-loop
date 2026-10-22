---
name: claudex-loop
description: "Coordinate requirements, plan authoring, configurable agent review, and authorized implementation with final inspection. Use for claudex this plan, claudex-loop, or the legacy crucible trigger; not for trivial edits."
---

# Claudex Loop

Compose [claudex-plan](../claudex-plan/SKILL.md) for requirements and plan authoring with [claudex-review](../claudex-review/SKILL.md) for independent plan or code review. The current conversation coordinates the workflow. Select agents by role; do not create a skill for each host/reviewer pair.

## Resolve roles once

Read [the role and capability contract](references/roles.md). The actual host is the planner and coordinator. Use `host=claude` in Claude Code, `host=codex` in Codex and `host=deepseek` in a DeepSeek Harness (`dsh`) session. Default review is the other Claude/Codex provider for a Claude or Codex host, and Claude for a DeepSeek host; default build is the host; default inspection is the other provider relative to the builder. A DeepSeek host plans and may implement directly, but the runner cannot delegate a build to `dsh`. Explicit reviewer and inspector choices are independent, and DeepSeek cannot review the plan it authored. Preserve the host's selected model and map per-role settings only to that role's CLI.

Read [the runtime reference](references/runtime.md) before launching a CLI. Resolve the runner from this installed skill, never from the project being reviewed.

## Tunables

| Argument | Default | Meaning |
|---|---|---|
| `PLAN_FILE` / `plan` | `docs/exec-plans/active/<date>-<slug>.md` | Plan path used throughout, including the build handoff. Resolve the plan/log pair once per run. When the path is generated from this default and already exists, add a numeric suffix rather than overwriting; an explicitly supplied path is used as given, including an existing one for `mode=review` |
| `LOG_FILE` / `log` | `docs/exec-plans/active/<date>-<slug>.review-log.md` | Append-only transcript, kept beside its plan. Archive both to `docs/exec-plans/completed/` under the completion rule below |
| `rounds` / `MAX_ROUNDS` | `20` | Maximum completed plan-review rounds |
| `builder` | host | Provider implementing the plan. `claude` or `codex` delegates through the runner; `deepseek` is the active dsh host building directly and is not a runner build target |
| `reviewer` | `default` | `claude`, `codex`, `deepseek`, or `agy`; map to `--reviewer`. Must differ from the planner; a DeepSeek host chooses Claude, Codex or Antigravity |
| `inspector` | `default` | `claude`, `codex`, `deepseek`, or `agy`; map to `--inspector`. Must differ from the builder |
| `deepseek_model` / `dsh_cli` | dsh default | Model id and absolute `dsh` path, used only for DeepSeek reviewer runs |
| `research` | proportionate to task | `none`, `web`, or explicit opt-in `deep` |
| `mode` | `full` | `full` composes planning and review; `plan` stops after authoring; `review` starts from an existing plan |
| `inspect` | `on` | `off` only when the user explicitly opts out; record it |
| `fallback` | `same-provider-on-unavailable` | After a recorded quota/authentication/CLI/service/timeout failure, use a fresh same-provider reviewer and mark reduced assurance; `off` disables this. A DeepSeek host or builder has no automatic fallback; select another explicit non-host agent |
| `MAX_FIX_ROUNDS` | `20` | Bounded build-fix attempts before reporting or taking over |
| `MAX_INSPECTION_ROUNDS` | `20` | Initial inspection plus fresh reinspections after fixes |

Echo roles, paths, round limits, requested models, fallback policy and inspection opt-out before starting. Preserve existing authorization: a request to plan does not authorize building; a request to plan and implement does. Do authorized preparation before seeking any remaining sign-off.

## Planning

For `mode=full` or `mode=plan`, use [claudex-plan](../claudex-plan/SKILL.md), following [the planning reference](references/planning.md). Resolve the plan/log pair once and carry it through every handoff. `mode=plan` ends with the plan and verification contract; it does not launch a review or build.

## Independent plan review

For `mode=full` or `mode=review`, use [claudex-review](../claudex-review/SKILL.md) with `kind=plan`, following [the review reference](references/review.md). `mode=review` starts from the existing plan without a new requirements interview. Review approval applies only to the exact plan and repository recorded by the runner.

## Build and inspect

Present the reviewed plan, improvements and remaining limits. If implementation is not already authorized, ask for that final decision. Use the selected builder, defaulting to the host. Use [claudex-review](../claudex-review/SKILL.md) with `kind=code` for the inspection loop, following [the build reference](references/build.md).

The host can implement directly with its normal tools. For a different builder, use the shared runner's `build` mode. A DeepSeek host builds directly or delegates to `--builder claude|codex`; the runner refuses `build --builder deepseek`. Either path must capture the pre-build commit, preserve unrelated user work, and carry the same resolved plan and verification contract.

Run the agreed proof checks, inspect all changed files and review the result through the selected inspector in a **fresh** `inspect` session. Supply the pre-build commit, builder identity and resolved `--inspector`. If the builder is the DeepSeek host, record `--builder deepseek` and inspect with Claude, Codex or Antigravity. Keep role selections on fallback launches. If that provider is unavailable and the failed result is fallback-eligible, automatically launch a fresh same-provider inspection with `--provider BUILDER --fallback-from FAILED_RESULT`. This is weaker assurance, not cross-provider inspection; surface it in the log and final result. A DeepSeek builder has no automatic fallback; select another explicit inspector. Reinspection after accepted fixes also uses a fresh session. Log findings and dispositions; rerun affected proof checks after fixes.

If the coordinator takes over coding, it has become a builder. Require a fresh other-provider inspection of its changes; never describe the earlier inspection as covering later edits. If both providers contributed code, record authorship and have each inspect the other's changes; do not claim any model independently reviewed code it authored. If the inspection budget is exhausted, report remaining findings and unreviewed edits explicitly for the user's decision.

**Completion rule.** When the work is done, re-check each checkbox against its evidence. Move the plan and its log to `docs/exec-plans/completed/` only when every item is `[x]` (including explained `N/A`), then set `status: completed` and add `completed: <YYYY-MM-DD>`. Any unexplained unchecked item keeps the plan active; report the remaining items instead of archiving.

Present the final diff, proof results, inspection coverage, assurance (`cross_provider` or `degraded_same_provider`), fallback cause, unresolved findings, deviations and rounds used. Honor existing commit/push authorization; otherwise leave the concrete diff ready for sign-off. External publication is never implied merely by running the loop.
