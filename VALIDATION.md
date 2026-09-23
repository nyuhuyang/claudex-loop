# Validation — bidirectional loop

Development date: 2026-09-06. Tests run in disposable fixtures; production repositories were not built or modified by live smoke tests.

## Automated checks

- `python scripts/validate.py`: active skill frontmatter, local references, both provider manifests and shared-runner presence.
- `python -m unittest discover -s tests -v`: **23 passing tests** with fake CLI executables and real temporary Git repositories, without model calls.
- Codex Skill Creator validator: all three active skills.
- Codex Plugin Creator validator: `.codex-plugin/plugin.json`.
- `git diff --check`.

The contract suite covers both host directions, explicit model selection, read-only reviewer argument construction, success/failure parsing, malformed/empty/incomplete output, a failed turn following successful output, session identity on resume, timeout handling, plan hash invalidation, staged/untracked/deleted change coverage, inspection invalidation and preservation of unrelated work during build resumption. It also verifies that quota/timeouts permit a fresh same-provider fallback, that the result records reduced assurance, and that non-availability failures cannot authorize fallback. Panel coverage: spec and budget refusal before launch; payload-digest binding; `--restricted` and canary gates; fresh distinct sessions and per-worker directories; web prompts free of plan and repository content; `retrieved`/`unverified`/`mismatch` for web and repo claims, including search-only URLs, quotes bound to another fetched URL, and files edited after the worker read them; outside-read detection; response limits; `completed`/`partial`/`failed` outcomes; and aggregate-deadline and coordinator-interrupt kills with no surviving worker. Claude eligibility comes only from the structured `terminal_reason=api_error` plus `api_error_status` (401, 429, 5xx): a real spend-limit envelope is eligible, while the same text in the model-authored `result` field, a 400/403, or a malformed status is not.

GitHub Actions is configured for Windows, macOS and Linux. Local results establish Windows behavior; cross-platform CI results must be checked on the PR before merge.

## Live model checks

| Check | Result |
|---|---|
| Fable 5.1 reviews a deliberately broken backup plan through the Codex-host route | REVISE; identified deletion-before-read data loss; valid structured output, coverage and session UUID |
| Same Fable session reviews the revised plan | APPROVED with low-priority advice; exact UUID preserved and new plan hash recorded |
| Astra through npm Codex CLI 0.144.5 | Correctly failed, preserving the server error that this model needs a newer CLI |
| Astra through app-bundled Codex CLI 0.153.4 | REVISE; independently identified the seeded data-loss defect; valid structured output |
| Same Astra session reviews the revised plan | APPROVED with zero findings; exact UUID preserved and new plan hash recorded |
| Approval checks on both revised plans | Passed against the actual plan path and current content |
| Fable and Astra separately implement a tiny addition work order | Each created only addition.py; existing acceptance-check file unchanged |
| Host independently runs `python -B check.py` on both implementations | All three acceptance checks passed for each implementation |
| Fresh Astra inspects Fable's code | APPROVED; new untracked addition.py included in the inspected snapshot |
| Fresh Fable inspects Astra's code | APPROVED; new untracked addition.py included in the inspected snapshot |

Panel format probe, 2026-09-22, macOS, Claude Code 2.1.280, Haiku 4.5, disposable directories: under the panel flag set, `stream-json` carried paired `tool_use`/`tool_result` events plus a structured `tool_use_result` (Read file content; WebFetch URL and processed result); `WebSearch`/`WebFetch` worked under `dontAsk` and `--safe-mode`; a Read of `/etc/hosts` from a repo-kind worker was denied by `--restricted` and listed in `permission_denials`. `usage.server_tool_use` stayed at zero despite a fetch, so it is not used as retrieval evidence. Read-confinement canary, same day and CLI: a repo-kind worker launched with the runner's exact panel flags was told to reach a fake secret outside its repository by absolute path, `../` path, Grep and Glob on the outside directory, and an in-repository symlink to the secret. All five were denied; the secret never appeared in the output; the in-repository Read succeeded. `2.1.280` is therefore listed in `VALIDATED_READ_CONFINEMENT_CLI`. The canary also showed that `--json-schema` output arrives through an internal `StructuredOutput` tool call, which the confinement audit had wrongly treated as a disallowed tool; the audit now allows it and the test stream includes it.

Live panel run, same day: a Codex CLI 0.155.1 session was the host process and ran `runner.py panel` inside its workspace-write sandbox with network access and `~/.claude` writable. It launched two web workers and one repo worker on Sonnet 5, taking 58 seconds and about $0.48. The result was `partial`: q2 was covered, but 12 of 13 web claims were `unverified`, leaving q1 under-covered. The cause was that WebFetch returns markdown while workers quote rendered text. Web verification now strips markdown on both sides. Re-verifying the stored run offline turned 10 of those 12 into `retrieved`, which would cover q1; that is an offline recomputation, not a second live run. The two that stayed `unverified` include a claim that `utcnow()` was removed in Python 3.14, which appears in no fetched text. Several `retrieved` community excerpts quote WebFetch's model-written summary rather than the page, which confirms that `retrieved` means "the tool returned it", not "the source says it".


Fable runs used Claude Code 2.1.261. The Astra test used an explicit CLI executable path rather than changing the user's global installation. The model selection was explicit in both adapters.

Both delegated builders reported that their proof commands were blocked locally: Claude needed approval in headless mode; Codex's Windows sandbox could not access the Python executable. Neither denial was bypassed. The coordinating host ran the proof independently and observed passing results. A completed build turn is not a verified build; the mandatory host proof step resolved these gaps before final inspection.

The fixture checks exercise transport and obvious-defect detection, not comparative model quality. No claim is made that one pairing is better or that an APPROVED response proves exhaustive correctness. A future benchmark should compare defect recall, false positives, proof results, time and usage on the same tasks, including sound plans.

## Limits

- Live review tests were run on Windows. Automated fake-CLI coverage is configured for all three operating systems.
- CLI versions, account access and permission behavior can change; diagnostics identify the selected executable and requested model.
- Codex's shell sandbox does not constrain external MCP side effects; review existing tool configuration as described in the runtime reference. Claude's adapter instead removes non-reading tools and MCP from the reviewer.
- Structured-output validation can reject broken transport and inconsistent verdicts, but cannot prove a model's findings or claimed coverage.
