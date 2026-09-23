# Plan Review Log: Antigravity CLI (agy) as a third provider
Phases 0-1 (recon + interrogation) complete — plan locked with the user. MAX_ROUNDS=5.

Recon: agy 1.2.8→1.2.9 probes and two canary rounds (24 flash calls) on 2026-09-23; canary records deleted from `~/.gemini` at the user's request. Decisions: Q1 web worker + plan-body reviewer; Q2 isolated HOME profile; Q3 transcript-based citation verification, fail-closed; Q4 stdlib CLI (AGENTS.md); Q4' plan-only assurance, never gates builds; cosmetic batch accepted.

## Round 1 — Codex
VERDICT: REVISE — "The plan leaves material gaps in agy isolation, tool auditing, and mixed-provider panel binding."
- R1 high: login and probe commands have no isolated cwd; repo cwd runs repo hooks. Fix: every agy process from a checked empty cwd; login command moves to a safe directory first.
- R2 high: unparseable transcript yields `partial`, yet denied calls may be absent from the stream, so the audit cannot be established. Fix: missing/unparseable transcript = audit failure, no panel output.
- R3 medium: shared `PROVIDERS` choices would expose `--host agy`, `--builder agy`, agy inspection. Fix: separate provider sets per role, enforced before command construction.
- R4 medium: profile does not deny file reads; canary lacks outside-read attempts. Fix: canary absolute/parent/symlink reads, fail rollout on success; deny reads where supported.
- R5 medium: panel resolves one model/effort/CLI/probe per run; a Gemini model would reach Codex. Fix: per-worker effective provider, model, effort, executable, preflight, version gate, bound into digest.
- R6 medium: web-only prompts omit the plan body, so a plan edit after dry-run leaves the digest unchanged. Fix: include plan hash in digest, recheck at launch.

### Claude's response
All six accepted. R1: step 2 now runs every agy process with the profile HOME from an ancestor-checked empty directory; the printed login command starts with `cd "$(mktemp -d)"`. R2: missing/unparseable transcript or stream/transcript disagreement fails the run as unauditable (no `panel.json`); citation verification runs only on audited transcripts. R3: separate `HOSTS/BUILDERS/INSPECTORS/REVIEWERS/PANEL_WORKERS` sets with argparse choices and a mode/provider check. R4: `read_file(*)` added to the profile deny list (neither role reads files); canary adds absolute, `../` and symlink reads as a rollout blocker. R5: per-worker provider resolution with `--agy-model/--agy-effort/--agy-cli`, per-provider preflight once before launch, effective values in the digest. R6: plan SHA256 added to the payload digest and rechecked at launch — an existing gap, fixed in this plan.

## Round 2 — Codex
VERDICT: REVISE — "The revision addresses the six prior findings. Five concrete gaps remain in launch gating, mixed-panel configuration, review instructions, transcript cleanup, and prompt handling."
- R7 high: step 9 preflights once per run; agy can auto-update or the profile drift before a later worker. Fix: recheck profile and version before each agy launch; record per-worker version.
- R8 medium: the spec's existing `model`/`effort` fields apply to every worker; a Codex model would reach agy. Fix: define their scope and precedence; bind per-worker values.
- R9 medium: the shared review prompt tells reviewers to read repo files; agy is denied reads and could claim coverage it lacked. Fix: agy-specific prompt limited to the plan body.
- R10 medium: `conversation_id` is interpolated into lookup/deletion paths without format validation. Fix: canonical UUID check; resolve targets under the profile; no unchecked globbing.
- R11 medium: the `-p PROMPT` argv fallback puts private plan text in process arguments. Fix: require a stdin transport; fail the canary otherwise.

### Claude's response
All five accepted. R7: version/profile/settings/config checks repeat before each agy worker launch; login, `mcp list`, `plugin list` stay once per run; per-worker agy version recorded. R8: spec `model`/`effort` and `--model/--effort/--cli` apply only to the default provider; agy uses only `--agy-*`. R9: agy-specific review prompt (plan body only, no tools, coverage limited to the plan body, unchecked repo evidence listed in limitations); prompt construction joins the adapter table. R10: canonical UUID validation before lookup/resume/cleanup; paths joined, resolved, and confined to the profile. R11: transport switched to the documented `--input-format stream-json` stdin user event; argv fallback removed; the canary must prove delivery and `--json-schema` on the result or rollout stops.

## Round 3 — Codex
VERDICT: REVISE — "The revision addresses the prior findings, but the printed login command still has a hook-execution path."
- R12 high: the printed `cd "$(mktemp -d)"` login command skips the ancestor check; a `TMPDIR` inside a repository would run that repository's hooks. Fix: create the login directory with the launch routine, recheck, print the verified path.

### Claude's response
Accepted. `agy-profile` creates the login directory with the step-3 empty + ancestor-check routine, rechecks it, and prints `cd <verified-dir> && HOME=<profile> agy`. Added: run directories live under the system temp directory because `~/.agents/skills` (Codex skills target) exists under `$HOME` and would be loaded by agy; recorded as assumption 9.

## Round 4 — Codex
VERDICT: APPROVED — "The revised plan resolves the prior material findings. The agy rollout remains gated on its stated live canary."
Limitations: no files edited, no tests or live agy commands run; raw canary records unavailable, so a new live canary is required before rollout.

## Resolution
APPROVED in 4 rounds (12 findings: 12 accepted, 0 rejected). Awaiting user sign-off; implementation not authorised yet.
