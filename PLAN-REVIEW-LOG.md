# Plan Review Log: Claude-only fallback for claudex-loop
Phases 0-1 (recon + interrogation) complete — plan locked with the user. MAX_ROUNDS=5.
Reviewer: Codex (codex-cli 0.150.1, config model = gpt-5.6-sol, reasoning effort xhigh).

## Round 1 — Codex

The plan is not sound enough to implement. Material findings:

1. **Critical — Claude “read-only” is not airtight.** The plan equates an allow/deny list with Codex’s filesystem sandbox ([PLAN.md:75](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:75)). `--safe-mode` disables customizations, not filesystem writes; the denylist omits other command-capable tools, and managed policy settings still apply. One refused `Write` attempt does not prove the invariant claimed in assumption 8.

   Fix: Use `--restricted --tools "Read,Grep,Glob" --permission-mode dontAsk --strict-mcp-config --safe-mode`, constrain the working directory, and describe this honestly as tool-level protection unless an OS-enforced read-only mount is added.

2. **Critical — the fallback’s own availability is never checked.** Locally, `codex login status` succeeds, but `claude auth status` currently exits 1 with `"loggedIn": false`; therefore this exact environment could select the Claude fallback and immediately fail despite Claude Code itself running.

   Fix: Preflight `claude --version`, required flag support, `claude auth status`, and model availability before selecting or offering the Claude branch.

3. **High — the Codex detector is not executable detection logic.** `codex --version` plus a comment does not parse or compare `codex-cli 0.150.1` against `0.130`, and the plan ignores the available cheap `codex login status` command while calling its existence an open question ([PLAN.md:20](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:20), [PLAN.md:256](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:256)).

   Fix: Specify deterministic numeric version parsing, run `codex login status`, validate override values, and retain launch-time handling for expired credentials.

4. **High — detection goes stale and `REVIEWER` conflates preference with capability.** A probe before lengthy Phases 0–1 can be obsolete by Phase 2, and much more so by Phase 3; additionally, forcing `reviewer=claude` incorrectly suppresses `codex-build` even when Codex is fully available ([PLAN.md:111](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:111)).

   Fix: Track `REVIEWER_SELECTION` separately from `CODEX_CAPABLE`, revalidate capability immediately before Phases 2 and 3, and never change an established reviewer session silently.

5. **High — unauthenticated Codex does not actually trigger the promised automatic fallback.** The goal promises an automatic end-to-end fallback ([PLAN.md:6](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:6)), but Round 1 merely “offers” it, while later provider failures stop outright ([PLAN.md:89](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:89)).

   Fix: Define exact transitions: auto mode retries Round 1 with Claude without incrementing the round, forced Codex stops, and post-Round-1 provider loss requires an explicitly logged restart because continuity cannot be preserved.

6. **High — failure classification is incompatible with the unchanged Codex command.** Stderr is discarded, so `<reason>` cannot be reported; moreover, the Codex pipeline’s status is normally `grep`’s status, which can succeed after `thread.started` even if Codex later fails.

   Fix: Capture Codex stdout, stderr, and its actual exit status separately without a live `grep` pipeline, then parse the saved event stream and surface a sanitized error.

7. **High — fixed `/tmp` filenames create races and a symlink vulnerability.** Concurrent loops overwrite each other, stale Codex output can be mistaken for a new verdict, and `> /tmp/claude-verdict.txt` follows a pre-existing symlink and truncates its target before Claude starts ([PLAN.md:54](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:54)).

   Fix: Create a private per-run directory with `umask 077` and `mktemp -d`, use round-specific files, validate freshness/non-emptiness, and clean up with a trap.

8. **High — verdict parsing does not enforce the stated contract.** Searching the last line for a token accepts suffixes, both verdicts, quoted instructions, or other malformed output; trailing blank lines are also unspecified. Appending the critique before validation leaves failed attempts looking like completed rounds.

   Fix: Require exactly one verdict and an exact last non-empty line matching `^VERDICT: (APPROVED|REVISE)$`, allow one format-only repair without consuming a round, and log failed attempts explicitly.

9. **High — the three-finding quota incentivizes hallucinated defects.** A sound plan may not contain three real flaws, so the reviewer is ordered to manufacture findings; the claim that same-family reviewers are more agreeable is also unverified ([PLAN.md:137](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:137)).

   Fix: Replace the quota with a required coverage checklist and permit zero findings when each area was examined and approval is justified.

10. **High — Phase 3’s Claude reviewer cannot perform the promised diff inspection.** With Bash denied, it cannot run `git status`, `git diff`, or `git show`; merely reading the current tree cannot distinguish the build from the base, and the plan gives no safe transport for large, untracked, or binary diffs ([PLAN.md:105](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:105)).

   Fix: Have the orchestrator produce a bounded changed-file manifest and diff including untracked files, provide them through a private readable input, and define handling for large and binary changes.

11. **High — `PLAN_FILE` is a fake tunable.** Both existing skills and the proposed resume prompt hardcode `PLAN.md`, while revisions use `PLAN_FILE`; a non-default value therefore reviews one file and edits another ([PLAN.md:65](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:65), [codex-review/SKILL.md:74](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/skills/codex-review/SKILL.md:74)).

   Fix: Resolve and quote one plan path at startup and interpolate it into every initial prompt, resume prompt, inspection prompt, log entry, and build handoff.

12. **Medium — the literal timeout regresses current portability guidance.** The new branch uses `timeout 600`, although the existing skill correctly notes that stock macOS has only `gtimeout` when coreutils is installed ([claudex-loop/SKILL.md:202](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/skills/claudex-loop/SKILL.md:202)); the UUID fallback also remains unresolved.

   Fix: Define a portable timeout/UUID preflight and use the host tool-call timeout when neither `timeout` nor `gtimeout` exists.

13. **High — user-facing documentation will remain materially false.** The plan leaves categorical “two models,” “rival model,” and “whoever made it never checks it” claims unchanged ([README.md:5](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/README.md:5), [README.md:58](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/README.md:58)); both skill frontmatters and resolution messages likewise remain Codex-only. “No memory” also contradicts the promised cross-round memory unless qualified as “no inherited primary-session memory.”

   Fix: Qualify all frontmatter, phase tables, safety text, resolution messages, manifests, and invariants as Codex-default behavior and state precisely what isolation the Claude fallback retains.

14. **Medium — “single source of truth” is knowingly three duplicated copies.** The plan calls the notice single-sourced and then admits prose cannot prevent those copies drifting ([PLAN.md:117](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:117), [PLAN.md:264](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:264)).

   Fix: Put the canonical protocol/notice in one shared file referenced by both skills and README, or add a deterministic consistency check to the proof procedure.

15. **High — the verified/unverified split overstates the evidence.** A single rejected `Write` does not verify global read-only behavior; reviewer self-report does not prove hooks were absent; two unrelated plugin manifests do not establish platform lifecycle limits; and the proof omits auth failure, malformed verdicts, concurrency, non-default paths, Phase 3, invalid overrides, and mid-session capability changes.

   Fix: Rewrite each assumption to separate documented behavior, narrowly observed behavior, and inference, record exact commands/versions/results, and expand proof into a branch-and-failure acceptance matrix.

No repository files were modified during this review.

VERDICT: REVISE
### Claude's response

Arbitration: 14 of 15 findings accepted, 1 factual claim rejected (its recommendation still adopted).

**Rejected — finding 2's factual claim.** Codex asserted `claude auth status` exits 1 with
`"loggedIn": false` on this machine. Verified directly: it exits 0 with `"loggedIn": true`,
`"authMethod": "claude.ai"`, `"subscriptionType": "team"`. Codex most likely probed from inside
its own read-only sandbox where the keychain was unreadable. The *recommendation* — preflight the
Claude branch before selecting it — is accepted regardless; the plan genuinely never checked it.

**Accepted and escalated — finding 1.** Codex was right and understated it. Probing the reviewer
session's actual tool inventory returned: Agent, Glob, Grep, ListAgents, Read, ReportFindings,
ScheduleWakeup, ShareOnboardingGuide, Skill, ToolSearch, Workflow, plus deferred CronCreate,
CronDelete, CronList, DesignSync, EnterWorktree, ExitWorktree, Monitor, PushNotification,
RemoteTrigger, SendMessage, TaskOutput, TaskStop, WebFetch, WebSearch. `Agent` alone defeats the
denylist entirely — a spawned subagent carries its own tool set including Write and Bash.
Assumption 8 proved only "the Write tool was refused", never "the session cannot write".
Verified replacement: `--restricted --tools "Read,Grep,Glob" --strict-mcp-config --safe-mode
--permission-mode dontAsk` yields exactly three tools (Glob, Grep, Read), still reads repo files,
and still resumes across rounds. All three verified 2026-08-31.

**Accepted — 3, 4, 5, 6, 7, 8, 10, 11, 12, 14, 15.** All correct as stated. Notably `codex login
status` does exist and exits 0 ("Logged in using ChatGPT"), which closes what the plan had listed
as an open question. Findings 6 and 11 describe defects that pre-exist in the current skills; the
revision fixes them on the paths it touches and records the rest as untouched pre-existing debt.

**Accepted — 9, with a flag to the user.** The three-finding quota is replaced by a coverage
checklist permitting zero findings. This reverses a cosmetic item the user accepted earlier in
Phase 1; it is called out at the next human gate rather than changed silently.

**Partially accepted — 13.** Accepted: both skills' frontmatter `description`, the Resolution
messages, and the imprecise "no memory" wording are functional text and are corrected. Rejected:
rewriting the README hero, the mermaid diagram, the phase table, and the "whoever made the thing
never checks the thing" invariant. The user explicitly locked Q4 at minimal-honest-change with
those assets untouched, on the grounds that Codex remains the default path and diluting the
headline for a downgrade path is a net loss. Reaffirming that decision, not deferring to the
reviewer.

**Partially accepted — 14.** The "single source of truth" label is dropped as false; the notice
stays duplicated in three places because Q2 explicitly rejected extracting a shared protocol file.
A consistency check is added to the proof matrix instead.

## Round 2 — Codex

Most Round-1 findings were addressed well. I withdraw the incorrect local-auth claim, and I will not re-litigate the explicitly locked README marketing scope. Material runtime defects remain:

1. **Critical — shell state cannot survive separate Claude Code Bash calls.** `RUN_DIR`, `TIMEOUT_CMD`, `run_reviewer`, and `SID` are created as shell-local state; the initialization shell’s `EXIT` trap immediately deletes `RUN_DIR`, and later review rounds cannot access the function or SID ([PLAN.md:82](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:82), [PLAN.md:143](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:143)).

   Fix: Persist the printed absolute `RUN_DIR` and SID as orchestrator state/files, use a persistent helper or inline status capture on every call, and clean up explicitly only after the workflow finishes.

2. **Critical — the no-timeout fallback executes `600` as the command.** When `TIMEOUT_CMD=""`, `run_reviewer $TIMEOUT_CMD 600 claude ...` collapses to `run_reviewer 600 claude ...`, contradicting the promise to rely on the host timeout ([PLAN.md:132](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:132), [PLAN.md:185](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:185)).

   Fix: Construct the timeout prefix conditionally as an argument array, omitting both the timeout executable and `600` when host timeout is used.

3. **High — output filenames and format-repair state are internally inconsistent.** The plan defines `verdict-r<n>.txt`, but `run_reviewer` writes `out-r<n>`; the Claude command provides no separate verdict path, and a repair response risks overwriting or replacing the original full critique ([PLAN.md:88](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:88), [PLAN.md:112](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:112), [PLAN.md:203](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:203)).

   Fix: Define exact per-attempt paths for original critique, repair verdict, stderr, events, and status, then append the original critique plus the validated repaired verdict without overwriting either.

4. **High — alternate-provider capability can still be stale, and Phase 3 selection is undefined.** Before Round 1 the plan re-probes only the selected reviewer, then may switch to an “other capable reviewer” based on the old Phase-0 result; it also never says whether a fresh Phase-3 inspection should retain Phase-2 selection or return to newly available default Codex ([PLAN.md:61](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:61), [PLAN.md:71](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:71)).

   Fix: Re-probe both providers before each phase boundary, freeze provider choice for the Phase-2 session, and specify a separate deterministic selection rule for the fresh Phase-3 inspector.

5. **High — the failure transition table is not exhaustive.** It covers Round-1 auth/model launch failures but not timeouts, network failures, exit-0 empty output, or a second malformed-verdict failure, although outcome handling classifies all of those as failed rounds ([PLAN.md:73](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:73), [PLAN.md:201](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:201)).

   Fix: Add a catch-all transition for every failed Round-1 attempt and explicitly state which failures permit provider fallback versus mandatory stop.

6. **Critical — the Phase-3 diff commands omit the actual uncommitted build.** `git diff "$BASE_COMMIT"..HEAD` compares commits; before the human commit gate, `HEAD` normally still equals `BASE_COMMIT`, so tracked working-tree changes produce an empty patch, and `BASE_COMMIT` is never captured or persisted ([PLAN.md:229](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:229)).

   Fix: Capture and persist `BASE_COMMIT=$(git rev-parse HEAD)` immediately before building, then use `git diff --stat "$BASE_COMMIT" --` and `git diff --binary "$BASE_COMMIT" --` to include staged and unstaged tracked changes.

7. **High — large-diff handling silently converts cross-inspection into partial inspection.** “Largest N files” leaves `N` undefined, may skip small security-critical files, and permits reporting inspection complete despite explicitly uninspected changes ([PLAN.md:239](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:239)).

   Fix: Chunk and inspect every textual changed file, or mark the inspection incomplete and require an explicit logged human opt-out before reaching the final gate.

8. **Medium — the downgrade notice still overstates hook isolation.** The plan correctly admits managed enterprise settings remain active, then categorically promises “no hooks”; managed hooks/settings are precisely the exception that prevents that guarantee ([PLAN.md:159](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:159), [PLAN.md:256](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:256)).

   Fix: Say “no user/project custom hooks; managed enterprise settings may still apply” everywhere the isolation guarantee appears.

9. **Medium — three acceptance cases do not test what they claim.** A non-zero `codex login status` is caught by the pre-Round-1 probe rather than testing launch-time fallback; masking only `timeout`, `gtimeout`, and `uuidgen` still leaves `/proc` or Python UUID sources; and dynamic sanitized reasons cannot be byte-identical across notice copies ([PLAN.md:323](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:323), [PLAN.md:331](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:331), [PLAN.md:332](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:332)).

   Fix: Simulate failure after a successful probe, mask every UUID source while separately testing host-timeout behavior, and compare the static notice template before reason substitution.

VERDICT: REVISE
### Claude's response

All 9 accepted, none rejected. Codex withdrew its round-1 auth claim unprompted and declined to
re-litigate the locked README scope — both correct.

Finding 1 is fatal to the round-1 design and I should have caught it: Claude Code's Bash tool
starts a fresh shell per call (working directory persists, shell state does not). `RUN_DIR`,
`SID`, `TIMEOUT_CMD`, and the `run_reviewer` function cannot survive between rounds, and
`trap 'rm -rf "$RUN_DIR"' EXIT` would delete the scratch directory the instant the initializing
call returned. The revision drops shell-persistent state entirely: the orchestrator captures the
absolute paths and ids as literals — exactly how the existing skill already handles `THREAD_ID` —
records them in `LOG_FILE`, interpolates them verbatim into later calls, and cleans up explicitly.
`umask 077` is likewise dropped as non-persistent; `mktemp -d` already yields a 0700 directory,
which protects the files inside it.

Finding 6 is the second real bug: before the human commit gate `HEAD` still equals `BASE_COMMIT`,
so `git diff "$BASE_COMMIT"..HEAD` is empty and the inspector would review nothing while reporting
success. Corrected to `git diff "$BASE_COMMIT" --`, with `BASE_COMMIT` captured before the build
and persisted.

Finding 2 is a plain empty-variable bug (`$TIMEOUT_CMD` unset makes `600` the command). Replaced
with two literal command forms selected by the preflight rather than a spliced prefix.

Finding 4 additionally exposed something neither of us had specified: the Phase-3 inspector must be
chosen by WHO BUILT, not by the Phase-2 reviewer. Codex-built code is already verified by Claude
inside `codex-build`; Claude-built code should be inspected by Codex when capable. Stated
explicitly now.

Findings 3, 5, 7, 8, 9 accepted as written. Finding 8 matters more than "medium" here: this machine
is on a Team plan (`"subscriptionType": "team"`, org Rancho BioSciences), so managed enterprise
settings are a live possibility rather than a hypothetical, and the isolation wording is corrected
everywhere it appears.

## Round 3 — Codex

The nine Round-2 findings are addressed. New material problems remain:

1. **High — `LOG_FILE` is being used as trusted executable state.** A resumed orchestrator recovers `RUN_DIR` and session IDs from a mutable repo file, then eventually executes `rm -rf <RUN_DIR>`; editing or planting that log can redirect cleanup or resume the wrong reviewer session ([PLAN.md:24](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:24), [PLAN.md:120](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:120)).

   Fix: Treat the log as audit-only; before reuse or deletion, require a canonical path under the system temp root, current-user ownership, mode 0700, an expected name prefix, and a run-marker file.

2. **High — `CLAUDE_CAPABLE` still excludes required fallback dependencies.** Claude can pass its CLI/auth/flag probes yet lack every UUID source; `mktemp` can also fail, so the workflow may select Claude and complete Phases 0–1 before discovering the selected branch cannot run ([PLAN.md:53](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:53), [PLAN.md:154](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:154)).

   Fix: Include UUID-source and private-scratch creation checks in `CLAUDE_CAPABLE` during every provider probe, cleaning up the probe directory immediately.

3. **High — format repair can turn “no review occurred” into a valid verdict.** The motivating failure is a reviewer refusing to review, but the repair then demands only a verdict line; it can produce `APPROVED` without ever supplying the required coverage or substantive analysis ([PLAN.md:254](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:254), [PLAN.md:259](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:259), [PLAN.md:351](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:351)).

   Fix: Permit format repair only after confirming `a1` contains a substantive review and, on the Claude path, conclusions for every required coverage area; otherwise classify `a1` as a failed attempt.

4. **Critical — `BASE_COMMIT` still does not isolate the build being inspected.** By Phase 3, `PLAN.md`, `LOG_FILE`, and possibly pre-existing user changes are already uncommitted, so `git diff <BASE_COMMIT>` mixes those with Claude’s implementation and cannot establish which hunks the builder introduced ([PLAN.md:286](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:286), [PLAN.md:297](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:297)).

   Fix: Capture a complete pre-build worktree baseline—tracked diff, status, and untracked-file hashes—and give the inspector both pre- and post-build states so it reviews only the build delta.

5. **Medium — untracked-file materialization is not safe for real filenames or file types.** “List and copy their contents” leaves spaces, newlines, symlinks, FIFOs, directories, and oversized files undefined; line-oriented output can corrupt the manifest or make the implementation choose unsafe shell expansion ([PLAN.md:306](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:306)).

   Fix: Specify a NUL-delimited enumeration, quoted path-preserving copies of regular files only, explicit handling for symlinks/special files, and per-file size limits.

6. **Medium — the proof matrix does not exercise the two newest trust boundaries.** It lacks a test that state survives genuinely separate Bash calls without trusting a modified log, and its Phase-3 case starts from an unspecified worktree rather than one already dirty with plan/log and user changes ([PLAN.md:389](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:389)).

   Fix: Add adversarial log-tampering/cleanup tests and a Phase-3 case with pre-existing tracked and untracked changes that must be excluded from the builder delta.

VERDICT: REVISE
### Claude's response

All 6 findings accepted. Two of the proposed *fixes* rejected in favour of simpler ones that
remove the hazard instead of validating around it.

**Finding 1 — accepted, fix simplified.** Codex proposed guarding the log-recovered path with five
checks (temp-root canonicalisation, ownership, mode 0700, name prefix, run-marker). The cheaper and
safer answer is to delete the dangerous operation: never `rm -rf` a path read back from a file. The
orchestrator cleans up only a `RUN_DIR` it captured in the current session; if the session is gone,
it cleans up nothing and the OS temp reaper handles it. The log keeps the path as audit text only,
explicitly marked non-executable. Fewer moving parts, and no validation logic that can itself be
wrong.

**Finding 4 — accepted, fix redirected to an existing house mechanism.** Codex is right that by
Phase 3 the worktree is already dirty with `PLAN.md`, `PLAN-REVIEW-LOG.md`, and possibly unrelated
user edits, so `git diff <BASE_COMMIT>` mixes them into the build delta. Its proposed fix (capture a
full pre-build worktree baseline including untracked-file hashes, hand the inspector both states) is
a new subsystem. `codex-build` already solves this with a **clean-tree gate**: dirty worktree ->
stop, commit or stash first. Extending that same gate to the Claude-built path makes
`git diff <BASE_COMMIT> --` exactly the build delta with no baseline machinery at all. Adopted.

**Finding 3 — accepted, and it invalidates a mechanism I introduced.** The format repair was added
because a reviewer refused to emit a verdict; Codex correctly points out the repair would then
launder that same refusal into a clean `APPROVED`. Repair is now gated on `a1` already containing a
substantive review — and on the Claude path, conclusions for every required coverage area. A refusal
is a failed attempt, never a repairable one.

**Findings 2, 5, 6 — accepted as written.** Finding 2 in particular closes the same class of hole as
round 1's finding 2: selecting a provider without proving the whole branch can run.

Convergence note: 15 -> 9 -> 6 findings. Findings 3 and 4 are material; 5 is hardening against
hostile filenames. This is round 4 of MAX_ROUNDS=5.

## Round 4 — Codex

Not implementable yet. The read-only Claude flag set is now honestly scoped and I see no direct write path. The verdict-repair gate is also substantially fixed. Material control-flow and evidence defects remain.

1. **High — cleanup instructions still contradict the audit-only rule.** The plan says persisted literals let a resumed session “recover” them, then forbids treating the log as executable state ([PLAN.md:22](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:22), [PLAN.md:30](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:30)). The substitution is safer than validation for the original log-tampering threat, but cleanup only after the final gate also leaves every earlier STOP orphaned, and an OS temp reaper is not guaranteed.

   Fix: Remove all log-recovery language, clean the session-captured directory on every controlled terminal path, and document crash-orphan retention instead of promising OS cleanup.

2. **Critical — the clean-tree substitution immediately invalidates its own baseline.** After requiring an empty worktree, the plan records `BASE_COMMIT` by writing to `LOG_FILE`, dirtying the repository before the build; that log hunk will appear in the claimed builder-only diff ([PLAN.md:310](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:310), [PLAN.md:318](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:318), [PLAN.md:321](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:321)). The gate is also weaker than a complete baseline for ignored files, which every listed Git command omits.

   Fix: Make no repository writes between the clean gate and evidence capture; retain `BASE_COMMIT` in trusted session/scratch state, append it afterward, and either inventory ignored files pre/post or explicitly narrow the inspection guarantee to Git-visible files.

3. **High — provider fallback and format repair collide in the attempt namespace.** Paths define only `a1=original` and `a2=repair`, but a Round-1 failure can launch another provider without consuming a round; no unique path remains, especially after a failed `a2`, so evidence can be overwritten or misclassified ([PLAN.md:113](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:113), [PLAN.md:139](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:139), [PLAN.md:275](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:275)).

   Fix: Give every process invocation a monotonically increasing attempt ID and record provider plus purpose (`review`/`repair`) separately.

4. **Medium — auto-selection ignores capability recovery before Round 1.** If Codex is unavailable at Phase 0 but becomes capable at the mandatory pre-Round-1 re-probe, nothing reselects it; Claude remains selected despite “Codex remains the default wherever capable” and despite selection not freezing until launch ([PLAN.md:8](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:8), [PLAN.md:90](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:90), [PLAN.md:99](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:99)).

   Fix: In auto mode, recompute selection after every pre-Round-1 probe with Codex preferred; preserve only forced selections.

5. **High — Phase-3 inspector capability and failure transitions are incomplete.** The Claude inspector requires `--add-dir`, yet that flag—and several other invoked flags—is absent from the “whole branch” probe; moreover, the allegedly exhaustive failure table is keyed to Phase-2 `REVIEWER_SELECTION` and does not define what happens when a selected Phase-3 inspector fails after probing ([PLAN.md:60](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:60), [PLAN.md:103](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:103), [PLAN.md:358](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:358)).

   Fix: Probe every mandatory Claude invocation flag, including `--add-dir`, and define Phase-3 launch/timeout/empty-output transitions with fallback or an explicit human opt-out.

6. **Medium — evidence serialization still violates its own requirements.** The NUL-safe enumeration later writes filenames with raw `%s`, so newline/control-character names corrupt record boundaries; separately, `git diff --binary` embeds binary patches despite the instruction not to inline binaries ([PLAN.md:332](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:332), [PLAN.md:342](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:342), [PLAN.md:353](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:353)).

   Fix: Encode manifest paths unambiguously, such as shell-escaped or JSON strings, and use a non-binary diff while listing binary paths and sizes separately.

VERDICT: REVISE
### Claude's response

All 6 accepted, no rejections. Codex confirmed the two round-3 substitutions were sound for their
original threats and then found where each one leaks — which is the correct outcome of asking it to
attack them specifically.

Finding 2 is the sharp one and it is self-inflicted: the plan required an empty worktree, then
immediately wrote `BASE_COMMIT` into `LOG_FILE`, dirtying the repo before the build so the log hunk
would appear inside the "builder-only" diff. Fixed by making `RUN_DIR` (outside the repo) the
holder of pre-build state and deferring every `LOG_FILE` append until after evidence capture. The
ignored-files gap is closed by narrowing the guarantee rather than inventorying: the inspection
covers git-visible files only, stated explicitly.

Finding 1: the "recover from the log" phrasing was a leftover contradicting the audit-only rule.
Removed. Cleanup now runs on every controlled terminal path including STOPs, and crash-orphan
retention is documented honestly instead of hand-waved to an OS reaper.

Finding 3 is a real namespace collision I created: provider fallback and format repair both need
attempt slots and only `a1`/`a2` existed. Replaced with a monotonic attempt counter carrying
provider and purpose.

Findings 4, 5, 6 accepted as written. Finding 6's second half is a plain contradiction —
`git diff --binary` inlines exactly what the neighbouring bullet says not to inline.

Convergence: 15 -> 9 -> 6 -> 6. Round 5 is the last.

## Round 5 — Codex

All six round-4 findings are materially addressed. The plan is implementable by a competent engineer.

Nonblocking cleanup items:

- [PLAN.md:148](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:148) retains obsolete final-gate/reaper wording. Delete it in favor of the authoritative every-terminal-path rule.
- Command examples and outcome handling still use `a1`/`a2` filenames despite the new monotonic `t` namespace ([PLAN.md:208](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:208), [PLAN.md:279](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:279)). Mechanically convert them and associate repair with the current successful review launch.
- `od -c` is not unambiguous: newline and literal `\n` filenames encode identically ([PLAN.md:381](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:381)). Use hexadecimal output such as `od -An -tx1`.
- `git diff --numstat` identifies binaries with `- -` but does not supply byte sizes ([PLAN.md:359](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:359)). Compute sizes separately for acceptance row 24.

These are localized implementation corrections with clear intended behavior, not unresolved design decisions.

VERDICT: APPROVED
### Claude's response

APPROVED at round 5 of 5. All four non-blocking cleanups applied rather than shipped as known-stale
text: the obsolete final-gate/reaper sentence in section 5 removed, the `a1`/`a2` filenames in the
command examples and section 8 mechanically converted to the `t` namespace with repairs bound to
their review launch, `od -An -c` replaced with `od -An -tx1` (Codex is right that `-c` renders a
real newline and a literal backslash-n identically), and a separate byte-size measurement added for
binaries since `--numstat` reports none.

Convergence: 15 -> 9 -> 6 -> 6 -> 0. Twenty-one findings accepted outright, one factual claim
rejected on verified evidence, three of Codex's proposed fixes replaced with simpler substitutions
it subsequently attacked and cleared, and one scope demand (rewriting the README hero, mermaid,
phase table, and invariant) rejected twice on the user's explicit Q4 decision.

---

## Act 3 — Build (Claude built, cross-inspected)

Builder: Claude. Base commit `42b22aa` (clean tree). Build commit `64d4699` — 5 files,
+654/-97. Spec deviations and beyond-spec fixes recorded below.

### Proof matrix executed

| Row | Case | Result |
|---|---|---|
| 1 | Claude Round 1 against `PLAN.md` | PASS — exit 0, 4479-byte substantive coverage review, last line matched the verdict regex exactly |
| 2 | Round 2 resume, same SID | PASS — recalled its `--no-renames` finding verbatim |
| 3 | Reviewer tool inventory | PASS — exactly Glob, Grep, Read |
| 4 | Write attempt in reviewer session | PASS — refused, no file created |
| 5 | `PATH` masked so codex absent | PASS — exit 127 masked / 0 unmasked |
| 8 | Override validation specified | PASS — both skills |
| 11 | Symlink at a fixed `/tmp` path | PASS — not followed, writes stayed in RUN_DIR |
| 13 | Untracked file in manifest | PASS |
| 14 | Downgrade template identical x3 | PASS — same SHA after whitespace normalisation |
| 21 | Clean-tree gate on dirty worktree | PASS — gate stops |
| 23 | No PLAN/LOG hunk in build delta | PASS (isolated repo) |
| 24 | Binary file | PASS — "Binary files differ", no inlined blob |

Counter-tests confirming the bugs the fixes remove: `git diff BASE..HEAD` returned **0 bytes**
where `git diff BASE --` returned 126; and writing `BASE_COMMIT` into the log before capture
**did** put a log hunk in the delta. Not run: rows 6, 9, 10, 12, 15a/b, 16, 17, 18, 19, 20, 22,
25-30 — they need shims (fake codex, hostile filenames, tampered log, concurrent loops). Logged
as untested per the scoping decision.

### Beyond-spec fixes found by the live proof run

Running the new Claude reviewer against `PLAN.md` found six defects in the mechanism itself:

1. **Verdict counting was wrong** — the spec's "`VERDICT:` exactly once" rule would have flagged
   the proof run's own valid review as malformed (3 substring hits from quoting the instruction).
   Changed to an anchored line pattern. `PLAN.md` corrected in a follow-up commit.
2. **Quota exhaustion** is a failure class the spec never named, and its reason arrives on
   **stdout** (Claude) or the **events stream** (Codex), not stderr — so "sanitized first line of
   stderr" would have logged nothing. Both observed live: opus hit its spend limit mid-proof, and
   Codex hit its usage limit during reinspection.
3. `--no-renames` missing from evidence commands (renames misalign `--numstat` fields).
4. Clean-tree gate is check-then-act with no lock.
5. Three missing failure-transition rows (fallback-also-fails, repair-launch failure, missing
   `-status.txt`).
6. `<reason>` sanitization must be redaction, not truncation — a first line bounds length, not
   sensitivity.

### Cross-inspection

Codex round 1 returned 9 findings, all accepted: prompt files referenced but never written;
`PLAN_FILE` not propagated to the build handoff; three contradictions in the Phase 3 sequence
(cleanup-before-Phase-3, "implement directly" ordered before the gate, and a "no repository
write" rule that forbade the build itself); timeouts saying "stop" while the table said retry;
logging still sourcing stderr only; `codex-review` control text still asserting Codex after
selecting Claude; the downgrade template drifting across its three copies; an out-of-scope edit
to the protected invariant line; and a duplicated block I introduced by double-patching.

Codex round 2 failed on its usage limit. **The new transition table was applied as written** —
first inspector failure falls back to a fresh restricted Claude inspector — which found 4 more:
`codex-review` had adopted none of the `PLAN_FILE` handoff fix, its Rounds 2..MAX blocks wrote
`resume-prompt.txt` and then never read it (so the coverage addendum never reached a fallback
reviewer from round 2 on), its transition table was missing the Round >= 2 STOP row, and
`PLAN.md` still carried the old verdict rule. All fixed; skill parity verified by grep.

Both inspection rounds spent (`MAX_INSPECTION_ROUNDS=2`). The second ran on the Claude fallback,
which is a weaker inspector than Codex — stated rather than glossed.
