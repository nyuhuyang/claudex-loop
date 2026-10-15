# Plan Review Log: Cross-provider Research Panel (Codex host → Claude workers)
Phases 0-1 (recon + interrogation) complete — plan locked with the user. MAX_ROUNDS=5.

## Run configuration
- Host/planner: Claude Code (Opus 5.5); reviewer: Codex CLI 0.155.1, ChatGPT auth, model `gpt-6-sol` (from `~/.codex/config.toml`), fresh session, read-only sandbox.
- Research tier: none (prior run's 2026-09-21 official-doc evidence reused).
- Predecessor: `2026-09-19-multi-provider-adversarial-research.md` + its review log (5 rounds, final REVISE; host accepted 42/42 findings, 0 rejected, and the plan grew each round).

## Interrogation decisions
- Q1 scope narrowed: panel first, Codex host → Claude workers; multi-provider interop kept as long-term direction.
- Q2 no adapter refactor now; provider-neutral panel data contract instead.
- Q3 no runner-side fetcher; verify citations locally against harness-recorded WebSearch/WebFetch results; prompt injection contained with a stated residual risk.
- Q4 no disposable copy; Claude permission-mode read confinement, gated by a live canary and checked per run.
- Q5 429/`result`-spoofing classification fix split out as P0 (separate authorization).
- Cosmetic C1–C8 accepted as a batch.

## Round 1 — Codex
Session `01a0cb86-b755-76b0-ab86-9f53b88dde01`, model per config (`gpt-6-sol`), exit 0.

1. Outside reads are detected after disclosure; a one-version canary does not enforce confinement. Fix: enforced filesystem read boundary or refuse repo workers.
2. Aggregate cancellation not specified; `execute()` kills only the process whose worker thread times out; main-thread interrupt can leave workers running. Fix: central live-process registry, stop queued launches, kill all groups.
3. Repo citations can be "retrieved" without a retrieval (matched against current file). Fix: bind to the worker's successful tool result.
4. Web citations can borrow evidence from another search hit in the same WebSearch result. Fix: match within the specific entry or label unverified.
5. Failed or thin panel can still get completed assurance. Fix: explicit success criteria; partial/failed without assurance.
6. Injection boundary covers only excerpts; other fields unbounded. Fix: bound every host-facing field, treat whole response as untrusted.
7. Schema/assignment checks underspecified (unassigned questions, source_type vs kind, IDs, budgets). Fix: validate all.
8. Web prompt can still carry repository material via questions/public_context. Fix: show exact payloads, require explicit approval for repo-derived text.

VERDICT: REVISE

### Claude's response
- 1 **partially accepted**. Accepted: canary-validated CLI version list enforced in the runner (override flag recorded), and a detected outside read writes no host-facing output. Rejected: an "enforced filesystem read boundary" — there is no stdlib, cross-platform OS read sandbox, and repo workers run under exactly the flag set the existing Claude review mode already uses in the repo, so they add no new exposure. The residual (disclosure to the provider before detection) is now stated.
- 2 accepted: central Popen registry; main thread owns deadline/interrupt, cancels queued futures, kills all groups.
- 3 accepted: repo claims verify against the worker's own Read/Grep tool_result on that path, never the current file.
- 4 accepted: only WebFetch can yield `retrieved`; WebSearch-only URLs are `unverified`.
- 5 accepted: `completed` / `partial` / `failed` rules; only `completed` carries assurance.
- 6 accepted: every worker-authored field length-bounded; claim count capped; whole response untrusted.
- 7 accepted: spec and claim validation enumerated, with tests.
- 8 **partially accepted**. Accepted: `--dry-run` prints exact web payloads; host must show them and get user approval, flagging repo-derived text. Rejected: mechanical enforcement — the runner cannot detect repo-derived text, and a host-passed confirmation flag is self-certification.

## Round 2 — Codex
Same session, exit 0. Findings 2–8 addressed in design.

1. Repo reads still not confined; `dontAsk` is a prompt policy. Claude's `--restricted` flag confines file tools to working directories and is present in 2.1.280. Fix: require `--restricted` for repo workers, keep canary, refuse if unavailable.
2. Approval not bound to the launched web payload; spec can change between dry-run and launch. Fix: dry-run digest must match at launch.

VERDICT: REVISE

### Claude's response
- 1 accepted, verified locally: `claude --help` confirms `--restricted` confines file tools to working directories and ignores user/project/local settings. Now required for both worker kinds; the runner refuses if the flag is absent. Noted as a follow-up that existing review/inspect mode lacks it (out of scope here).
- 2 accepted: `payload_sha256` from dry-run is required at launch. This binds the launch to what was displayed (integrity), which differs from the self-certification rejected in Round 1.

## Round 3 — Codex
Same session, exit 0.

The revised plan addresses the material findings: `--restricted` supplies a working-directory read boundary, the live canary gates repo workers, and `payload_sha256` binds launch to the displayed prompts. The cancellation, citation, schema, and assurance rules now have concrete acceptance tests. No further material plan defect found.

VERDICT: APPROVED

## Resolution
APPROVED after 3 rounds (Codex reviewer, cross-provider). 10 findings: 8 accepted, 2 partially accepted with logged rejections. Awaiting user sign-off; implementation not authorized.

## P0 build (Claude) — 2026-09-22
Authorized by the user ("开工，claude来实现P0"). Built on top of the pre-existing uncommitted fallback work (baseline diff captured outside the repo; that baseline is out of scope for this inspection).
- `provider_failure_diagnostic` no longer reads Claude `result` (or any `message`/`result` key); it returns a structured flag derived from `terminal_reason=api_error` + `api_error_status`.
- `unavailable_http_status`: int (not bool) 401, 429, 500–599 → eligible; 400/403/other/non-int → ineligible.
- Tests: real 429 envelope end-to-end → eligible + degraded fallback completes; `result`-only spend-limit text and 400 → ineligible; status policy table incl. malformed types. The real 2026-09-19 artifact now classifies `provider_unavailable`.
- `references/runtime.md`: eligibility evidence sources documented.
- Verification: 36 tests OK; validate.py passed (PyYAML in scratch venv); `runner.py --help` OK; `git diff --check` clean.

## Post-build inspection
Inspector: Codex (fresh read-only session), 2 rounds of MAX_INSPECTION_ROUNDS=2.

Round 1 findings:
1. [P1] runner.py:27 — status allowlist omits most 5xx (e.g. 520). Fix: accept 500–599.
2. [P1] runner.py:118 — a structured 400/403 can still become eligible if the provider error object or stderr contains "spend limit". Fix: explicit ineligible status precedence over text markers.
3. [P2] runner.py:95 — malformed `api_error_status` (array/object) raises TypeError in classification, leaving result.json at `running`. Fix: type-check.

Claude's dispositions:
- 1 accepted: 500–599 range.
- 2 rejected: text in the provider-owned error object or stderr is legitimate outage evidence (a quota message the provider itself emits under a 403 is still an outage); the spec excludes only model-authored fields.
- 3 accepted: int-only check; bool excluded; covered by the status policy test.

Round 2: "No material findings."

## P1 build (Claude) — 2026-09-22
Authorized by the user ("开始做P1"). Base commit `184a9c6` on `fix/fallback-provider-classification`; only `docs/` was dirty and is excluded from the evidence.
- Format probe (Claude 2.1.280, Haiku, disposable dirs) confirmed plan assumptions 1–3: `--restricted` denied `/etc/hosts`; WebSearch/WebFetch work under `dontAsk` + `--safe-mode`; stream-json pairs tool_use/tool_result and adds structured `tool_use_result`. `usage.server_tool_use` stayed 0 despite a fetch, so it is not used as evidence. Not the formal canary; `VALIDATED_READ_CONFINEMENT_CLI` stays empty.
- Implemented `panel` mode in `runner.py`, per P1.1–P1.12. Deviations: the manifest is `result.json` (consistent with other modes); exit code 0 only for `completed`.
- Tests: 36 → 54; six mutation checks (confinement, verification, kill path, assignment validation, `--restricted`, completion rule) each make a panel test fail.
- Docs: SKILL.md Phase 0 paragraph; runtime.md "Research panel"; research.md enforced-vs-advisory; README section; VALIDATION coverage + probe.

## Post-build inspection (P1)
Inspector: Codex, fresh read-only sessions, 2 rounds (MAX_INSPECTION_ROUNDS=2).

Round 1:
1. [High] Confinement audit skipped when a worker exits nonzero → partial run still writes panel.json. — accepted: audit in `finally` over a tolerant parser; test with truncated stream + exit 1.
2. [Medium] Launch-time `--model`/`--effort` not bound to the digest. — accepted: hashed and shown in dry-run; test.
3. [Medium] Any filename substring in Grep output counted as "seen". — accepted: Grep paths parsed and compared to the resolved target; test.
4. [Medium] A non-2xx WebFetch result could support `retrieved`. — accepted; test.
5. [Medium] `kill_tree` skipped the group once the parent exited. — partially accepted: POSIX always signals the group; Windows descendant tracking (Job Objects) rejected as out of scope, documented.

Round 2:
1. Descendants of an already-exited worker are not tracked at deadline/interrupt. — rejected: signalling a recorded group ID after its leader exited risks hitting a reused process group, and `--restricted` workers have no code-running tools; documented in runtime.md.
2. Content-mode Grep could never yield `retrieved`, contrary to P1.7 ("Read/Grep"). — accepted: content-mode `path:N:text` lines bind text to that path; files-only results stay `unverified`; tests incl. hyphenated filenames.

The Round 2 Grep fix was made after the final inspection round and is not independently re-inspected.
Final verification: 54 tests OK; validate.py passed; `runner.py --help` OK; `git diff --check` clean.

## P1 committed + live validation — 2026-09-22
- P1 committed as `f9f0288`. The user then authorized the canary and one live run.
- **Canary (Claude 2.1.280, Haiku, panel repo-worker flags):** absolute path, `../`, Grep and Glob on the outside dir, and an in-repo symlink were all denied; the secret was absent from the output. `2.1.280` added to `VALIDATED_READ_CONFINEMENT_CLI`.
- **Bug found by the canary:** `--json-schema` answers arrive via an internal `StructuredOutput` tool call; the audit treated it as a disallowed tool, which would have failed every real run. Fixed; the fake stream now emits it. With the old runner, 11 panel tests fail against the corrected fixture.
- **Flaky test found while re-running:** macOS `killpg` returns EPERM while an exited group leader is a zombie (exposed by the Round-1 removal of the `poll()` short-circuit). Now tolerated; 25/25 reruns clean.
- **Live run, Codex CLI 0.155.1 as host process** (workspace-write + network + writable `~/.claude`; also needed `--skip-git-repo-check` outside a trusted directory): 3 workers on Sonnet 5, 58 s, about $0.48, status `partial` (q1 under-covered; 12/13 web claims `unverified`).
- **Bug found by the live run:** WebFetch returns markdown while workers quote rendered text. Web matching now strips markdown symmetrically; test added. Offline re-verification of the stored artifacts: 10/12 become `retrieved`, which would make q1 covered. That is an offline recomputation, not a second live run. The two that stayed `unverified` include an unsupported "removed in Python 3.14" claim.
- Observed limitation: some `retrieved` community excerpts quote WebFetch's model summary, not the page.
- These post-inspection fixes (StructuredOutput allowance, EPERM tolerance, markdown normalization) are small and test-covered, but have not been independently re-inspected.

## P2 probes — 2026-09-22 (Codex CLI 0.155.1, ChatGPT auth, CLI-default model)
- `codex exec` has no `--search`; `-c web_search="live"` enables the hosted search. `item.completed` `web_search` events carry `query`, `action`, and per-result `{url, title, snippet}`, so an excerpt can be bound to one URL's snippet (short text, provider-returned).
- **Read-confinement canary FAILED:** under `-s read-only`, `cat` by absolute path and by `../` both returned the outside secret. Codex repo workers stay refused, as P2 predicted.
- **Tool surface is not allowlistable.** With `--ignore-user-config` the worker still listed `mcp__codex_apps__github_*` write tools (create_commit, delete_file, enable_auto_merge, ...), `spawn_agent`, `functions.exec`, `apply_patch`, `image_gen`, and `view_image`. With `--disable shell_tool` only, `view_image` still opened the outside secret (and failed only at image decoding).
- A denylist (`apps plugins remote_plugin multi_agent shell_tool unified_exec view_image image_generation browser_use browser_use_external computer_use code_mode_host goals sleep_tool tool_suggest skill_search skill_mcp_dependency_install in_app_browser hooks`) removed the GitHub tools and `view_image`; `functions.exec` became inert ("code-mode host is disabled"); the secret was not read. **`collaboration.spawn_agent` stayed listed despite `--disable multi_agent`.** The tool list is model self-report, not authoritative.
- **Cross-cutting finding:** the existing Codex review/inspect argv (`exec -s read-only`) exposes the same `codex_apps` GitHub write tools, whose side effects the filesystem sandbox does not constrain.
- P2 paused for a user decision.

## P2 build (Claude) — 2026-09-22
User chose "harden existing review first, then P2 web workers".
- **Review/inspect hardening:** Codex read-only runs now disable `apps plugins remote_plugin multi_agent image_generation browser_use browser_use_external computer_use in_app_browser skill_mcp_dependency_install`, but only those the installed CLI lists (an unknown `--disable` name is a hard CLI error). The result records `disabled_features`. Live: review completed (REVISE, correct) and the GitHub tools were gone. User-config MCP servers still load (`-c mcp_servers={}` does not clear them; `--ignore-user-config` would drop the configured model); documented.
- **P2 Codex web workers:** `codex exec --ignore-user-config --ephemeral -s read-only -c web_search="live" --output-schema`, plus the web disable set (adds shell, unified_exec, view_image, goals, sleep, tool_suggest, skill_search, hooks). Repo workers refused. The final JSON is read from the last `agent_message`. Audit: any item other than web_search / message / error fails the run. Verification: exact URL, excerpt in that result's title/snippet (markdown-stripped). Version gate `VALIDATED_CODEX_WEB_PANEL_CLI`.
- **Live finding:** Codex auto-updated 0.155.1 → 0.156.0, where disabling `code_mode_host` also disables web search (the first live run failed closed). With code mode on and shell/view_image/connectors off, code-mode `require`/`fetch` and `file://` opens failed to read the secret. Code-mode executions are invisible to the JSONL audit; documented.
- **Live P2 run:** `completed`, `cross_provider_panel`, 50 s, only web_search/agent_message items, 4/7 retrieved. `0.156.0` validated.

## Post-build inspection (P2)
Inspector: Codex, fresh read-only sessions, 2 rounds.
Round 1: (1) [High] a feature probe with empty or odd output fails open — accepted: rows must parse, empty output raises, and the panel requires shell_tool/view_image/apps to be listed; (2) [High] the audit missed failed/declined and started-only disallowed items — accepted; (3) [Medium] Codex URLs compared with trailing slashes stripped — accepted: exact match.
Round 2: (1) review/inspect probe did not require `apps` — accepted; (2) the started-only test passed vacuously (exit 1, no completion) — accepted: rewritten on a successful stream asserting the violation; a mutation that ignores item.started now fails it.
The Round 2 fixes were made after the final inspection round and are not independently re-inspected.
Final: 62 tests OK; validate.py passed; `git diff --check` clean.

## Codex MCP lockdown — 2026-09-22
User asked for Codex to load only necessary MCP servers. Read-only review/inspection now lists servers (`codex mcp list --json` with the feature disables), overrides each enabled one with `-c mcp_servers.NAME.enabled=false`, re-lists to prove none stays enabled, and fails closed otherwise; `--codex-mcp-allow NAME` keeps one. Plugin-provided servers (cua_repl, codex_app) cannot take a `-c` override (the CLI reports "invalid transport") and disappear with `--disable plugins`. Live: review completed with node_repl, playwright, tradingview and tradingview-desktop disabled; the tool listing showed no MCP tools and shell access intact. 63 tests. Commit `cf25059`; not Codex-inspected (the user asked to commit and push directly). Branch pushed to `fork` (nyuhuyang/claudex-loop).
