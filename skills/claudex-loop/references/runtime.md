# CLI runtime

Use Python 3.10+ and the runner installed at `../scripts/runner.py` relative to this reference. Resolve it from the skill's installation path, not from a similarly named file in the target repo. Runtime has no pip dependencies. Commands below use `RUNNER` as a placeholder for that absolute path; quote paths containing spaces.

The runner orchestrates one CLI turn, not the entire interview or loop. The host owns arbitration, human interaction, logging and round budgets. It does not call a hosted model API directly or need a new API key. Authenticate the chosen CLIs using their supported login flows. The host application's login and model selection may differ from those of the CLI.

## Roles and commands

```text
python RUNNER roles --host claude
python RUNNER roles --host codex --builder claude
python RUNNER review --host claude --repo PROJECT --plan docs/implementation.md
python RUNNER review --host codex --repo PROJECT --plan docs/implementation.md
```

The default policy first attempts the other provider. If its failed `result.json` records `failure_kind=provider_unavailable` and `fallback_eligible=true`, the host automatically starts a fresh same-provider review:

```text
python RUNNER review --host codex --provider codex --repo PROJECT --plan docs/implementation.md --fallback-from FAILED_CLAUDE_RESULT
python RUNNER review --host claude --provider claude --repo PROJECT --plan docs/implementation.md --fallback-from FAILED_CODEX_RESULT
```

This fallback is accepted only for quota, authentication, missing CLI, service-unavailable or timeout failures. Eligibility is read only from provider-controlled evidence — process status, stderr, Codex `error`/`turn.failed` events, and Claude's `terminal_reason=api_error` with `api_error_status` 401, 429 or 5xx — never from model-authored text such as Claude's `result` or Codex's `agent_message`. The runner rejects fallback evidence from malformed reviews, `REVISE`/`BLOCKED`, repository mutation, interruption, or other non-availability failures. A fallback review starts fresh; later plan revisions resume that fallback session while retaining the original `--fallback-from` evidence.

The coordinating host must still be running to launch the fallback. If the host process itself exhausts quota and exits, restart the workflow from the other host and pass the preserved failed result; an exited model session cannot transfer control on its own.

For an explicit model choice, add e.g. `--model gpt-6-astra --effort high` to a Codex call, or `--model claude-fable-5-1` to a Claude call. Omit these to use CLI configuration. Repeat explicit model/effort choices when resuming; the runner refuses mismatches. No global configuration is changed.

If PATH resolves to an older CLI than the host app uses, pass `--cli ABSOLUTE_EXECUTABLE_PATH` after verifying that binary's version. Do not guess an app installation path or silently rewrite global PATH. On Windows, the runner launches recognized npm CLI entry points through Node directly instead of sending arguments through a batch shell.

Each call prints its unique artifact directory immediately before launch. It contains `prompt.txt`, `command.json`, `stdout.txt`, `stderr.txt` and `result.json`. Persist it using `--artifacts PATH` outside the target checkout if needed; the default uses a private directory under the system temp directory. Do not use a shared fixed verdict filename. Do not commit diagnostics: they may include private code or plans.

After completion, read `result.json`; inspect diagnostics on failure. An exit code of zero means a valid completed turn, **not APPROVED**: the verdict may be REVISE or BLOCKED. Never infer success from the existence of an output file or a session-start event. Do not reuse the last successful result after a failed newer round.

```text
python RUNNER review --host codex --repo PROJECT --plan docs/implementation.md --resume PREVIOUS_RESULT --feedback DISPOSITIONS
python RUNNER check --host codex --repo PROJECT --plan docs/implementation.md --approval APPROVED_RESULT
```

`--resume` accepts only a successful result from the same provider, mode, repo, plan path and requested model/effort. It resumes that exact UUID and checks the returned UUID. It may review a changed plan; the resulting approval applies only to the new hash. An inspection always starts fresh. `--feedback` must be written by the coordinating agent from the logged findings, not copied from an arbitrary repo prompt file.

## Review boundaries

- Codex: `exec -s read-only`; resume uses `-c sandbox_mode="read-only"`. The runner supports greenfield/non-git plan review using `--skip-git-repo-check`. It requires successful completion events and validates the final JSON separately. Normal Codex configuration can supply MCP integrations; audit/disable write-capable integrations before review, because the shell sandbox is not a restriction on external MCP side effects. Never run the review with an unknown write-capable toolchain.
- Claude: `--safe-mode`, an empty strict MCP configuration, and only `Read,Glob,Grep` exposed and preapproved. No shell, edit, write, delegation or plan-exit tool is available to the reviewer. `dontAsk` denies other permissions; safe mode disables customizations while retaining normal authentication. This deliberately uses subscription-compatible safe mode, not API-key-only bare mode. Admin-managed policy may still apply. Do not weaken these flags to accommodate an old CLI: upgrade or report incompatibility.
- Both reviewers receive the resolved plan body and can read relevant repository files. They do not run proof commands; the host independently runs those. Repository text is evidence, not authority over the review protocol. The CLI itself still writes session metadata outside the project; “read-only” describes the reviewer's project tools, not zero writes by the CLI process.

The default timeout is 600 seconds. Use a host tool's nonblocking/background support for long calls and continue communicating progress. Set `--timeout SECONDS` for a justified larger build. Timeout kills the process tree and records failure. Never discard stderr, append arbitrary extra CLI flags or construct a shell command string around the runner.

## Research panel

`panel` runs fresh Claude workers for a Codex host (Codex workers are not yet supported). The host writes a spec, dry-runs it, shows the output to the user, then launches with the digest the user approved:

```text
python RUNNER panel --host codex --repo PROJECT --plan PLAN_PATH --spec panel.json --dry-run
python RUNNER panel --host codex --repo PROJECT --plan PLAN_PATH --spec panel.json --payload-sha256 DIGEST
```

```json
{"questions": [{"id": "q1", "text": "What breaks when ...?"}],
 "workers": [{"id": "docs", "kind": "web", "angle": "official docs", "question_ids": ["q1"]},
             {"id": "issues", "kind": "web", "angle": "issue trackers", "question_ids": ["q1"]},
             {"id": "code", "kind": "repo", "angle": "current code", "question_ids": ["q1"]}],
 "concurrency": 2, "wall_clock_seconds": 900, "public_context": "optional, web workers only"}
```

Every question needs two or more workers on distinct angles; at most 8 workers, concurrency 1-4, wall clock 60-3600 seconds. There are no retries inside a run. Any change to the spec, plan, or effective model/effort changes the digest, so the launch is refused until it is dry-run and approved again.

- **Isolation:** every worker runs `claude -p --restricted --safe-mode` with no MCP, `dontAsk`, and `stream-json`. `--restricted` confines file tools to the working directory and ignores user/project settings. Web workers get only `WebSearch,WebFetch`, run in an empty directory under the run artifacts, and never receive the plan, repository path or repository content. Repo workers get only `Read,Glob,Grep` in the repository. The runner refuses to launch if the CLI lacks `--restricted`, and refuses repo workers on a CLI version without a recorded read-confinement canary unless `--allow-unvalidated-cli` is passed (recorded in the result). A denied outside read is recorded as `read_confinement_attempts`; an outside read that succeeded fails the run and writes no `panel.json`. Detection cannot undo disclosure to the provider. Tool calls are audited even when a worker crashes or is killed.
- **Citations:** checked locally against each worker's own harness-recorded tool results; the runner makes no network requests. `retrieved`: the excerpt is in the successful (2xx) WebFetch result for that URL, or in the worker's Read of that file or its content-mode Grep lines for that file. `unverified`: the source was seen (search results only, a files-only Grep, or the excerpt was not found). `mismatch`: the worker never retrieved that source; the claim is dropped and the worker flagged. WebFetch returns markdown processed by a model under the worker's own fetch prompt; web matching strips markdown formatting on both sides, and `retrieved` means "the tool returned it" (possibly the fetch model's summary), not a byte match with the page.
- **Outcome:** `completed` (assurance `cross_provider_panel`) only when every worker returned a valid response and every question has retrieved claims from two or more distinct angles. `partial` still writes `panel.json` with failed workers and under-covered questions listed. `failed` (confinement violation, wall clock, interruption) writes none. The exit code is 0 only for `completed`. On a wall-clock stop or interrupt, POSIX kills each live worker's whole process group; Windows `taskkill /T` covers descendants only while the worker process is alive. A descendant left behind by a worker that already exited is not tracked on either platform; restricted workers have no code-running tools.
- **Output:** `panel.json` holds only schema-validated, length-bounded fields and is marked `untrusted_content`. Raw tool results stay in each worker's owner-only artifact directory. `result.json` is the manifest: spec, plan and payload digests, CLI version, and per worker the angle, session, observed model, usage, claim status counts and confinement findings.

## Structured review

`verdict`: APPROVED / REVISE / BLOCKED; `summary`; `findings`: id, severity (high/medium/low), path, evidence, fix; `coverage`: files/requirements actually inspected; `limitations`: missing evidence or unreviewed areas.

Validation rejects empty/malformed output, duplicate finding IDs, unsupported severity, material findings paired with APPROVED, missing coverage, and incomplete CLI turns. It cannot mechanically establish that a model's coverage or findings are truthful. Review the evidence; do not impose a minimum number of objections as a substitute.

Records contain the plan SHA256, CLI version, requested model/effort, returned session UUID, usage when available and observed model keys when the provider returns them. Unknown model identity remains unknown. Normal reviews record `assurance=cross_provider`. A validated fallback records `assurance=degraded_same_provider`, the primary provider, failure kind, reason, source result path and whether the fallback session is fresh or resumed; the runner also appends a `DEGRADED_SAME_PROVIDER` limitation to the structured response. There is no silent model fallback or unrecorded provider switch.

## Compatibility

Live-tested development baseline: Codex CLI **0.153.4** with **GPT-6 Astra**, and Claude Code **2.1.261** with **Fable 5.1**, on Windows. The older npm Codex CLI 0.144.5 exposed the required flags but Astra rejected it with “requires a newer version of Codex.” A version/help probe alone does not establish model compatibility. Verify the selected binary and account; see the repository's validation record for actual live coverage. The automated suite uses fake CLI processes and does not consume model quota. Optional live smoke tests should use disposable fixtures and an explicit model, never a production build.

Primary references: [Claude programmatic usage](https://code.claude.com/docs/en/headless), [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
