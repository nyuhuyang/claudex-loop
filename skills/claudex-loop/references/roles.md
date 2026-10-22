# Agent roles and capabilities

Planning, plan review, implementation and final inspection are separate roles. A skill describes the job; a provider adapter describes how one agent executes it. Add future agents once to the runner's capability sets and adapters, with contract tests and runtime documentation, rather than adding host/reviewer pair skills.

## Supported roles

| Agent | Host/coordinator | Plan author | Plan reviewer | Builder | Code inspector | Panel worker |
|---|---|---|---|---|---|---|
| Claude Code (`claude`) | Yes | Current session | Repository-aware | Yes | Yes | Web and repo |
| Codex (`codex`) | Yes | Current session | Repository-aware | Yes | Yes | Web only |
| DeepSeek Harness (`deepseek`, CLI `dsh`) | No runner support | No delegated planning | Repository-aware, opt-in | No | Opt-in | No |
| Antigravity (`agy`) | No runner support | No delegated planning | Plan body only | No | No | Web only |

`claudex-plan` can be followed by an agent that can read the project and write the plan. Certified CLI review/build orchestration currently requires an actual Claude Code or Codex host. Installing a skill in a different agent does not add a runner host adapter. Unsupported roles must be reported, not mapped to a false host identity.

Identify the actual host from runtime identity, never PATH, installed skills or model-name guesses. If runtime identity is unavailable, ask once. The current conversation remains planner and coordinator even when a CLI builds. To change the planning conversation, start in the desired host; a reviewer CLI is not that conversation.

## Independent selections

- `reviewer=default`: the other Claude/Codex provider relative to the host. Explicit `claude`, `codex`, `deepseek` or `agy` maps to `--reviewer`; it must differ from the host.
- `builder`: `claude` or `codex`, default host; maps to `--builder`.
- `inspector=default`: the other Claude/Codex provider relative to the builder. Explicit `claude`, `codex` or `deepseek` maps to `--inspector`; it must differ from the builder.
- `default` means omit the corresponding CLI flag; it is not a provider id. Carry resolved selections through `roles`, review, build, inspection, resume and fallback calls. A same-provider fallback uses `--provider HOST` for review or `--provider BUILDER` for inspection, preserving preferred roles and `--fallback-from` evidence.
- `--provider` remains the legacy per-turn selector. Prefer the role flags for new calls. Conflicting provider and role choices are refused; it cannot redirect a build to an unrecorded builder.

Examples (run from either supported host with its actual `--host`):

```text
python RUNNER roles --host codex --reviewer deepseek --builder claude --inspector codex
python RUNNER review --host codex --reviewer deepseek --repo PROJECT --plan PLAN_PATH
python RUNNER inspect --host codex --builder claude --inspector codex --repo PROJECT --plan PLAN_PATH --base PRE_BUILD_COMMIT
```

The plan reviewer need not be the code inspector. Cross-provider review is preferred; direct same-provider certification remains disallowed. A recorded unavailable-provider failure may authorize a fresh degraded same-provider review under [the runtime fallback rules](runtime.md#roles-and-commands). DeepSeek and agy have no same-provider fallback in either direction. A live coordinator must launch any fallback.

## Models and executable paths

Preserve the host's selected model. For Claude/Codex, map `reviewer_model`, `builder_model`, `inspector_model` and corresponding `*_effort` only to the current role's `--model`/`--effort`. Omitted settings inherit that CLI's configuration. Map `claude_cli` or `codex_cli` to `--cli` only for that provider. Verify an explicit binary path and version without changing global installation or configuration. Requested and observed models are separate evidence; a host UI model does not establish a CLI model. Never silently change models or providers.

**DeepSeek (opt-in).** `reviewer=deepseek` or `inspector=deepseek` runs the DeepSeek Harness CLI (`dsh`) as the plan reviewer or final inspector, recorded as `cross_provider`. Before the first DeepSeek run in a loop, say in one line that the plan and every file the reviewer reads go to the DeepSeek API, and get the user's explicit opt-in for that repository; never use it for confidential or client repositories, and never pick it automatically, including as a fallback. Map `deepseek_model` to `--model` and `dsh_cli` to `--cli` only for DeepSeek runs, translating display names first (`DeepSeek-V4.1-Flash` or `DeepSeek-V41-Flash` → `deepseek-flash`, `DeepSeek-V4-Pro` → `deepseek-v4-pro`; the runner accepts only lowercase ids); never apply `reviewer_model`, `inspector_model`, `*_effort`, `codex_cli` or `claude_cli` to them (`--effort` is refused). DeepSeek has no same-provider fallback: on `provider_unavailable`, rerun with `reviewer=default` or `inspector=default` for the failed role (remove both its explicit role flag and `--provider deepseek`), rebuilding `--model`/`--effort`/`--cli` from the replacement provider's own settings or CLI defaults (an inspection keeps its `--base`), and log the switch. DeepSeek runs never resume (dsh persists a session's `cd`): every round, including a retry after a malformed reply, is a fresh run with the prior findings and dispositions in `--feedback`, and counts as a round. A `confinement_violation` is never retried automatically; report it. DeepSeek runs are refused on Windows and outside a git repository.

An explicit `review --provider agy` is a plan-body-only review. Set up its isolated profiles with `agy-profile` and log in to each once; use `--agy-model`, `--agy-effort`, and `--agy-cli` for this provider. Its `cross_provider_plan_only` result cannot authorize a build. Never route agy to hosting, building, inspection, or repository research. The offline `agy-review` profile retains review plan text for session resume until the user cleans it.

