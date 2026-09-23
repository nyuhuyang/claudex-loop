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

## Act 3 — Build
### Round 1 — Codex build
Codex (thread 01a0ce4a-ece7-7683-8c32-c5dae459a274) implemented Approach steps 1-12: `agy-profile`, preflight, stdin stream-json transport, stream parser, transcript audit and citation verification, panel transcript cleanup, per-worker provider settings, plan hash in the panel digest, role-separated provider sets, `cross_provider_plan_only` rejected by `check_approval`, provider adapter table, docs; 11 fake-agy tests. Reported no deviations.
### Claude's verdict
Full diff read; proof rerun by Claude: validate OK, 76 tests OK, `--help` OK, `git diff --check` clean. Fix requested:
- F1 blocker: preflight scans all of `.gemini`; a real profile has `antigravity-cli/cli.log` (symlink), `builtin/skills`, and a 0-byte `config/mcp_config.json`, so preflight would always fail after login. Scope the scan to `.gemini/config`, accept empty MCP config, refuse non-empty `antigravity-cli/plugins`.
- F2 high: multi-call planner responses give every call the first result's text, allowing a false `retrieved`. Such results become non-evidence (`unverified`).
- F3 `--agy-effort` choices limited to low/medium/high; F4 login probe timeout 30s; F5 top-level `shlex` import; F6 drop duplicate version check in review.
### Round 2 — Codex fix
F1-F6 fixed: config scan limited to `.gemini/config` (realistic logged-in layout passes; hooks/skills under config, non-empty `antigravity-cli/plugins`, configured MCP servers still fail); multi-call transcript results marked `evidence_ambiguous` (URL seen, never `retrieved`); `--agy-effort` low/medium/high; login probe 30s; top-level `shlex`; single version probe in review. Five new tests.
### Claude's verdict
Diff re-read; proof rerun by Claude: validate OK, 81 tests OK, `--help` OK, `git diff --check` clean. Claude corrected the VALIDATION.md test count (76 → 81). Accepted; ready for the human diff gate. Pending after commit: live profile canary (needs the user's one-time agy login) and live runs.
### Round 3 — Codex fix (live-canary findings G1-G4)
Profile preset `request-review` (strict overrides allow rules); semantic settings check (login rewrites the file); transcript-only `finish` allowed; denied `ERROR` calls recorded as `denied_attempts`. Claude restored the `auto-denied` stderr failure Codex had removed (explicit denies surface as ERROR steps with empty stderr; `auto-denied` means an unlisted action ended the turn) and removed a test fixture that contradicted the live evidence.
### Claude takeover (fix rounds exhausted) — Q5 two profiles
Live finding: `read_url_content` saves pages under the profile's `brain/` and returns only the path; with `read_file(*)` denied the worker could never read a page. User chose Q5: `agy-web` (web + own brain reads) and offline `agy-review`. Claude implemented role profiles, `view_file` confined by audit to the conversation's own `steps/`, citation evidence from the saved page (saved path outside the conversation = unauditable), saved pages copied to artifacts before cleanup; three new tests; both new safeguards mutation-checked (removing either makes its test fail). Plan amended; docs updated.
- Live preflight of both logged-in profiles passed after accepting the default-dropped `toolPermission` key (agy rewrites settings.json on every launch, not only at login).

## Live agy plan review (runner end-to-end, gemini-3.1-pro-high, agy-review profile)
First run failed validation: agy wrote severity `HIGH`. Fix: agy prompt states the finding fields; agy-only lowercase normalisation (unknown values still fail); test added. Its content was right: plan steps 1 and 6 lagged the amendment — synced.
Second run: `completed`, `cross_provider_plan_only`, session UUID returned, no denied attempts; `check` refused it (REVISE). Findings: (1) step 2 still said byte-for-byte settings equality — accepted, rewritten; (2) step 7 still searched `read_url_content` text — accepted, now the saved page; (3) add allows for `search_web`/`finish` — rejected: both ran live without allows, and the reviewer listed this as unverifiable; (4) step 3 "HOME only" reads as stripping PATH — clarified wording (implementation already preserves the environment).

## Live mixed panel (user-approved digest 8f78401e…)
Before approval: agy source rules now tell the worker that `read_url_content` saves the page and to read it with `view_file` (prompt change, re-dry-run, new digest shown to the user).
Result `partial`: Codex worker completed (1 retrieved, 3 unverified); agy worker failed with exit 3 / `AGY_ERROR RESOURCE_EXHAUSTED` — Gemini weekly quota 0% until 2026-09-30. Runner behaviour correct (failed worker, partial panel, transcript + saved pages copied, profile cleaned). Added: preflight refuses launch when `/usage` shows 0% Gemini quota (live-verified). Open: macOS keychain dialog under the profile `HOME` on token refresh (user told to Cancel); agy `retrieved` citations unproven live until quota resets.
