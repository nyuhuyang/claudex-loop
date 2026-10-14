---
status: in-progress
created: 2026-10-14
---

# Plan: DeepSeek (dsh) as an opt-in plan reviewer and code inspector

_Drafted by Claude for Yang Hu, 2026-10-14. Reviewed by Gemini (2 rounds, APPROVED). This plan does not authorize implementation._

## Goal

Let a Claude- or Codex-hosted Claudex Loop use DeepSeek, through the official DeepSeek Harness CLI (`dsh`), as the plan reviewer (`review`) or final code inspector (`inspect`). The reviewer must be as locked down as the existing Claude and Codex reviewers, and its result must use the same structured-review contract. The default roles do not change. DeepSeek is used only when the user asks for it.

### Acceptance criteria

1. `runner.py review --host claude --reviewer deepseek ...` and `--host codex --reviewer deepseek` each run one dsh turn. The result is `result.json` with `provider: deepseek`, `assurance: cross_provider` and a `validate_review`-valid response.
2. `runner.py inspect --host claude --inspector deepseek --base X ...` does the same for inspection, with the existing snapshot checks.
3. `--resume PREVIOUS_RESULT` continues the same dsh session. A different returned session id is refused.
4. Any dsh tool call outside the allowlist `read`, `glob`, `grep` fails the run. So does any read path outside the repository (other than the plan file), and any change to the working tree during a review. No verdict is accepted from such a run.
5. An authentication, balance, rate-limit or service failure is recorded as `failure_kind=provider_unavailable`. The skill then reruns with the default role: the default reviewer for `review`, the default (non-builder) inspector for `inspect`. There is no degraded same-provider fallback while a cross-provider reviewer is available.
6. Without `--reviewer deepseek` / `--inspector deepseek`, behaviour and the existing tests are byte-for-byte unchanged.
7. `python scripts/validate.py` and `python -m unittest discover -s tests -v` pass on Linux, macOS and Windows CI. One live DeepSeek review and one live inspection are recorded in `VALIDATION.md`.

## Non-goals

- DeepSeek as host, planner or builder.
- DeepSeek panel workers (`panel` mode).
- Running two reviewers in parallel (Codex and DeepSeek) and merging their verdicts. The user can run them one after the other by hand.
- Calling the DeepSeek HTTP API directly. The runner keeps driving vendor CLIs only.
- Confidential or client repositories. See Decision 2.

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

1. **DeepSeek is a third, opt-in reviewer, not a third host.**
   - `PROVIDERS` stays `("claude", "codex")` for `--host` and `--builder`. Add `REVIEWERS = PROVIDERS + ("deepseek",)`.
   - New flags: `--reviewer {claude,codex,deepseek}` and `--inspector {...}`.
   - `resolve_roles(host, reviewer, builder, inspector)` keeps its current defaults. The reviewer may be `deepseek` or the non-host provider, never the host. The inspector may be `deepseek` or the non-builder provider, never the builder.
   - `roles` mode prints the result. `--provider` keeps its current meaning, the provider actually launched; with a DeepSeek role it must equal that role unless a fallback is recorded. Its argparse `choices` widen from `PROVIDERS` to `REVIEWERS` (DSR-09); `--host`/`--builder` keep `PROVIDERS`.
   - Roles are stored in `result.json` as today, so `--resume`, `check` and fallback validation reject a role change mid-loop.
   - Assurance is `cross_provider`, because DeepSeek is neither the host nor the builder.
   - Skill tunables: `reviewer=default|deepseek` and `inspector=default|deepseek`, echoed with the other roles before starting.

2. **Data-egress gate (skill level, mandatory).**
   - A DeepSeek review sends the plan, plus every file the reviewer reads, to the DeepSeek API.
   - Before the first DeepSeek run in a loop, the skill states this in one line and requires the user's explicit opt-in for that repository. A DeepSeek role is never chosen automatically, including as a fallback.
   - Confidential or client repositories are out of scope, consistent with the agentic-os rule that rejects dsh for confidential projects.
   - The runner sets `DSH_TELEMETRY_MODE=DISABLED` in the child environment, and the patch also disables the `otel` and `session-telemetry-otel` plugins (DSR-08).
   - The runner cannot detect confidentiality; this stays a host responsibility, documented in SKILL.md and runtime.md.

3. **Read-only lockdown, three layers, fail closed.**
   - **(a) Sandbox.** The child env sets `DSH_PERMISSION_MODE=read-only` and `DSH_TOOLS_MODE=native`. Writes are denied, and headless `ask` auto-denies escalation.
     - `execute()` currently calls `Popen` without `env`, so it gains an optional `env: dict | None = None` parameter, passed through to `Popen`. `run()` builds `{**os.environ, DSH_PERMISSION_MODE, DSH_TOOLS_MODE, DSH_TELEMETRY_MODE}` for dsh only. Existing providers pass `None`, so their behaviour is unchanged (DSR-02).
   - **(b) Tool removal.** The runner writes `dsh-patch.yml` into the run directory and passes `--patch`. The patch disables:
     - the shell: `tool-bash`, `tool-pwsh`, `pwsh-sandbox`, `tool-jobs`, `jobs`. `bash-sandbox` stays enabled: it provides the `shell` service that `permission` (`dsh-permission-presets`) waits for. Disabling it left that entry pending ("1 entry did not activate"; spike r1), while `tool-bash` disabled alone already removes the shell tool (spike r2);
     - delegation: `tool-subagent`, `tool-subagent-fork`, `tool-subagent-control`, `tool-subagent-list-agents`, `tool-workflow`, `workflow-ptc`, `ptc-runtime`;
     - the network: `tool-web`, `web`, `web-search-deepseek`, `web-fetch-http`, `mcp-resources`;
     - customisation: `tool-skill`, `skill`, `skill-filesystem`, `agent-instructions`;
     - planning and interaction: `tool-todo`, `tool-goal`, `goal`, `goal-round-driver`, `command-goal`, `plan-mode` (its prompt section steers the model to `exit_plan_mode` instead of a final reply; DSR-01), `user-questions` (DSR-01);
     - background model calls and telemetry: `session-title-llm`, `session-title` (DSR-07), `otel`, `session-telemetry-otel` (DSR-08).
     - Disabling `agent-instructions` matches Claude's `--safe-mode`: repository text reaches the reviewer only as evidence it chooses to read.
     - Final list, verified by spike r2–r4: the entries above. The model then sees exactly `read`, `glob`, `grep`, `write`, `edit` and `read_image`.
     - **Fail closed on a bad patch.** An unknown id does not stop dsh: it prints `dsh: [PATCH] patch: entry "ID" not found` on stderr and runs anyway (spike). A `dsh: warning: N entry did not activate` also only warns. The runner therefore fails the run (`provider_failure`, ineligible) when stderr contains `patch: entry` or `did not activate`.
   - **(c) Post-run audit.** The audit runs unconditionally, on every exit path — non-zero exit, timeout, interruption, malformed output — and before `classify_failure`, as `run_panel_worker` already does for panel workers (DSR-03). A violation sets `status=failed`, `failure_kind=confinement_violation` and `fallback_eligible=false`, overriding any other classification, so a violation can never surface as `provider_unavailable`. The runner parses every `tool_call` event it captured and fails the run if any of these holds:
     - the tool is not in `{"read", "glob", "grep"}` (`edit`, `write` and `read_image` stay registered because `tool-fs` cannot be split, but any call to them fails the run);
     - a path argument resolves outside the repository and is not the resolved plan path. Relative paths resolve against the repository. Key map from spike s9 (DSR-06): `read.file_path`; `glob.path` (optional) and `glob.pattern`; `grep.path` (optional) only, never `grep.pattern`. An argument outside the map fails closed;
     - any call carries `sandbox_permissions` (an escalation request; seen on `write`/`edit` in spike r1);
     - `git status --porcelain --untracked-files=all` differs before and after a review.
     - The result records `tool_calls_audited`, `disallowed_tool_calls` and `read_confinement_violations`.
     - Detection after the fact cannot undo disclosure to the provider. Runtime.md says so, as it already does for panel workers.
     - **The audit is the only read guard.** Spike s3: the `read-only` sandbox does not confine reads; `read` of an absolute path outside the cwd succeeded. In spike r4 the reviewer, unprompted, globbed the parent of the repository (where the plan file lived) and read 9 files there. To lower that rate, the dsh prompt adds: "Your repository root is REPO. Read only files inside it; the plan text is already included below." The plan body is in the prompt, so the plan path need not be read.

4. **Structured output by prompt, validated locally.**
   - dsh has no output-schema flag. The prompt appends the `REVIEW_SCHEMA` JSON and requires exactly one JSON object as the final reply.
   - The runner reads the `final` event text, strips one surrounding Markdown code fence if present, then runs `json.loads` and `validate_review`.
   - Malformed output is an ordinary failure (`provider_failure`), not eligible for fallback. The host may resume once with feedback asking for valid JSON, and that attempt counts as a round.

5. **Event parsing (`parse_result` dsh branch).** A run succeeds only if all of these hold:
   - exit 0;
   - exactly one `session` event, whose id matches `^session-` followed by a UUID;
   - exactly one non-empty `final`;
   - no `error` event and no `turn_end` error.
   - Usage is the sum of `step_end.usage` input and output tokens, or `null` when any `step_end` lacks it. `observed_models` is `[]`.
   - The UUID check in `parse_result` and `previous_record` becomes a helper `valid_session(provider, value)`.

6. **Resume.** `--resume` passes `--session-id ID` with cwd set to the repository. `previous_record` already binds the repository and plan.

7. **Prompt delivery.**
   - Fresh run: argv is `dsh --profile headless --patch RUN_DIR/dsh-patch.yml --json -`, with the prompt on stdin through the existing `execute`.
   - Resume adds `--session-id ID` before `-`.

8. **Model and effort.**
   - `--model X` adds a patch entry `agent-default-model` with config `{provider: deepseek-official, model: X}`. Both keys are needed, because a patch replaces the entry's whole config.
   - Without `--model` the dsh default is used and reported as an unresolved CLI default. Today that default is `deepseek-flash` (DeepSeek-V4.1-Flash), the user's chosen reviewer model.
   - The skill maps `reviewer_model` / `inspector_model` to `--model`. It also accepts the display names `DeepSeek-V4.1-Flash` / `DeepSeek-V41-Flash` → `deepseek-flash` and `DeepSeek-V4-Pro` → `deepseek-v4-pro` as aliases in the skill text only; the runner passes ids through unchanged.
   - The runner records `requested_model` as given. dsh headless prints no model, so `observed_models` stays `[]`.
   - `--effort` is refused for DeepSeek: there is no verified mapping.
   - Spike s6: both ids work through the patch (the model names itself `deepseek-v4-pro` / `deepseek-flash`). An unknown id fails with "The supported API model names are deepseek-flash, deepseek-v4-pro".

9. **Failure classification.**
   - `provider_failure_diagnostic` gets a dsh branch. It reads stderr plus `error` and `turn_end` error events, which are provider-owned. It never reads `text`, `thinking` or `final`, which are model-authored.
   - `UNAVAILABLE_MARKERS` gains `"dsh: auth"`, `"missing_credential"` (spike s5) and `"insufficient balance"` (DeepSeek's HTTP 402). Existing markers such as `"rate limit"` and `"service unavailable"` already apply. A bad model id gives `turn_end` error `INVALID_REQUEST` status 400 and exit 1 (spike s6); it stays `provider_failure`, as 400 does for Claude.
   - When a dsh run exits 0 but carries an `error` event or a `turn_end` error, `parse_result` raises "DeepSeek reported a failed turn; …". That phrase contains `classify_failure`'s existing operational marker `reported a failed turn`, so provider diagnostics are always read for it (DSR-05).

10. **No degraded fallback from DeepSeek.**
    - `validate_fallback` refuses a source whose provider is `deepseek`, with a mode-specific message: "rerun with the default reviewer instead" for `review`, "rerun with the default inspector instead" for `inspect` (DSR-04).
    - On `provider_unavailable`, the skill automatically restarts without the DeepSeek role: `review` without `--reviewer deepseek`, `inspect` without `--inspector deepseek` (a fresh inspection by the non-builder provider, with the same `--base`). Both are fresh cross-provider runs with the standard roles. The DeepSeek failure is logged.
    - From then on the existing fallback chain applies unchanged. This adds no new runner fallback path.

11. **Version gate.**
    - `VALIDATED_DSH_CLI = ("0.2.0-rc.2",)` is set after the live canary passes.
    - Other versions are refused unless `--allow-unvalidated-cli` is passed; that choice is recorded in the result.
    - dsh is a release candidate whose CLI changed between rc builds.

12. **Windows.**
    - `cli_prefix` resolves `dsh`. For a Windows npm shim it launches the package's `bin` entry from `@deepseek-ai/dsh/package.json` through `node`, if it is present, and refuses otherwise, as it does for Claude and Codex.
    - There is no live Windows run; that is recorded as a limitation.

## Remaining risks

- **The CLI may change.** The rc CLI can change its event schema or plugin ids. Mitigations: the version gate, plus `dsh-patch.yml` failing to boot loudly rather than silently re-enabling a tool. The spike checks that an unknown id is an error.
- **JSON compliance.** It is weaker than schema-enforced output. Malformed replies cost a round.
- **Review quality.** It is unknown, because `deepseek-flash` is the default. The live validation compares one DeepSeek review against a Codex review of the same plan.
- **Disclosure.** Reads outside the repository are detected, not prevented, unless the spike shows the read-only sandbox already confines reads.

## Verification

- `python scripts/validate.py`: passes.
- `python -m unittest discover -s tests -v`: all existing and new tests pass. A fake `dsh` covers:
  - a successful review and a successful inspection;
  - resume with a matching session id, and a mismatched session id refused;
  - a malformed `final`, and a fenced JSON `final`;
  - a non-allowlisted tool call, an outside-repo read, and a working-tree change during review;
  - `dsh: AUTH:` on stderr, which must give `provider_unavailable`, and auth-like text inside `final`, which must not;
  - `--fallback-from` with a DeepSeek source, refused;
  - `--effort`, refused;
  - an unvalidated version, refused unless overridden;
  - the patch file contents and child env (`DSH_PERMISSION_MODE`, `DSH_TELEMETRY_MODE`, `DSH_TOOLS_MODE`);
  - role validation: reviewer equal to host is refused, inspector equal to builder is refused, and `roles` output.
- **Live, manual.** In a disposable repository:
  - `runner.py review --host claude --reviewer deepseek` on a small seeded-defect plan returns a valid result;
  - `inspect --inspector deepseek` on a small diff does the same;
  - both are recorded in `VALIDATION.md` with the CLI version, model and usage.

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

- [x] Plan reviewed: Gemini 3.8 Flash High (via agy, outside the runner; Codex usage exhausted). APPROVED in round 2 on sha `36dd9bbb…`; see the review log. Only this checkbox changed after approval.
- [x] Spike, in a disposable git repo, dsh 0.2.0-rc.2, small budget. Record the answers in this plan: See Spike results.
  - (s1) The patch boots. Each disabled tool is absent: asking the model to run a shell command or a web search yields an unknown-tool error or no call. An unknown patch id fails startup.
  - (s2) Under `read-only`, `write` and `edit` calls are denied and the tree is unchanged.
  - (s3) Is a `read` of a file outside the cwd allowed or denied? This decides whether Decision 3(c) is the only guard.
  - (s4) The `-` stdin task works with `--json`, both fresh and with `--session-id`.
  - (s5) A run with `DEEPSEEK_API_KEY` unset authenticates from `~/.dsh/.credentials.yaml`.
  - (s6) The `agent-default-model` patch override takes effect with `deepseek-flash` and with `deepseek-v4-pro`. A bogus id fails cleanly; record how.
  - (s7) `DSH_TELEMETRY_MODE=DISABLED` is accepted.
  - (s8) A full review prompt returns parseable JSON in `final`.
  - (s9) Record the `tool_call.input` argument names for `read`, `glob` and `grep` (Decision 3(c) key map).
  - (s10) The profile still boots with `plan-mode`, `user-questions`, `session-title*` and `otel*` disabled.
- [x] Finalize the Decision 3(b) disable list and the Decision 8 model guidance from the spike.
- [ ] `resolve_roles`, `--reviewer`, `--inspector` and `REVIEWERS`; role validation in `run()`; `valid_session` helper.
- [ ] dsh `command()` branch, `dsh-patch.yml` writer, child env, `cli_prefix` dsh/Windows entry, version gate.
- [ ] `execute(env=...)`; `--provider` choices widened.
- [ ] dsh `parse_result` branch; tool-call audit, read confinement and working-tree check run on every exit path before `classify_failure`.
- [ ] dsh `provider_failure_diagnostic` branch and new unavailable markers; `validate_fallback` refuses a DeepSeek source.
- [ ] Fake-dsh tests for every case listed under Verification; full suite green.
- [ ] `SKILL.md`: roles note, `reviewer`/`inspector` tunables, data-egress gate, the "unavailable → default reviewer" rule.
- [ ] `references/runtime.md`: DeepSeek commands, a Review boundaries bullet and its limitations. `AGENTS.md`: a fallback-invariant line. `README.md`: example.
- [ ] Bump manifests to 2.3.0 (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, marketplace if versioned).
- [ ] Live review and live inspection recorded in `VALIDATION.md`; set `VALIDATED_DSH_CLI`.
- [ ] Fresh Codex inspection of the final diff; findings resolved.
- [ ] Archive the plan and log to `docs/exec-plans/completed/`.
