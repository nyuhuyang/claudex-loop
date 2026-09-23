---
status: superseded
created: 2026-09-19
archived: 2026-09-22
superseded_by: ../active/2026-09-22-cross-provider-research-panel.md
---

> **Superseded 2026-09-22** by `2026-09-22-cross-provider-research-panel.md` (scope narrowed via claudex-loop interrogation). Kept for its evidence links and provider assessment.

# Plan: Codex-only and Multi-provider Adversarial Research

## Goal

Determine whether Claudex Loop can run adversarial research using only Codex subscription usage, and define a safe path for adding Gemini, DeepSeek, and GLM without weakening evidence, permission, or assurance guarantees.

This is a research and architecture plan. It does not authorize implementation.

## Current-state findings

1. **Codex-only research is technically viable but is not a first-class Claudex Loop mode.** The local Codex CLI is authenticated with ChatGPT. Official OpenAI documentation says `codex exec` reuses stored CLI authentication, and ChatGPT login uses subscription access rather than API-key billing. Fresh Codex sessions and Codex subagents therefore consume Codex/ChatGPT usage. Each subagent consumes additional tokens.
2. **The current runner allows same-provider review only as a degraded fallback.** `PROVIDERS` contains only `claude` and `codex`; role resolution rejects host-as-reviewer; `--fallback-from` requires a validated unavailable other-provider result. This is correct for failure recovery but cannot express an intentional Codex-only panel.
3. **Research fan-out is policy without execution.** `references/research.md` defines launch counts, angle coverage, token estimates, and source discipline, but `runner.py` has no research/panel mode or fan-out scheduler. The review prompt also forbids delegation.
4. **Provider behavior is embedded in branches.** Command construction, result parsing, failure classification, model metadata, permissions, session identity, and Windows launch behavior assume exactly the Claude and Codex CLIs. Adding names to `PROVIDERS` would be unsafe.
5. **Fresh-session diversity is useful but weaker than provider diversity.** Multiple Codex sessions can use different prompts, roles, evidence angles, and context, but retain correlated model/provider blind spots. They must never be labeled cross-provider review.
6. **The live fallback classifier misses a real Claude quota response.** A review attempt returned a provider-owned envelope with `terminal_reason=api_error`, `api_error_status=429`, and “individual spend limit.” The runner classified it as `provider_failure` because it discards the structured fields and scans a shortened string. The fix must not make the model-authored `result` field authoritative: only provider-controlled status, error objects, process state, and stderr may authorize fallback.

## Proposed assurance model

Record independent dimensions instead of one overloaded label:

- `provider_diversity`: number and names of providers.
- `harness_diversity`: number and names of execution harnesses, recorded independently from providers.
- `session_independence`: `fresh`, `resumed`, or `mixed`.
- `assigned_prompt_diversity`: adversarial angles assigned by the coordinator; this does not prove independent reasoning.
- `self_reported_evidence_diversity`: distinct sources cited by workers; this does not prove the sources exist or support the claims.
- `assurance`: `cross_provider`, `degraded_same_provider`, `same_provider_panel`, `multi_provider_panel`, or `shared_harness_multi_provider_panel`.

An explicitly selected Codex-only panel uses `same_provider_panel`. A panel spanning two or more providers uses `multi_provider_panel` only when it also spans multiple harnesses; multiple providers behind one harness use `shared_harness_multi_provider_panel`. Provider and harness diversity are never inferred from model names. No panel label authorizes a build. Pre-launch/running and failed records carry only `attempted_assurance`; `assurance` is written only after successful completion. Existing fallback policy remains unchanged except for correcting the observed structured 429 classification.

## Recommended architecture

### 1. Provider adapters

Replace provider branches with a small adapter interface:

- Resolve executable and probe version/authentication.
- Declare capabilities: fresh session, resume, JSON/schema output, usage reporting, read-only enforcement, live source retrieval, build support, and subscription/API billing source.
- Build argv and isolated environment without editing global configuration.
- Preserve the complete provider-owned failure envelope, including status/code, `terminal_reason`, nested error objects, and process exit state. Normalize session, model, usage, response, and failure kind from this object.
- Classify availability only from fields the model cannot author: process status, provider status/error codes, provider-owned error objects, and stderr. Exclude normal response fields such as Claude `result` and Codex `agent_message`. Text matching is permitted only in provider-owned stderr/error fields. Preserve the exact raw event used for the decision.
- Fail closed when a requested capability is absent or experimental.

Keep role policy separate from transport. Role policy decides who may review; adapters only execute a chosen provider.

### 2. N-provider role policy

- Require an explicit reviewer and inspector once more than two providers are registered; never choose by tuple order.
- Persist the mapping resolved from the current invocation's explicit role arguments. Fallback requires the failed record's role map to equal this independently resolved map; only then derive primary/fallback expectations from the agreed mapping. A record can never define its own authorization.
- Keep `review`, `inspect`, and `panel` as distinct modes. Approval uses one allowlist: a completed `review` with `cross_provider` or `degraded_same_provider`. Every other mode, missing/`legacy_unspecified` value, panel label, and unknown future label is rejected. Legacy approval artifacts must be re-reviewed; there is no implicit compatibility bypass.

### 3. Research panel mode

Add a read-only `research` or `panel` mode that:

1. Accepts an explicit provider list, angle assignments, concurrency limit, and launch budget.
2. Starts every finder/reader in a fresh session; it never uses `--last`.
3. Creates one child artifact directory per launch and a parent manifest containing angle, provider, harness, session, model, exit code, usage, child path, disposable-copy root, and original repository root. No workers share output filenames. Worker paths must resolve inside the copy, are rewritten relative to the original root before synthesis, and are rejected if they escape the copy.
4. Uses bounded parallelism, an aggregate wall-clock budget, and a shared cancellation signal. Timeout, interrupt, or normal early stop terminates every live process group and preserves completed results.
5. Requires `live_source_retrieval` for web research. For Codex, the initial implementation must explicitly enable and observe hosted web search (for example `--search` / `web_search` events) while retaining a read-only local sandbox. Without verified retrieval, refuse web-research mode or label a repository-only run `no_live_sources`; do not accept external citations.
6. Separates repository-only workers from web-only workers. Web workers receive research questions and allowlisted public context, never repository content; sending repository-derived text or queries to a search provider requires explicit user opt-in. Record every issued query and fetched URL in the child manifest. Retrieved pages are untrusted data for every actor, including the host, and cannot alter role, schema, assigned angle, tool policy, authorization, or confidence rules.
7. Uses a panel-specific prompt, claim schema, validator, and assurance mapping. Each claim contains question ID, claim, source URL, locator, short excerpt, source type, confidence, and limitation.
8. Verifies every locator used by synthesis outside any privileged agent context. The standard-library fetcher accepts HTTPS only by default; HTTP requires an explicit flag. It sends no cookies, credentials, or authorization headers, ignores ambient proxy settings unless explicitly configured, caps redirects/bytes/wall-clock time, resolves before connecting and on every redirect, and rejects loopback, link-local, RFC1918, CGNAT, ULA, multicast, metadata, and other non-public addresses. The locator must already appear in that worker's query/fetched-URL manifest. Verification records the final URL and resolved IP.
9. The verifier normalizes bytes and matches the claimed excerpt; only the outcome, locator, content hash, and matched-region coordinates reach the host. Raw page content stays in an owner-only artifact for human inspection and is never injected into the host prompt. If semantic inspection is unavoidable, use a separate fetch-only worker with no repository, plan, build, or write access and an output schema limited to verification facts. The originating worker and its panel peers cannot verify their claims.
10. Records `verified`, `unverified`, or `mismatch`. `unverified` retains the claim with a limitation. `mismatch` removes the claim from synthesis, flags the worker, and triggers verification of all its remaining claims. Assigned angles and self-reported URLs never raise assurance by themselves.
11. Builds a coverage matrix and records disagreements before synthesis.
12. Runs synthesis separately and preserves every sanitized result and provider diagnostic plus hashes/metadata for restricted raw fetch artifacts.

For Codex-only mode, orchestrating multiple explicit `codex exec` processes is preferable to asking one opaque Codex turn to decide its own subagent fan-out. It makes launch counts, session IDs, failures, usage, and angle assignments auditable. Codex native subagents can remain an optional backend after their event/audit contract is tested.

## Provider assessment and sequence

### Codex — implement first

- Mature headless JSONL, JSON Schema output, read-only sandbox, explicit session IDs, resume, and usage events.
- ChatGPT authentication consumes Codex subscription usage; API-key authentication is separately billed and must be recorded.
- Add an intentional `same_provider_panel` policy rather than abusing fallback.

### Gemini — second

- Official CLI provides headless JSON/stream-JSON, session metadata, resume, cached authentication, subscription/free/API quota choices, and native subagents.
- Read-only plan mode exists, but official documentation says it is still under development and may transition to automatic execution after plan exit. The adapter must use an isolated settings file, restrict core tools to file read/search, exclude mutators, and prove no writes in disposable fixtures before panel use.
- Gemini CLI is not currently installed on this machine, so only documentation-level feasibility is established.

### DeepSeek — research adapter before code inspector

- The official API supports JSON output and tool calls, but API access uses a key/balance and does not itself read a repository. A research adapter can send a bounded evidence bundle and validate JSON locally.
- The official DeepSeek Harness has headless agents, sessions, subagents, and sandboxes, but is explicitly developer preview. Its product headless command emits final text; canonical JSONL is currently test infrastructure rather than a stable product contract.
- Treat Harness support as experimental until versioned output, resume identity, and read-only enforcement are live-tested. Do not rely on the unrelated local `deepseek` skill as a Claudex approval authority without adding the same audit contract.

### GLM — isolated bridge POC, then native adapter

- Z.ai officially supports GLM Coding Plan in Claude Code and OpenCode and exposes separate coding-plan and prepaid/API endpoints.
- The lowest-effort POC can invoke Claude Code against GLM through a temporary isolated configuration/environment, reuse structured-output parsing, and record provider as `glm`, endpoint class, observed model, and billing source. Never mutate `~/.claude/settings.json` or call the result Claude.
- OpenCode is a promising native harness, but its headless output, session identity, schema enforcement, and read-only behavior need direct validation. ZCode should not be used until its headless interface is officially documented.

## Security and honesty requirements

- Never pass API keys on argv or write them to artifacts; inherit only named credential variables.
- Isolate tools and MCP for every read-only mode. Prefer provider-supported per-invocation flags; otherwise use a temporary config root that references an existing OS keychain/documented credential store without copying credentials. The final rung is an explicit user-maintained allowlist file asserting named MCP servers are read-only; record that assertion and residual risk verbatim, perform no name-based capability inference, and reject servers absent from the list. If a provider can enumerate tools, additionally reject tools outside a declared read-only tool set. Temporary roots contain no credentials, use restrictive permissions, receive best-effort cleanup, and carry current-UID owner plus live-process locks; startup sweeps remove only same-UID roots whose owner is no longer alive and never run during active fan-out.
- Create artifact directories with owner-only permissions. Replace direct file-descriptor output capture with concurrently drained pipes. Structured provider output must flow through a parent-mediated event/stdout channel rather than child-written response files; parse in memory, redact only string leaves using adapter-injected credential values and unambiguous provider-key patterns, then persist. Record pattern ID, count, and logical location in a redaction manifest; any hit in a validated review response fails loudly instead of silently changing evidence. Unstructured stderr uses an overlap-aware streaming redactor. An adapter that cannot provide parent-mediated output declares the capability gap and cannot handle credential-bearing modes.
- Use a base-free, Git-optional repository fingerprint for read-only modes. For review, record pre/post fingerprints and changed paths in structured `readonly_mutation`; exclude host-owned plan/log paths and allow the round to finish, but approval rejects nonempty `readonly_mutation` unless an explicit recorded override is supplied. For inspect, retain hard failure on tracked and untracked-non-ignored changes and record the ignored-path blind spot.
- Run panel workers in an owner-only disposable copy outside the checkout. Copy regular tracked and untracked-non-ignored files by default; omit `.git`, omit symlinks rather than following or recreating them, and record both limitations. Include checked-out submodule work trees through the same bounded copy policy and record each gitlink commit; fail if a required submodule is absent. Enforce entry/byte limits and fail loudly on limit or containment violations. Exclude ignored/credential-bearing paths and record this coverage limitation; do not duplicate `.env`, keystores, package credentials, service-account files, databases, or caches. Compare pre/post fingerprints for the copied scope. The copy uses live-process ownership locks, best-effort cleanup, and same-UID dead-owner startup sweeping.
- Bind results to plan hash, repository path, provider identity, requested/observed model, adapter version, and evidence snapshot.
- A provider-specific quota failure may trigger only an explicitly configured policy; preserve the failed attempt and new assurance level.
- Do not equate different harnesses around the same model with provider diversity.
- Do not claim subscription usage when authentication mode is unresolved.

## Delivery phases and acceptance criteria

### Phase A — adapter and execution-safety refactor

- Existing Claude/Codex review/build/inspect semantics remain unchanged except for corrected structured failure classification, read-only mutation detection, provider-config isolation, and strict rejection of legacy/missing-assurance approval artifacts.
- Isolate Claude and Codex review/inspect tooling in Phase A. Use per-invocation MCP controls where available (including Claude's current safe/strict flags), otherwise an isolated credential-free config root, otherwise an audited read-only MCP allowlist with a recorded residual limitation. Never silently disable the validated cross-provider path, inherit a write-capable MCP entry, or duplicate credentials.
- Replace direct stdout/stderr file-descriptor capture with deadlock-safe concurrent pipe readers. For Codex, obtain the final response from JSONL events rather than `-o reply.txt`; other adapters must also use parent-mediated structured output. Parse before leaf-level redaction, persist only sanitized events/responses, and fail on redaction inside validated review evidence. Preserve stdin, timeout, interrupt, process-group kill, and Windows behavior. Tests cover multi-megabyte output, a fake secret split across stderr chunks, structured credential leaves, absence of raw reply files, best-effort cleanup, and a live-lock root that sweeping must preserve.
- Adapter contract tests cover capability rejection, malformed events, model identity, auth/billing metadata, live retrieval, isolated configuration, redaction, and scoped read-only mutation detection for Git and non-Git roots.
- Preserve the complete provider failure object through normalization. A Claude envelope containing provider-controlled `api_error_status=429` plus `terminal_reason=api_error` is recorded as `provider_unavailable` and becomes fallback-eligible.
- A failed Claude event whose model-authored `result` merely quotes “individual spend limit,” without provider-controlled unavailability fields, remains `provider_failure` and ineligible. Ordinary rejection, malformed output, repository mutation, and interruption also remain ineligible.
- Every provider adapter maps its documented auth, quota, rate-limit, balance, service, and timeout signals explicitly instead of sharing one global substring list.
- With a three-provider registry, reviewer/inspector selection must be explicit and the fallback validator must use the provider and roles in the failed record.
- Fallback tests retain the independently resolved invocation-to-record roles equality check and reject self-declared same-provider roles.
- Running and failed records contain `attempted_assurance` and no completed `assurance`.
- Approval tests enforce the allowlist: accept only completed `review` records with `cross_provider` or `degraded_same_provider`; reject missing/`legacy_unspecified`, every panel label, every non-review mode, and an unknown future label. They also reject nonempty `readonly_mutation` unless an explicit override is supplied and recorded. Document re-review as the legacy migration.
- Update `AGENTS.md` fallback invariants, `references/runtime.md` classification/configuration-isolation/migration/assurance rules, and `README.md` approval migration and Codex MCP statements in the same phase.

### Phase B — Codex-only panel

- A two-angle fixture launches two fresh Codex sessions with distinct UUIDs and no resume flag.
- A parent manifest points to distinct, collision-free child artifact directories, records per-run usage plus original/copy roots, and maps copy-relative paths back to original-relative paths while rejecting escapes.
- A single-provider panel says `same_provider_panel`. Multiple providers across multiple harnesses say `multi_provider_panel`; multiple providers through one harness say `shared_harness_multi_provider_panel`. All use mode `panel` and are always rejected by build approval. A Phase D fixture covers Claude plus GLM through Claude Code. Completed degraded same-provider `review` remains approval-eligible.
- Fake-CLI fixtures prove flag construction, search-event parsing, and fail-closed behavior when provider-owned search events are missing; fixtures alone never unlock web-panel use. Each retrieval-capable provider additionally needs one recorded live smoke run with observed search events and mechanically verified locators in `VALIDATION.md`. A provider without retrieval refuses web mode or emits `no_live_sources` for repository-only research.
- Web and repository context run in separate workers by default. Manifests record queries and fetched URLs. A fetched page that attempts to override the claim schema is treated as untrusted and rejected; repository-derived outbound queries require explicit user opt-in. URL-verifier fixtures reject metadata/private targets and public redirects to private targets and enforce byte/time/redirect limits.
- Panel launches use isolated tooling/MCP controls in an owner-only disposable copy containing only the declared regular-file scope. Copy fixtures cover containment, `.git`/symlink omission, size/entry caps, checked-out and absent submodules, credential exclusions, live locks, and cleanup. Pre/post fingerprints prove no mutation within the copied scope; ignored-path, `.git`, and symlink exclusions are named limitations.
- Fan-out never exceeds printed launch, concurrency, and wall-clock budgets. Cancellation leaves no child process alive.
- Panel claims use their own schema and validator rather than `REVIEW_SCHEMA`.
- Update `SKILL.md` tunables/modes/assurance vocabulary, `references/build.md` approval eligibility, `references/research.md` enforced-versus-advisory budget language, and `README.md` panel modes/provider-versus-harness diversity/assurance vocabulary.

### Phase C — Gemini POC

- Disposable-repository smoke tests prove JSON parsing, session identity, quota failure classification, and zero filesystem mutation.
- Live source retrieval is demonstrated through provider-owned events, and the out-of-context mechanical verifier records locator outcomes, hashes, and match coordinates without exposing raw pages to the privileged host.
- Any inability to enforce read-only operation or source retrieval blocks web-panel use.

### Phase D — DeepSeek and GLM experimental adapters

- Direct API/provider credentials stay out of prompts, argv, persisted stdout/stderr, event logs, manifests, result records, provider-written reply files, and disposable copies. Fake-secret fixtures verify parent-mediated capture, leaf-level redaction, loud review-evidence failure, credential-path exclusion, and owner-only permissions.
- Each adapter declares billing source and unsupported capabilities.
- Panel use remains disabled until live tests establish structured output, identity, cancellation, read-only evidence access, and source retrieval. These adapters do not gain build approval authority.

## Verification

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
python skills/claudex-loop/scripts/runner.py --help
git diff --check
```

Add fake-CLI contract suites for every adapter. Live smoke tests must use disposable repositories, explicit models, minimal prompts, and separately authorized credentials; record versions and limitations in `VALIDATION.md`.
Update `VALIDATION.md`'s date, live-check table, and test count with every phase, or remove the prose count and rely on command output. Reconcile canonical documentation links in skill references during Phase A.

## Primary evidence

- OpenAI Codex non-interactive mode: https://developers.openai.com/docs/non-interactive-mode?site_locale=en
- OpenAI Codex authentication: https://developers.openai.com/docs/auth?site_locale=en
- OpenAI Codex subagents: https://developers.openai.com/docs/agent-configuration/subagents?site_locale=en
- OpenAI Codex web search: https://developers.openai.com/docs/web-search?surface=cli&site_locale=en
- Gemini CLI headless mode: https://geminicli.com/docs/cli/headless/
- Gemini CLI authentication and quota: https://geminicli.com/docs/get-started/authentication/ and https://geminicli.com/docs/resources/quota-and-pricing/
- Gemini CLI subagents: https://geminicli.com/docs/core/subagents/
- DeepSeek JSON output and tool calls: https://api-docs.deepseek.com/guides/json_mode/ and https://api-docs.deepseek.com/guides/tool_calls/
- DeepSeek Harness headless and safety: https://github.com/deepseek-ai/deepseek-harness/tree/master/examples/headless-agent and https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md
- Z.ai GLM Coding Plan and integrations: https://docs.z.ai/devpack/overview, https://docs.z.ai/devpack/tool/claude, and https://docs.z.ai/devpack/tool/opencode

Provider documentation was accessed on 2026-09-21. External links and capability claims must be rechecked during the corresponding live POC; repository validation does not verify them.

## Non-goals

- No implementation, installation, credential setup, paid API call, or live third-party model invocation in this research pass.
- No claim that same-provider panels match cross-provider defect discovery.
- No generic adapter that hides provider capability differences or silently downgrades permissions.
