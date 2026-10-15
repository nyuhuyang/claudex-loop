---
status: in-progress
created: 2026-10-14
---

# Plan: DeepSeek (dsh) as an opt-in plan reviewer and code inspector

_Drafted by Claude for Yang Hu, 2026-10-14. Revised the same day to build on the provider adapter table from PR #2 (`feat/agy-provider`) instead of adding provider branches to `main`. A Gemini pre-review ran outside the runner (2 rounds, APPROVED on an earlier revision). It is advisory only and does not count as a claudex-loop approval. This plan does not authorize implementation._

## Goal

Let a Claude- or Codex-hosted Claudex Loop use DeepSeek as the plan reviewer (`review`) or as the final code inspector (`inspect`), through the official DeepSeek Harness CLI (`dsh`). The reviewer must be as locked down as the existing reviewers. Its result must follow the same structured-review contract. Default roles stay the same; DeepSeek runs only when the user asks for it.

## Acceptance Criteria

- [x] `runner.py review --host claude --provider deepseek ...` runs one dsh turn and writes `result.json` with `provider: deepseek`, `assurance: cross_provider` and a response that passes `validate_review`. — fake dsh (`test_review_and_inspection_succeed_with_lockdown`); live run pending below
- [x] `runner.py review --host codex --provider deepseek ...` does the same. — fake dsh
- [x] `runner.py inspect --host claude --provider deepseek --base X ...` does the same for inspection, with the existing snapshot checks, and records `roles.inspector: deepseek`. — fake dsh
- [x] `--resume PREVIOUS_RESULT` continues the same dsh session. A different returned session id is refused.
- [x] A dsh tool call outside the allowlist `read`, `glob`, `grep` fails the run, and no verdict is accepted.
- [x] A read path outside the repository (other than the plan file) fails the run, and no verdict is accepted.
- [x] A working-tree change during a review fails the run, and no verdict is accepted.
- [x] An authentication, balance, rate-limit or service failure is recorded as `failure_kind=provider_unavailable`.
- [x] After that failure the skill reruns without `--provider deepseek`, using the default reviewer or the default non-builder inspector. No degraded same-provider fallback runs. — skill rule in SKILL.md; runner refuses DeepSeek fallback
- [x] Without `--provider deepseek`, behaviour is unchanged and every existing test passes unmodified. — 93 pre-existing tests pass unmodified
- [x] `python scripts/validate.py` passes on Linux, macOS and Windows CI. — CI run 38672220186 (`0e456d3`), Linux/macOS/Windows green
- [x] `python -m unittest discover -s tests -v` passes on Linux, macOS and Windows CI. — CI run 38672220186 (`0e456d3`), Linux/macOS/Windows green
- [ ] One live DeepSeek review is recorded in `VALIDATION.md`. — BLOCKED: no DeepSeek API key yet (`DEEPSEEK_API_KEY` unset; store one with `dsh web` or export it)
- [ ] One live DeepSeek inspection is recorded in `VALIDATION.md`. — BLOCKED: no DeepSeek API key yet

## Non-goals

- DeepSeek as host, planner or builder.
- DeepSeek panel workers. `PANEL_WORKERS` does not change.
- Running two reviewers in parallel (Codex and DeepSeek) and merging their verdicts. The user can run them one after the other by hand.
- Calling the DeepSeek HTTP API directly. The runner keeps driving vendor CLIs only.
- Confidential or client repositories. See Decision 2.

## Dependency on PR #2 and the research panel

- **The research panel (`2026-09-22-cross-provider-research-panel.md`) is already on `main`** (PR #1, merged 2026-09-23). This plan does not change `panel` mode.
- **PR #2 (`feat/agy-provider`, open)** adds the pieces this plan reuses:
  - `HOSTS`, `BUILDERS`, `INSPECTORS`, `REVIEWERS` and `PANEL_WORKERS` (today `REVIEWERS = PANEL_WORKERS = PROVIDERS + ("agy",)`);
  - `PROVIDER_ADAPTERS`, with the `review_prompt`, `review_command`, `review_parse` and `review_audit` hooks;
  - reviewer selection by `review --provider X`;
  - `execute(..., env=...)`;
  - a version preflight, and the rule that a third-party provider has no same-provider fallback.
- That panel plan's appendix says the adapter interface is extracted when a new provider is added. PR #2 did that, so this plan adds `deepseek` as one more adapter entry and does not add a parallel set of `if provider == "deepseek"` branches.
- **For reviewers:** PR #2's code is not on `main`. Read it with `git show feat/agy-provider:skills/claudex-loop/scripts/runner.py` (`PROVIDER_ADAPTERS` near line 1433, `run()` near line 1759).
- **Order:** finish PR #2 first (live agy runs, merge), then branch from `main`. If PR #2 is abandoned, this plan is BLOCKED until it is revised to extract the adapter table itself.
- **Difference from agy.** agy reviews the plan body only (`cross_provider_plan_only`), and that assurance cannot approve a build. DeepSeek reads the repository under the Decision 3 audit. It records `cross_provider`, so `check_approval` accepts its approval like a Codex or Claude approval.

## Verified facts (dsh 0.2.0-rc.2, 2026-10-14)

Sources: `dsh --profile headless --help`, `dsh --profile headless --dump-config`, `--dump-config-schema`, the installed packages under `/opt/homebrew/lib/node_modules/@deepseek-ai/dsh/`, and the agentic-os dsh spike (`prototypes/agentic-os/docs/exec-plans/active/2026-10-14-dsh-backend-swap.md`, Verified facts and spike items a–h).

- **Headless CLI.** `dsh --profile headless [--json] [--session-id ID] [task...]`. A task of `-` reads stdin. `--json` prints NDJSON run events:
  - the first event is `session {sessionId, cwd}`, where `sessionId` is `session-<uuid>`;
  - then `status` events (`turn_start`/`step_start`/`step_end`/`turn_end`), `thinking`, `text`, `tool_call {callId, tool, input}` and `tool_result {callId, status, result}`;
  - the run ends with `final`.
  - `step_end.usage` carries `inputTokens`/`outputTokens` but is sometimes missing. Headless prints no model name.
- **Resume.** `--session-id` resumes only from the same cwd. From another cwd it prints an `error` event and exits 1.
- **Failure.** A bad key gives exit 1, a `turn_end` error, an empty `final`, and a `dsh: AUTH:` line on stderr.
- **Permission presets.** `DSH_PERMISSION_MODE` selects one of `read-only`, `workspace-write` or `danger-full-access`. The first two use approval `ask`. In headless mode `ask` auto-denies escalation ("no approval channel is available") and does not hang. The sandbox `workspaceRoot` is the cwd.
- **Network.** The Seatbelt sandbox leaves the network open in every mode. Shell commands can therefore reach the network, so the shell tool must be removed (Decision 3), not just sandboxed.
- **Profile overlays.** `--patch <file.yml>` applies a patch list after the profile layer. `- id: tool-bash\n  disabled: true` removes that plugin; verified with `--dump-config`. A patch `config` replaces the whole config of that entry.
- **Tools.** The tool plugins are:
  - `tool-fs`, which registers `read`, `edit`, `write` and `read_image` together and cannot be split;
  - `tool-fs-search`, which registers `glob` and `grep`;
  - and `tool-bash`, `tool-jobs`, `tool-skill`, `tool-subagent*`, `tool-workflow`, `tool-web`, `tool-todo`, `tool-goal` and `mcp-resources`.
  - `ptc-runtime` adds `run_code` only when `DSH_TOOLS_MODE` is `ptc` or `both`. The default is `native`.
- **Model.** The default model comes from the `agent-default-model` entry (`provider: deepseek-official`, `model: deepseek-flash`). The built-in catalog in `dsh-llm-deepseek` (`DEFAULT_MODELS`) has two entries:
  - id `deepseek-flash`, display name `DeepSeek-V41-Flash` (DeepSeek-V4.1-Flash), which is the default;
  - id `deepseek-v4-pro`, display name `DeepSeek-V4-Pro`, described as "stronger … suited to complex or quality-critical tasks at higher cost".
  - Model ids are the lowercase ids, not the display names.
- **Telemetry.** `DSH_TELEMETRY_MODE` is `FEEDBACK_ONLY` by default; `DISABLED` is also accepted.
- **Credentials.** dsh resolves the DeepSeek key from its credentials service (`~/.dsh/.credentials.yaml`, written by the `dsh web` Models page) or from `DEEPSEEK_API_KEY` in the launching environment. Spike s5: this machine's credentials file holds only a browser session, so without the env var a run fails with `dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"`. The runner inherits the environment unchanged and never reads, writes or logs the key; the user either stores it through `dsh web` or exports it.
- **Instructions.** `agent-instructions` loads repository instruction files (for example `AGENTS.md`) into the system prompt, up to 64 KiB.

## Decisions

1. **DeepSeek is a third, opt-in reviewer and inspector, added as an adapter.**
   - `HOSTS` and `BUILDERS` stay `PROVIDERS`. `REVIEWERS` gains `deepseek`. `INSPECTORS` becomes `PROVIDERS + ("deepseek",)`. `PANEL_WORKERS` does not change.
   - Selection uses PR #2's existing flag: `review --provider deepseek` and `inspect --provider deepseek`. No `--reviewer`/`--inspector` flags are added.
   - `resolve_roles(host, reviewer, builder, inspector=None)` gains `inspector`.
     - The inspector may be `deepseek` or the non-builder provider, never the builder.
     - In `inspect` mode, `run()` passes `args.provider` as the inspector **only when it is `deepseek`** (DSH-01). Any other `--provider` keeps the default inspector role. The existing same-provider fallback (`--provider BUILDER --fallback-from ...`) therefore still reaches `validate_fallback` unchanged, and `test_quota_failure_allows_fresh_same_provider_inspection` passes unmodified.
     - Roles are stored in `result.json` and are now enforced, not just stored (DSH-05):
       - `previous_record` compares the stored `roles` with the roles of the current run and refuses a mismatch, for example a review started with `--host claude` and resumed with `--host codex`;
       - `check_approval` compares the approval's `roles.host` and `roles.planner` with the current host. In `build`, it also requires the approval's `roles.reviewer` to differ from that host;
       - `validate_fallback` keeps its existing role comparison.
   - `run()` refuses `deepseek` for `build` and `panel`, as it refuses agy outside its roles.
   - Assurance is `cross_provider`, because DeepSeek is neither the host nor the builder.
   - Skill tunables `reviewer=default|deepseek` and `inspector=default|deepseek` map to `--provider deepseek`. The skill echoes them with the other roles before starting.
   - DeepSeek reuses the runner's generic `--cli` and `--model` flags; agy has its own flags because a single panel can mix providers. In the skill, the DeepSeek values come from their own tunables, `deepseek_model` and `dsh_cli`. They are never read from `reviewer_model`/`inspector_model`/`codex_cli`/`claude_cli`, and those are never applied to a DeepSeek run (DSH-09).

2. **Data-egress gate (skill level, mandatory).**
   - A DeepSeek review sends the plan, plus every file the reviewer reads, to the DeepSeek API.
   - Before the first DeepSeek run in a loop, the skill says this in one line and requires the user's explicit opt-in for that repository. A DeepSeek role is never chosen automatically, including as a fallback.
   - Confidential or client repositories are out of scope, consistent with the agentic-os rule that rejects dsh for confidential projects.
   - The runner sets `DSH_TELEMETRY_MODE=DISABLED` in the child environment. The patch also disables the `otel` and `session-telemetry-otel` plugins (DSR-08).
   - The runner cannot detect confidentiality. That stays a host responsibility, documented in SKILL.md and runtime.md.

3. **Read-only lockdown: three layers, fail closed.**
   - **(a) Sandbox.** The child env sets `DSH_PERMISSION_MODE=read-only` and `DSH_TOOLS_MODE=native`. Writes are denied, and headless `ask` auto-denies escalation.
     - PR #2's `execute(env=...)` already exists.
     - Every adapter gains a `review_env(ctx) -> dict | None` hook (DSH-03). `ctx` carries `run_dir`, `repo` and the resolved agy `profile`. `run()` passes `PROVIDER_ADAPTERS[provider]["review_env"](ctx)` to `execute`, instead of growing the `provider == "agy"` conditional.
     - The hooks:
       - Claude and Codex return `None`;
       - agy's hook is the existing `agy_env(profile)`, moved over unchanged. Preflight, execution and audit therefore keep using the same isolated agy profile;
       - dsh returns `{**os.environ, DSH_PERMISSION_MODE, DSH_TOOLS_MODE, DSH_TELEMETRY_MODE}`.
   - **(b) Tool removal.** The runner writes `dsh-patch.yml` into the run directory and passes `--patch`. The patch disables:
     - the shell: `tool-bash`, `tool-pwsh`, `pwsh-sandbox`, `tool-jobs`, `jobs`. `bash-sandbox` stays enabled, because it provides the `shell` service that `permission` (`dsh-permission-presets`) waits for. Disabling it left that entry pending ("1 entry did not activate"; spike r1). Disabling `tool-bash` alone already removes the shell tool (spike r2);
     - delegation: `tool-subagent`, `tool-subagent-fork`, `tool-subagent-control`, `tool-subagent-list-agents`, `tool-workflow`, `workflow-ptc`, `ptc-runtime`;
     - the network: `tool-web`, `web`, `web-search-deepseek`, `web-fetch-http`, `mcp-resources`;
     - customisation: `tool-skill`, `skill`, `skill-filesystem`, `agent-instructions`. Disabling `agent-instructions` matches Claude's `--safe-mode`: repository text reaches the reviewer only as evidence it chooses to read;
     - planning and interaction: `tool-todo`, `tool-goal`, `goal`, `goal-round-driver`, `command-goal`, `plan-mode` (DSR-01: its prompt section steers the model to `exit_plan_mode` instead of a final reply) and `user-questions` (DSR-01);
     - background model calls and telemetry: `session-title-llm`, `session-title` (DSR-07), `otel`, `session-telemetry-otel` (DSR-08).
     - Spike r2–r4 verified this list. With it, the model sees exactly `read`, `glob`, `grep`, `write`, `edit` and `read_image`.
     - **Fail closed on a bad patch.** An unknown id does not stop dsh: it prints `dsh: [PATCH] patch: entry "ID" not found` on stderr and runs anyway (spike). `dsh: warning: N entry did not activate` is also only a warning. The runner therefore fails the run (`provider_failure`, not fallback-eligible) when stderr contains `patch: entry` or `did not activate`.
   - **(c) Post-run audit, in the `review_audit` hook.** In PR #2 the hook already runs in `finally` after `execute`, on every exit path, before the exit code is checked and before `classify_failure`.
     - A violation sets `status=failed`, `failure_kind=confinement_violation` and `fallback_eligible=false`.
     - `run()`'s `except` path keeps that classification and does not call `classify_failure`, so a violation can never surface as `provider_unavailable` (DSR-03).
     - The run fails if any of the following holds:
       - a `tool_call` names a tool outside `{"read", "glob", "grep"}`. `edit`, `write` and `read_image` stay registered, because `tool-fs` cannot be split, but any call to them fails the run;
       - a path argument resolves outside the repository and is not the resolved plan path. Relative paths resolve against the repository. Key map from spike s9 (DSR-06): `read.file_path`; `glob.path` (optional) and `glob.pattern`; `grep.path` (optional) only, never `grep.pattern`. An argument outside the map fails closed;
       - any call carries `sandbox_permissions` (an escalation request; seen on `write`/`edit` in spike r1);
       - any `tool_call` event is marked `truncated`, or a `tool_call` lacks `input` or has a malformed audit-critical field (DSH-04). A `tool_result` must keep an intact `callId` that matches a call, and an intact `status`. Truncation of its result body is allowed (DSH-08): the confinement checks use only the call's input, and an ordinary read of a file larger than 8 KiB produces a truncated result. dsh's JSON stream caps tool-call strings at 8 KiB and events at 32 KiB, and can drop `input` entirely, so the audit could otherwise see only a harmless prefix of a path that dsh later normalizes. Such evidence is unauditable and fails the run, never fallback-eligible;
       - the working-tree fingerprint differs before and after the run (DSH-02). The fingerprint is the existing `snapshot(repo, "HEAD")`, which hashes the contents of every changed and untracked file, plus the `HEAD` commit id and a digest of `git ls-files -s` for the index. Porcelain status alone is not enough: a file that is already modified, or already untracked, can change again without changing its status line. A DeepSeek review therefore requires a git repository and refuses `--skip-git-repo-check`-style greenfield runs.
     - The result records `tool_calls_audited`, `disallowed_tool_calls` and `read_confinement_violations`.
     - Detecting a violation afterwards cannot undo the disclosure to the provider. runtime.md says so, as it already does for panel workers.
     - **The audit is the only read guard.** Spike s3: the `read-only` sandbox does not confine reads; a `read` of an absolute path outside the cwd succeeded. In spike r4 the reviewer, unprompted, globbed the repository's parent directory (where the plan file lived) and read 9 files there. To lower that rate, the dsh `review_prompt` adds: "Your repository root is REPO. Read only files inside it; the plan text is already included below."

4. **Structured output by prompt, validated locally.**
   - dsh has no output-schema flag. The dsh `review_prompt` appends the `REVIEW_SCHEMA` JSON and requires exactly one JSON object as the final reply.
   - `review_parse` reads the `final` event text and strips one surrounding Markdown code fence if present. It then runs `json.loads` and `validate_review`.
   - Malformed output is an ordinary `provider_failure`, not fallback-eligible. A failed run cannot be resumed (`previous_record` requires `status=completed`), so the host retries with a **fresh** DeepSeek run, not a resume (DSH-06). That attempt counts as a round. In a resumed loop, the fresh run carries the previous host dispositions as `--feedback`.

5. **Event parsing (`_dsh_review_parse`).** A run succeeds only if all of the following hold:
   - the exit code is 0;
   - there is exactly one `session` event, and its id matches `^session-` followed by a UUID;
   - there is exactly one `final` event, and it is non-empty;
   - there is no `error` event and no `turn_end` error.
   - Usage is the sum of the `step_end.usage` input and output tokens, or `null` when any `step_end` lacks it. `observed_models` is `[]`.
   - The session-id check in `parse_result` and `previous_record` becomes the helper `valid_session(provider, value)`.

6. **Resume.** `--resume` passes `--session-id ID`, with cwd set to the repository. `previous_record` already binds the repository, plan and provider.

7. **Prompt delivery (`review_command`).**
   - Fresh run: argv is `dsh --profile headless --patch RUN_DIR/dsh-patch.yml --json -`, with the prompt on stdin through `execute`.
   - Resume adds `--session-id ID` before `-`.

8. **Model and effort.**
   - `--model X` adds a patch entry `agent-default-model` with config `{provider: deepseek-official, model: X}`. Both keys are needed, because a patch replaces the entry's whole config.
   - Without `--model`, the dsh default is used and reported as an unresolved CLI default. Today that default is `deepseek-flash` (DeepSeek-V4.1-Flash), the user's chosen reviewer model.
   - The skill maps `deepseek_model` to `--model`, and only for DeepSeek runs (Decision 1). In the skill text only, it accepts these display names as aliases: `DeepSeek-V4.1-Flash` / `DeepSeek-V41-Flash` → `deepseek-flash`, and `DeepSeek-V4-Pro` → `deepseek-v4-pro`. The runner passes ids through unchanged.
   - The runner records `requested_model` as given. dsh headless prints no model, so `observed_models` stays `[]`.
   - `--effort` is refused for DeepSeek, because there is no verified mapping.
   - Spike s6: both ids work through the patch (the model names itself `deepseek-v4-pro` / `deepseek-flash`). An unknown id fails with "The supported API model names are deepseek-flash, deepseek-v4-pro".

9. **Failure classification.**
   - `provider_failure_diagnostic` gets a dsh branch. It reads stderr plus the `error` and `turn_end` error events, which are provider-owned. It never reads `text`, `thinking` or `final`, which are model-authored.
   - `UNAVAILABLE_MARKERS` gains `"dsh: auth"`, `"missing_credential"` (spike s5) and `"insufficient balance"` (DeepSeek's HTTP 402). Existing markers such as `"rate limit"` and `"service unavailable"` already apply.
   - A bad model id gives a `turn_end` error `INVALID_REQUEST` with status 400 and exit 1 (spike s6). It stays `provider_failure`, as a 400 does for Claude.
   - When a dsh run exits 0 but carries an `error` event or a `turn_end` error, `review_parse` raises "DeepSeek reported a failed turn; …". That phrase contains `classify_failure`'s existing operational marker `reported a failed turn`, so the provider diagnostics are always read for it (DSR-05).

10. **No degraded fallback, in either direction.**
    - `run()` refuses `--fallback-from` when the launched provider is `deepseek`, as PR #2 does for agy.
    - `validate_fallback` refuses a source whose provider is `deepseek`, with a mode-specific message (DSR-04):
      - for `review`: "rerun with the default reviewer instead";
      - for `inspect`: "rerun with the default inspector instead".
    - On `provider_unavailable`, the skill automatically restarts without `--provider deepseek`. That is a fresh cross-provider run with the standard roles; for `inspect` it keeps the same `--base`. The DeepSeek failure is logged.
    - The replacement invocation is rebuilt from the replacement provider's own settings (DSH-09):
      - `--model`, `--effort` and `--cli` come from `reviewer_model`/`inspector_model`, `*_effort` and `codex_cli`/`claude_cli`, or the CLI defaults;
      - `deepseek_model` and `dsh_cli` are dropped;
      - the log records the replacement's requested model and executable.
    - From then on, the existing fallback chain applies unchanged.

11. **Version gate.**
    - `VALIDATED_DSH_CLI = ("0.2.0-rc.2",)` is set after the live canary passes.
    - The preflight follows agy's pattern. Other versions are refused unless `--allow-unvalidated-cli` is passed, and that choice is recorded in the result.
    - dsh is a release candidate, and its CLI changed between rc builds.

12. **Windows: refused for now (DSH-07).**
    - dsh's base profile replaces `bash-sandbox` with `pwsh-sandbox` on Windows. The Decision 3(b) list disables `pwsh-sandbox`, so on Windows `permission` would lose its `shell` provider and fail to activate.
    - Rather than ship an unvalidated platform-specific patch, `run()` refuses `--provider deepseek` when `os.name == "nt"`, with "DeepSeek review is not validated on Windows".
    - Windows CI still runs every fake-`dsh` test that does not launch dsh. The refusal itself is tested on every platform by patching `os.name`.
    - Supporting Windows later needs a platform-aware patch (keep `pwsh-sandbox`, disable `tool-pwsh`) and a live Windows canary.

## Remaining risks

- **The CLI may change.** The rc CLI can change its event schema or plugin ids. Mitigations: the version gate, and the stderr check that fails the run on a bad patch.
- **JSON compliance.** It is weaker than schema-enforced output. A malformed reply costs a round.
- **Review quality.** It is unknown, because `deepseek-flash` is the default. The live validation compares one DeepSeek review with a Codex review of the same plan.
- **Disclosure.** Reads outside the repository are detected, not prevented (spike s3).
- **Windows.** It is unsupported until a platform-aware patch and a live canary exist.
- **Merge timing.** PR #2 may still change the adapter hook signatures before it merges. Re-read them when branching.

## Verification

### Automated (fake `dsh`, no quota)

- [x] `python scripts/validate.py` passes.
- [x] `python -m unittest discover -s tests -v`: every existing test passes unmodified, and every new test below passes.
- [x] A successful review returns `provider: deepseek`, `assurance: cross_provider` and a valid response.
- [x] A successful inspection records `roles.inspector: deepseek` and keeps the snapshot checks.
- [x] Resume with a matching session id succeeds and passes `--session-id` before `-`.
- [x] Resume where dsh returns a different session id is refused.
- [x] A malformed `final` fails as `provider_failure`, not fallback-eligible.
- [x] A `final` wrapped in a JSON code fence parses.
- [x] A non-allowlisted tool call gives `confinement_violation`.
- [x] An outside-repo read gives `confinement_violation`.
- [x] A working-tree change during a review gives `confinement_violation`.
- [x] A content change to a file that was already modified before the review gives `confinement_violation`.
- [x] A content change to a file that was already untracked before the review gives `confinement_violation`.
- [x] An index-only change (`git add`) during a review gives `confinement_violation`.
- [x] A `tool_call` marked `truncated` gives `confinement_violation`.
- [x] A `tool_call` without `input` gives `confinement_violation`.
- [x] A confinement violation on a run that also exits non-zero, times out or carries `dsh: AUTH:` still gives `confinement_violation`, never `provider_unavailable`. — non-zero exit + `dsh: AUTH:` and timeout cases tested
- [x] `dsh: AUTH:` on stderr gives `provider_unavailable`.
- [x] Auth-like text inside `final` does not give `provider_unavailable`.
- [x] stderr with `patch: entry` or `did not activate` fails the run.
- [x] `--fallback-from` with a DeepSeek source is refused with the mode-specific message.
- [x] `--fallback-from` while launching DeepSeek is refused.
- [x] `--effort` with DeepSeek is refused.
- [x] DeepSeek with `build` or `panel` is refused.
- [x] DeepSeek with `os.name == "nt"` is refused. — implemented as `sys.platform == "win32"` (patching `os.name` breaks pathlib)
- [x] A DeepSeek review in a non-git directory is refused.
- [x] Same-provider inspection fallback (`--provider BUILDER --fallback-from ...`) still passes the existing test unchanged.
- [x] Resume with a changed `--host` or `--builder` is refused.
- [x] `check` and `build` refuse an approval whose `roles.host` differs from the current host. — `check_approval(..., host)` used by both `check` and `build`
- [x] agy review still runs with `agy_env(profile)` through its `review_env` hook (the existing agy tests pass unmodified).
- [x] A malformed DeepSeek result cannot be used with `--resume`.
- [x] A successful review whose allowed `read` returns a `tool_result` body over 8 KiB (marked `truncated`) is accepted.
- [x] A `tool_result` with a missing or unmatched `callId` gives `confinement_violation`.
- [x] An unvalidated dsh version is refused without `--allow-unvalidated-cli` and recorded with it.
- [x] The `dsh-patch.yml` contents equal the Decision 3(b) list, plus `agent-default-model` when `--model` is given.
- [x] The child env contains `DSH_PERMISSION_MODE=read-only`, `DSH_TOOLS_MODE=native` and `DSH_TELEMETRY_MODE=DISABLED`.
- [x] Claude and Codex runs still get `env=None` from their `review_env` hooks.
- [x] A reviewer equal to the host is refused.
- [x] An inspector equal to the builder is refused.
- [x] `roles` output shows `deepseek` when requested.

- [x] Skill walk-through (manual, no quota): with `deepseek_model=deepseek-flash` and `dsh_cli` set, a recorded `provider_unavailable` result produces a replacement command without the DeepSeek model or executable. — verified by reading the SKILL.md DeepSeek paragraph; no runner change involved

### Live, manual (disposable repository, separately authorized)

- [ ] `runner.py review --host claude --provider deepseek` on a small seeded-defect plan returns a valid result that finds the seeded defect. — BLOCKED: no DeepSeek API key yet
- [ ] `runner.py inspect --host claude --provider deepseek --base X` on a small diff returns a valid result. — BLOCKED: no DeepSeek API key yet
- [ ] Both runs are recorded in `VALIDATION.md` with the CLI version, model and usage. — BLOCKED: no DeepSeek API key yet

## Spike results (2026-10-14, dsh 0.2.0-rc.2)

Disposable repo `/private/tmp/claude-501/-Users-yanghu-Documents-AI-Workspace-prototypes-agentic-os/c3556399-efee-4cfb-8b33-41a356cb4134/scratchpad/dsr-spike/repo`; runner `/private/tmp/claude-501/-Users-yanghu-Documents-AI-Workspace-prototypes-agentic-os/c3556399-efee-4cfb-8b33-41a356cb4134/scratchpad/dsr-spike/run.py` (read-only, `DSH_TOOLS_MODE=native`, `DSH_TELEMETRY_MODE=DISABLED`, task on stdin, `--json`). Roughly 76k tokens in total, including cache reads.

| Item | Result |
|---|---|
| s1 | With the patch, the tools are exactly `read`, `glob`, `grep`, `write`, `edit`, `read_image`. The model reports no shell and no web tool. An unknown patch id only warns on stderr; Decision 3(b) fails closed on it. |
| s2 | `write` and `edit` are denied: "file access denied under read-only mode". Retries with `sandbox_permissions: workspace-write` are denied: "requires approval, but no approval channel is available". `git status` is clean. |
| s3 | **A read outside the cwd is allowed** (`outside.txt` was read). The audit is the only guard (Decision 3(c)). |
| s4 | A `-` stdin task works with `--json`, both fresh (r1) and with `--session-id` (r2: same session id, recalled PELICAN-42). |
| s5 | **No.** `~/.dsh/.credentials.yaml` has no DeepSeek key, so the run fails with `MISSING_CREDENTIAL`. The key must come from `dsh web` or `DEEPSEEK_API_KEY` (Verified facts). |
| s6 | `deepseek-v4-pro` and `deepseek-flash` both work through an `agent-default-model` patch. A bogus id gives exit 1 with `INVALID_REQUEST` 400. |
| s7 | `DSH_TELEMETRY_MODE=DISABLED` is accepted, with no error. |
| s8 | A full review prompt on a seeded-bug plan returned unfenced JSON that passes `validate_review`. Verdict REVISE, with a high finding on the seeded `a - b` bug. It made 14 tool calls, 9 of them outside the repo (see s3). |
| s9 | Argument names: `read {file_path}`, `glob {pattern, path?}`, `grep {pattern, path?}`. Escalation adds `sandbox_permissions` and `justification`. |
| s10 | It boots with every listed entry disabled except `bash-sandbox`. Disabling that one leaves `permission` pending, so it is kept enabled. |

## Progress Checklist

### Planning and spike (done)

- [x] Pre-review by Gemini 3.8 Flash High via agy, outside the runner (Codex usage was exhausted). APPROVED in round 3 on an earlier revision (sha `2cb4a6e7…`). Advisory only; see the review log.
- [x] Spike in a disposable git repo, dsh 0.2.0-rc.2, small budget. Results are in "Spike results".
  - [x] (s1) The patch boots, and each disabled tool is absent. An unknown patch id only warns, so Decision 3(b) fails closed on it.
  - [x] (s2) Under `read-only`, `write` and `edit` are denied and the tree is unchanged.
  - [x] (s3) A `read` outside the cwd is allowed, so the Decision 3(c) audit is the only read guard.
  - [x] (s4) The `-` stdin task works with `--json`, both fresh and with `--session-id`.
  - [x] (s5) Without `DEEPSEEK_API_KEY`, `~/.dsh/.credentials.yaml` did not authenticate (`MISSING_CREDENTIAL`).
  - [x] (s6) The `agent-default-model` override works for `deepseek-flash` and `deepseek-v4-pro`. A bogus id gives `INVALID_REQUEST` 400.
  - [x] (s7) `DSH_TELEMETRY_MODE=DISABLED` is accepted.
  - [x] (s8) A full review prompt returns JSON in `final` that passes `validate_review`.
  - [x] (s9) Recorded the `tool_call.input` argument names for `read`, `glob` and `grep`.
  - [x] (s10) The profile boots with `plan-mode`, `user-questions`, `session-title*` and `otel*` disabled.
- [x] Finalize the Decision 3(b) disable list and the Decision 8 model guidance from the spike.
- [x] Revise the plan onto PR #2's adapter table, with every item as a checkbox (2026-10-14).
- [x] Codex plan review (claudex-loop `review`) APPROVED in round 3 on sha `4873a3b4…`. Only this checkbox changed after approval; see the review log.

### Prerequisite

- [x] PR #2 (`feat/agy-provider`): live agy runs recorded and the PR merged to `main`. — merged 2026-10-14 (`bab2add`); agy `retrieved` item N/A by user decision
- [x] Create a branch `feat/deepseek-reviewer` from the updated `main`, and re-read the adapter hook signatures.

### Roles

- [x] `REVIEWERS` and `INSPECTORS` include `deepseek`; `HOSTS`, `BUILDERS` and `PANEL_WORKERS` are unchanged.
- [x] `resolve_roles(..., inspector=None)` refuses an inspector equal to the builder.
- [x] `run()` passes `--provider` as the inspector only when it is `deepseek`, and refuses `deepseek` for `build`, `panel` and Windows.
- [x] `previous_record` refuses a role mismatch.
- [x] `check_approval` binds `roles.host`/`roles.planner`, and requires the reviewer to differ from the host.
- [x] `valid_session(provider, value)` is used by `parse_result` and `previous_record`.

### Adapter entry

- [x] `dsh-patch.yml` writer: the Decision 3(b) list, plus `agent-default-model` for `--model`.
- [x] `review_command`: fresh argv, and resume argv with `--session-id`.
- [x] `review_env(ctx)` hook on every adapter: `None` for Claude and Codex, `agy_env(profile)` moved into agy's hook.
- [x] dsh `review_env` with the three `DSH_*` variables.
- [x] dsh `review_prompt`: repository-root sentence, plus the appended `REVIEW_SCHEMA`.
- [x] `cli_prefix` entry for `dsh` (POSIX only).
- [x] `VALIDATED_DSH_CLI` and the version preflight, with `--allow-unvalidated-cli` recorded.
- [x] `--effort` refused for `deepseek`.

### Parsing and audit

- [x] `_dsh_review_parse`: event checks, fence strip, `validate_review`, usage sum.
- [x] Fail the run on stderr containing `patch: entry` or `did not activate`.
- [x] `_dsh_review_audit`: tool allowlist, path key map, `sandbox_permissions`; records the three audit fields.
- [x] `_dsh_review_audit`: rejects truncated `tool_call` events and missing or malformed `input`; allows result-body truncation when `callId` and `status` are intact.
- [x] Working-tree fingerprint (`snapshot(repo, "HEAD")` + `HEAD` id + `git ls-files -s` digest) before and after the run.
- [x] `run()`'s `except` path keeps `confinement_violation` and skips `classify_failure`.

### Failure handling

- [x] dsh branch in `provider_failure_diagnostic` (stderr, `error` and `turn_end` only).
- [x] `UNAVAILABLE_MARKERS` gains `dsh: auth`, `missing_credential` and `insufficient balance`.
- [x] `--fallback-from` is refused when launching DeepSeek, and `validate_fallback` refuses a DeepSeek source with the mode-specific message.

### Tests

- [x] Fake-`dsh` tests for every Automated item under Verification.
- [x] Full suite and `validate.py` green locally. — 107 tests OK (1 skipped), validate OK, `git diff --check` clean; six safety checks mutation-tested
- [x] CI green on Linux, macOS and Windows. — CI run 38672220186 (`0e456d3`), Linux/macOS/Windows green

### Documentation

- [x] `SKILL.md`: roles note, plus the `reviewer`, `inspector`, `deepseek_model` and `dsh_cli` tunables.
- [x] `SKILL.md`: the unavailable-restart rebuilds `--model`/`--effort`/`--cli` from the replacement provider's settings.
- [x] `SKILL.md`: data-egress opt-in gate.
- [x] `SKILL.md`: the "unavailable → rerun with the default role" rule, and "malformed → fresh retry, not resume".
- [x] `references/runtime.md`: DeepSeek commands.
- [x] `references/runtime.md`: a Review boundaries bullet, plus the limitation that detection comes after disclosure.
- [x] `AGENTS.md`: a fallback-invariant line for DeepSeek.
- [x] `README.md`: an example.
- [x] Bump the manifests to the next minor version after PR #2 (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`).

### Live validation and handoff

- [ ] Live DeepSeek review recorded in `VALIDATION.md`. — BLOCKED: no DeepSeek API key yet
- [ ] Live DeepSeek inspection recorded in `VALIDATION.md`. — BLOCKED: no DeepSeek API key yet
- [ ] `VALIDATED_DSH_CLI` set to the version that passed. — BLOCKED: waits for the live canary
- [ ] Fresh Codex inspection of the final diff, with findings resolved. — BLOCKED: Codex quota exhausted (user, 2026-10-14); inspect when it returns
- [ ] Commit and PR, per the user's authorization.
- [ ] Archive the plan and log to `docs/exec-plans/completed/`.
