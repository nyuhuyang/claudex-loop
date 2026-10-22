# CLI launch budget

Read before a review, inspection, delegated build or panel launch.

**Token budget.** Never let quota burn silently. Before every expensive review, inspection, delegated-build or panel launch, warn about the likely workload and offer concrete token-reducing options. Settle the budget choice in the Phase 1 decision interview; bring it forward before a Phase 0 panel. With `mode=review`, ask a focused budget question alongside any material-gap questions, without restarting the interview.

Estimate by mode: plan review reads the plan and the relevant code; inspection receives the tracked diff against the pre-build `--base` plus a manifest of changed and non-ignored untracked files, which the inspector must open. Count untracked files individually (`git status --porcelain --untracked-files=all`) and weigh their sizes with diff size, planned work, effort and launch count. Label the estimate rough; file counts are not token predictions.

Recommend the applicable options: commit or isolate unrelated work before building so the pre-build base excludes it; exclude irrelevant untracked generated outputs; a supported lower effort or model chosen explicitly; batching fixes so fewer reinspections run; fewer panel questions or workers while keeping required angle coverage. Never hide required evidence: a baseline must not absorb build changes, and ignored deliverables still need separate inspection. Repository changes need authorization; honor authorization already given. An effort change needs a fresh session where resume validation requires it. A review run outside the runner, or a plan-body-only agy review, never replaces this workflow's approval; a runner-validated DeepSeek review (`assurance=cross_provider`) can.

Record the choice in `LOG_FILE` and warn again before a later launch whose workload grew materially. Automatic eligible fallback keeps running without a new approval gate and keeps the failed attempt's base and snapshot. Panel dry-run and payload approval still apply.

