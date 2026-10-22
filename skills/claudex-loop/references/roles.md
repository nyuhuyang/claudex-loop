# Agent roles and capabilities

Planning, plan review, implementation and final inspection are separate roles. A skill describes the job; a provider adapter describes how one agent executes it. Add future agents once to the runner's capability sets and adapters, with contract tests and runtime documentation, rather than adding host/reviewer pair skills.

## Supported roles

| Agent | Host/coordinator | Plan author | Plan reviewer | Builder | Code inspector | Panel worker |
|---|---|---|---|---|---|---|
| Claude Code (`claude`) | Yes | Current session | Repository-aware | Yes | Yes | Web and repo |
| Codex (`codex`) | Yes | Current session | Repository-aware | Yes | Yes | Web only |
| DeepSeek Harness (`deepseek`, CLI `dsh`) | Yes, from a dsh session | Current session | Repository-aware, opt-in | Host-direct only | Repository-aware, opt-in | No |
| Antigravity (`agy`) | No runner support | No delegated planning | Repository snapshot, opt-in | No | Snapshot, opt-in | Web only |

`claudex-plan` can be followed by an agent that can read the project and write the plan. A DeepSeek Harness (`dsh`) session can host the coordinator role: its default profiles discover the shared `~/.agents/skills` installation, and it plans and may implement directly with dsh's own tools. Runner-certified review/inspection orchestration supports Claude Code, Codex and DeepSeek Harness hosts. The runner has no delegated dsh build adapter, so `build` mode accepts only `builder=claude` or `builder=codex`; `builder=deepseek` means the active DeepSeek host is writing the code directly. Installing a skill in a different agent does not add a runner host adapter. Unsupported roles must be reported, not mapped to a false host identity.

Identify the actual host from runtime identity, never PATH, installed skills or model-name guesses. Use `host=claude` in Claude Code, `host=codex` in Codex and `host=deepseek` in a DeepSeek Harness session. If runtime identity is unavailable, ask once. The current conversation remains planner and coordinator even when a CLI builds. To change the planning conversation, start in the desired host; a reviewer CLI is not that conversation.

## Independent selections

- `reviewer=default`: the other Claude/Codex provider relative to a Claude or Codex host; Claude for a DeepSeek host. Explicit `claude`, `codex`, `deepseek` or `agy` maps to `--reviewer`; it must differ from the host, so a DeepSeek host chooses `claude`, `codex` or `agy`.
- `builder`: `claude` or `codex` for a delegated runner build, defaulting to the host. `deepseek` is valid only for the active DeepSeek host building directly; the runner refuses to launch it as a build target.
- `inspector=default`: the other Claude/Codex provider relative to the builder; Claude when the builder is DeepSeek. Explicit `claude`, `codex`, `deepseek` or `agy` maps to `--inspector`; it must differ from the builder.
- `default` means omit the corresponding CLI flag; it is not a provider id. Carry resolved selections through `roles`, review, build, inspection, resume and fallback calls. A same-provider fallback uses `--provider HOST` for review or `--provider BUILDER` for inspection, preserving preferred roles and `--fallback-from` evidence. A DeepSeek host or builder has no automatic same-provider fallback: select another explicit non-host agent and record the switch.
- `--provider` remains the legacy per-turn selector. Prefer the role flags for new calls. Conflicting provider and role choices are refused; it cannot redirect a build to an unrecorded builder.

Examples (run with the actual host):

```text
python RUNNER roles --host deepseek
python RUNNER roles --host deepseek --reviewer codex --builder claude --inspector agy
python RUNNER review --host deepseek --reviewer claude --repo PROJECT --plan PLAN_PATH
python RUNNER review --host deepseek --reviewer codex --repo PROJECT --plan PLAN_PATH
python RUNNER inspect --host deepseek --builder deepseek --inspector claude --repo PROJECT --plan PLAN_PATH --base PRE_BUILD_COMMIT
python RUNNER inspect --host deepseek --builder claude --inspector agy --repo PROJECT --plan PLAN_PATH --base PRE_BUILD_COMMIT
python RUNNER roles --host codex --reviewer deepseek --builder claude --inspector codex
python RUNNER review --host codex --reviewer deepseek --repo PROJECT --plan PLAN_PATH
python RUNNER inspect --host codex --builder claude --inspector codex --repo PROJECT --plan PLAN_PATH --base PRE_BUILD_COMMIT
python RUNNER review --host claude --reviewer agy --inspector deepseek --repo PROJECT --plan PLAN_PATH
python RUNNER inspect --host claude --reviewer agy --inspector deepseek --repo PROJECT --plan PLAN_PATH --base PRE_BUILD_COMMIT
python RUNNER inspect --host codex --reviewer deepseek --inspector agy --repo PROJECT --plan PLAN_PATH --base PRE_BUILD_COMMIT
```

The plan reviewer need not be the code inspector. Cross-provider review is preferred; direct same-provider certification remains disallowed. A recorded unavailable-provider failure may authorize a fresh degraded same-provider review under [the runtime fallback rules](runtime.md#roles-and-commands). DeepSeek and agy have no same-provider fallback in either direction. A live coordinator must launch any fallback.

## Models and executable paths

Preserve the host's selected model. For Claude/Codex, map `reviewer_model`, `builder_model`, `inspector_model` and corresponding `*_effort` only to the current role's `--model`/`--effort`. Omitted settings inherit that CLI's configuration. Map `claude_cli` or `codex_cli` to `--cli` only for that provider. Verify an explicit binary path and version without changing global installation or configuration. Requested and observed models are separate evidence; a host UI model does not establish a CLI model. Never silently change models or providers.

**DeepSeek (opt-in).** A DeepSeek Harness (`dsh`) session can be the host (`host=deepseek`): it plans, may implement directly, and selects Claude, Codex or Antigravity for plan review and code inspection because it cannot review its own plan. Its shared `~/.agents/skills` installation is discovered by dsh's default profiles. The runner refuses `build --builder deepseek`; implement in the dsh session, or delegate with `--builder claude|codex`. With a DeepSeek builder, record `builder=deepseek` for the fresh inspection. Before the first dsh-hosted round, confirm the user accepts that dsh's own model sees the plan and repository files it reads, and that the selected reviewers receive the material their adapters send. A DeepSeek host exports session/profile controls; the runner launches any dsh reviewer as a fresh headless process and removes `DSH_SESSION_ID`, `DSH_PROFILE`, `DSH_PROFILE_DIR`, `DSH_SHELL` and other `DSH_*` session controls while keeping `DSH_HOME` and `DSH_AGENTS_HOME`.

`reviewer=deepseek` or `inspector=deepseek` from a Claude or Codex host runs the DeepSeek Harness CLI (`dsh`) as the plan reviewer or final inspector, recorded as `cross_provider`. Before the first DeepSeek reviewer run in a loop, say in one line that the plan and every file the reviewer reads go to the DeepSeek API, and get the user's explicit opt-in for that repository; never use it for confidential or client repositories, and never pick it automatically, including as a fallback. Map `deepseek_model` to `--model` and `dsh_cli` to `--cli` only for DeepSeek runs, translating display names first (`DeepSeek-V4.1-Flash` or `DeepSeek-V41-Flash` → `deepseek-flash`, `DeepSeek-V4-Pro` → `deepseek-v4-pro`; the runner accepts only lowercase ids); never apply `reviewer_model`, `inspector_model`, `*_effort`, `codex_cli` or `claude_cli` to them (`--effort` is refused). DeepSeek has no same-provider fallback: on `provider_unavailable`, rerun with `reviewer=default` or `inspector=default` for the failed role (remove both its explicit role flag and `--provider deepseek`), rebuilding `--model`/`--effort`/`--cli` from the replacement provider's own settings or CLI defaults (an inspection keeps its `--base`), and log the switch. A DeepSeek host or builder also has no automatic same-provider fallback; select another explicit non-host agent. DeepSeek runs never resume (dsh persists a session's `cd`): every round, including a retry after a malformed reply, is a fresh run with the prior findings and dispositions in `--feedback`, and counts as a round. A `confinement_violation` is never retried automatically; report it. DeepSeek reviewer runs are refused on Windows and outside a git repository.

**Antigravity (opt-in).** `reviewer=agy` and `inspector=agy` support plan and code review from any supported host, including DeepSeek Harness. Set up its isolated profiles with `agy-profile` and log in to each once. Use `--agy-model`, `--agy-effort`, and `--agy-cli`, never another provider’s model or executable settings. Before the first run, disclose that the plan and a snapshot of all tracked and nonignored untracked repository text are sent to the Gemini model through Antigravity, and obtain repository-specific opt-in. The offline `agy-review` profile receives that snapshot through stdin; it has no file, shell or network tools. Results record `cross_provider`, the repository context hash and snapshot limitations, and can pass the plan approval gate. Legacy `cross_provider_plan_only` records remain ineligible. Each request is capped at 1,000,000 UTF-8 bytes with no truncation; use another reviewer when the context is too large or requires binary/submodule inspection. Plan rounds may resume the exact review UUID; code inspection is always fresh with `--base`. Never route agy to hosting, building or repository research; it has no same-provider fallback. The offline profile retains supplied repository and plan text for resume until cleaned manually. See [runtime](runtime.md#antigravity-snapshot-review) for evidence boundaries.

