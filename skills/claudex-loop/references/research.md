# Research fan-out: estimate before launching

Expands Phase 0. Applies when research opts in to a multi-agent fan-out. The skill decides *whether*
to research and how deep; this is how to show the user what that will cost in work before it runs.
Provider-agnostic by construction: it names no model and depends on no particular fan-out mechanism.

## Print the shape, at the opt-in that already exists

Deep research already requires explicit opt-in. Show the estimate in that same exchange — it is not
a second approval step.

```
Research fan-out — review before launch

  resolved configuration
    finders        4 launches   effort=low       model: <resolved, or "CLI default (unresolved)">
    deep-readers   6 launches   effort=low       model: <same>
    synthesis      1 launch     effort=default   model: <same>
    retry allowance: 0-2 finder relaunches, conditional (NOT scheduled)

  question -> angle assignment (angle shown, not just the id)
    Q1  prior art    -> a1 "existing tools"      a3 "standards + papers"
    Q2  stack        -> a2 "official docs"       a4 "community comparisons"
    Q3  pitfalls     -> a1 "postmortems"         a4 "issue trackers"
    (every question needs >= 2 DISTINCT agents on DISTINCT angles)

  workload estimate — UNCALIBRATED GUESSES, NOT A PREDICTION
    finders        4 x ~25k   ~100k output tokens
    deep-readers   6 x ~40k   ~240k
    synthesis      1 x ~30k    ~30k
    ─────────────────────────────────
    11 scheduled launches · ~370k output tokens
    plus 0-2 conditional retries   ~0-50k  (up to 13 launches)

  These per-launch numbers have never been measured for this workflow. Output
  tokens only — input is excluded and is not small. Actual spend includes input.
  Approval constrains LAUNCH COUNTS, not tokens: a single launch emitting more
  than its guessed band can exceed these totals while fully compliant.

  <cost line: see "When to give a cost figure">

  Launch runs exactly this configuration and these counts.
Reply: launch / set <stage>=<n> / effort=<level> / cancel
```

## When to give a cost figure

Only when the model that will actually run is resolved. The skill requires reporting requested and
observed model information separately and reporting an unresolved CLI default honestly — a price
computed against a guessed model is exactly the kind of confident-looking fiction that rule exists
to prevent.

- **Model resolved:** one figure, for the configuration that will run, at that model's published
  rates. Label it arithmetic over the guessed bands above, not a forecast. Never price a
  configuration the run will not execute.
- **Model unresolved:** give launches and token estimates, and say plainly that no cost figure is
  given because the CLI default is unresolved.

Do not write "bound", "ceiling", or "maximum" anywhere in the block. Nothing here is enforceable.

## Sign-off binds the shape

`launch` runs exactly the printed configuration and scheduled counts, and may use **up to** the
printed retry allowance. Unused retries are the expected case, not a shortfall — approval binds a
per-stage ceiling for retries and an exact count for scheduled launches. `set <stage>=<n>` and
`effort=<level>` are edits: each reprints the block and waits. Reject an edit that leaves a question with fewer than
two distinct agents on distinct angles, and say why. If the run would exceed the approved counts for
any reason, stop and re-present rather than continuing.

## Try effort before adding a second model

[Published guidance](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)
is to sweep effort on the model already in use before reaching for a cheaper second one, because a
multi-model configuration that looks cheaper can cost more than the same model at lower effort. The
supporting measurements — a near-flat accuracy-against-cost curve on WideSearch, DeepWideSearch,
BrowseComp and GDPval — were taken with one specific model and orchestration shape, so they do not
transfer to an arbitrary workload. Low effort is a reasonable **starting point** for retrieval and
extraction stages, with synthesis at the default.

That is a reason to *try* effort first. It is not a prediction about any particular workload, and it
does not license hard-coding a model for research agents — the skill forbids that.

## Coverage discipline

- Assign angles explicitly and print them; agents that choose their own collapse onto the same one.
- A question is covered only when at least two distinct agents on distinct angles each return at
  least one candidate relevant to *that* question. Returning irrelevant candidates is a failure too,
  not just returning none.
- Bound retries with the allowance printed in the estimate. Do not loop until dry — it is unbounded
  against an approved budget.
- Name any question that ends with fewer than two covering agents in the brief. Silent partial
  coverage reads as completed coverage.

## When the runner panel executes the fan-out

The runner's `panel` mode (see the runtime reference) enforces part of this: launch count, concurrency and wall clock are hard limits, the launch is bound to the dry-run the user approved, and a question with fewer than two distinct angles is refused before launch and reported as under-covered after it. Token bands stay advisory. The panel has no retry allowance; a retry is a new, separately approved run.

Workers may select `provider: claude|codex|agy`, provided it differs from the host. The default remains the opposite provider. agy supports `kind: web` only; its verified excerpts come from full `read_url_content` transcript results for the exact cited URL. Its `search_web` summaries do not verify a citation. The dry-run digest includes the effective provider, model and effort for each worker and the plan SHA256, even for web-only prompts. Set up `agy-profile` and complete the separate manual login before launching; see [runtime](runtime.md#antigravity-plan-body-review).

## What extraction can and cannot promise

Ask readers for a verbatim quote and a locator alongside each claim, plus what they reviewed and
what they skipped. Quotes establish that a *retained* claim is faithful to its source. They cannot
establish that nothing was missed: a reader can quote accurately, report full coverage, and still
have skipped the limitation that mattered. Treat self-reported coverage as a warning signal, and
spot-check locators against sources for the claims the brief leans on.
