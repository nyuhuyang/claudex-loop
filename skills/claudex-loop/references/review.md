# Independent plan review

Used by `claudex-review` and the review phase of `claudex-loop`. Start from the supplied plan. Fill only material gaps; do not restart the planning interview. The invocation authorizes review and warranted plan revisions, not implementation. Read [the runtime reference](runtime.md) before a CLI launch.

## Review rounds

Resolve the reviewer using [the role contract](roles.md) and settle [the launch budget](budget.md). Use the shared runner in `review` mode with the actual `--host`, resolved `--plan`, selected `--reviewer` and optional model/effort. Preserve the resolved role selections on every round, resume, and fallback; `--provider` only overrides the current launch. First round creates a session. Further rounds use `--resume <previous-successful-result.json>` with the same provider/model/effort and a host-authored `--feedback` file containing dispositions; DeepSeek rounds never resume and start fresh with that `--feedback`. Never use a guessed session id, `--last`, or a build session as a reviewer.

Each successful response contains a verdict, evidence-backed findings, actual coverage and limitations. Preserve the entire response and runner result path in `LOG_FILE`.

- **APPROVED:** no unresolved material defects. Approval is bound to the exact plan path and SHA256. Present remaining low-priority advice and limitations; zero findings is valid and is not proof of exhaustive correctness.
- **REVISE:** the host arbitrates each finding. Implement warranted plan changes; reject unsupported suggestions with reasons. Record dispositions and send the revised plan to the same reviewer. Avoid relitigating resolved points without new evidence.
- **BLOCKED / malformed result / ordinary process failure:** never count this as approval. Explain the actual missing evidence or operational failure. Do not burn remaining rounds on blind retries.
- **Provider unavailable:** when the failed result records `failure_kind=provider_unavailable` and `fallback_eligible=true`, and `fallback` is enabled, immediately start a fresh same-provider review using `--provider HOST --fallback-from FAILED_RESULT`, retaining the preferred `--reviewer` and other role flags. Do not ask again after echoing the policy. This is automatic but never silent: preserve the primary diagnostics, record `assurance=degraded_same_provider`, and retain the injected `DEGRADED_SAME_PROVIDER` limitation. Do not trigger fallback for `REVISE`, `BLOCKED`, malformed output, repository mutation, or user interruption. Use the fallback reviewer session for later plan revisions with both `--resume` and the original `--fallback-from`; do not return to the unavailable provider mid-loop.

Automatic fallback requires a live coordinator. If the active host process itself exhausts quota and stops, it cannot launch another process; resume the workflow from the other host with the preserved failed result. A live Codex host can automatically replace an unavailable Claude reviewer with a fresh Codex CLI session.

Stop at `MAX_ROUNDS`. Present unresolved findings and the host's position instead of manufacturing convergence. A changed plan requires another review. Before building, run the approval check on the final plan. If the user explicitly chooses to proceed without independent approval, record that override and use the standalone unreviewed-spec path; never label it approved.

