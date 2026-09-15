# Plan: pre-flight estimate + effort-first default for the deep-research tier
_Locked via claudex-loop — by Claude + Yang Hu. Revised after Codex rounds 1-2. Round 1 inverted the
model/effort default; round 2 removed the cost predictions that kept generating defects._

## Goal

Make the `deep` research tier's workload visible before it runs, and replace its blanket
`model: 'opus'` pin and "leave effort at the default" rule with an effort-first default.

**What this plan deliberately does NOT do:** predict what a run will cost. Two review rounds
established that every such prediction here is unfounded — the bands are guesses, the published
reductions are cost-per-task (input included) measured on a different model in a different
architecture, and none of it has been measured on this workflow. The tier ships **explicitly
labelled experimental cost guidance** until acceptance row 7 is executed.

**Scope:** the `deep` tier of the Phase 0 research gate. Declared edit boundary: the `deep` bullet
in `skills/claudex-loop/SKILL.md`, one row in that file's Tunables table, and two lines in
`README.md`. Nothing else in the skill acquires a new rule.

## Approach

### 1. Effort-first default

Published guidance (`optimizing-for-cost-and-intelligence`): *"Sweep effort on your current model
first. It is the cheapest experiment on this page, and most workloads end there. If the sweep shows
a gap, price the stronger model alone at low effort."*

| stage | default |
|---|---|
| finders | `effort: 'low'` |
| deep-readers | `effort: 'low'` |
| synthesizer | `model: 'opus'`, `effort` omitted (default `high`) |

`model` is omitted for finders and deep-readers — restoring workflow-authoring's stated default.
The synthesizer **is** pinned to Opus, because the rest of the paragraph reasons about "the Opus
synthesizer" arbitrating coverage gaps; leaving it to inherit would make that language false in a
Sonnet session. This pin is a stated choice, not a measured one.

**No claim is made that `low` is cheaper or better on this workflow.** The published results are
cited as the reason to *try* effort first. They were measured with Claude Fable 5, on whole-task
cost, comparing an orchestrator against a solo model — this workflow keeps eleven agents either
way. The transfer is across model, architecture, and stage.

### 2. Configuration resolution — one defined order, printed

Ambiguity here was a round-2 defect. Resolution order, applied top to bottom, last wins:

1. Session model, inherited (finders/readers); synthesizer pinned Opus.
2. **Session-pricing policy**: if the session model's published output rate exceeds Opus's, pin
   finders and readers to `model: 'opus'`. This is a **user-approved pricing policy, not a
   demonstrated saving** — it avoids multiplying an above-Opus rate across ~11 agents. Fable 5.1's
   cached-input rate is *lower* than Opus's (Fable 5's is not), so "2x Opus" is not uniformly true; the policy is
   about output rate only and says so.
3. `models=sonnet-workers` — overrides 1 and 2 for finders and readers.
4. `effort=<level>` — applies to finders and readers only; the synthesizer is not affected.

The resolved configuration is **printed in the estimate**, per stage, with the rule that set it.

### 3. `models=sonnet-workers` — opt-in, no "must beat" claim

Available as a switch. The paragraph records the published context and nothing more:

> On DeepWideSearch, *"`low` also matched an orchestrator with a Claude Sonnet 5 worker at 29% lower
> cost: lowering effort beat an architecture change."* That comparison was orchestrator-vs-solo on
> Claude Fable 5; this workflow is orchestrated either way, so it does not predict the ranking here.
> It is why effort-first is the default, not evidence that Sonnet workers lose on your workload.
> Orchestrators did win on a 21.6M-token context-exceeding corpus (about half the cost, 10-12 points
> lower accuracy) — a shape a very large sweep can reach.

No gate enforces "must beat", so the plan does not claim one.

### 4. Pre-flight estimate at the existing sign-off

```
Deep research plan — review before launch

  resolved configuration
    finders        4 agents   effort=low       model: inherited (session)
    deep-readers   6 agents   effort=low       model: inherited (session)
    synthesizer    1 agent    effort=default   model: opus (pinned)
    retry allowance: up to 2 finder relaunches (counted below)

  question -> finder angle assignment (angle shown, not just the id)
    Q1  prior art        -> f1 "existing tools/products"   f3 "academic + standards"
    Q2  stack landscape  -> f2 "official docs"             f4 "community comparisons"
    Q3  pitfalls         -> f1 "postmortems"               f4 "issue trackers + gotchas"
    (every question has >= 2 DISTINCT angles; edits that break this are rejected)

  workload estimate — UNCALIBRATED GUESSES, NOT A PREDICTION
    finders        4 x ~25k   ~100k output tokens
    deep-readers   6 x ~40k   ~240k
    synthesizer    1 x ~30k    ~30k
    retries        2 x ~25k    ~50k
    ─────────────────────────────────────
    13 launches · ~420k output tokens

  These per-agent numbers have never been observed for this workflow. Output
  tokens only — input is excluded and is not small. Actual spend includes input
  and may differ substantially in either direction.

  Arithmetic at the resolved configuration and current published rates: ~$X.XX
  (this is arithmetic over the guesses above, not a forecast)

  Launch runs exactly this configuration and these counts.
Reply: launch / set agents <stage>=<n> / models=sonnet-workers / effort=<level> / cancel
```

- **One** dollar figure, for the configuration that will actually run. No ranges for configurations
  the run will not execute; no percentage discount transferred from another model's benchmark.
- **Token accounting defined**: output tokens across all agent turns, including thinking and
  tool-call arguments — the units `effort` governs. The bands are stated *for the resolved effort
  level*, so nothing is discounted twice.
- The words "bound", "ceiling", and "maximum" do not appear.

### 5. Sign-off binds execution

`launch` runs exactly the printed configuration, counts, and retry allowance. `set agents` /
`models=` / `effort=` are **edits**: each reprints the block and waits. An edit that leaves any
question with fewer than 2 finder angles is rejected with the reason. Exceeding approved counts for
any reason stops the workflow and re-presents.

### 6. Finder coverage

- Angles are **assigned** (printed above), not chosen by agents, so they cannot collapse onto one.
- A finder qualifies as covering its question only if it returns >= 1 candidate **relevant to that
  question** — the synthesizer judges relevance; zero-candidate is not the only failure.
- Up to **2 relaunches total** across the whole run, drawn from the printed allowance. Not per-finder.
- Loop-until-dry is not used — unbounded against an approved allowance.
- Questions ending with fewer than 2 covering finders are named in the brief.

### 7. Deep-reader schema

```js
const READ_SCHEMA = { type: 'object', properties: {
  source_id: { type: 'string' },                  // restored — binds every record to its document
  claims: { type: 'array', items: { type: 'object', properties: {
    claim:   { type: 'string' },
    quote:   { type: 'string' },                  // provenance for THIS claim
    locator: { type: 'string' },                  // heading/anchor within source_id
    caveats: { type: 'string' },                  // limitations stated near the quote, or "none found"
  }, required: ['claim','quote','locator','caveats'] } },
  sections_reviewed: { type: 'array', items: { type: 'string' } },
  sections_skipped:  { type: 'array', items: { type: 'string' } },
  coverage_note:     { type: 'string' },
}, required: ['source_id','claims','sections_reviewed','sections_skipped','coverage_note'] }
```

**Honest scope, stated in the paragraph:** quotes establish that a *retained* claim is faithful.
Self-reported coverage is a **warning signal, not an omission control** — a reader can report full
coverage and "none found" while having missed the limitation that mattered, and every field
validates. The only real check is the synthesizer spot-checking `source_id` + `locator` against the
source for the claims the brief leans on. That is a prose instruction, not a guarantee.

### 8. `budget` guard

```js
const A = typeof args === 'string' ? JSON.parse(args) : args
// derived from the APPROVED counts, not a hardcoded constant
const EST_OUTPUT = approved.finders * BAND.finder
                 + approved.readers * BAND.reader
                 + BAND.synth
                 + approved.retries * BAND.finder
const SYNTH_RESERVE = BAND.synth
if (budget.total !== null && budget.remaining() < EST_OUTPUT + SYNTH_RESERVE) {
  log(`budget remaining ${Math.round(budget.remaining()/1000)}k < approved estimate + synthesis reserve`)
  return { launched: false, reason: 'insufficient_budget' }
}
```

- Derived from approved counts and the calibrated bands, so editing counts moves the threshold.
- Retries included.
- **Synthesis headroom is best-effort, and the check must survive the next worker's own band.**
  Before dispatching a worker, require `budget.remaining() >= SYNTH_RESERVE + BAND[thatStage]` —
  comparing against `SYNTH_RESERVE` alone permits a 40k reader to launch with 31k left against a
  30k reserve and exhaust the budget before synthesis. When the check fails, stop launching workers
  and go to synthesis with what has returned, logging the truncation.
- **Concurrency caveat, stated rather than papered over:** workers launched in parallel are not
  individually accounted for while in flight, so several can each see sufficient headroom. Dispatch
  workers in bounded batches and re-check between batches. Headroom is therefore **best-effort, not
  a guarantee** — the bands are guesses, so no arithmetic over them can be one.
- **Genuine exhaustion is a different case and is not recoverable.** Per D4 an exhausted budget makes
  `agent()` throw, so synthesis cannot be promised after it. That path returns partial results
  naming the stages that completed; it does not claim a brief.
- **Units caveat, stated:** `budget.remaining()` counts output tokens per workflow-authoring
  (*"output tokens spent this turn"*); `EST_OUTPUT` uses the same units. If that ever diverges the
  guard is wrong — flagged in Risks.
- Parent handling: on `launched: false` the skill reports the shortfall and offers the `web` tier or
  reduced counts. Mid-run exhaustion is reported as a partial run naming completed stages.

### 9. Retained verbatim
Tier description; "The user choosing this tier IS the explicit opt-in the Workflow tool requires";
the `args` JSON-string gotcha (2026-08-13); the brief-saving convention.

## Key decisions & tradeoffs

1. **Effort-first default**, on the published recommendation to sweep effort before changing
   architecture — cited as a reason to try, not as evidence about this workflow.
2. **No cost predictions.** One arithmetic figure for the configuration that will run, over bands
   labelled uncalibrated. Removing predictions was the response to two rounds in which every
   prediction produced a defect.
3. **`model` omitted for workers; synthesizer pinned Opus.** The pin exists so the paragraph's own
   reasoning about the synthesizer stays true under any session model. Stated as a choice.
4. **The session-pricing policy is a policy, not a saving.** It caps inherited output rates; it is
   not claimed to lower task cost.
5. **This inverts two Phase-1 decisions** (Sonnet workers as default). Round 1 established the
   rationale for them was false. Flagged to the user, not absorbed.
6. **Quotes are provenance; coverage is a warning signal.** Neither is an omission control, and the
   paragraph says so rather than implying a guarantee.
7. **Ships labelled experimental** until acceptance row 7 runs.

## Assumptions

### Documented
- D1. `effort` affects **all** output tokens — text, tool calls and arguments, thinking;
  *"Lower effort also means fewer and terser tool calls."* `low` is recommended for *"subagents"*.
- D2. Research-benchmark cost curve is nearly flat: `low` costs a third to a half less for 1-3
  points; `medium` matches default accuracy at 70-87% of cost. **Measured with Claude Fable 5, as
  cost per task (input included), whole-task not per-stage.**
- D3. *"On DeepWideSearch, `low` also matched an orchestrator with a Claude Sonnet 5 worker at 29%
  lower cost."* **Orchestrator vs solo** — an architecture comparison, not a worker-model one.
  Orchestrators won on a 21.6M-token context-exceeding corpus at ~half cost, 10-12 points lower.
- D4. `agent()` takes `opts.model`/`opts.effort`, default omit `model`. `budget.total` null absent a
  directive; `remaining()` is output tokens for the turn; exhaustion throws. — workflow-authoring
- D5. Rates per MTok in/out: Opus 5 $5/$25, Sonnet 5 $2/$10, Fable 5/5.1 $10/$50, Haiku 4.5 $1/$5.
  Fable 5.1's cached-input rate is lower than Opus's; Fable 5's is not. — claude-api / pricing docs
- D6. *"Even at its lowest effort setting, Opus 5 passes more tasks than any other model"* —
  **Zapier AutomationBench specifically.**

### Observed (2026-09-15)
- O1. codex-cli 0.153.4, claude 2.1.272, both capable. Reviewer model `gpt-6-astra` per config.
- O2. `codex login status` writes to stderr, not stdout, in 0.153.4; exit code is the gate.

### Inferred
- *(I1 deleted round 1: "effort trims only reasoning tokens" — contradicted by D1.)*
- *(I2 deleted round 2: "extraction is the least effort-sensitive stage" — unsupported, same class
  of error as I1.)*
- I3. The published effort-first recommendation is worth following on this workflow. This transfers
  across model (Fable->Opus), architecture (solo-vs-orchestrator -> orchestrated either way), and
  granularity (whole-task -> per-stage). **It justifies trying effort first; it predicts nothing.**
- I4. The 25k/40k/30k bands are guesses from stage descriptions. Never observed.

### Repo facts
R1. Brownfield docs-only repo. R2. No `CONTEXT.md`/`docs/adr`. R3. `main` at `fa2b231`.
R4. No matching skill on either bench; none loaded.

## Risks / open questions

1. **Nothing here is measured.** The estimate is arithmetic over guessed bands; the published
   results are someone else's, on another model, in another architecture. This is the plan's
   defining limitation and the reason for the experimental label.
2. **I3 is the load-bearing inference** and is weaker than it looks — it transfers on three axes.
3. **Bands (I4) are uncalibrated**; acceptance row 7 is the only thing that touches them.
4. **Coverage is self-reported.** The synthesizer spot-check is prose, not enforcement.
5. **Budget units.** If `budget.remaining()` ever counts anything other than output tokens, the
   guard's comparison is wrong.
6. **The synthesizer Opus pin is unmeasured**, like everything else here.
7. **The deep-research workflow has never run end-to-end in this repo.**

## Acceptance

| # | Scenario | Pass |
|---|---|---|
| 1 | Sonnet session, no overrides | resolved block prints Sonnet workers + Opus synthesizer; no text anywhere calls the workers Opus |
| 2 | Fable session, no overrides | pricing policy fires, workers pinned Opus, the printed reason names the policy not a saving |
| 3 | Fable session + `models=sonnet-workers` | switch wins over the policy per the resolution order; resolved block shows Sonnet workers |
| 4 | `effort=medium` | applies to workers only; synthesizer still shows effort=default |
| 5 | `set agents finders=1` | rejected — a question would drop below 2 angles; reason printed |
| 6 | `set agents readers=12` | accepted; estimate AND budget threshold both move |
| 7 | **Live calibration run** on one small real question: record the question, the resolved configuration, observed output tokens per stage, and whether the brief named any source the reader had skipped | bands corrected in the same commit AND the recorded question/config written beside them; the uncertainty qualifier is retained for every other question, model, and effort level — one observation calibrates one point, not a curve. If skipped, the paragraph keeps the experimental label |
| 8 | Budget with `total` set just above workers but below workers+synthesis | refuses to launch; parent offers `web` tier or reduced counts |
| 9a | Budget falls below `SYNTH_RESERVE + BAND[next stage]` before a dispatch | that worker is not launched; synthesis runs on what returned; log names the truncation |
| 9b | Budget **genuinely exhausted** (an `agent()` call throws) | partial results returned naming completed stages; **no synthesis is attempted or promised** |
| 10 | Grep the edited paragraph | no instruction applies outside the deep-research workflow; `REVIEWER_MODEL` untouched; no "bound"/"ceiling"/"maximum" in the estimate block |

Row 7 is the only row that measures anything. Rows 1-6 and 8-9 are behaviour, not wording.

## Out of scope

`REVIEWER_MODEL`, Phase 2, Phase 3 · any rule outside the deep-research workflow ·
`completeness critic` as a new stage · `.gitignore`/`.DS_Store` · `legacy/`, `codex-build`,
`codex-review` · Haiku as a worker tier · README hero, mermaid, phase table, badges, SVGs ·
**any claim about which configuration is cheaper or better on this workload** — unmeasured.
