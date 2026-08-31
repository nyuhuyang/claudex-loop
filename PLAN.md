# Plan: Claude-only fallback for claudex-loop
_Locked via claudex-loop — by Claude + Yang Hu. Revised after Codex review rounds 1-2._

## Goal

Make `claudex-loop` and `codex-review` run end-to-end when the OpenAI Codex CLI is
absent, outdated, or unauthenticated, by falling back to a second isolated Claude
session as the adversarial reviewer. Capability is probed at runtime and re-probed at
every phase boundary; every downgrade is announced, never silent. Codex remains the
default reviewer wherever it is capable; the Claude path is an explicitly-labelled
downgrade, not a peer option.

## Approach

### 0. Execution model — no shell state survives between calls

**This constraint drives the whole design.** Claude Code's Bash tool starts a fresh shell
per call: the working directory persists, shell variables and functions do not. Therefore
the skill MUST NOT rely on exported variables, defined functions, or `trap ... EXIT`
across rounds — a trap fires the moment the initializing call returns.

Instead, the orchestrator (Claude) captures values as **literals** and interpolates them
verbatim into every later command, exactly as the existing skill already does with
`THREAD_ID`.

Literals carried across calls: `RUN_DIR` (absolute), `SID` (Claude path), `THREAD_ID`
(Codex path), `BASE_COMMIT` (Phase 3), `PLAN_FILE`, `TIMEOUT_MODE`.

**`LOG_FILE` is audit text, never executable state.** It records what happened for a human
reader. The orchestrator MUST NOT read any path, id, or sha back out of it and act on it — a
mutable repo file must never determine the target of an `rm -rf` or the identity of a resumed
session. There is no log-recovery path: a resumed session starts a fresh `RUN_DIR` and a fresh
reviewer session rather than adopting an old one.

**Cleanup** deletes only a `RUN_DIR` captured in the *current* session's context, and runs on
**every controlled terminal path** — APPROVED resolution, deadlock resolution, and every STOP in
the section-4 table — not merely after the final human gate. If the session crashes, the directory
is orphaned under the system temp root; that is stated plainly rather than promised away to an OS
reaper, whose behaviour is not guaranteed. The orphan's path is in the log for manual removal.

### 1. Two capability flags and one selection, never conflated

| Var | Meaning |
|---|---|
| `CODEX_CAPABLE` | Codex CLI present, >= 0.130, authenticated |
| `CLAUDE_CAPABLE` | `claude` CLI present, authenticated, **every** mandatory flag advertised, and a UUID source plus a private scratch dir both obtainable |
| `REVIEWER_SELECTION` | which reviewer this run uses: `codex` / `claude` |

`REVIEWER_SELECTION=claude` MUST NOT suppress `codex-build` when `CODEX_CAPABLE` — reviewer
preference and builder capability are independent. Phase 2 Resolution offers the Codex
build option iff `CODEX_CAPABLE`.

### 2. Capability probes

Codex — `CODEX_CAPABLE` iff all pass:

```bash
codex --version        # exit 0; parse the numeric field ("codex-cli 0.150.1" -> 0.150.1)
                       # and compare major.minor.patch numerically against 0.130.0.
                       # Unparseable version = NOT capable.
codex login status     # exit 0  (verified: prints "Logged in using ChatGPT")
```

Claude — `CLAUDE_CAPABLE` iff all pass:

```bash
claude --version       # exit 0
claude auth status     # exit 0 AND "loggedIn": true
claude --help          # must advertise EVERY flag any Claude-path invocation uses:
                       # --restricted --tools --safe-mode --strict-mcp-config
                       # --session-id --resume --effort --model --output-format
                       # --permission-mode --add-dir
                       # (--add-dir is Phase 3 only, but a branch that cannot run
                       #  Phase 3 must not be declared capable at Phase 0)
# whole-branch dependencies — a CLI that runs but cannot get a UUID or a scratch dir
# is NOT capable. Probe them here, not at Phase 2:
uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null \
  || python3 -c 'import uuid;print(uuid.uuid4())' 2>/dev/null || echo NOUUID
D=$(mktemp -d) && rmdir "$D"          # must succeed; probe dir removed immediately
```

Selecting a provider whose branch cannot actually run — and discovering it only after Phases 0-1 —
is the same defect class as probing presence without authentication. The probe covers the whole
branch or it covers nothing.

Model availability is proven by the first real round; pre-probing it would cost a full
model invocation for no added certainty.

Neither capable -> stop with both probe results before any Phase 0 work.

`reviewer=codex|claude` sets `REVIEWER_SELECTION`. Validate against exactly those two
strings — anything else is an error, never a silent default. **An override expresses a
preference; it never asserts a capability.** Forcing a reviewer whose probe failed stops
with the probe error.

### 3. Probe placement — both providers, every boundary

Probe **both** providers (not just the selected one) at each of:

- Phase 0 Step 0 — set `REVIEWER_SELECTION`, print the notice if downgrading.
- Immediately before Phase 2 Round 1 — Phases 0-1 are long; the Phase 0 result is stale.
- Immediately before Phase 3 cross-inspection.

Probing only the selected provider was a round-2 defect: falling back requires current
knowledge of the *other* provider, and a stale Phase-0 result is not that.

**In auto mode, recompute `REVIEWER_SELECTION` after every pre-Round-1 probe, Codex preferred.**
A provider that was down at Phase 0 and is capable at the pre-Round-1 re-probe must be reselected —
otherwise "Codex remains the default wherever it is capable" is false in exactly the case the
re-probe exists to catch. Forced selections are never recomputed.

**Once Round 1 launches, the Phase-2 provider choice is frozen** for the life of that review
session. Cross-round continuity lives inside a provider's session and cannot be transferred.

### 4. Failure transitions — exhaustive

Failure classes: launch failure (auth/model/exec error), timeout, network failure,
exit 0 with empty output, and a second malformed-verdict attempt. All are "failed
attempts"; the table covers every one.

| When | `REVIEWER_SELECTION` | Action |
|---|---|---|
| Any pre-Round-1 probe failure | auto-detected | Switch to the other capable provider, print the notice, proceed. No prompt. |
| Any pre-Round-1 probe failure | forced via `reviewer=` | STOP with the probe error. |
| **Any** Round-1 failure, any class | auto-detected | Retry Round 1 **once** with the other capable provider. **Do not increment the round.** Log both attempts. If the other provider is not capable, STOP. |
| **Any** Round-1 failure, any class | forced | STOP. |
| **Any** Round >= 2 failure, any class | either | STOP. Continuity cannot transfer between providers; restarting with the other reviewer is a user decision, logged explicitly as a restart. |

No blind retries anywhere. A timeout is a failed attempt, never a reason to re-run the
same command.

### 5. Per-run scratch directory

Fixed `/tmp` paths race between concurrent runs, and `>` follows a pre-existing symlink,
truncating its target.

```bash
mktemp -d          # prints e.g. /var/folders/ab/.../T/tmp.Xy7QpL — mode 0700
```

Run this once. **Record the printed absolute path as `RUN_DIR` and interpolate it
literally into every later command.** Write it into `LOG_FILE` as
`Run directory: <abs path>`.

- No `trap`: it would fire when the initializing call returns.
- No `umask 077`: it does not persist either. `mktemp -d` yields a 0700 directory, and a
  0700 parent is what protects the files inside it.
- Cleanup is an explicit `rm -rf <literal RUN_DIR>` on every controlled terminal path (see
  section 0) — not only the final gate.

Per-invocation paths. A round can contain more than two process launches — a provider fallback
and a format repair both need slots, and a failed repair needs another — so `a1`/`a2` is not a
sufficient namespace. **Every process launch gets the next value of a monotonic counter `t`,
never reused**, and the filename records round, counter, provider, and purpose:

```
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-out.txt      stdout (the critique)
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-err.txt      stderr
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-status.txt   exit code
<RUN_DIR>/r<n>-t<NNN>-codex-<purpose>-events.jsonl      Codex path only
<RUN_DIR>/review-prompt.txt                             Round 1 prompt
<RUN_DIR>/resume-prompt.txt                             Rounds 2..MAX prompt
```

`<provider>` is `codex` or `claude`; `<purpose>` is `review` or `repair`. Nothing is ever
overwritten. Before reading any file, assert it exists, is non-empty, and carries the counter
value just launched. Section 8 refers to these as the round's `review` launch and its `repair` launch; both are
`t`-numbered above and a repair is always bound to the specific review launch it repairs.

### 6. Portability preflight (once; result carried as a literal)

The existing skill already notes stock macOS has no `timeout`. Determine `TIMEOUT_MODE`
once and carry it as a literal — never splice a possibly-empty variable into a command,
which is how `run_reviewer $TIMEOUT_CMD 600 claude ...` degenerated into running `600`.

```bash
command -v timeout || command -v gtimeout || echo NONE
uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null \
  || python3 -c 'import uuid;print(uuid.uuid4())' 2>/dev/null || echo NOUUID
```

- Found `timeout` -> `TIMEOUT_MODE=timeout`; commands are written with the literal prefix
  `timeout 600 `.
- Found `gtimeout` -> `TIMEOUT_MODE=gtimeout`; literal prefix `gtimeout 600 `.
- `NONE` -> `TIMEOUT_MODE=host`; commands are written with **no prefix at all**, and the
  Bash tool call carries `timeout: 600000`. Log which mode was used.
- `NOUUID` -> the Claude branch is unavailable; stop with
  "no UUID source; set reviewer=codex or install uuidgen/python3".

### 7. Phase 2 — dual-branch review loop

Identical semantics both branches: fresh reviewer context, read-only, cross-round memory,
one `VERDICT:` line, `MAX_ROUNDS` cap, Claude as final arbiter. Blocks are titled with a
hard condition: `### Round 1 — REVIEWER_SELECTION=codex` / `...=claude`. Hard rule: pick
the block matching `REVIEWER_SELECTION`; never mix them.

`PLAN_FILE` is resolved and quoted ONCE at startup and interpolated into every initial
prompt, resume prompt, inspection prompt, log entry, and build handoff. **No prompt may
contain a literal `PLAN.md`.**

#### Status and stderr capture — no pipelines

Today's Codex invocation pipes into `grep`, so `$?` is grep's status: a Codex process that
dies after emitting `thread.started` reads as success. And `2>/dev/null` discards the very
text the downgrade notice needs for `<reason>`. Every reviewer invocation is therefore
written as three redirections and an explicit status write, with no pipe:

```bash
<TIMEOUT_PREFIX>codex exec -s read-only --json \
  -o <RUN_DIR>/r1-t001-codex-review-out.txt "$(cat <RUN_DIR>/review-prompt.txt)" \
  > <RUN_DIR>/r1-t001-codex-review-events.jsonl \
  2> <RUN_DIR>/r1-t001-codex-review-err.txt < /dev/null
echo $? > <RUN_DIR>/r1-t001-codex-review-status.txt
```

Parse `thread_id` from the saved events file afterwards. On failure, surface a sanitized
first line of stderr as `<reason>` — never echo raw stderr wholesale; it can carry tokens
and paths.

#### `REVIEWER_SELECTION=claude`

Round 1 — generate the UUID, record it as the literal `SID`:

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

Rounds 2..MAX — same literal `SID`:

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

**The flag set is the security boundary and is not negotiable.** An earlier draft used
`--allowedTools "Read Grep Glob" --disallowedTools "Edit Write NotebookEdit Bash"`.
Probing that session's real tool inventory returned Agent, Glob, Grep, ListAgents, Read,
ReportFindings, ScheduleWakeup, ShareOnboardingGuide, Skill, ToolSearch, Workflow, plus
deferred CronCreate, CronDelete, CronList, DesignSync, EnterWorktree, ExitWorktree,
Monitor, PushNotification, RemoteTrigger, SendMessage, TaskOutput, TaskStop, WebFetch,
WebSearch. `Agent` alone defeats a denylist — a spawned subagent carries its own tools,
Write and Bash included. The `--restricted --tools` set above returns exactly Glob, Grep,
Read.

**Honest scope of the guarantee:** tool-level restriction enforced by the Claude Code
process, not an OS-enforced read-only mount. Managed enterprise settings still apply.
Weaker than Codex's `-s read-only` filesystem sandbox, and documented as weaker.

Flag mapping:

| Codex | Claude | Note |
|---|---|---|
| `codex exec` | `claude -p --session-id <SID>` | id generated up front, nothing to parse |
| `codex exec resume <THREAD_ID>` | `claude -p --resume <SID>` | same id both calls |
| `-s read-only` (OS sandbox) | `--restricted --tools "Read,Grep,Glob" --strict-mcp-config` | tool-level only — weaker, documented |
| `-c sandbox_mode="read-only"` on resume | (not needed) | no exec/resume flag asymmetry |
| implicit clean context | `--safe-mode` | disables CLAUDE.md, user/project hooks, output styles, plugins, MCP |
| `-o /tmp/codex-verdict.txt` | `--output-format text > <RUN_DIR>/...` | no JSON parsing, no python3 |
| `< /dev/null` | identical | kept |

`--bare` MUST NOT be used: it forces `ANTHROPIC_API_KEY`/apiKeyHelper and never reads
OAuth, failing with `Not logged in` on subscription auth.

### 8. Round-outcome handling

Per round, in order:

1. Read the `-status.txt` file of the launch just made. Non-zero -> failed attempt; apply the
   section-4 table.
2. Assert its `-out.txt` exists and is non-empty. Empty on exit 0 -> failed attempt.
3. **Validate the verdict BEFORE appending anything to `LOG_FILE`**, so a failed attempt
   never looks like a completed round:
   - strip trailing blank lines; the last non-empty line must match exactly
     `^VERDICT: (APPROVED|REVISE)$`
   - the token `VERDICT:` must appear exactly once in the whole reply
   - violation -> repair is permitted **only if the review launch already produced a substantive
     review**:
     non-trivial length, concrete findings or explicit conclusions, and — on the Claude path —
     a stated conclusion for every coverage area from section 11. A refusal, a clarifying
     question, or an empty gesture is a **failed attempt**, never a repairable one, and goes to
     the section-4 table.
   - repair permitted -> one format-only request, launched with the next `t` value and purpose
     `repair`, bound to the review launch it repairs. It **does not consume a round**: *"Your
     reply did not end with exactly one `VERDICT: APPROVED` or `VERDICT: REVISE` line. Resend
     only that one line."* The review launch's output is retained and logged; the repair launch
     supplies only the verdict line. Neither overwrites the other.
   - a second violation is a failed attempt -> section-4 table.
   - **Why the gate exists:** the repair was introduced *because* a reviewer refused to review
     (O8). Without this gate the repair would launder that same refusal into a clean
     `APPROVED` — turning the motivating failure into a silent pass.
   - Rationale, observed 2026-08-31: a Claude reviewer handed a contentless prompt refused
     to emit a verdict at all. Reading a missing verdict as an implicit REVISE would burn
     rounds against a reviewer that never reviewed anything.
4. Append to `LOG_FILE` under `## Round <n> — Codex` or `## Round <n> — Claude (reviewer)`:
   the full critique from the review launch, plus the repair launch's verdict line when a repair
   occurred. Failed attempts are logged separately under `## Round <n> — failed attempt` with the reason.
5. `APPROVED` -> Resolution. `REVISE` -> Claude arbitrates, revises `<PLAN_FILE>`, appends
   `### Claude's response`, increments the round.
6. Round > `MAX_ROUNDS` -> deadlock resolution, unchanged.

### 9. Phase 3 — build and cross-inspection

**Inspector selection is determined by who BUILT, not by the Phase-2 reviewer.** The
doctrine is *whoever made the thing never checks the thing*.

| Builder | Inspector | Notes |
|---|---|---|
| Codex (`codex-build`) | Claude | Already the `codex-build` design: Claude reads the full diff and runs the proof. No extra inspector. |
| Claude | Codex if `CODEX_CAPABLE`, else a fresh restricted Claude session if `CLAUDE_CAPABLE` | Re-probe both first. Codex is preferred even if Phase 2 used Claude — a rival inspector is the point. |
| Claude, neither capable | none | Explicit, logged opt-out at the human gate. Never silent. |

#### Materialising the diff (the inspector has no Bash)

The Claude inspector has only Read/Grep/Glob — it cannot run `git`. Reading the working
tree cannot distinguish the build from its base. The orchestrator must produce the
evidence.

**Clean-tree gate before the build** — the same gate `codex-build` already enforces, now applied
to the Claude-built path too. By Phase 3 the worktree already carries `<PLAN_FILE>`, `LOG_FILE`,
and possibly unrelated user edits; without the gate `git diff <BASE_COMMIT> --` mixes all of that
into the "build delta" and the inspector cannot tell which hunks the builder wrote.

```bash
git status --porcelain      # must be empty. Commit the plan artifacts (or stash unrelated
                            # edits) first. Dirty tree -> STOP and ask the user.
git rev-parse HEAD > <RUN_DIR>/base-commit.txt   # BASE_COMMIT held OUTSIDE the repo
```

**No repository write may occur between the clean gate and evidence capture.** An earlier draft
wrote `BASE_COMMIT` into `LOG_FILE` at this point, which dirtied the worktree the gate had just
cleaned — the log hunk would then appear inside the diff claimed to be builder-only. `RUN_DIR` is
outside the repo, so it is the correct holder of pre-build state; **every `LOG_FILE` append for
Phase 3 is deferred until after `diff.patch` and `manifest.txt` are written.**

With a clean tree at `BASE_COMMIT`, `git diff <BASE_COMMIT> --` *is* the build delta — no pre-build
worktree baseline, no untracked-file hashing, no two-state diffing.

**Scope of the guarantee:** git-visible files only. Files matched by `.gitignore` are invisible to
every command here and are NOT inspected. Say so in the log rather than implying full coverage; a
build whose output is gitignored needs a manual review path.

After the build, before inspection — note there is **no `..HEAD`**. Before the human
commit gate `HEAD` still equals `BASE_COMMIT`, so `git diff <BASE_COMMIT>..HEAD` is empty
and the inspector would review nothing while reporting success:

```bash
git diff --stat <BASE_COMMIT> --            > <RUN_DIR>/manifest.txt
git status --porcelain                     >> <RUN_DIR>/manifest.txt
git ls-files --others --exclude-standard   >> <RUN_DIR>/manifest.txt   # git C-quotes odd names
git diff --numstat <BASE_COMMIT> --        >> <RUN_DIR>/manifest.txt   # binaries show "-  -"
git diff <BASE_COMMIT> --                   > <RUN_DIR>/diff.patch     # NOT --binary
# --numstat flags binaries but reports no byte size; measure them separately:
git diff --numstat -z <BASE_COMMIT> -- \
  | while IFS= read -r -d '' -r a && IFS= read -r -d '' b && IFS= read -r -d '' f; do
      [ "$a" = "-" ] && printf 'BINARY %s %s bytes\n' "$f" "$(wc -c < "$f" 2>/dev/null || echo 0)"
    done >> <RUN_DIR>/manifest.txt
```

Two encoding rules the earlier draft violated:

- **No `--binary`.** It embeds binary patches, contradicting the neighbouring instruction not to
  inline them. Plain `git diff` emits `Binary files ... differ`; `--numstat` supplies the sizes.
- **Manifest paths use git's own C-style quoting** (`core.quotePath`, the default for
  `git ls-files` and `git status` without `-z`). A filename containing a newline is emitted
  quoted and escaped, so one record stays one line. Never `printf '%s'` a raw filename into the
  manifest — that is what corrupts record boundaries.

`git diff <BASE_COMMIT> --` compares the base commit to the working tree, covering staged
and unstaged tracked changes.

- **Untracked files** are invisible to `git diff`; a build made entirely of new files would
  otherwise inspect as an empty diff. Enumerate them NUL-delimited and copy safely — filenames
  can contain spaces and newlines:
  ```bash
  git ls-files --others --exclude-standard -z \
    | while IFS= read -r -d '' f; do
        q=$(printf '%s' "$f" | od -An -tx1 | tr -d ' \n')  # hex: unambiguous, newline-free
        [ -L "$f" ] && { printf 'SYMLINK %s\n' "$q"; continue; }
        [ -f "$f" ] || { printf 'SPECIAL %s\n' "$q"; continue; }
        sz=$(wc -c < "$f")
        [ "$sz" -gt 262144 ] && { printf 'OVERSIZE %s %s bytes\n' "$q" "$sz"; continue; }
        mkdir -p "<RUN_DIR>/untracked/$(dirname "$f")" && cp -- "$f" "<RUN_DIR>/untracked/$f"
      done >> <RUN_DIR>/manifest.txt
  ```
  Regular files only. Symlinks, FIFOs, sockets, and directories are named in the manifest and
  not copied. Anything skipped is named — never silently dropped.
- **Binary files**: list as `<path> (binary, N bytes)`; do not inline.
- **Large diffs**: inspect every textual changed file, chunking across inspection rounds if
  needed. If any textual file goes uninspected, the inspection is marked **INCOMPLETE** in
  `LOG_FILE` with the uninspected paths named, and reaching the final human gate requires
  an explicit logged opt-out. Partial inspection is never reported as complete.
- The inspector receives `<RUN_DIR>` via `--add-dir` and is instructed to read
  `manifest.txt` first.
- Fresh `SID` (the inspector must see the code cold), same restricted flag set plus
  `--add-dir <RUN_DIR>`, no verdict line required, `MAX_INSPECTION_ROUNDS=2`.

**Phase-3 inspector failure transitions.** The section-4 table is keyed to Phase-2 review rounds
and does not cover the inspector; this table does. Any class of failure — launch, timeout, network,
exit 0 with empty output — is treated identically:

| Inspector | First failure | Second failure |
|---|---|---|
| Codex | fall back to a fresh restricted Claude inspector if `CLAUDE_CAPABLE`; log both attempts | mark the inspection **not performed**, require an explicit logged human opt-out at the final gate |
| Claude (Codex not capable) | retry once with a fresh `SID` | mark **not performed**, explicit logged opt-out |

Cross-inspection is never silently skipped. "Not performed" is a state the human must acknowledge,
exactly like `inspect=off`.

`skills/codex-build/SKILL.md` is NOT modified.

### 10. Downgrade notice (one wording, three copies by decision)

NOT single-sourced — Q2 rejected extracting a shared protocol file, and prose cannot
enforce consistency. Three copies exist deliberately (Phase 0 notice, Round-1 fallback log
line, README section); acceptance row 14 compares the static template.

> Codex unavailable (<sanitized reason>). Falling back to Claude-only review: Phase 2 runs
> a separate `claude -p` session, restricted to Read/Grep/Glob, against your plan.
> **Kept:** a reviewer with no inherited primary-session context — no CLAUDE.md, no
> user/project custom hooks, no output styles, plugins, or MCP (managed enterprise settings
> may still apply) — plus its own cross-round memory of this review, the VERDICT gate,
> MAX_ROUNDS, and Claude as final arbiter.
> **Lost:** cross-provider blind-spot decorrelation. Same-family models have correlated
> systematic blind spots — they favour the same architectures and miss the same edge cases.
> The read-only guarantee is also weaker: tool-level restriction, not Codex's OS-level
> filesystem sandbox.
> This is a downgrade path, not a peer option. Full effect:
> `npm i -g @openai/codex && codex login`.

"No inherited primary-session context" replaces the earlier "no memory", which contradicted
the cross-round memory the same paragraph promises. "No user/project custom hooks (managed
enterprise settings may still apply)" replaces the categorical "no hooks" — this machine is
on a Team plan, so managed settings are live, not hypothetical.

### 11. Reviewer prompt addendum (`REVIEWER_SELECTION=claude` only)

The earlier draft demanded at least three findings in Round 1 — that orders a reviewer
facing a sound plan to manufacture defects, and the premise that same-family reviewers are
more agreeable was never measured. Replaced with coverage that permits zero findings:

> Before answering, explicitly cover each of: security and authorization; data integrity
> and migrations; concurrency and ordering; error and failure paths; edge cases and
> boundary conditions; observability; unstated assumptions; and whether a materially
> simpler approach exists. State your conclusion for every area — including the ones you
> found nothing wrong with. `VERDICT: APPROVED` with all areas addressed and no material
> findings is a valid and expected outcome; do not invent defects to appear rigorous.

### 12. Tunables

| Var | Default | Meaning |
|---|---|---|
| `reviewer` | auto-detect | `codex` / `claude`. Sets `REVIEWER_SELECTION`; never asserts capability. |
| `REVIEWER_MODEL` | `opus` | Reviewer model on the Claude path. |
| `REVIEWER_EFFORT` | `high` | Reviewer reasons longer than the planner did. |

### 13. Docs

Changed (functional text):
- Both skills' frontmatter `description` — they assert Codex categorically and drive skill
  triggering. Qualify as Codex-default with a Claude fallback.
- Phase 2 Resolution messages — offer a Codex build iff `CODEX_CAPABLE`.
- `README.md` `## Prerequisites` — Codex demoted from required to recommended.
- `README.md` new `### No Codex?` — the section-10 wording verbatim.
- `README.md` `## Tunables` — the three rows from section 12.
- `README.md` `## Safety` — the Claude path's read-only is tool-level, weaker than the
  Codex sandbox; managed enterprise settings still apply.
- `plugin.json` + `marketplace.json` `description` — one added clause.

NOT changed, reaffirming the user's Q4 decision against reviewer pressure: the README hero
line, mermaid diagram, four-phase table, badges, `logo.svg`, `run.svg`, and the "whoever
made the thing never checks the thing" invariant. Codex remains the default path; diluting
the headline for a downgrade path is a net loss.

### 14. Proof — acceptance matrix

Prose deliverable, so the proof is an executed matrix. Each row records the exact command,
version, and observed result in `LOG_FILE`.

| # | Case | Pass condition |
|---|---|---|
| 1 | Claude Round 1 against this repo's `<PLAN_FILE>` | exit 0, non-empty critique, last non-empty line matches the verdict regex exactly |
| 2 | Claude Round 2 resume, same `SID` | demonstrably recalls Round 1 content |
| 3 | Reviewer tool inventory | returns exactly Glob, Grep, Read — nothing else |
| 4 | Write attempt inside reviewer session | refused AND no file created on disk |
| 5 | `PATH` masked so `codex` is absent | Phase 0 selects Claude, prints the notice |
| 6 | Codex passes both probes, then fails at launch (shim whose `exec` exits non-zero while `--version` and `login status` succeed) | auto mode retries Round 1 with Claude, round counter unchanged, both attempts logged |
| 7 | `reviewer=codex` forced with codex absent | STOPS with the probe error, no silent downgrade |
| 8 | `reviewer=bogus` | errors, does not default |
| 9 | Malformed verdict: none / two / suffixed | one `repair` launch, round not consumed, review-launch critique retained; second violation = failed attempt |
| 10 | Two loops concurrently in the same repo | separate `RUN_DIR`s, no cross-contamination |
| 11 | Symlink planted at a legacy fixed `/tmp` path | not followed; nothing outside `RUN_DIR` written |
| 12 | `PLAN_FILE=OTHER.md` | reviewed file and revised file are the same file; no prompt contains a literal `PLAN.md` |
| 13 | Phase 3 inspection with the build **uncommitted** and containing one new untracked file | diff is non-empty, the untracked file appears in the manifest and its content is inspectable |
| 14 | Downgrade notice: Phase 0 vs Round-1 log line vs README | static template byte-identical after whitespace normalisation, compared **before** `<reason>` substitution |
| 15a | `timeout` and `gtimeout` both masked | `TIMEOUT_MODE=host`, no prefix emitted, `600` never run as a command, Bash tool carries `timeout: 600000` |
| 15b | `uuidgen`, `/proc/sys/kernel/random/uuid`, and `python3` all masked | Claude branch stops with the stated message; nothing runs unbounded |
| 16 | Round >= 2 provider failure | STOPS; no silent provider switch mid-session |
| 17 | State survives genuinely separate Bash calls | Round 2 runs from a fresh shell using only interpolated literals; no exported var, function, or trap relied on |
| 18 | `LOG_FILE` tampered with a bogus `Run directory:` line, then cleanup runs | the planted path is NOT deleted; only the session-captured `RUN_DIR` is |
| 19 | Claude CLI present and authenticated but every UUID source masked | `CLAUDE_CAPABLE` is false at probe time, before Phase 0 work begins — not discovered at Phase 2 |
| 20 | The review launch returns a refusal or a clarifying question | classified a failed attempt; no format repair offered; cannot become `APPROVED` |
| 21 | Phase 3 with the worktree dirty (uncommitted plan/log plus an unrelated user edit) | clean-tree gate STOPS before the build; after committing, the diff contains only builder hunks |
| 22 | Untracked file named with a space and a newline, plus a symlink and a 1MB file | manifest lists all four on one record each; regular files copied intact; symlink and oversize named, not copied |
| 23 | Phase 3 end to end, then inspect the diff | `diff.patch` contains no `LOG_FILE` or `<PLAN_FILE>` hunk — no repo write happened between the clean gate and evidence capture |
| 24 | A binary file changed in the build | `diff.patch` says "Binary files ... differ" with no embedded blob; manifest carries its path and size |
| 25 | Codex down at Phase 0, up at the pre-Round-1 re-probe, auto mode | selection flips back to Codex before Round 1 launches |
| 26 | Same, but `reviewer=claude` forced | selection stays Claude |
| 27 | Round 1 fails over to the other provider AND that attempt needs a format repair | three distinct `t`-numbered file sets exist; none overwritten |
| 28 | Any STOP path in the section-4 table | the session's `RUN_DIR` is deleted before the skill returns |
| 29 | Build output matched by `.gitignore` | log states the inspection covered git-visible files only and names the gap |
| 30 | Phase-3 inspector fails twice | inspection marked "not performed"; final gate requires an explicit logged opt-out |

## Key decisions & tradeoffs

1. **No shell-persistent state.** Every cross-call value is a literal recorded in `LOG_FILE`
   and interpolated by the orchestrator, matching how the existing skill handles
   `THREAD_ID`. Alternatives — a wrapper script, or a state file sourced each call — add an
   artifact the skill would have to ship and keep in sync with the prose.
2. **Runtime probes at every phase boundary, not install time.** Claude Code plugins expose
   no install lifecycle hook — only session events — per the `openai-codex` and `ponytail`
   manifests and `claude plugin install --help`. A `SessionStart` hook would fire in every
   session of every project for an occasionally-used skill and would still go stale.
   `userConfig` exists but adds a second source of truth beside the probe. Cost: a few cheap
   probe calls per run.
3. **In-place dual-branch edits, no sibling skill.** A `claude-review` sibling duplicates
   ~95% of the prose and drifts. Extracting a shared protocol file would pay down real
   pre-existing duplication but is out of scope. Risk accepted: adjacent bash blocks invite
   picking the wrong one; mitigated by hard-conditioned titles plus a Hard rule.
4. **`REVIEWER_MODEL=opus` + `--effort high`.** Review quality tracks capability more than
   lineage; cross-provider decorrelation is already lost on this path, and a weaker reviewer
   fails silently. `--effort high` is the only asymmetry lever left. ~5x sonnet over a
   5-round loop, hence tunable.
5. **Phase-3 inspector chosen by who built, not by the Phase-2 reviewer.** Preserves the
   invariant in every combination.
6. **Minimal honest doc change, reaffirmed against reviewer pressure.** Functional text is
   corrected; hero, mermaid, phase table, and invariant are not.
7. **`codex-review` keeps its name** despite possibly running a Claude reviewer. Renaming
   breaks existing invocations and every README reference for nominal accuracy only.
8. **Tool-level restriction accepted as weaker than the Codex sandbox and documented as
   weaker**, rather than hardened further. An OS-enforced read-only mount would close the
   gap but is a platform-specific project of its own.

## Assumptions

Split by evidence class. "Observed" means measured once on this machine on 2026-08-31 — not
a documented guarantee.

### Documented (vendor-stated)
- D1. `--restricted` removes command/code-running tools and WebFetch unless `--tools` names
  them, ignores user/project/local settings, and confines file tools to the working
  directories; **managed settings and `--settings` still apply**. — `claude --help`
- D2. `--tools` selects from the built-in set; `--safe-mode` disables CLAUDE.md, skills,
  plugins, hooks, MCP, commands, agents, output styles. — `claude --help`
- D3. `--bare` uses `ANTHROPIC_API_KEY`/apiKeyHelper only; OAuth and keychain are never
  read. — `claude --help`
- D4. Claude Code plugin hooks are session lifecycle events; `claude plugin install` exposes
  `--config` for manifest-declared `userConfig` and no install hook. — `claude plugin
  install --help`, `openai-codex` and `ponytail` `hooks/hooks.json`
- D5. The Bash tool's working directory persists between calls; shell state (env vars,
  functions) does not. — Claude Code tool documentation

### Observed (single trial, this machine, 2026-08-31)
- O1. `claude -p --session-id <uuid>` then `--resume <uuid>` preserved context; the reviewer
  recalled round-1 content exactly. Repeated under the restricted flag set.
- O2. `--restricted --tools "Read,Grep,Glob" --strict-mcp-config --safe-mode
  --permission-mode dontAsk` returned exactly Glob, Grep, Read when asked to enumerate its
  tools, and still read `PLAN.md` correctly.
- O3. The earlier `--allowedTools/--disallowedTools` set returned 25 tools including `Agent`,
  `Workflow`, `ToolSearch`, and deferred `WebFetch`/`RemoteTrigger`.
- O4. `--safe-mode` reviewer self-reported no CLAUDE.md, memory, or output-style instructions
  in context. **Self-report, not an independent measurement.**
- O5. `--bare` returned `Not logged in · Please run /login`; `ANTHROPIC_API_KEY` unset.
- O6. `--output-format text` exits 0 with the reply on stdout; a bad `--resume` id exits 1
  with empty output.
- O7. `--model opus --effort high` composes with `-p --safe-mode`.
- O8. A Claude reviewer refused to emit a `VERDICT:` line for a contentless prompt.
- O9. `claude auth status` exits 0 with `"loggedIn": true`, `"authMethod": "claude.ai"`,
  `"subscriptionType": "team"`. (Codex's round-1 finding 2 asserted the opposite; it most
  likely probed from inside its own sandbox where the keychain was unreadable.)
- O10. `codex login status` exits 0, printing "Logged in using ChatGPT"; `codex --version`
  prints `codex-cli 0.150.1`.

### Inferred (reasoning, not measured)
- I1. Same-family models have correlated systematic blind spots, so the Claude path is weaker
  than cross-provider review. Argued, not benchmarked — a design rationale, never a measured
  claim.
- I2. Review quality tracks model capability more than lineage. Same status.

### Repo facts
- R1. Brownfield, docs-only: 17 files, no source, no build or test system.
- R2. No `CONTEXT.md`, no `docs/adr/`; Phase 1 ran docs-agnostic.
- R3. Direct clone of `chaseai-yt/claudex-loop`, `main` tracking `origin/main`; assumed no
  push access, changes stay local.
- R4. The invoked skill loads from `~/.claude/plugins/cache/claudex-loop/claudex-loop/
  f8c111de1fc7/`; editing this repo does not change the live skill until reinstall or
  `cp -r skills/* ~/.claude/skills/`.
- R5. Seven `codex exec` call sites: `claudex-loop` x3, `codex-review` x2, `codex-build` x2.
- R6. Phases 0 and 1 carry zero Codex dependency.
- R7. `userConfig`'s schema shape is UNVERIFIED — no installed plugin declares one.
- R8. Skill inventory matched `skill-creator` / `write-a-skill` on both benches; none loaded.
- R9. This machine is on a Team plan (org "Rancho BioSciences"), so managed enterprise
  settings are a live possibility, not hypothetical.

## Risks / open questions

1. **Tool-level restriction is not an OS sandbox.** Managed enterprise settings still apply
   and a future release could re-add a tool to the `--restricted` baseline. Acceptance row 3
   is the tripwire; it is not elimination. Genuinely weaker than the Codex path, documented
   as such.
2. **`--safe-mode` and `--restricted` semantics could change.** They do load-bearing
   isolation work. If a release narrows what they disable, the reviewer silently starts
   inheriting context with no visible symptom. Rows 3 and 4 are the only detection.
3. **Two adjacent bash blocks, wrong one picked.** Core execution risk of the in-place
   design; hard-conditioned titles reduce but do not remove it.
4. **O4 is self-report.** The reviewer saying it has no CLAUDE.md is not proof. A stronger
   check would plant a known marker string in a CLAUDE.md and assert the reviewer cannot
   quote it. Not yet designed; row 3 partially compensates.
5. **Pre-existing defects on untouched paths.** The grep-masked exit status and the
   hardcoded `PLAN.md` in prompts also exist where this change does not reach. Fixed where
   touched; the remainder is recorded debt, not silently inherited.
6. **The downgrade notice is knowingly triplicated.** Row 14 is a manual check, not a
   guarantee, and nothing runs it automatically.
7. **No test system exists.** The matrix is executed by hand once; nothing prevents a later
   edit from breaking the Claude path silently.
8. **Single-trial observations.** Every O-item is one run, one machine, one OS, one CLI
   version. None is a cross-platform guarantee.
9. **Rows 6, 11, 15a, 15b, 18, 19 and 22 need shims** (a fake `codex` that passes probes then
   fails at exec; a planted symlink; a tampered log line; `PATH` masking; hostile filenames).
   Writing those shims is part of the build, and they must not leak into the repo.
10. **The clean-tree gate adds friction to the Claude-built path.** The user must commit the plan
    artifacts before Phase 3. That is the cost of a meaningful diff; the alternative (a full
    pre-build worktree baseline) is a subsystem this plan deliberately declines to build.
11. **The substantive-review gate on format repair is a judgement call, not a parser.** "Contains
    a substantive review" is evaluated by the orchestrating model. A sufficiently plausible
    non-review could still pass it.

## Out of scope

- `skills/codex-build/SKILL.md` — correctly Codex-specific; untouched.
- `legacy/` — untouched.
- Any third reviewer provider (Gemini CLI, OpenAI-compatible endpoints).
- Extracting the shared review protocol between `claudex-loop` and `codex-review`.
- Renaming `codex-review`.
- README hero, mermaid diagram, phase table, badges, `logo.svg`, `run.svg`, the "whoever made
  the thing never checks the thing" invariant.
- An OS-enforced read-only mount for the Claude reviewer.
- Fixing pre-existing `PLAN_FILE` and exit-status defects on paths this change does not touch.
- The pre-existing contradiction between the skills' "Do NOT pin `-m`" rule and this machine's
  `~/.codex/config.toml` pinning `model = "gpt-5.6-sol"`.
- Upstream contribution (fork, PR).
