---
name: codex-review
description: "Have Codex independently review an existing implementation plan while Claude coordinates a bounded revision loop. For automatic reviewer selection from either host, use claudex-loop with mode=review."
---

# Codex Review

Compatibility entry point: explicitly use Codex as the plan reviewer. The shared workflow and executable live in the sibling `claudex-loop` skill; install that skill alongside this one.

In Claude Code, load [claudex-loop](../claudex-loop/SKILL.md) and start at `mode=review`, `host=claude`, reviewer Codex. Preserve `PLAN_FILE`, `LOG_FILE`, `MAX_ROUNDS` / `rounds`, and explicit model/effort arguments. The invocation authorizes reviewing, not implementation. Do not restart an interview when the supplied plan is already adequate.

In Codex, first use the shared `claudex-loop mode=review` workflow with Claude as the independent reviewer. If Claude fails with a runner result marked `failure_kind=provider_unavailable` and `fallback_eligible=true`, automatically start a fresh Codex review with `--provider codex --fallback-from FAILED_RESULT`. Preserve the injected `DEGRADED_SAME_PROVIDER` limitation and never call it cross-provider approval. Without validated failure evidence, same-provider review remains an explicitly requested ordinary Codex review and must not use the fallback certification path.

Read the shared [runtime reference](../claudex-loop/references/runtime.md). Resolve the runner from the installed sibling skill, not the target repository. Use the actual resolved plan path on every round and build handoff. A valid completed result and APPROVED verdict are both required; failed, empty, blocked or malformed results are not approval. The host logs findings and dispositions, and stops at the round cap.

If implementation follows, use the shared build/inspection phase. An independent plan review does not replace independent review of the final code.
