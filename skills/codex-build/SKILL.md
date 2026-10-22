---
name: codex-build
description: "Compatibility alias selecting builder=codex for a concrete work order. Use claudex-review with an independent inspector for final code review, or claudex-loop for the complete workflow."
---

# Codex Build

Compatibility entry point: the builder is explicitly Codex. Review follows [claudex-review](../claudex-review/SKILL.md) with `kind=code`, `builder=codex` and an independent `inspector` (default Claude); preserve any explicit supported inspector choice. The shared workflow and executable live in the sibling `claudex-loop` skill; install that skill alongside this one.

Load the shared [build reference](../claudex-loop/references/build.md) and [runtime reference](../claudex-loop/references/runtime.md). Preserve `SPEC_FILE` (mapped to the runner's `--plan`), `LOG_FILE`, `PROOF_CMD`, `MAX_FIX_ROUNDS`, and explicit model/effort arguments. The spec may have any filename; never substitute PLAN.md silently.

The following are default Claude/Codex inspection examples; an explicit `inspector=deepseek` or `inspector=agy` uses the shared role contract and its opt-in rules instead.

- In Claude Code, Claude coordinates and delegates implementation to Codex through the runner's `build --host claude --builder codex` path. Claude then inspects all changes and independently runs proof checks. Log evidence and limitations. A fresh Claude CLI inspector is also available through the shared runner if useful.
- In Codex, implement in the current host session with its normal tools, then use a fresh Claude inspector through `inspect --host codex --builder codex`. If Claude is unavailable and its failed result is marked fallback-eligible, automatically launch a fresh Codex inspector with `--provider codex --fallback-from FAILED_RESULT`. Record `degraded_same_provider`; do not describe it as cross-provider inspection.

Use the current valid plan approval when this follows claudex-loop. An explicitly requested standalone work order can use `--unreviewed-spec`, with that status recorded. If the spec still needs consequential decisions, settle those before delegating; do not build by inventing missing requirements.

When the spec is an execution plan with a `## Progress Checklist`, tick each item only after Claude has verified it, and archive under the claudex-loop completion rule. Preserve unrelated changes, record the baseline, independently run the proof, inspect staged and new files as well as the unstaged diff, and keep fix rounds bounded. After a Claude takeover, require fresh Codex inspection of Claude's edits; if both contributed, log authorship and have each inspect the other's changes. Never present an earlier review as covering later fixes. Present the completed diff for any remaining sign-off required by the user's authorization.
