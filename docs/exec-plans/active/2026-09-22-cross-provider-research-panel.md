---
status: in-progress
created: 2026-09-22
---

# Plan: Cross-provider Research Panel (Codex host → Claude workers)
_Locked via claudex-loop — by Claude + Yang Hu, 2026-09-22. Supersedes the scope of `../completed/2026-09-19-multi-provider-adversarial-research.md`._

## Goal

Let a Codex-hosted Claudex Loop run adversarial research through a panel of fresh, read-only Claude workers, with auditable launches, locally verified citations, and a result that can never authorize a build. Long-term direction: multi-agent interop across more providers. This plan lays that groundwork only through a provider-neutral panel data contract; it adds no third provider.

This plan does not authorize implementation.

## Progress Checklist
- [x] Plan reviewed: Codex APPROVED after 3 rounds (see review log)
- [x] P0 fallback classification — commit `fd4991f` on `fix/fallback-provider-classification`; 36 tests, Codex inspection clean
- [x] Codex-host install verified by the user (2026-09-22, `npx skills add ./ -g -a codex`)
- [x] Fallback docs, AGENTS.md and 2.2.0 manifests — commit `184a9c6`
- [x] P1 `panel` mode, Claude workers — commit `f9f0288`; Codex-inspected (2 rounds)
- [x] P1 live canary (passed, 2.1.280 validated) + Codex-hosted panel run (`partial`; exposed the markdown-matching bug) recorded in `VALIDATION.md`
- [x] Post-live fixes (StructuredOutput allowance, EPERM tolerance, markdown normalization) — commit `c3682c5`
- [ ] Optional: second live run to confirm `completed` after the markdown fix
- [x] Codex MCP lockdown in read-only review/inspection (`--codex-mcp-allow` for exceptions) — commit `cf25059`
- [x] Branch pushed to fork: https://github.com/nyuhuyang/claudex-loop/tree/fix/fallback-provider-classification
- [ ] Open PR; archive this plan
- [x] Codex review/inspect hardening (connector features disabled; user MCP caveat documented) — commit `09ff540`
- [x] P2 reverse direction: Codex web workers (repo workers refused: canary failed); live run `completed` on 0.156.0; Codex-inspected (2 rounds) — commit `990d418`

## Approach

### P0 — prerequisite (separate change, not part of this plan)

Finish the uncommitted fallback work: classify availability only from provider-controlled fields (`api_error_status`, `terminal_reason`, error objects, exit status, stderr), never from the model-authored `result`/`agent_message`. Regression tests: a real structured 429 envelope is `provider_unavailable`; "spend limit" appearing only in `result` is `provider_failure`. Committed separately, with its own authorization. The panel depends only on "classification is correct".

### P1 — `panel` mode, Claude workers

1. New runner mode `panel`: `runner.py panel --host codex --repo <repo> --plan <plan> --spec <panel.json>`. Worker provider = the provider opposite the host (existing `resolve_roles`). `provider == host` is rejected. In P1 a Codex worker is rejected with "not yet supported" (fail closed).
2. Panel spec (JSON, written by the host): `questions[] {id, text}`, `workers[] {id, kind: web|repo, angle, question_ids[]}`, `concurrency` (default 2, max 4), `wall_clock_seconds`, optional `model`/`effort`, optional `public_context` (web workers only). Validation before launch: unique question and worker IDs; every `question_ids` entry exists; every question is covered by ≥2 workers on distinct angles; 1 ≤ workers ≤ 8; 1 ≤ concurrency ≤ 4; 60 ≤ `wall_clock_seconds` ≤ 3600; every text field nonempty and bounded (question ≤ 500 chars, `public_context` ≤ 2000). Launch count = `len(workers)` (no retries in v1; a retry is a new run).
   `runner.py panel --dry-run` prints the launch count, concurrency, wall-clock budget, **the exact prompt each web worker will receive**, and a `payload_sha256` over the canonical spec plus every rendered worker prompt. A real launch requires `--payload-sha256 <value>` and refuses on mismatch, so the run is bound to exactly what was displayed. SKILL rule: the host shows that dry-run output to the user and launches only after the user approves. Any repository-derived text in a web payload must be pointed out to the user explicitly in that approval. The runner cannot detect repository-derived text, and a host-supplied confirmation flag would be self-certification, so enforcement lives in the human gate.
3. Execution reuses the existing `command()` / `execute()` / `parse_result()` Claude branch plus a `panel` flag set. No adapter refactor. Every worker runs in a fresh session (no `--resume`) with its own child directory `<run_dir>/w<NN>-<id>/` (stdout, stderr, result.json). Bounded parallelism via `concurrent.futures.ThreadPoolExecutor`. A central registry holds every live `Popen`. The main thread owns the aggregate deadline and `KeyboardInterrupt`; when either fires, it cancels queued futures, stops new launches, and kills every registered process group (the existing POSIX `killpg` / Windows `taskkill /T` logic, factored into a helper). Per-worker timeouts keep the current `execute()` behaviour. Completed worker results are preserved.
4. Worker isolation, both kinds: `-p --restricted --safe-mode --strict-mcp-config --mcp-config '{"mcpServers":{}}' --permission-mode dontAsk --permission-prompts none --no-chrome --output-format stream-json --verbose --json-schema <PANEL_SCHEMA>`.
   - **repo worker**: `cwd=repo`; `--tools`/`--allowedTools` `Read,Glob,Grep`; prompt carries the plan body, assigned angle and questions.
   - **web worker**: `cwd` = an empty owner-only directory inside the run dir; `--tools`/`--allowedTools` `WebSearch,WebFetch`; prompt carries only the questions, angle, and `public_context`. The runner never appends the plan body, repo path, or repo content to a web prompt.
5. **Read confinement.** The enforcing boundary is Claude Code's `--restricted` mode: per `claude --help` (2.1.280) it confines file tools to the working directories, ignores user/project/local settings files (so no inherited allow rules), and removes code-running tools. `--tools` then limits the tool set. The runner probes `claude --help` for `--restricted` and refuses to launch any worker if it is absent. It is still a tool-level boundary, not an OS sandbox, and is stated as such.
   - Live canary: a fake secret file outside the repo that the worker is explicitly told to read must be denied and absent from all output. The canary-validated Claude CLI versions are recorded in a runner constant and in `VALIDATION.md`. Repo workers are refused when `claude --version` is not in that list, unless the user passes `--allow-unvalidated-cli`; that override is recorded in the manifest.
   - Per-run detection (second layer): the runner inspects every `Read`/`Glob`/`Grep` `tool_use` input. An outside-repo path is recorded as `read_confinement_attempt`. An outside-path call whose `tool_result` is not a permission denial fails the whole run, and **no host-facing `panel.json` is written**; only the owner-only artifacts remain. Detection cannot undo disclosure to the provider; that residual is stated.
6. Claim schema `PANEL_SCHEMA` (provider-neutral, `additionalProperties: false`): `summary` (≤1000 chars), `claims[]` (≤20) `{id, question_id, claim (≤500), source_type: web|repo, locator (≤500), excerpt (≤300), confidence: high|medium|low, limitation (≤300)}`, `coverage[]` and `limitations[]` (≤10 items, each ≤300). Own validator; never `REVIEW_SCHEMA`. The validator also requires unique claim IDs, `question_id` in that worker's assigned `question_ids`, and `source_type == worker.kind`. A violation fails that worker.
7. **Local citation verification, no network access by the runner**:
   - web claim: only a successful `WebFetch` binds a quote to a URL. If `locator` equals the URL of one of that worker's successful `WebFetch` calls, and the whitespace-normalized, case-folded excerpt is a substring of **that call's** `tool_result` → `retrieved`. Same URL fetched but excerpt not found → `unverified` (WebFetch returns processed content). URL seen only in `WebSearch` results → `unverified` (one search result mixes several URLs, so the quote cannot be bound). URL never seen in any of that worker's tool records → `mismatch`.
   - repo claim: `locator` is `relative/path[:line]`, and the resolved path must stay inside the repo (absolute or escaping → `mismatch`). The excerpt must be found in the `tool_result` of one of that worker's successful `Read`/`Grep` calls on that same path → `retrieved`. Path never read by the worker → `mismatch`. Read but excerpt absent → `unverified`. The runner verifies against what the worker actually received, never against the current file, so a file changing mid-run cannot produce a false `retrieved`.
   - `mismatch` claims are excluded from host-facing output; the worker is flagged, and its remaining claims are shown with the flag.
   - `retrieved` means "the worker saw this through its tool", not "bytes match the source". Decision-relevant claims require a human spot-check; the SKILL says so.
8. **Prompt-injection containment**: raw `tool_result` content stays only in owner-only child artifacts and is never sent to the host. Host-facing `panel.json` contains only schema-validated, length-bounded fields (P1.6) plus verification status, and is marked `"untrusted_content": true`. The SKILL instructs the host to treat **every** worker-authored field (summary, claim, excerpt, coverage, limitations) as quoted data, never instructions. Residual risk, stated as unresolved: injected text can still reach the host within those bounds.
9. Parent `manifest.json`: spec sha256, plan sha256, repo, host, per worker {id, kind, angle, provider, harness (`claude-code`), session_id, requested/observed model, effort, exit code, usage including `server_tool_use`, child path, read-confinement findings, claim status counts}. The runner builds a coverage matrix (question × worker × retrieved count) and flags questions left with fewer than two workers holding retrieved claims. The host performs synthesis and records disagreements in the log; there is no separate synthesis session.
10. Record lifecycle: `mode: panel`; `attempted_assurance: cross_provider_panel` from launch.
   - `completed` with `assurance: cross_provider_panel` only when every worker exited 0 with a valid response, no confinement failure occurred, and every question has ≥2 workers on distinct angles holding at least one `retrieved` claim.
   - `partial` (no `assurance`; failed workers and under-covered questions listed) when all workers finished but the coverage rule is not met, or some workers failed. `panel.json` is still written.
   - `failed` (no `assurance`, no `panel.json`) on a confinement failure, aggregate timeout, interruption, or spec error. The existing `check_approval` (requires completed `review` + `APPROVED`) already rejects panel results; a test pins this.
11. Codex host note: the Claude CLI needs network access. The SKILL tells a Codex host to run `runner.py panel` with network permission, and records a clear error when a worker fails to reach the API.
12. Docs: `SKILL.md` (panel mode, one paragraph plus link), `references/research.md` (the runner panel is the enforced mechanism; printed budgets are enforced for launches/concurrency/wall clock, token bands stay advisory), `references/runtime.md` (panel flag set, read confinement, injection rules), `README.md` (mode list, `cross_provider_panel` never authorizes a build), `VALIDATION.md` (canary and live panel run).

### P2 — reverse direction (Claude host → Codex workers)

Same spec, schema, manifest and verification. It requires a Codex branch: `--search` for web workers, `-s read-only`, `web_search` event capture. Each capability is gated by its own fixtures and live checks; a failed gate refuses that worker kind. Expected limits, to be confirmed: the Codex read-only sandbox does not confine reads, so repo workers stay refused unless a canary passes; if Codex events carry no page text, every Codex web claim is at best `unverified`.

## Key decisions & tradeoffs

- **Q1 scope**: cross-provider panel first (Codex host → Claude workers); multi-provider interop is the direction, not a deliverable. Gemini, DeepSeek, GLM and OpenCode move to the appendix.
- **Q2 no adapter refactor**: reuse the existing provider branches. Extract an adapter interface when a third provider is actually added; the provider-neutral manifest and claim schema are the durable contract.
- **Q3 local verification**: no runner-side fetcher, so no SSRF, DNS-rebinding or TLS-pinning surface. The cost is weaker citation strength (`retrieved` ≠ byte match), mitigated by labels and human spot-checks. Prompt injection is contained, not solved.
- **Q4 no disposable copy**: a copy does not stop reads of original paths (prior J2). Rely on Claude's `--restricted` working-directory confinement, proven by a live canary and checked per run from the stream-json tool calls.
- **Q5** the 429 fix is P0, separate.
- Cosmetic (accepted as a batch): mode name `panel`; only `cross_provider_panel` is implemented (`same_provider_panel` is defined and reserved); panel results never approve builds; concurrency 2 by default, 4 max; host-side synthesis; CLI-default model unless given, requested and observed recorded separately; the pipe/redaction refactor is out of scope.

## Assumptions

1. `--restricted` confines Claude `Read`/`Glob`/`Grep` to the working directories. — source: `claude --help` 2.1.280; **the live canary confirms it**.
2. `--allowedTools WebFetch` permits fetches without per-domain prompts under `dontAsk`, and `WebSearch`/`WebFetch` stay available under `--safe-mode`. **Unverified; the live smoke run gates it.**
3. In `-p` mode, `stream-json` requires `--verbose`, carries `tool_use`/`tool_result` blocks, and ends in a `result` event with `structured_output`, `usage.server_tool_use`, and `session_id`. — source: Claude Code CLI 2.1.280, to be confirmed by fixture capture
4. Codex 0.155.1 with ChatGPT auth, Claude 2.1.280 on claude.ai auth; both installed. The repo skill is installed for Codex at `~/.codex/skills/claudex-loop` and matches the working tree. — source: probes 2026-09-22
5. The runner is 561 lines, standard library only, CI on Linux/macOS/Windows. — source: repo, AGENTS.md

## Risks / open questions

- Existing Claude review/inspect mode runs without `--restricted`. Adding it there is a recommended follow-up, outside this plan (it changes review semantics).
- Assumptions 1–2 may fail on the current CLI. Then repo workers (1) or web workers (2) stay refused; the plan does not ship an unproven mode.
- WebFetch content processing may make most web claims `unverified`, weakening the panel's value. Measure this in the live run before promoting the mode in the README.
- Residual prompt injection through excerpts (see P1.8).
- Running on Windows needs the process-group kill for parallel children; CI covers it with the fake CLI.

## Out of scope

The adapter interface; Gemini, DeepSeek, GLM and OpenCode adapters; a runner-side URL fetcher; disposable repo copies; UID/SID lock sweeping; the pipe-capture/redaction refactor; any change to review, build, inspect or fallback semantics beyond P0; retries inside a panel run.

## Verification

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
python skills/claudex-loop/scripts/runner.py --help
git diff --check
```

Fake-CLI tests (no quota): two web workers and one repo worker launch with distinct session UUIDs, no `--resume`, and distinct child directories; captured web-worker stdin contains no plan body or repo path, and equals the `--dry-run` printout; launch with a missing or stale `--payload-sha256` is refused; argv for every worker contains `--restricted`, and a fake `claude --help` lacking it refuses the run; web `retrieved`/`unverified`/`mismatch`, including a quote that appears only in a `WebSearch` result (→ `unverified`) and a quote matching a different fetched URL (→ not `retrieved`); repo claim for a never-read path → `mismatch`, and a file edited after the worker's read still verifies against the read; repo locator escape → `mismatch`; an outside-path tool call is recorded, and an allowed outside read fails the run with no `panel.json`; unvalidated CLI version refuses repo workers without the override; every over-length field, an extra schema field, a claim for an unassigned question, and a `source_type` ≠ worker kind are rejected; spec errors (duplicate IDs, unknown question, <2 distinct-angle workers, out-of-range budgets) are refused before launch; aggregate deadline and a main-thread interrupt both leave no live child and cancel queued workers (fake CLI sleeps; concurrency 2 with 3 workers); `completed`/`partial`/`failed` rules each tested; `check_approval` rejects a completed panel record; `provider == host` and P1 Codex workers are rejected; only `completed` records carry `assurance`.

Live (separately authorized, disposable repo): the canary test, then one Codex-hosted panel run with two Claude web workers and one repo worker. Record CLI versions, the claim status distribution, and limitations in `VALIDATION.md`.

## Appendix — future providers (assessment only, no acceptance criteria)

Trigger for a new plan: a provider CLI is installed and a smoke test passes. The adapter interface is extracted in that same plan.
- **Gemini CLI**: headless JSON, sessions, native subagents; its read-only plan mode is documented as under development. Not installed.
- **DeepSeek**: the API offers JSON/tool calls with key billing; the Harness is a developer preview. Not installed.
- **GLM (Z.ai)**: officially usable through Claude Code or OpenCode. A bridge must record provider `glm` with harness `claude-code`, and must never mutate `~/.claude/settings.json` or be labeled Claude.
- **OpenCode**: installed at `~/.opencode/bin/opencode`; headless output, session identity, and read-only behavior are unvalidated.
Evidence links: see the superseded plan's "Primary evidence" (`../completed/2026-09-19-multi-provider-adversarial-research.md`) (accessed 2026-09-21; recheck at POC time).
