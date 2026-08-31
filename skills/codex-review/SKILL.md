---
name: codex-review
description: A standalone adversarial PLAN-review loop where Claude Code (builder) and a read-only critic tag-team an implementation plan before any code is written. The critic is OpenAI Codex by default; when the Codex CLI is missing, outdated, or logged out the skill falls back to a separate isolated Claude session and announces the downgrade — never silently. Use this when you ALREADY have a plan or a clear idea and just want the cross-model stress-test — no requirements interview first. Claude drafts/loads the plan into PLAN.md, the critic reviews it read-only and returns VERDICT:APPROVED or VERDICT:REVISE, Claude revises and re-submits to the SAME critic session (context preserved) until APPROVED or a configurable MAX_ROUNDS cap is hit. Human approves the converged plan before code. Use when the user says "/codex-review", "codex review my plan", "have Codex review my plan", "argue this plan with Codex", "adversarial plan review", "make Claude and Codex argue/fight over the plan", or is about to build something high-stakes (auth, schema, concurrency, migrations, payments) and wants a second-model sanity check on the PLAN before implementation. For a guided requirements interview BEFORE the review, use /grill-me-codex instead. NOT for reviewing already-written CODE (that is the Codex plugin's /codex:review) and NOT for trivial changes.
---

# Codex-Review — Adversarial Plan-Review Loop

Two models, one plan, a bounded argument. **Claude is the builder and orchestrator. The critic is read-only** — it can read the repo and the plan but cannot touch a single file. The critic is OpenAI Codex by default, or an isolated Claude session when Codex is unavailable (see Step -1). They communicate strictly through `<PLAN_FILE>` + a critic session that persists across rounds. The human enters at exactly two points: kickoff and final sign-off.

This is a **deliberate, high-stakes tool** — reach for it on auth, data models, concurrency, migrations, payments, anything expensive to get wrong. Skip it for obvious/cheap work.

## Step -1 — Reviewer availability (FIRST action, before anything else)

Probe **both** providers before planning. Discovering at Step 2 that the critic cannot run wastes
the whole draft.

```bash
# CODEX_CAPABLE — both must pass
codex --version        # exit 0; parse the numeric field and compare >= 0.130.0 numerically
codex login status     # exit 0

# CLAUDE_CAPABLE — all must pass. Probe the WHOLE branch, not just the CLI.
claude --version       # exit 0
claude auth status     # exit 0 AND "loggedIn": true
claude --help          # must advertise --restricted --tools --safe-mode --strict-mcp-config
                       # --session-id --resume --effort --model --output-format --permission-mode
uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null \
  || python3 -c 'import uuid;print(uuid.uuid4())' 2>/dev/null || echo NOUUID
D=$(mktemp -d) && rmdir "$D"
```

- Both capable, or Codex only -> `REVIEWER_SELECTION=codex` (default, unchanged behaviour).
- Claude only -> `REVIEWER_SELECTION=claude`; print the downgrade notice immediately.
- Neither -> STOP with both probe results.
- `reviewer=codex|claude` overrides. Validate against exactly those two strings. **An override is
  a preference, never a capability claim** — forcing an incapable reviewer STOPS with the probe
  error.

Determine `TIMEOUT_MODE` once and carry it as a literal: `timeout` -> prefix `timeout 600 `;
else `gtimeout` -> `gtimeout 600 `; else `host` -> **no prefix**, pass `timeout: 600000` on the
Bash tool call. Never splice a possibly-empty variable — an empty prefix runs `600` as the command.

**Downgrade notice** (identical wording in the Round-1 fallback log line and the README):

> Codex unavailable (<sanitized reason>). Falling back to Claude-only review: a separate
> `claude -p` session, restricted to Read/Grep/Glob, reviews your plan.
> **Kept:** a reviewer with no inherited primary-session context — no CLAUDE.md, no user/project
> custom hooks, no output styles, plugins, or MCP (managed enterprise settings may still apply) —
> plus its own cross-round memory of this review, the VERDICT gate, MAX_ROUNDS, and Claude as
> final arbiter.
> **Lost:** cross-provider blind-spot decorrelation. Same-family models have correlated systematic
> blind spots — they favour the same architectures and miss the same edge cases. The read-only
> guarantee is also weaker: tool-level restriction, not Codex's OS-level filesystem sandbox.
> This is a downgrade path, not a peer option. Full effect:
> `npm i -g @openai/codex && codex login`.

Re-probe both providers immediately before Round 1; in auto mode recompute the selection with
Codex preferred. Once Round 1 launches the choice is frozen — cross-round continuity lives inside
a provider's session and cannot be transferred.

## Prerequisites — Codex path

- Do NOT pin `-m` unless the user asks; pinning `gpt-5.x-codex` variants fails on ChatGPT-account auth.
- **Echo the active model before Round 1** — read the `model` line from `~/.codex/config.toml`
  (absent = "CLI default") and state it with the resolved tunables. If the user objects, stop
  before burning a round.
- **Sandbox flag differs between the two commands.** `codex exec` accepts `-s read-only`.
  `codex exec resume` does NOT — it rejects `-s` ("unexpected argument"). On resume you MUST force
  read-only via `-c sandbox_mode="read-only"`, because `config.toml` may default `sandbox_mode` to
  `danger-full-access` (+ `approval_policy="never"`) — which would let Codex WRITE files mid-loop.
  Single most important safety detail on this path: verified end-to-end 2026-06-04.

## Prerequisites — Claude path

- **The flag set is the security boundary.** `--allowedTools`/`--disallowedTools` is NOT
  sufficient: such a session still exposes `Agent`, `Workflow`, `Skill`, `ToolSearch`, and deferred
  `WebFetch`/`RemoteTrigger` among ~25 tools, and `Agent` alone defeats a denylist because a
  spawned subagent carries its own Write and Bash. Use
  `--restricted --tools "Read,Grep,Glob" --strict-mcp-config --safe-mode --permission-mode dontAsk`,
  which exposes exactly Glob, Grep, Read (verified 2026-08-31).
- **Honest scope:** tool-level restriction enforced by the Claude Code process, not an OS-enforced
  read-only mount; managed enterprise settings still apply. Weaker than Codex's `-s read-only`.
- **`--bare` MUST NOT be used** — it forces `ANTHROPIC_API_KEY`/apiKeyHelper and never reads OAuth,
  failing with `Not logged in` on subscription auth. `--safe-mode` is the isolation flag.
- No exec/resume flag asymmetry: the permission flags are identical on both calls.

## Tunable variables (read from skill args, else default)

| Var | Default | Meaning |
|-----|---------|---------|
| `MAX_ROUNDS` | `5` | Hard cap on review rounds. The loop ALWAYS terminates at this. |
| `PLAN_FILE` | `PLAN.md` | Where the evolving plan lives (repo root). |
| `LOG_FILE` | `PLAN-REVIEW-LOG.md` | Append-only transcript of the argument (every round's critique + what changed). The artifact. |
| `reviewer` | auto-detect | `codex` / `claude`. Sets `REVIEWER_SELECTION`; never asserts capability. |
| `REVIEWER_MODEL` | `opus` | Reviewer model on the Claude path. |
| `REVIEWER_EFFORT` | `high` | Reviewer reasons longer than the planner did. |

If the user invoked the skill with an argument like `rounds=3`, use that for `MAX_ROUNDS`. Echo the resolved values back before starting.

## Flow

### Step 0 — Kickoff (human gate #1)

The invocation itself is the kickoff. Confirm scope in one line: what is being planned. If the user gave no task, ask for it (one question). Then proceed — do NOT ask for approval round-by-round; that comes at the end.

### Step 1 — Claude plans

Do real planning: read the relevant code, think through the approach, surface decisions and tradeoffs. Then write the plan to `PLAN_FILE` in this structure:

```markdown
# Plan: <task>
_Round 0 — initial draft by Claude_

## Goal
<one paragraph>

## Approach
<numbered steps, concrete>

## Key decisions & tradeoffs
<the contestable choices — name them explicitly so Codex has something to bite>

## Risks / open questions
<what you're unsure about>

## Out of scope
<bounds>
```

Initialize `LOG_FILE`:
```markdown
# Plan Review Log: <task>
Started <stamp the user's local time if known, else "session start">. MAX_ROUNDS=<n>.
```

Show the user the plan inline and say you're sending it to the selected reviewer for adversarial review — name which one (`Codex` or `Claude`), so a downgrade is never invisible at kickoff.

### Step 2 — The loop

Maintain `ROUND` (start 1), a monotonic launch counter `t` (never reused), and the reviewer's
session id (`THREAD_ID` on the Codex path, `SID` on the Claude path).

**Scratch directory.** `mktemp -d` once; record the printed absolute path as `RUN_DIR` and
interpolate it literally into every later command. No `trap` (it fires when the call returns) and
no `umask` (it does not persist) — `mktemp -d` already yields a 0700 directory. Each Bash call is
a fresh shell, so **nothing survives in variables or functions**: carry literals. Clean up
`RUN_DIR` on every controlled terminal path, not just the last one. `LOG_FILE` is audit text —
never read a path or id back out of it and act on it.

Per-launch files, nothing ever overwritten:

```
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-out.txt      stdout (the critique)
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-err.txt      stderr
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-status.txt   exit code
<RUN_DIR>/r<n>-t<NNN>-codex-<purpose>-events.jsonl      Codex path only
```

`<provider>` is `codex`/`claude`; `<purpose>` is `review`/`repair`.

`PLAN_FILE` is resolved ONCE and interpolated everywhere — no prompt may contain a literal
`PLAN.md`.

**Write the prompt files before the first launch** — the commands below `cat` them, so an unwritten
file sends an empty prompt. `<RUN_DIR>/review-prompt.txt` holds the review prompt with `<PLAN_FILE>`
substituted **plus the Claude-path coverage addendum when `REVIEWER_SELECTION=claude`**; a
Codex→Claude fallback must rewrite it before relaunching. `<RUN_DIR>/resume-prompt.txt` holds the
Rounds 2..MAX prompt.

**The review prompt** sent each round:

> You are an adversarial reviewer for an implementation plan. Be skeptical and specific — your job
> is to find what breaks, not to be agreeable. Read the plan at `<PLAN_FILE>` (and any repo files
> you need; you are read-only). Identify concrete flaws: security holes, race conditions, missing
> edge cases, schema conflicts, wrong assumptions, observability gaps, simpler alternatives. For
> each, give a one-line fix. Do NOT modify any files. End your reply with EXACTLY one line:
> `VERDICT: APPROVED` if the plan is sound enough to implement, or `VERDICT: REVISE` if it still
> has material problems.

On the **Claude path only**, append:

> Before answering, explicitly cover each of: security and authorization; data integrity and
> migrations; concurrency and ordering; error and failure paths; edge cases and boundary
> conditions; observability; unstated assumptions; and whether a materially simpler approach
> exists. State your conclusion for every area — including the ones you found nothing wrong with.
> `VERDICT: APPROVED` with all areas addressed and no material findings is a valid and expected
> outcome; do not invent defects to appear rigorous.

**No pipelines.** Piping into `grep` makes `$?` grep's status, so a reviewer that dies after
emitting `thread.started` reads as success, and `2>/dev/null` discards the text `<reason>` needs.
Three redirections plus an explicit status write, every launch.

#### Round 1 — REVIEWER_SELECTION=codex

```bash
<TIMEOUT_PREFIX>codex exec -s read-only --json \
  -o <RUN_DIR>/r1-t001-codex-review-out.txt "$(cat <RUN_DIR>/review-prompt.txt)" \
  > <RUN_DIR>/r1-t001-codex-review-events.jsonl \
  2> <RUN_DIR>/r1-t001-codex-review-err.txt < /dev/null
echo $? > <RUN_DIR>/r1-t001-codex-review-status.txt
```

Parse `thread_id` from the saved events file -> `THREAD_ID`. **`< /dev/null` is mandatory:**
`codex exec` reads stdin in addition to the prompt arg and otherwise blocks forever on EOF under
any non-TTY driver — a silent ~0% CPU hang.

#### Rounds 2..MAX — REVIEWER_SELECTION=codex

```bash
# resume rejects -s. Force read-only via -c sandbox_mode, or Codex inherits config.toml
# (possibly danger-full-access) and could write files.
<TIMEOUT_PREFIX>codex exec resume "$THREAD_ID" -c sandbox_mode="read-only" --json \
  -o <RUN_DIR>/r<n>-t<NNN>-codex-review-out.txt \
  "$(cat <RUN_DIR>/resume-prompt.txt)" \
  > <RUN_DIR>/r<n>-t<NNN>-codex-review-events.jsonl \
  2> <RUN_DIR>/r<n>-t<NNN>-codex-review-err.txt < /dev/null
echo $? > <RUN_DIR>/r<n>-t<NNN>-codex-review-status.txt
```

#### Round 1 — REVIEWER_SELECTION=claude

Generate the UUID once and record it as the literal `SID`.

```bash
<TIMEOUT_PREFIX>claude -p \
  --model <REVIEWER_MODEL> --effort <REVIEWER_EFFORT> \
  --session-id <SID> \
  --restricted --tools "Read,Grep,Glob" --strict-mcp-config --safe-mode \
  --permission-mode dontAsk \
  --output-format text "$(cat <RUN_DIR>/review-prompt.txt)" \
  > <RUN_DIR>/r1-t001-claude-review-out.txt \
  2> <RUN_DIR>/r1-t001-claude-review-err.txt < /dev/null
echo $? > <RUN_DIR>/r1-t001-claude-review-status.txt
```

#### Rounds 2..MAX — REVIEWER_SELECTION=claude

```bash
<TIMEOUT_PREFIX>claude -p --resume <SID> \
  --model <REVIEWER_MODEL> --effort <REVIEWER_EFFORT> \
  --restricted --tools "Read,Grep,Glob" --strict-mcp-config --safe-mode \
  --permission-mode dontAsk \
  --output-format text "$(cat <RUN_DIR>/resume-prompt.txt)" \
  > <RUN_DIR>/r<n>-t<NNN>-claude-review-out.txt \
  2> <RUN_DIR>/r<n>-t<NNN>-claude-review-err.txt < /dev/null
echo $? > <RUN_DIR>/r<n>-t<NNN>-claude-review-status.txt
```

**Timeout guard, all rounds both paths:** ten-minute ceiling so a stall fails loud. Via Claude
Code's Bash tool pass `timeout: 600000` (the 2-minute default kills real reviews). A tripped ceiling is a failed attempt:
**apply the failure-transition table below** — never blindly retry the same provider.

#### Failure transitions (exhaustive)

Failure classes: launch failure, timeout, network failure, exit 0 with empty output, second
malformed-verdict attempt. All are failed attempts.

| When | `REVIEWER_SELECTION` | Action |
|---|---|---|
| Any pre-Round-1 probe failure | auto | Switch to the other capable provider, print the notice, proceed. |
| Any pre-Round-1 probe failure | forced | STOP with the probe error. |
| **Any** Round-1 failure, any class | auto | Retry Round 1 **once** with the other capable provider under a new `t`. **Do not increment the round.** Other provider not capable -> STOP. |
| **Any** Round-1 failure, any class | forced | STOP. |
| Round-1 **fallback** attempt also fails | auto | STOP. No third provider; do not loop. |
| A **repair** launch fails (any class) | either | Failed attempt — route to this table like a review-launch failure. |
| `-status.txt` missing entirely | either | Failed attempt. Absence of a status file is never success. |
| **Any** Round >= 2 failure, any class | either | STOP. Continuity cannot transfer between providers; restarting with the other reviewer is a user decision, logged explicitly as a restart. |
Failure classes include **quota/spend-limit exhaustion**, observed 2026-08-31: the CLI exits
non-zero and prints the reason **on stdout, not stderr**. Source `<reason>` from stderr *or*
stdout, whichever is non-empty, and sanitize by **redaction** (strip URLs, tokens, absolute paths,
env values) — a first line bounds length, not sensitivity.

**Each round, after the reviewer returns:**

1. Read the launch's `-status.txt`. Non-zero -> failed attempt; apply the table.
2. Assert its `-out.txt` exists and is non-empty. Empty on exit 0 -> failed attempt.
3. **Validate the verdict BEFORE appending anything to `LOG_FILE`.** Strip trailing blank lines;
   the last non-empty line must match exactly `^VERDICT: (APPROVED|REVISE)$`, and the **anchored
   line pattern** `^VERDICT: (APPROVED|REVISE)$` must match exactly once. Do NOT count the bare
   substring `VERDICT:` — a reviewer that quotes the instruction back ("...end with VERDICT:
   APPROVED or VERDICT: REVISE") legitimately produces several occurrences. Observed 2026-08-31:
   a valid Claude review scored 3 substring hits and would have been wrongly flagged malformed.
   - Violation -> repair only if the launch already produced a **substantive review** (non-trivial
     length, concrete findings or explicit conclusions, and on the Claude path a conclusion for
     every coverage area). A refusal or a clarifying question is a **failed attempt**, never
     repairable — otherwise the repair launders a non-review into a clean `APPROVED`.
   - Repair permitted -> one format-only request under the next `t`, purpose `repair`, bound to
     the review launch it repairs; it **does not consume a round**. A second violation is a failed
     attempt.
4. Append to `LOG_FILE`: `## Round <n> — Codex` or `## Round <n> — Claude (reviewer)` + the full
   critique, plus the repair verdict line if a repair occurred. Failed attempts go under
   `## Round <n> — failed attempt` with **the sanitized reason selected above** — stderr or stdout,
   whichever was non-empty. Never echo raw output wholesale; redact URLs, tokens, absolute paths,
   and env values.
5. `VERDICT: REVISE` -> Claude decides **what's actually worth acting on** (Claude has final say —
   the reviewer advises, it does not command). Revise `<PLAN_FILE>`. Append `### Claude's response`
   + what changed, what was rejected and why. Increment `ROUND`.
6. `VERDICT: APPROVED` -> Step 3. `ROUND > MAX_ROUNDS` -> Step 3 (deadlock).

### Step 3 — Resolution (human gate #2)

**If APPROVED:** Present to the user — the final `<PLAN_FILE>`, a 3-bullet summary of what the argument improved, and the round count. Ask: *"Plan survived N rounds of <reviewer>. Implement it now — Codex builds it (`/codex-build`), Claude builds it, or stop here?"* **Offer the Codex build option iff `CODEX_CAPABLE`** — reviewer preference and builder capability are independent, so `reviewer=claude` with Codex installed still offers a Codex build. Only on a yes is code written. **No code is written during the loop.** If the user picks Codex, invoke the `codex-build` skill with `SPEC_FILE=<PLAN_FILE>` and the same `LOG_FILE` — roles flip (Codex writes, Claude reviews the diff) and the build rounds append to the same log.

**If MAX_ROUNDS hit without APPROVED (deadlock):** Do NOT pretend it converged. Surface the unresolved disagreements explicitly: list each point the reviewer still flags and Claude's counter-position. Hand it to the human to break the tie. This is a legitimate, useful outcome — a flagged disagreement beats a false "approved."

## Hard rules

- **Pick the command block matching `REVIEWER_SELECTION`. Never mix the two branches.** The titles are hard conditions, not labels.
- The reviewer is read-only EVERY round. Codex: `-s read-only` first call, `-c sandbox_mode="read-only"` every resume (resume has no `-s`). Claude: the full `--restricted --tools "Read,Grep,Glob" --strict-mcp-config --safe-mode --permission-mode dontAsk` set — an allow/deny list alone is NOT read-only. Neither ever writes. If you're tempted to give write access, stop — that's a different skill.
- Probe **both** providers before planning and again before Round 1, and probe the whole branch (CLI, auth, flags, UUID source, scratch dir) — not just presence.
- An explicit `reviewer=` override is a preference, never a capability claim.
- Downgrades are announced verbatim. Silent degradation is never allowed.
- Each Bash call is a fresh shell: carry literals, never rely on variables, functions, or `trap` persisting.
- The loop ALWAYS terminates at `MAX_ROUNDS`. No unbounded recursion.
- Claude is the final arbiter on every REVISE — incorporate good critiques, reject bad ones *with a reason logged*. Don't cave to Codex on everything (that defeats the cross-model check) and don't ignore it (that defeats the point).
- Code only after human gate #2.
- `LOG_FILE` is the deliverable — it tells the whole story of the argument. Keep it complete.

## What NOT to do

- Don't use this to review existing code — that's `/codex:review`.
- Don't pin a `-codex` model variant on ChatGPT-account auth — it 400s.
- Don't skip the log — the argument transcript is the most valuable artifact.
- Don't let the reviewer edit files. Read-only, always.
- Don't use `--bare` for the Claude reviewer — it forces `ANTHROPIC_API_KEY` and fails under OAuth.
- Don't present the Claude fallback as equivalent to cross-provider review. It is a downgrade.
