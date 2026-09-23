---
status: in-progress
created: 2026-09-23
---

# Plan: Antigravity CLI (agy) as a third provider — web researcher and plan-body reviewer
_Locked via claudex-loop — by Claude + the user_

## Goal

Add Google's Antigravity CLI (`agy`, Gemini models) to the runner as a third provider in two roles that never touch the repository: a **panel web worker** and a **plan-body-only plan reviewer**. agy must run Gemini, never Claude/GPT models that agy also offers. Live canaries on agy 1.2.8/1.2.9 (2026-09-23) showed that any repository exposure (cwd or `--add-dir`) loads the repo's `.agents/hooks.json` and runs its shell commands, that a hook can return `{"decision":"allow"}` for any tool, and that custom-agent `tools:` allowlists do not reduce the exposed toolset. Repo reading, building, inspecting and hosting by agy are therefore out of scope.

## Approach

1. **Isolated profile.** New subcommand `runner.py agy-profile` creates `~/.claudex-loop/agy-home` (mode 0700) and writes `HOME/.gemini/antigravity-cli/settings.json`:
   `{"toolPermission":"strict","enableTerminalSandbox":true,"allowNonWorkspaceAccess":false,"enableTelemetry":false,"permissions":{"deny":["read_file(*)","write_file(*)","command(*)","unsandboxed(*)","mcp(*)","execute_url(*)"],"allow":["read_url(*)"]}}`.
   It creates a login directory with the same empty-directory + ancestor-check routine used for launches (step 3), rechecks it, and prints the one-time login command using that verified absolute path (`cd <verified-dir> && HOME=<profile> agy`), because agy loads workspace customizations from its cwd and ancestors; the runner never performs or automates login. The user's own `~/.gemini` is never read or written.
2. **Preflight on every agy launch** (fail closed, no launch on any mismatch). Every agy process the runner starts — version, `mcp list`, `plugin list`, login probe, and the worker itself — runs with `HOME=<profile>` from a runner-created empty directory that passed the ancestor check in step 3; the runner's own cwd is never used:
   - profile exists and is owner-only;
   - `settings.json` equals the expected document byte-for-byte after JSON normalisation;
   - no `hooks.json`, `mcp_config.json` with servers, `agents/`, `skills/`, `plugins/` or `rules` under `HOME/.gemini/config`; `agy mcp list` and `agy plugin list` report none;
   - the profile is logged in, detected by a non-interactive status probe with stdin closed and a short timeout (an auth prompt is a failure, not a hang);
   - `agy --version` is in `VALIDATED_AGY_CLI = ("1.2.9",)` unless `--allow-unvalidated-cli` (recorded).
   The version, profile-permission, `settings.json` and config-tree checks repeat immediately before **each** agy worker launch (agy auto-updates mid-session); the login, `mcp list` and `plugin list` probes run once per run. Each worker record stores the agy version it launched with.
3. **Invocation.** Environment is the parent environment with `HOME=<profile>` only. cwd is a fresh empty directory under the run artifacts, never the repo; no `--add-dir`. The runner walks from that cwd to `/` and refuses to launch if any `.agents`/`.agent`/`_agents`/`_agent`, `GEMINI.md` or `AGENTS.md` is found. Run directories therefore live under the system temp directory, not `$HOME`: this machine has `~/.agents/skills` (the Codex skills install target), which agy would load as workspace customizations.
   `agy --input-format stream-json --output-format stream-json --json-schema <schema file> --model <slug> [--effort E] [--conversation ID] --print-timeout <remaining>s`, with the prompt written to stdin as one documented `{"event":"user","message":{"content":...}}` line and stdin then closed. Prompt text never appears in argv; there is no argv fallback. The canary must show that this transport delivers the prompt and that `--json-schema` applies to its `result`; if not, the rollout stops. `--dangerously-skip-permissions`, `--agent`, `--mode`, `--continue` and `--sandbox` are never passed.
4. **Model policy.** Default `gemini-3.1-pro-high`. The agy provider accepts only slugs matching `^gemini-`; anything else is refused before launch. The requested model must appear as `init.model`; the observed model is recorded as unknown because agy does not report it.
5. **Result parsing** (`parse_agy_stream`). Exactly one `init` and one terminal `result`; `result.status == "SUCCESS"`; non-empty `response`; `structured_output` present and schema-valid. Any of: non-zero exit, missing events, other status, empty response, a stderr line matching `auto-denied`, or `AGY_ERROR:` on stderr → failed turn. Record `conversation_id`, usage and `permission_mode`. `conversation_id` must be a canonical lowercase UUID before any lookup, resume or cleanup; paths are built by joining that UUID under the profile, resolved, and checked to stay inside the profile — no globbing with an unchecked value. Resume passes `--conversation ID` and requires the same id back.
6. **Tool audit** from both the stream `tool` steps and `transcript_full.jsonl` `tool_calls`: web workers may call only `search_web` and `read_url_content`; plan reviewers may call none. Any other tool, a transcript/stream tool-set disagreement, or a missing/unparseable transcript fails the run as unauditable (no `panel.json`, like a confinement violation), because denied calls can be absent from the stream. The audit runs in `finally`, as for the existing panel.
7. **Citation verification** for agy web workers reads `HOME/.gemini/antigravity-cli/brain/<conversation_id>/.system_generated/logs/transcript_full.jsonl`: pair each `PLANNER_RESPONSE.tool_calls` entry with the following `GENERIC` step. `retrieved` only when the excerpt (markdown-normalised) appears in the `read_url_content` result for the claim's exact URL; a match only in `search_web` output (a Gemini-written summary) is `unverified`; a URL never fetched or searched is `mismatch`. Verification runs only on a transcript that passed the step-6 audit; within it, insufficient evidence yields `unverified`, never a pass.
8. **Transcript hygiene.** After a panel worker finishes, copy its transcript into the worker artifact directory (owner-only), then delete `brain/<id>`, `conversations/<id>.db*` and its `conversation_summaries` row from the profile. Review sessions are kept for `--conversation` resume; the docs state that the profile then holds plan text until cleaned.
9. **Panel integration.** Worker spec gains optional `provider` (`claude|codex|agy`, default = the current opposite-provider rule). agy workers are `kind: web` only. `cross_provider_panel` still requires every worker to be a non-host provider. Model, effort, executable, preflight and version gate resolve **per worker provider**: `--model/--effort/--cli` and the spec's existing `model`/`effort` fields apply only to the default opposite provider (existing precedence between them unchanged); agy workers use only `--agy-model/--agy-effort/--agy-cli` (defaults: `gemini-3.1-pro-high`, CLI default effort, `agy` on PATH), never the spec fields. Each provider present is preflighted once before any launch. The payload digest covers each worker's effective provider, model and effort **and the plan SHA256**; launch recomputes the plan hash and refuses a mismatch (this also fixes an existing gap: web-only prompts omit the plan body, so a plan edit after dry-run did not change the digest).
10. **Review integration.** `review --provider agy` (any host) runs the full REVISE/APPROVED loop. agy gets its own review prompt: it embeds the resolved plan body, tells the reviewer it has no tools or repository access, limits `coverage` to the supplied plan body, and asks it to list repository evidence it could not check under `limitations`; the runner also appends a `PLAN_BODY_ONLY` limitation. The shared repo-reading review prompt is never sent to agy. Records carry `assurance=cross_provider_plan_only`; `check_approval` rejects it for builds. agy is never a default reviewer, builder or inspector; `resolve_roles` defaults are unchanged. Provider sets are separate: `HOSTS = BUILDERS = INSPECTORS = ("claude", "codex")`, `REVIEWERS = ("claude", "codex", "agy")`, `PANEL_WORKERS = ("claude", "codex", "agy")`; argparse choices and a mode/provider check before command construction enforce them, so `--host agy`, `--builder agy` and agy inspection are rejected. agy failures are `fallback_eligible=false` (no same-provider fallback path exists for agy).
11. **Adapter extraction** (prior decision: extract when the third provider lands). Move per-provider prompt construction, `command`/parse/audit/verify into a small provider table keyed by name, keeping Claude and Codex behaviour byte-identical (existing tests unchanged).
12. **Docs.** `SKILL.md`, `references/runtime.md`, `references/research.md`, `README.md`, `VALIDATION.md` (canary record). No new skill directory.

### Amendment after the live canary (2026-09-23, Q5 with the user)
Live facts changed step 1: `strict` overrides `permissions.allow`, so both profiles use `request-review` with explicit denies (denies held live); login rewrites `settings.json`, so preflight checks security properties, not equality; with `--json-schema` agy returns output through a transcript-only `finish` call; denied calls surface as `ERROR` and are recorded as `denied_attempts`; `read_url_content` returns only the path of a page it saved under the profile's `brain/`. Q5 split the profile in two: `~/.claudex-loop/agy-web` (allow `read_url(*)` and `read_file(<profile>/.gemini/antigravity-cli/brain)`, deny writes/commands/MCP/`execute_url`; `view_file` is audited to the conversation's own `steps/`, and citations are checked against that saved page) and `~/.claudex-loop/agy-review` (deny all file reads and `read_url(*)` too), so the role that can reach the web never shares a profile with stored plan text.

## Key decisions & tradeoffs

- **Q1 roles:** web worker + plan-body reviewer only. Rejected: repo reviewer/builder (repo hooks = code execution; allowlists ineffective).
- **Q2 isolation:** dedicated `HOME` profile with locked deny rules instead of mutating `~/.gemini` or running unconfigured. Cost: a second login; settings drift is caught by preflight.
- **Q3 citations:** undocumented `transcript_full.jsonl`, version-gated; an unparseable transcript fails the run as unauditable (R2), and weak evidence in an audited transcript is `unverified`. Rejected: trusting model-authored citations; no verification (agy could never satisfy coverage).
- **Q4 stdlib CLI, not the Python SDK:** AGENTS.md requires a standard-library-only runtime. Revisit the SDK's `enabled_tools=read_only()` only when a repo role is proposed.
- **Q4' plan-only assurance:** agy APPROVED never gates a build.
- **Q5 two profiles:** web workers may read their fetched pages; plan reviewers are offline. Rejected: one shared profile with brain reads (prompt-injected pages could read stored plan text and exfiltrate it through `read_url`), or no file reads (agy could never produce `retrieved` claims).
- Cosmetic batch accepted as proposed (profile path, model default and `gemini-` restriction, `provider: agy` + `model_family: gemini`, version gate, spec `provider` field, failure signals, tool audit, transcript cleanup, resume id check, docs-only Claude-side integration).

## Assumptions

1. agy headless: `init`/`step_update`/`result` NDJSON; stderr `AGY_ERROR` + exit 3 on API failure; unknown `--model` exits non-zero. — agy headless docs; live run 2026-09-23.
2. A denied tool ends the turn with `status: SUCCESS`, exit 0, empty `response`, and an `auto-denied` stderr line; denied calls may be absent from the stream. — canary t3–t6, r1–r6.
3. Stream `tool_info.output` is a summary (`"2 lines, 17 bytes"`) or empty; full results exist only in `transcript_full.jsonl`. — canary r5/r6 and transcript inspection.
4. `HOME` override isolates credentials (fresh `HOME` demanded login). — probe 2026-09-23. **Unverified:** that deny rules in the profile are enforced and that `read_url(*)` is honoured; step 1 of Verification.
5. Workspace `.agents/hooks.json` executes under `--add-dir` in trusted and untrusted directories; `trustedWorkspaces` does not prevent it. — canary round 2 markers.
6. `--agent` with `tools:` leaves all 57 tools exposed. — canary t2.
7. Gemini and Claude/GPT models have separate weekly quotas in agy. — `agy -p /usage`.
8. agy auto-updates (1.2.8 → 1.2.9 within one session). — observed.
9. `~/.agents/skills` exists on this machine, so any agy cwd under `$HOME` would pick up those skills; the ancestor check rejects it. — `ls ~/.agents`.

## Risks / open questions

- `transcript_full.jsonl` is undocumented; an agy update can silently change it (mitigated by version gate and fail-closed parsing).
- Prompt text reaches Google; plan bodies may contain private design detail. The dry-run/approval digest already shows the user exactly what is sent to panel workers; plan review sends the plan body by design.
- Terminal-sandbox and deny rules are enforced by the agy process, not by the runner; residual risk stated in docs.
- Windows uses agy's older permission system; the runner refuses agy on Windows until a canary passes there.

## Out of scope

agy repo reading, building, inspecting, or hosting claudex-loop; the Python SDK; same-provider fallback for agy; changes to Claude/Codex fallback rules; automating agy login; Windows support.

## Progress Checklist

- [x] Live profile canary (user-authorised): create profile, user logs in, then verify the stdin stream-json prompt transport with `--json-schema`, deny rules block write/command and outside reads (absolute path, `../`, symlink — any success blocks rollout), `read_url` succeeds, stdin prompt delivery, no hooks fire, transcript path/shape — record in VALIDATION.md
- [x] Provider table extraction with no Claude/Codex behaviour change
- [x] `agy-profile` subcommand and preflight
- [x] agy command builder, stream parser, failure classification
- [x] Tool audit and transcript-based citation verification
- [x] Panel `provider` field, per-worker provider resolution, plan hash in payload digest, agy web workers
- [x] `review --provider agy`, plan-only assurance, `check_approval` rejection
- [x] Transcript cleanup for panel workers
- [x] Tests with a fake `agy` (stream, transcript, denial, AGY_ERROR, hostile tool, non-gemini model, preflight failures, resume id)
- [ ] Docs updated; live runs: one agy plan review, one Claude-hosted panel with Codex + agy web workers
- [ ] Open PR; archive this plan

## Verification

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
python skills/claudex-loop/scripts/runner.py --help
git diff --check
```
