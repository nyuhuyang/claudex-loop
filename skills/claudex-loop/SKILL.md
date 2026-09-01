---
name: claudex-loop
description: Four-phase plan hardening (renamed from /crucible 2026-08-16; old triggers still work) — supersedes /grill-me-codex and /grill-with-docs-codex. PHASE 0 RECON — Claude scouts first (codebase + docs on brownfield; prior art, stack, and pitfalls research on greenfield) and drafts an assumptions ledger. PHASE 1 INTERROGATE — confirm the ledger in one batch, then question only the load-bearing decisions one at a time (each with why-it-matters, a recommendation, and what-breaks-if-we-guess-wrong), cosmetic ones batched, with a visible decision map and an accept-all-recommendations escape hatch. PHASE 2 REVIEW — the locked plan goes to PLAN.md and a read-only adversarial reviewer attacks it (VERDICT: APPROVED/REVISE); Claude revises and re-submits to the SAME reviewer session until APPROVED or MAX_ROUNDS, then you sign off before any code. The reviewer is OpenAI Codex by default; when the Codex CLI is missing, outdated, or logged out the skill falls back to a separate isolated Claude session and says so out loud — a downgrade path, never silent. PHASE 3 BUILD (optional) — you pick the builder and the models swap jobs: Codex builds via codex-build and Claude reads the full diff + runs the proof itself; Claude builds and a fresh read-only rival session cross-inspects the diff (Codex when capable, else an isolated Claude inspector; on by default, logged opt-out only); either way you approve the final diff. Use when the user says "/claudex-loop", "claudex this", "run the claudex loop", "/crucible" (legacy), "put this through the crucible", "crucible this plan", "grill me then have codex review", "stress-test this plan before we build", or is about to build something high-stakes (auth, schema, concurrency, migrations, payments, greenfield architecture) and wants alignment AND a cross-model sanity check first. Locked plan needing only the Codex loop → /codex-review. Reviewing already-written code → /codex:review. NOT for trivial changes.
---

# Claudex-Loop — Recon, Interrogate, Review, Build

_(Renamed from Crucible 2026-08-16. Old trigger phrases still work.)_

Four phases, four failure modes killed:

- **Phase 0 — RECON** kills *interviewing blind*: Claude scouts the terrain (code or research) before asking you anything, so the interview starts informed instead of generic.
- **Phase 1 — INTERROGATE** kills *building the wrong thing*: Claude interrogates you until intent is locked — but only on decisions that are actually load-bearing.
- **Phase 2 — REVIEW** kills *a plan that sounds right but breaks*: a separate read-only reviewer attacks the locked plan — Codex by default, an isolated Claude session when Codex is unavailable. Cross-model = no echo chamber; the fallback keeps the fresh-context part and loses the cross-provider part, and says so.
- **Phase 3 — BUILD** *(optional)* kills *grading your own work*: one model implements the locked plan, the rival model grades the diff — in both directions.

You enter at four points only: confirming the assumptions ledger, answering the fire, signing off the converged plan, and approving the final diff if you build. The reviewer — Codex or the Claude fallback — is read-only throughout recon, interrogation, and review — **no code is written until you sign off the converged plan.**

---

## PHASE 0 — RECON (Claude alone)

Before asking the user a single question, determine the terrain and gather what can be gathered without them.

### Step 0 — Reviewer availability (FIRST action, before terrain detection)

Probe **both** providers before any other Phase 0 work. Discovering at Phase 2 that the reviewer
cannot run wastes the whole interview.

```bash
# CODEX_CAPABLE — all three must pass
codex --version        # exit 0; parse the numeric field ("codex-cli 0.150.1" -> 0.150.1) and
                       # compare major.minor.patch numerically against 0.130.0.
                       # Unparseable version = NOT capable.
codex login status     # exit 0

# CLAUDE_CAPABLE — all must pass. Probe the WHOLE branch, not just the CLI.
claude --version       # exit 0
claude auth status     # exit 0 AND "loggedIn": true
claude --help          # must advertise every flag the Claude path uses:
                       # --restricted --tools --safe-mode --strict-mcp-config
                       # --session-id --resume --effort --model --output-format
                       # --permission-mode --add-dir
uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null \
  || python3 -c 'import uuid;print(uuid.uuid4())' 2>/dev/null || echo NOUUID
D=$(mktemp -d) && rmdir "$D"          # private scratch must be creatable
```

Selection:

- Both capable, or Codex only -> `REVIEWER_SELECTION=codex`. Default path, unchanged behaviour.
- Claude only -> `REVIEWER_SELECTION=claude`; print the downgrade notice **immediately**, before
  any other Phase 0 work.
- Neither -> STOP, reporting both probe results. Do not start Phase 0.
- `reviewer=codex|claude` overrides selection. Validate against exactly those two strings —
  anything else is an error, never a silent default. **An override expresses a preference; it
  never asserts a capability.** Forcing a reviewer whose probe failed STOPS with the probe error.

Also determine the portability mode once and carry the result as a literal:

- `command -v timeout` -> `TIMEOUT_MODE=timeout`, literal prefix `timeout 600 `
- else `command -v gtimeout` -> `TIMEOUT_MODE=gtimeout`, literal prefix `gtimeout 600 `
- else `TIMEOUT_MODE=host` -> **no prefix at all**; pass `timeout: 600000` on the Bash tool call.
  Never splice a possibly-empty variable into the command — an empty prefix turns `600` into the
  command being run.
- `NOUUID` -> the Claude branch is unavailable; if it was selected, STOP with
  "no UUID source; set reviewer=codex or install uuidgen/python3".

**Forced selection is not a downgrade-due-to-unavailability.** When `reviewer=claude` is given
while `CODEX_CAPABLE` is true, do NOT print the "Codex unavailable" notice — it would be false and
its `<reason>` would be empty. Print instead:

> Reviewer: Claude (you asked for it; Codex is available). Same trade-off as the fallback path —
> you keep the fresh-context reviewer and lose cross-provider blind-spot decorrelation, and the
> read-only guarantee is tool-level rather than an OS sandbox. Drop `reviewer=claude` to use Codex.

The "Codex unavailable" notice is reserved for the case where Codex genuinely is not capable.

**The downgrade notice** (identical wording in the Round-1 fallback log line and README):

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

### Detect the terrain
- **Brownfield** — the working directory has real source code (not just scaffolding/config). Recon the codebase.
- **Greenfield** — empty dir, fresh scaffold, or the user is describing a brand-new project with no repo yet. There is nothing to recon; research replaces it.

### Brownfield recon
1. Explore the codebase: architecture, relevant modules, existing patterns the plan must fit, current schema/auth/infra as applicable.
2. Look for living docs: `CONTEXT.md` (or `CONTEXT-MAP.md` for multi-context repos) and `docs/adr/`. If they exist, load them — the project has a ubiquitous language and prior decisions the plan must respect, and Phase 1 runs **docs-aware** (see below).
3. If the task involves tech or an integration the repo can't answer, open the **research gate** (below) before proceeding.

### Greenfield recon
No code to read, so research carries the phase. Open the **research gate**, then cover:
1. **Prior art** — how do existing tools/products solve this? What's the standard shape?
2. **Stack** — reasonable default stack for this kind of project, with one alternative worth considering.
3. **Known pitfalls** — the 3-5 things people building this class of thing get wrong (search for postmortems, "lessons learned", common gotchas of the candidate stack).

### The research gate (one question, asked at kickoff when external research would help)
Don't silently pick a research depth — offer the tiers with a recommendation based on stakes, and let the user choose:

- **`none`** — Claude's knowledge + codebase only. Right for medium tasks on familiar ground.
- **`web`** — a handful of targeted WebSearch passes (docs, gotchas, prior art). Minutes, not a project. The default recommendation for most greenfield work.
- **`deep`** — launch a **deep-research dynamic workflow** via the Workflow tool: a multi-agent research orchestration (parallel finder agents each searching a different way — prior art, stack landscape, pitfalls/postmortems, docs — then deep-read agents on the best sources, then one synthesis agent producing the brief). Heavy and token-expensive — recommend only for high-stakes greenfield, unfamiliar tech, or when the landscape itself is the question. The user choosing this tier IS the explicit opt-in the Workflow tool requires. **Model pin:** every `agent()` call in the research workflow MUST pass `model: 'opus'` (finders, deep-readers, and the synthesizer alike) — if the main session is on Fable, letting a dozen research agents inherit it annihilates token usage for what is mostly search-and-summarize work. Leave effort at the default — don't pass an `effort` override. **Args gotcha (found in smoke test 2026-08-13):** the workflow runtime may deliver `args` as a JSON-encoded STRING instead of an object — always open the script with `const A = typeof args === 'string' ? JSON.parse(args) : args` and reference `A.*`, or `pipeline(args.questions, ...)` dies instantly with "expects an array".

If invoked with `research=none|web|deep`, skip the question and use that tier.

**If `deep` is chosen: draft the research prompt and get sign-off before launching.** Show the user the topic framing + the 3-5 specific questions the assumptions ledger needs answered (not a generic "research X" — questions shaped like "what do teams building X get wrong about auth?" / "what's the current standard stack for Y and why?"). The user edits or approves, THEN author the workflow script with the approved questions as its `args` and run it. Save the synthesized brief to `docs/research/YYYY-MM-DD-<slug>-claudex-research.md` (or your notes location of choice, with `## Key Takeaways`) — link it from the ledger entries it sourced and from `<PLAN_FILE>`.

### Skill inventory scan (both terrains, after terrain detection)
Both benches carry installed skill packs. Enumerate and match against the task's domain:

- **Claude side:** list `~/.claude/skills/` (folder names + frontmatter `description` first lines are enough — don't read full SKILL.mds during recon).
- **Codex side:** list `~/.agents/skills/` (the `skills` CLI's Codex install target).

Filter to skills whose descriptions match the project's domain (e.g. a three.js game matches the `threejs-*` pack; an email feature matches resend skills). Record hits in the Assumptions Ledger as proposed toolchain entries, never auto-loads:

> "threejs-game-skills pack installed on BOTH agents (9 skills incl. aaa-graphics-builder, gameplay-systems, 3d/image/audio generators) — proposing the build phase load graphics-builder + gameplay-systems, and the asset track use the generator skills. — source: skill inventory scan"

If a matched skill exists on only one bench, say which. If a Codex-side skill's loading behavior under headless `codex exec` is unverified, ledger that as an assumption to smoke-test before the build phase counts on it. **Discovery informs the plan; nothing loads unless `<PLAN_FILE>`'s `## Toolchain` section names it and survives review.**

### Output: the Assumptions Ledger
End Phase 0 by presenting a single batch — NOT one-at-a-time — of everything Claude resolved on its own:

```markdown
## Assumptions Ledger
_Confirm or correct in one pass. Anything unmarked I treat as confirmed._
1. <assumption> — source: <code path / doc / research finding / convention>
2. ...
```

Each entry cites its source. The user confirms/corrects in one reply. Corrections that open real questions get promoted into the Phase 1 decision map.
 This is the single biggest time-save over a naive grill: the interview never wastes questions on things the repo or the research already answered.

---

## PHASE 1 — INTERROGATE (you ↔ Claude)

The interview. Rebuilt around one principle: **every question must justify its own existence.**

### Open with the Decision Map
Lay out the tree of genuinely open decisions, tiered:

```markdown
## Decision Map
### Load-bearing (asked one at a time)
- [ ] <decision> — irreversible / expensive-if-wrong (schema, auth, data model, concurrency, money, public API)
### Cosmetic (batched with defaults)
- [ ] <decision> — cheap to change later
```

Load-bearing = wrong answer costs a migration, a rewrite, a security hole, or user trust. Cosmetic = renameable, refactorable, swappable. Update the map as questions resolve (check items off, add branches corrections open) so the user can see convergence instead of wondering how many questions are left.

### Load-bearing questions — one at a time, structured
Every question ships in this format:

> **Q<n>: <the question>**
> **Why it matters:** <the dependency or constraint that makes this load-bearing>
> **Recommendation:** <Claude's answer, committed — not a menu>
> **If we guess wrong:** <the concrete failure — migration, rewrite, breach, churn>

Wait for the answer before the next question. If drafting a question and the "if we guess wrong" line comes out weak — the question is cosmetic; demote it to the batch. If mid-interrogation a question turns out answerable from the code or the research, answer it yourself and log it to the ledger instead of asking.

### Cosmetic decisions — one batch
Present the whole cosmetic tier as recommendations with a one-line rationale each. The user vetoes by exception; silence = accepted.

### Escape hatch
At any point the user can say **"accept all remaining recommendations"** — Claude locks every open decision at its recommended answer, logs them as such in the plan, and proceeds. Offer it explicitly if the load-bearing tier exceeds ~8 questions.

### Docs-aware mode (auto-on when Phase 0 found CONTEXT.md/ADRs; offer once on greenfield)
- **Enforce the glossary** — when the user's wording collides with a `CONTEXT.md` definition, stop and resolve it on the spot: quote the glossary's meaning, state the apparent meaning, make them pick.
- **Pin down loose words** — an overloaded or vague term gets a proposed canonical replacement before the conversation continues on top of it.
- **Probe boundaries with scenarios** — when two concepts blur, construct a concrete edge case that forces the line between them to be drawn.
- **Check claims against the code** — when the user asserts how something behaves, verify in the source; a mismatch is surfaced as a question, not silently trusted either way.
- **Maintain `CONTEXT.md` as terms settle** (format: [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md)). Glossary ONLY — never implementation details. Created lazily on the first settled term.
- **Offer ADRs only past the three-part test** — expensive to reverse AND puzzling without context AND a genuine trade-off. Format: [ADR-FORMAT.md](./ADR-FORMAT.md). `docs/adr/` created lazily.

### Lock the plan
When the decision map is fully checked and you're aligned, **write `<PLAN_FILE>`** (the resolved
tunable — `PLAN.md` only when it was left at its default):

```markdown
# Plan: <task>
_Locked via claudex-loop — by Claude + <user>_

## Goal
<one paragraph — reflects what the interrogation actually settled>

## Approach
<numbered, concrete steps>

## Key decisions & tradeoffs
<the contestable choices the interrogation resolved — name them so Codex has something to bite; link any ADRs; mark any locked via the escape hatch>

## Toolchain
<only when the skill inventory scan matched something — which installed skills each build track MUST load and follow, per agent (Claude / Codex), plus any generator skills or MCP capabilities the build depends on. Omit the section entirely on no matches. Reviewable like everything else: Codex should attack unused relevant skills and unjustified inclusions alike>

## Assumptions
<the confirmed ledger — with sources>

## Risks / open questions
<anything still genuinely open>

## Out of scope
<bounds the interrogation established>
```

Initialize `<LOG_FILE>`:
```markdown
# Plan Review Log: <task>
Phases 0-1 (recon + interrogation) complete — plan locked with the user. MAX_ROUNDS=<n>.
```

---

## PHASE 2 — REVIEW (Claude ↔ reviewer)

Hand the locked plan to the reviewer selected in Phase 0 Step 0. Codex mechanics verified
end-to-end 2026-06-04; Claude mechanics verified 2026-08-31. Do not "improve" the invocations.

### Re-probe before Round 1 (mandatory)

Phases 0-1 are long; the Phase 0 probe is stale by now. **Re-probe both providers** exactly as in
Step 0. In auto mode, recompute `REVIEWER_SELECTION` with **Codex preferred** — a provider that was
down at Phase 0 and is capable now must be reselected. Forced selections are never recomputed.
**Once Round 1 launches the choice is frozen**: cross-round continuity lives inside a provider's
session and cannot be transferred.

For the Codex path, echo the active model first: read the `model` line from `~/.codex/config.toml`
(absent = "CLI default") and state it with the resolved tunables. Do NOT pin `-m` — pinning
`gpt-5.x-codex` variants 400s on ChatGPT-account auth.

### Tunables (read from args, else default)

| Var | Default | Meaning |
|-----|---------|---------|
| `MAX_ROUNDS` | `5` | Hard cap on review rounds. The loop ALWAYS terminates here. |
| `PLAN_FILE` | `PLAN.md` | The plan Phase 1 produced. Resolved ONCE and interpolated everywhere — no prompt may contain a literal `PLAN.md`. |
| `LOG_FILE` | `PLAN-REVIEW-LOG.md` | Append-only argument transcript. The artifact. |
| `reviewer` | auto-detect | `codex` / `claude`. Sets `REVIEWER_SELECTION`; never asserts capability. |
| `REVIEWER_MODEL` | `opus` | Reviewer model on the Claude path. |
| `REVIEWER_EFFORT` | `high` | Reviewer reasons longer than the planner did. |
| `research` | ask | `none` / `web` / `deep` — pre-answers the Phase 0 research gate. |
| `inspect` | `on` | Post-build cross-inspection. `off` = skip (logged opt-out, never silent). |
| `MAX_INSPECTION_ROUNDS` | `2` | Initial post-build review + one reinspection after accepted fixes. |

Echo resolved values before starting.

### Scratch directory and file naming

```bash
mktemp -d          # prints e.g. /var/folders/.../T/tmp.Xy7QpL — mode 0700
```

Run once. **Record the printed absolute path as `RUN_DIR` and interpolate it literally into every
later command.** No `trap` (it fires the moment the call returns) and no `umask` (it does not
persist); `mktemp -d` already yields a 0700 directory, which is what protects the files inside.

`LOG_FILE` is audit text, never executable state. Never read a path, id, or sha back out of it and
act on it. Cleanup deletes only a `RUN_DIR` captured in the current session, and runs on **every
controlled terminal path** — APPROVED, deadlock, and every STOP below. A crashed session orphans
the directory; say so and leave the path in the log rather than promising an OS reaper.

Every process launch takes the next value of a monotonic counter `t`, never reused:

```
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-out.txt      stdout (the critique)
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-err.txt      stderr
<RUN_DIR>/r<n>-t<NNN>-<provider>-<purpose>-status.txt   exit code
<RUN_DIR>/r<n>-t<NNN>-codex-<purpose>-events.jsonl      Codex path only
<RUN_DIR>/review-prompt.txt   <RUN_DIR>/resume-prompt.txt
```

`<provider>` is `codex`/`claude`; `<purpose>` is `review`/`repair`. Nothing is ever overwritten.

**Write the prompt files before the first launch** — the commands below `cat` them, so an unwritten
file sends an empty prompt. `<RUN_DIR>/review-prompt.txt` holds the review prompt with `<PLAN_FILE>`
substituted **plus the Claude-path coverage addendum when `REVIEWER_SELECTION=claude`**; a
Codex→Claude fallback MUST rewrite this file before relaunching, or the fallback reviewer runs
without its addendum. `<RUN_DIR>/resume-prompt.txt` holds the Rounds 2..MAX prompt, same
substitution. `PLAN_FILE` is resolved ONCE and interpolated into every prompt, log entry, and build
handoff — **no prompt may contain a literal `PLAN.md`.**

### The review prompt (sent each round)

> You are an adversarial reviewer for an implementation plan. Be skeptical and specific — your job
> is to find what breaks, not to be agreeable. Read the plan at `<PLAN_FILE>` (and `CONTEXT.md`/ADRs
> for domain language, if present) and any repo files you need (you are read-only). Identify
> concrete flaws: security holes, race conditions, missing edge cases, schema conflicts, wrong
> assumptions, observability gaps, simpler alternatives. For each, give a one-line fix. Do NOT
> modify any files. End your reply with EXACTLY one line: `VERDICT: APPROVED` if the plan is sound
> enough to implement, or `VERDICT: REVISE` if it still has material problems.

On the **Claude path only**, append:

> Before answering, explicitly cover each of: security and authorization; data integrity and
> migrations; concurrency and ordering; error and failure paths; edge cases and boundary
> conditions; observability; unstated assumptions; and whether a materially simpler approach
> exists. State your conclusion for every area — including the ones you found nothing wrong with.
> `VERDICT: APPROVED` with all areas addressed and no material findings is a valid and expected
> outcome; do not invent defects to appear rigorous.

(On greenfield there are no repo files — the reviewer attacks `<PLAN_FILE>` and its `## Assumptions`
section on their own merits.)

### No pipelines — capture status and stderr separately

Piping into `grep` makes `$?` grep's status, so a reviewer that dies after emitting
`thread.started` reads as success; `2>/dev/null` discards the very text `<reason>` needs. Every
launch is three redirections plus an explicit status write.

### Round 1 — REVIEWER_SELECTION=codex

```bash
<TIMEOUT_PREFIX>codex exec -s read-only --json \
  -o <RUN_DIR>/r1-t001-codex-review-out.txt "$(cat <RUN_DIR>/review-prompt.txt)" \
  > <RUN_DIR>/r1-t001-codex-review-events.jsonl \
  2> <RUN_DIR>/r1-t001-codex-review-err.txt < /dev/null
echo $? > <RUN_DIR>/r1-t001-codex-review-status.txt
```

Parse `thread_id` from the saved events file afterwards -> `THREAD_ID`. **`< /dev/null` is
mandatory:** `codex exec` reads stdin in addition to the prompt arg and otherwise blocks forever
on EOF under any non-TTY driver — a silent ~0% CPU hang.

### Rounds 2..MAX — REVIEWER_SELECTION=codex

```bash
# resume REJECTS -s. Force read-only via -c sandbox_mode, or Codex inherits config.toml
# (possibly danger-full-access) and could WRITE files. Single most important safety line
# on this path — verified 2026-06-04.
<TIMEOUT_PREFIX>codex exec resume "$THREAD_ID" -c sandbox_mode="read-only" --json \
  -o <RUN_DIR>/r<n>-t<NNN>-codex-review-out.txt \
  "$(cat <RUN_DIR>/resume-prompt.txt)" \
  > <RUN_DIR>/r<n>-t<NNN>-codex-review-events.jsonl \
  2> <RUN_DIR>/r<n>-t<NNN>-codex-review-err.txt < /dev/null
echo $? > <RUN_DIR>/r<n>-t<NNN>-codex-review-status.txt
```

### Round 1 — REVIEWER_SELECTION=claude

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

### Rounds 2..MAX — REVIEWER_SELECTION=claude

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

**The Claude flag set is the security boundary and is not negotiable.**
`--allowedTools`/`--disallowedTools` is NOT sufficient: a session configured that way still exposes
`Agent`, `Workflow`, `Skill`, `ToolSearch`, and deferred `WebFetch`/`RemoteTrigger` among ~25 tools,
and `Agent` alone defeats a denylist because a spawned subagent carries its own Write and Bash.
The `--restricted --tools` set above exposes exactly Glob, Grep, Read (verified 2026-08-31).

**Honest scope:** tool-level restriction enforced by the Claude Code process, not an OS-enforced
read-only mount; managed enterprise settings still apply. Weaker than Codex's `-s read-only`.

**`--bare` MUST NOT be used** — it forces `ANTHROPIC_API_KEY`/apiKeyHelper and never reads OAuth,
failing with `Not logged in` on subscription auth. `--safe-mode` is the isolation flag.

**Timeout guard (all rounds, both paths):** ten-minute ceiling so a stall fails loud. Via Claude
Code's Bash tool pass `timeout: 600000` (the 2-minute default kills real reviews). In a plain shell
use the `TIMEOUT_MODE` prefix from Step 0. A tripped ceiling is a failed attempt: **apply the
failure-transition table below** — never blindly retry the same provider.

### Failure transitions (exhaustive)

Failure classes: launch failure (auth/model/exec), timeout, network failure, exit 0 with empty
output, second malformed-verdict attempt. All are failed attempts.

| When | `REVIEWER_SELECTION` | Action |
|---|---|---|
| Any pre-Round-1 probe failure | auto | Switch to the other capable provider, print the notice, proceed. No prompt. |
| Any pre-Round-1 probe failure | forced | STOP with the probe error. |
| **Any** Round-1 failure, any class | auto | Retry Round 1 **once** with the other capable provider under a new `t`. **Do not increment the round.** Log both. Other provider not capable -> STOP. |
| **Any** Round-1 failure, any class | forced | STOP. |
| Round-1 **fallback** attempt also fails | auto | STOP. There is no third provider; do not loop. |
| A **repair** launch fails (any class, as opposed to returning a second malformed verdict) | either | Failed attempt — route to this table exactly like a review-launch failure. |
| `-status.txt` missing entirely (redirection never completed — disk full, process killed) | either | Failed attempt. Absence of a status file is never treated as success. |
| **Any** Round >= 2 failure, any class | either | STOP. Continuity cannot transfer between providers; restarting with the other reviewer is a user decision, logged as a restart. |

Failure classes include **quota/spend-limit exhaustion**, observed 2026-08-31: the CLI exits
non-zero and prints the reason **on stdout, not stderr**. Source `<reason>` from stderr *or*
stdout, whichever is non-empty. **Sanitize by redaction, not truncation** — strip URLs, tokens,
absolute paths, and environment values before logging; a first line bounds length, not
sensitivity. Quota exhaustion on one model is worth reporting to the user with the reset time
rather than silently switching models.

### Each round, after the reviewer returns

1. Read the launch's `-status.txt`. Non-zero -> failed attempt; apply the table above.
2. Assert its `-out.txt` exists and is non-empty. Empty on exit 0 -> failed attempt.
3. **Validate the verdict BEFORE appending anything to `LOG_FILE`**, so a failed attempt never
   looks like a completed round:
   - strip trailing blank lines; the last non-empty line must match exactly
     `^VERDICT: (APPROVED|REVISE)$`, and **the anchored line pattern** `^VERDICT: (APPROVED|REVISE)$`
     must match exactly once. Do NOT count the bare substring `VERDICT:` — a reviewer that quotes
     the instruction back ("...end with VERDICT: APPROVED or VERDICT: REVISE") legitimately
     produces three occurrences. Observed 2026-08-31: a valid Claude review scored 3 substring
     hits and would have been wrongly flagged malformed.
   - violation -> repair is permitted **only if the review launch already produced a substantive
     review**: non-trivial length, concrete findings or explicit conclusions, and on the Claude
     path a stated conclusion for every coverage area. A refusal, a clarifying question, or an
     empty gesture is a **failed attempt**, never repairable. *This gate exists because the
     motivating failure was a reviewer refusing to review; without it the repair would launder
     that refusal into a clean `APPROVED`.*
   - repair permitted -> one format-only request under the next `t` with purpose `repair`, bound
     to the review launch it repairs; it **does not consume a round**: *"Your reply did not end
     with exactly one `VERDICT: APPROVED` or `VERDICT: REVISE` line. Resend only that one line."*
     Neither output overwrites the other. A second violation is a failed attempt.
4. Append to `LOG_FILE` under `## Round <n> — Codex` or `## Round <n> — Claude (reviewer)`: the
   full critique, plus the repair launch's verdict line if a repair occurred. Failed attempts go
   under `## Round <n> — failed attempt` with **the sanitized reason selected above** — stderr or
   stdout, whichever was non-empty, plus Codex's events stream where relevant. Never echo raw
   output wholesale; redact URLs, tokens, absolute paths, and env values.
5. `VERDICT: REVISE` -> Claude decides **what's actually worth acting on** (Claude is final
   arbiter — the reviewer advises, it does not command). Revise `<PLAN_FILE>`. Append
   `### Claude's response`: what changed, what was rejected, why. Increment the round.
6. `VERDICT: APPROVED` -> Resolution. Round > `MAX_ROUNDS` -> Resolution (deadlock).

### Resolution (you sign off — final gate)

- **APPROVED:** present the final `<PLAN_FILE>`, a 3-bullet summary of what the loop improved, and
  the round count. Ask: *"Interrogated + survived N rounds of <reviewer>. Implement it now — Codex
  builds it (`/codex-build`), Claude builds it, or stop here?"* **Offer the Codex build option iff
  `CODEX_CAPABLE`** — reviewer preference and builder capability are independent, so
  `reviewer=claude` with Codex installed still offers a Codex build. Code only on a yes.
- **MAX_ROUNDS hit without APPROVED (deadlock):** do NOT fake convergence. List each unresolved
  point + Claude's counter-position; hand it to the user. A flagged disagreement beats a false
  "approved."

### PHASE 3 (optional) — BUILD

**Ordered sequence — follow it exactly; the steps are not interchangeable:**

1. **Retain or recreate `RUN_DIR`.** Do NOT clean it at Resolution if the user chose to build —
   Phase 3 writes its evidence into the same directory. Cleanup happens after the final diff gate.
2. **Clean-tree gate** (below). Commit the plan artifacts or stash unrelated edits first.
3. **Capture `BASE_COMMIT`** into `<RUN_DIR>/base-commit.txt` — outside the repo.
4. **Build.** The builder writes to the repo; that is the only writing permitted in this window.
   If the user picks Codex, invoke `codex-build` with `SPEC_FILE=<PLAN_FILE>` and the same
   `LOG_FILE` — roles flip, Codex writes with full access and Claude reads the diff and runs the
   proof. If the user picks Claude, implement directly.
5. **Re-check** `git status --porcelain`; abort if anything dirty is not the build's own output.
6. **Capture evidence** into `RUN_DIR`.
7. **Cross-inspection**, then all deferred `LOG_FILE` appends.
8. **Final human diff gate**, then clean up `RUN_DIR`.

The "no repository write between the gate and evidence capture" rule means **no orchestrator or
bookkeeping write** — no `LOG_FILE` append, no scratch file inside the repo. The build's own output
is exactly what the diff is meant to contain.

### Post-build cross-inspection (default on every Claude-built path)

The doctrine is *whoever made the thing never checks the thing* — that applies to Claude's code too.
**Re-probe both providers first**, then select by WHO BUILT, not by the Phase-2 reviewer:

| Builder | Inspector |
|---|---|
| Codex (`codex-build`) | Claude — already the `codex-build` design (reads the full diff, runs the proof). No extra inspector. |
| Claude | Codex if `CODEX_CAPABLE`, else a fresh restricted Claude session if `CLAUDE_CAPABLE`. Codex is preferred even if Phase 2 used Claude — a rival inspector is the point. |
| Claude, neither capable | None. Explicit, logged opt-out at the human gate. Never silent. |

**Clean-tree gate before the build** — the same gate `codex-build` enforces, now on this path too.
By Phase 3 the worktree carries `<PLAN_FILE>`, `LOG_FILE`, and possibly unrelated edits; without
the gate the diff mixes them into the claimed build delta.

```bash
git status --porcelain      # must be empty. Commit the plan artifacts (or stash unrelated
                            # edits) first. Dirty tree -> STOP and ask the user.
git rev-parse HEAD > <RUN_DIR>/base-commit.txt   # BASE_COMMIT held OUTSIDE the repo
```

The gate is check-then-act with no lock. **Re-run `git status --porcelain` immediately before
evidence capture** and abort if the set of dirty paths is anything other than the build's own
output — a second loop in the same repo, or a manual edit landing mid-build, otherwise
contaminates the delta with the gate never noticing. Concurrent Phase-3 builds in one repo are
not supported; state that rather than pretending the gate covers it.

**No repository write may occur between the clean gate and evidence capture** — writing
`BASE_COMMIT` into `LOG_FILE` here would re-dirty the tree the gate just cleaned and put the log
hunk inside the "builder-only" diff. Defer every Phase-3 `LOG_FILE` append until after the evidence
files exist.

The Claude inspector has no Bash and cannot run `git`; reading the worktree cannot separate the
build from its base. Materialise the evidence:

```bash
git diff --no-renames --stat <BASE_COMMIT> --      > <RUN_DIR>/manifest.txt
git status --porcelain                            >> <RUN_DIR>/manifest.txt
git ls-files --others --exclude-standard          >> <RUN_DIR>/manifest.txt  # git C-quotes odd names
git diff --no-renames --numstat <BASE_COMMIT> --  >> <RUN_DIR>/manifest.txt  # binaries show "-  -"
git diff --no-renames <BASE_COMMIT> --             > <RUN_DIR>/diff.patch    # NOT --binary
```

**`--no-renames` on every evidence command.** With `diff.renames` enabled (an increasingly common
non-default), a renamed entry changes `--numstat`'s field count and misaligns every record after
it, corrupting the binary-size portion of the manifest.

Note there is **no `..HEAD`**: before the human commit gate `HEAD` still equals `BASE_COMMIT`, so
`git diff <BASE_COMMIT>..HEAD` is empty and the inspector would review nothing while reporting
success. `git diff <BASE_COMMIT> --` compares the base commit to the working tree.

- **No `--binary`** — it embeds binary patches, contradicting the rule not to inline them. Plain
  `git diff` emits `Binary files ... differ`; measure their sizes separately with `wc -c`.
- **Manifest paths use git's own C-style quoting**, so a filename containing a newline stays one
  record. Never `printf '%s'` a raw filename into the manifest.
- **Untracked files** are invisible to `git diff`; enumerate NUL-delimited, copy regular files
  only, name (and skip) symlinks, special files, and anything over 256KB. Nothing silently dropped.
- **Scope:** git-visible files only. `.gitignore`d files are NOT inspected — say so in the log.
- **Large diffs:** inspect every textual changed file, chunking across rounds. Any file left
  uninspected marks the inspection **INCOMPLETE** with the paths named, and the final gate then
  requires an explicit logged opt-out. Partial inspection is never reported as complete.

Launch the inspector with a fresh `SID` (it must see the code cold), the same restricted flag set
plus `--add-dir <RUN_DIR>`, told to read `manifest.txt` first. PR-style findings — correctness,
spec fidelity, edge cases, nothing outside scope. No verdict line; this is advisory, not a gate
loop. Claude arbitrates each finding: accept (fix, rerun affected tests) or reject *with a logged
reason*. Cap at `MAX_INSPECTION_ROUNDS`.

**Inspector failure transitions** (any class — launch, timeout, network, empty output):

| Inspector | First failure | Second failure |
|---|---|---|
| Codex | fall back to a fresh restricted Claude inspector if `CLAUDE_CAPABLE`; log both | mark **not performed**, explicit logged human opt-out at the final gate |
| Claude | retry once with a fresh `SID` | mark **not performed**, explicit logged opt-out |

Append to `LOG_FILE` under `## Post-build inspection`: findings verbatim, Claude's dispositions,
rounds used, and any INCOMPLETE/not-performed state. Present alongside the final diff.

Opt-out: `inspect=off`, or the user declining at Resolution. Skipping silently is never allowed.

---

## Hard rules
- Phases run in order: 0 → 1 → 2. Don't write `<PLAN_FILE>` until the interrogation has actually resolved the decision map with the user (or they invoked the escape hatch).
- The assumptions ledger is presented ONCE as a batch — never drip assumptions as individual questions.
- **Pick the command block matching `REVIEWER_SELECTION`. Never mix the two branches.** The blocks sit next to each other precisely so the wrong one is easy to grab; the titles are hard conditions, not labels.
- The reviewer is read-only EVERY round. Codex: `-s read-only` first call, `-c sandbox_mode="read-only"` on every resume (resume has no `-s`). Claude: the full `--restricted --tools "Read,Grep,Glob" --strict-mcp-config --safe-mode --permission-mode dontAsk` set — an allow/deny list alone is NOT read-only. Neither ever writes.
- Probe **both** providers at every phase boundary, and probe the whole branch (CLI, auth, flags, UUID source, scratch dir) — not just presence.
- An explicit `reviewer=` override is a preference, never a capability claim. Forcing an incapable reviewer STOPS.
- `REVIEWER_SELECTION=claude` does NOT suppress the Codex build option when `CODEX_CAPABLE`.
- Downgrades are announced with the Phase 0 notice, verbatim. Silent degradation is never allowed.
- `LOG_FILE` is audit text. Never read a path, id, or sha back out of it and act on it.
- The loop ALWAYS terminates at `MAX_ROUNDS`.
- Claude is final arbiter on every REVISE — incorporate good critiques, reject bad ones *with a logged reason*. Don't cave to everything (defeats the cross-model check) and don't ignore it (defeats the point).
- Code only after the user's final sign-off.
- `LOG_FILE` is the deliverable — keep the whole argument.
- `CONTEXT.md` stays a glossary only — never implementation details.

## What NOT to do
- Don't invoke this skill just to review pre-existing code — that's `/codex:review`. (Code built BY this skill does get reviewed — that's the post-build cross-inspection, and it's on by default.)
- Don't pin a `-codex` model variant on ChatGPT-account auth — it 400s.
- Don't let the reviewer edit files. Read-only, always.
- Don't use `--bare` for the Claude reviewer — it forces `ANTHROPIC_API_KEY` and fails under OAuth.
- Don't rely on shell variables, functions, or `trap` surviving between Bash calls — each call is a fresh shell. Carry literals instead.
- Don't present the Claude fallback as equivalent to cross-provider review. It is a downgrade, and the notice says what it loses.
- Don't skip Phase 1 — the interrogation is half the value.
- Don't ask questions the recon already answered, and don't ask a load-bearing-format question whose "if we guess wrong" is weak — demote it to the cosmetic batch.
- Don't turn Phase 0 into a research project on a medium-stakes task — the research gate exists so the user picks the depth; don't launch the deep-research workflow without an approved prompt.
