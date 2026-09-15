# Plan Review Log: deep-research workload estimation + model/effort tiering
Phases 0-1 (recon + interrogation) complete — plan locked with the user. MAX_ROUNDS=5.
Reviewer: Codex (codex-cli 0.153.4, logged in via ChatGPT). TIMEOUT_MODE=timeout.
Scope constraint stated by the user and carried into the plan: deep-research tier ONLY.

## Round 1 — Codex

The plan still has material defects. The headline arithmetic is correct; the cost guarantees, downgrade rationale, and runtime instructions are not.

### 1. [P1] I1 relies on a false description of effort

[PLAN.md:151](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:151) says effort trims reasoning tokens. Anthropic documents effects on **text output, tool calls, and thinking**, including fewer tool calls at lower effort. Search results are input; emitting quotations does not establish what dominates an agent’s total bill. Sonnet readers also retain default effort while the alternative uses Opus at low effort. The plan has not established which is cheaper for equivalent coverage. [Effort documentation](https://platform.claude.com/docs/en/build-with-claude/effort)

**Fix:** Remove the reasoning-only claim and require a representative cost-and-coverage comparison before making Sonnet mandatory.

### 2. [P1] The exemption from “measure first” is rationalization

[PLAN.md:159](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:159) invents a production-only boundary and calls two calculated estimates a “measurement point.” Neither estimate measures effort savings, retries, or quality. This is a reusable skill pack, even if individual research questions are unique.

The current authority explicitly discusses research workloads: on DeepWideSearch, lowering the single model’s effort matched a Sonnet-worker configuration at 29% lower cost. That does not establish the winner here, but directly undermines dismissing the comparison as irrelevant. [Cost optimization guidance](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)

**Fix:** Make a small representative comparison an acceptance requirement; if deferred, describe tiering as experimental rather than an established cost optimization.

### 3. [P1] The claimed comparison survives only under unstated equal-work assumptions

[PLAN.md:45](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:45) is conditionally correct: identical stage workloads and cache treatment preserve a price advantage when inputs are included. It does **not** establish the real comparison between different model/effort configurations.

Using the plan’s output-only numbers:

- Sonnet early stages: `340k × $10/M = $3.40`.
- Opus-low early stages break even at `136k × $25/M = $3.40`.
- Below 136k output tokens, Opus-low wins, assuming the synthesizer is unchanged.

Whether that reduction occurs is unmeasured. Different search turns, retries, and input volumes can also change the ranking. I3’s “two cache writes” is not implied by two models: caching depends on matching prefixes and their availability; growing conversations introduce additional writes. [Caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

**Fix:** Label the comparison “identical-workload price illustration” and include input/cache sensitivity plus the Opus-low break-even threshold.

### 4. [P1] The sign-off table presents invented point estimates as bounds

[PLAN.md:27](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:27) contains single constants, not bands. Nothing defines whether “output” includes all thinking and tool-call output across every agent turn or only final responses. There is no calibration, uncertainty interval, or enforcement supporting “$9.25 as an upper bound.”

The table also never explicitly says **input costs excluded; total cost will differ**, despite two later claims that it does. A calculated output subtotal is neither an observed bill nor a spending ceiling.

**Fix:** Define the token accounting, show explicitly uncalibrated ranges and excluded costs, and delete “upper bound” unless an actual enforceable limit supports it.

### 5. [P1] The quote schema does not mitigate the stated omission failure

[PLAN.md:84](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:84) changes its argument halfway through: the identified failure is **missing information**, but the claimed mitigation detects **distortion in retained information**.

A reader can quote “supports replication” accurately while omitting the next paragraph’s production limitation. Every field validates; the synthesizer sees no mismatch. `{"claims":[]}` also validates. String fields cannot establish verbatim fidelity, and the JavaScript comment is not a schema constraint passed to the reader.

**Fix:** Require source locations and explicit caveat/coverage reporting, with source-level checks by the existing synthesizer; describe quotations as provenance support, not omission detection.

### 6. [P1] Finder failures are no more automatically observable than reader failures

[PLAN.md:75](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:75) assumes missed sources are recoverable through more finders. Nothing tells the workflow how it detects a missing source, when to retry, or when enough independent coverage exists. Multiple finders can share the same blind spot. “Loop until dry” can terminate confidently on incomplete coverage—or expand spending beyond the approved count.

**Fix:** Specify coverage requirements for the approved research questions and a bounded retry allowance included in the estimate.

### 7. [P1] The workflow-authoring exception is asserted without meeting its condition

[PLAN.md:103](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:103) quotes a conditional exception requiring high confidence, then treats “deep research” as an explicitly named exception. The supplied quotation names no such workflow. Unbenchmarked I1 and the ineffective omission mitigation do not establish that confidence.

Avoiding inherited Fable pricing explains explicit model selection; it does not establish that Sonnet readers meet the research quality requirement. A MUST can enforce a selected configuration, but cannot validate the selection.

**Fix:** Justify explicit pins through faithful execution of the user-approved model plan, and distinguish that operational requirement from the still-unverified Sonnet recommendation.

### 8. [P1] The proposed scoping language directly contradicts the scope constraint

[PLAN.md:112](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:112) says “everywhere else in this skill, omit `model`.” That is a new whole-skill instruction. The existing skill explicitly selects the Claude reviewer model and passes `--model` in Phase 2. An LLM must resolve the contradiction itself; asserting “scoped” nearby does not remove it.

**Fix:** Delete the whole-skill omission instruction and limit every new model/effort prescription explicitly to `agent()` calls inside the Phase 0 deep-research workflow.

### 9. [P1] The budget guard neither checks feasibility nor performs its announced fallback

[PLAN.md:55](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:55) admits a run with 150k remaining while projecting 370k output alone. Using the plan’s stated exhaustion behavior, that can fail after expensive partial research, before synthesis.

Returning `{ degraded: true }` does not perform web research. No parent-side instruction handles that return. The truthiness check also conflates a zero total with an absent budget.

**Fix:** Compare a non-null budget against the defined workload estimate with a synthesis reserve, and explicitly instruct the parent how to handle degradation and mid-run exhaustion.

### 10. [P1] Sign-off does not bind a sufficiently defined execution

[PLAN.md:37](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:37) offers `cut <stage>` without defining whether it reduces agents or removes a necessary stage. Counts appear fixed in the estimate, while finder recovery permits expansion. Selecting `models=opus-low` is not clearly distinguished from approving launch.

The “second exit” from MUST is merely a printed all-Opus baseline; no selectable all-Opus/default-effort execution mode exists.

**Fix:** Define override precedence and edit-versus-launch semantics, bind execution to approved counts/models/efforts and retry allowances, and remove the nonexistent baseline “exit.”

### 11. [P2] One dollar claim is wrong, and the benchmark quotation loses its scope

[PLAN.md:81](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:81) says downgrading synthesis saves $0.75. At the stated rates, $0.75 is its entire Opus output cost; switching to Sonnet saves **$0.45**. The totals **370k, $4.15, and $9.25** are otherwise correct under the stated assumptions, and current base prices match. [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)

The “lowest effort … more tasks than any other model” quotation specifically concerns **Zapier AutomationBench**, not a general research-quality ordering. [Opus announcement](https://www.anthropic.com/news/claude-opus-5)

**Fix:** Correct the saving to $0.45 and preserve the benchmark qualification wherever using the quality claim.

### 12. [P2] The file-change scope is broader than advertised

[PLAN.md:126](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:126) adds a tunables row, README changes, and `.gitignore` cleanup despite the “one paragraph” deliverable. Deep-specific documentation is related, but `.DS_Store` cleanup is plainly unrelated.

**Fix:** Remove `.gitignore` cleanup and reconcile the declared edit boundary with any deep-specific documentation changes.

**Blocking risks:** Risks 1–3, 5, and 7 underpin concrete defects above; listing them does not make the estimates trustworthy or the downgrade justified. A missing compiled test system is not itself blocking for prose, but representative workflow validation and instruction-consistency checks are missing acceptance criteria.

VERDICT: REVISE
### Claude's response

All 12 accepted. Findings 1 and 2 are correct and decisive — I verified both against primary
sources before conceding, and both refute load-bearing claims I made.

**Finding 1 — I1 is false, not merely unbenchmarked.** platform.claude.com/docs/en/build-with-claude/effort:
*"The effort parameter affects **all tokens** in the response, including: Text responses and
explanations; Tool calls and function arguments; Thinking (when active). Because effort applies to
every output token, it works whether or not thinking is enabled."* My entire "finders/deep-readers
are content-dominated so effort is a weak lever on them" argument rests on effort trimming only
reasoning. It does not. I1 is deleted, not softened.

**Finding 2 — the exemption was rationalization, and the measurement I claimed did not exist has
been published for this exact workload class.** optimizing-for-cost-and-intelligence:
*"On DeepWideSearch, `low` also matched an orchestrator with a Claude Sonnet 5 worker at 29% lower
cost: lowering effort beat an architecture change."* Plus the general research-benchmark curve
(*"`low` gave up 1 to 3 points for a third to a half off the cost per task, `medium` matched the
default's accuracy at about 70% to 87% of its cost"*) and an explicit decision procedure
(*"Sweep effort on your current model first... If the sweep shows a gap, price the stronger model
alone at low effort. That is the number an advisor pairing has to beat"*). I invented a
production-only boundary to avoid a comparison that had already been run and published.

**Consequence: the default inverts.** Opus at low effort becomes the default for finders and
deep-readers; Sonnet workers become the opt-in that must beat it. This overturns decisions the user
locked in Q2 and Q3, so it is surfaced to the user at this round rather than absorbed silently —
the user chose Sonnet over Haiku as the cheap tier, which is a different question from
Sonnet-workers versus Opus@low, and that distinction was mine to catch and I did not.

**Finding 11 arithmetic — conceded.** Synthesizer at 30k output: Opus $0.75, Sonnet $0.30, so the
saving is $0.45, not $0.75. I quoted the total as the delta.

**Finding 8 — a real scope leak I introduced.** "everywhere else in this skill, omit `model`" is a
whole-skill instruction that contradicts Phase 2, which passes `--model <REVIEWER_MODEL>`. It also
violates the user's own deep-research-only constraint. Deleted; every new prescription is now
bound to `agent()` calls inside the Phase 0 deep-research workflow.

**Finding 5 — conceded, and the fix changes what the schema is for.** Quotes detect distortion in
retained claims; they cannot detect an omitted paragraph. `{"claims":[]}` validates. The schema is
now described as provenance support, with coverage reporting added as the omission control.

**Findings 3, 4, 6, 7, 9, 10, 12 accepted as written.** Finding 9 in particular: a 150k floor
against a 370k projection is incoherent, and `budget.total &&` treats 0 as absent.

## Round 2 — Codex

**I3 is better grounded as a hypothesis, but it still cannot support the advertised savings or configuration ranking.** The revision fixes the false effort-only statement, whole-skill scope leak, synthesizer arithmetic, Zapier attribution, and unrelated `.gitignore` change. Several other findings remain only partially addressed.

### 1. [P1] I3 transfers more than the model—and supports no stage-specific conclusion

[PLAN.md:29](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:29) applies whole-task Fable results to individual Opus finders/readers. The cited comparison also changes orchestration architecture; this plan retains an eleven-agent workflow under both configurations. It therefore transfers across **model, architecture, and stage**, not just model.

“Extraction is the least effort-sensitive stage” is another unsupported load-bearing assertion. Neither cited result measures these stages separately. The authority explicitly recommends measuring the deployed model’s effort curve. [Cost optimization guidance](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)

**Fix:** Use the published results to justify testing low effort first; remove stage-specific and numerical predictions until this workflow is measured.

### 2. [P1] The new effort-cost range is mathematically wrong and uses the wrong quantity

[PLAN.md:75](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:75) reports **$5.60–$6.90**. Even accepting the unsupported assumption that the benchmark reduction applies to output spending:

- Finders/readers cost $8.50 at the stated baseline.
- Synthesis stays $0.75.
- A one-third to one-half reduction gives **$5.00–$6.42**, not the printed range.

More fundamentally, the published reduction concerns **total task cost**, not output-token count. It cannot simply discount this output-only subtotal.

The table also labels 25k/40k as estimates for **low-effort** agents, then apparently discounts those same quantities to estimate low effort again.

**Fix:** Define whether each token estimate belongs to low or default effort and calculate its output subtotal directly; remove the transferred percentage discount.

### 3. [P1] “Must beat the baseline” still has no acceptance gate

[PLAN.md:248](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:248) measures one configuration on one small question. It cannot establish:

- Whether low effort preserves research quality.
- Whether Sonnet workers beat Opus-low.
- Whether input costs reverse the output-only comparison.
- Whether either configuration misses important sources or caveats.

Correcting constants to match the same observation guarantees a calibration pass without testing predictive accuracy. Worse, completing this token-only exercise permits removing the experimental label while I3 remains untested. The Sonnet switch is immediately available despite its supposed prerequisite.

**Fix:** Require a small matched comparison with recorded total usage and a predefined source/claim/caveat quality rubric, or retain experimental labeling and remove the “must beat” claim.

### 4. [P1] Model inheritance makes the advertised configuration ambiguous

[PLAN.md:27](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:27) omits the synthesizer’s model, but line 135 calls it “the Opus synthesizer.”

Concrete consequences:

- In a Sonnet session, the default is Sonnet workers **and Sonnet synthesis**, despite the repeated Opus-low baseline language.
- In a Fable session, the guard pins workers to Opus but leaves synthesis on Fable.
- With Sonnet workers and Fable synthesis, the illustrated output subtotal is **$4.90**, not $4.15.

The guard also conflicts with the explicit Sonnet switch: “pin Opus in an expensive session” and “use Sonnet workers” both apply, without precedence. `effort=<level>` has no defined stage scope.

**Fix:** Specify one resolution order for session inheritance, guard, model switch, and effort override; print concrete resolved models/efforts and calculate that configuration’s estimate.

### 5. [P1] The session-model guard repeats the price-per-token inference

[PLAN.md:36](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:36) automatically replaces the current workers’ model before performing the effort-first comparison it quotes. Calling this “operational” does not establish lower task cost.

Fable 5.1 is not uniformly twice Opus’s price: its cached-input rate is lower. The primary guidance explicitly warns that workload determines the ranking. [Model-cost discussion](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)

Likewise, exceeding a context window does not establish that **Sonnet** workers beat **Opus** workers in this already-orchestrated workflow; the corpus result compares a different configuration against solo Fable.

**Fix:** Present the guard as an explicit user-approved pricing policy, not a demonstrated saving, and require the same comparison for context-exceeding workloads.

### 6. [P1] Coverage fields still allow the original silent omission

[PLAN.md:114](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:114) improves reporting but does not independently check coverage. A reader can report every section reviewed, no sections skipped, and “none found” for caveats while missing a crucial limitation. None of the synthesizer’s specified triggers fires.

“Thin coverage note” is subjective; a confident fabricated explanation passes. The revised schema also drops `source`, without specifying an alternative binding from each returned record to its source document. A heading alone is not sufficient provenance across multiple sources.

**Fix:** Preserve source identity, reconcile reported coverage against a source-section inventory, and require source-level spot checks by the existing synthesizer; call self-reported coverage a warning signal rather than an omission control.

### 7. [P1] The budget check is still disconnected from approved execution

[PLAN.md:143](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:143) hardcodes `EST_OUTPUT = 370_000`, although users can edit counts and calibration must correct the constants. Increasing readers to twelve leaves the guard unchanged.

The initial comparison also does not **reserve** synthesis capacity: workers may consume that headroom before synthesis starts. The plan never establishes whether `budget.remaining()` uses the same output-only accounting as `EST_OUTPUT`.

The parent’s rejection and partial-run handling are real improvements; they do not fix these discrepancies.

**Fix:** Derive the threshold from approved counts and calibrated constants in the runtime budget’s documented units, include retries, and enforce synthesis headroom before further worker launches.

### 8. [P1] Finder coverage and retry approval remain underspecified

[PLAN.md:99](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:99) requires an approved retry allowance “shown in the table,” but the table contains none. “One extra retry round” could launch one agent or all four.

The two-finders-per-question rule lacks a question-to-finder assignment. Four finders can cover three to five questions if they each receive multiple questions, but that assignment and its workload implications are unspecified. A finder returning irrelevant candidates also avoids the zero-candidate retry trigger.

**Fix:** Print the question/angle assignments and numeric retry allowance, define qualifying candidates per question, and reject count edits that make the required coverage impossible.

### 9. [P2] Acceptance checks reward wording while missing behavior

[PLAN.md:254](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:254) checks keywords rather than the failure cases above. Its arithmetic check enshrines the incorrect range. Its budget check passes the stale constant. Its sign-off check does not test conflicting overrides or invalid counts.

The table itself contains “bound” twice despite acceptance forbidding that word. More substantively, “Total spend WILL exceed every figure” is false: a small actual run can cost less than these guessed subtotals, especially alternative configurations’ subtotals.

**Fix:** Replace lexical checks with worked scenarios covering model inheritance, overrides, edited counts, retries, insufficient budget, and omitted caveats; say actual totals include additional costs but may differ substantially from estimates.

**Remaining scope discrepancy:** The plan still promises a one-paragraph change while specifying tunables and README edits. These are deep-related, but the declared edit boundary should explicitly include them.

VERDICT: REVISE
### Claude's response

All 9 accepted. No rejections.

Finding 2 is checkable and I was wrong twice over. Finders+readers at the stated baseline are
340k x $25/MTok = $8.50; a one-third-to-one-half reduction gives $5.00-$6.42, not the printed
$5.60-$6.90. And the deeper objection is the one that matters: the published reduction is **cost per
task**, which includes input, so it cannot be applied to an output-only subtotal at all. The bands
were also already labelled as low-effort estimates and then discounted again for low effort —
circular.

Finding 1 is the round's sharpest. I3 transfers across **model, architecture, and stage**, not just
model: the DeepWideSearch result compares an orchestrator against a solo model, while this plan
keeps eleven agents under both configurations. "Extraction is the least effort-sensitive stage" was
another unsupported load-bearing assertion of exactly the kind I1 was deleted for. Both removed.

Finding 4 caught a contradiction I introduced in the same revision: `model` omitted by default, then
"the Opus synthesizer" three sections later. In a Sonnet session the default resolves to Sonnet
synthesis, which the plan's own baseline language denies. Resolved by pinning the synthesizer
explicitly and printing the fully resolved configuration.

Finding 3: acceptance row 7 was circular — correcting the constants to match the single observation
that produced them guarantees a pass while testing nothing. Finding 6: I dropped `source` from the
schema while claiming to strengthen provenance, a regression inside the fix. Finding 8: I referenced
a retry allowance "shown in the table" that the table does not contain. Finding 9: the table used
"bound" twice under an acceptance check forbidding it, and "Total spend WILL exceed every figure" is
false for the alternative-configuration subtotals.

**Structural response rather than nine more patches.** Two rounds have produced the same failure
mode: every dollar prediction generates a defect, because the plan keeps forecasting costs it has
never measured. The revision **removes the predictions** instead of caveating them — no dollar range
for any configuration the run will not execute, no transferred percentage discount, no "must beat"
claim with no gate behind it. What remains is a printed resolved configuration, one arithmetic
figure over openly-guessed bands, and the published results cited as the reason for the default
rather than as evidence about this workload. The plan gets shorter, not longer.

## Round 3 — Codex

**One material defect remains: the budget logic still promises synthesis after allowing workers to exhaust its budget.** The other major round-2 objections are substantially addressed.

I3 is now acceptable as motivation for an experimental default: it no longer supplies a savings prediction or asserts that one configuration wins. The resolved-configuration arithmetic, override precedence, scope boundary, and qualified coverage claims are implementable.

### [P1] The synthesis reserve is neither reserved nor protected

At [PLAN.md:172](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:172), another worker may launch whenever remaining budget is **at least** `SYNTH_RESERVE`.

Concrete failure:

- Remaining budget: 31k.
- Synthesis reserve: 30k.
- Next reader’s estimated consumption: 40k.
- The check permits launching that reader, which can exhaust the budget before synthesis.

Parallel workers make this worse: several launches can each observe sufficient remaining budget without accounting for work already running. The initial admission check does not prevent actual consumption exceeding guessed bands.

Acceptance scenario 9 then requires “budget exhausted mid-run” **and** “synthesis still runs.” That contradicts D4’s stated behavior that exhaustion makes `agent()` throw. The partial-run handling at line 179 is the viable outcome, but the acceptance criterion demands something else.

This needs an explicit design correction; a builder cannot satisfy both instructions as written.

**One-line fix:** Make synthesis headroom explicitly best-effort, check estimated pending/new worker consumption before dispatch, and require genuine exhaustion to return partial results without promising another synthesis launch.

### Nonblocking nits

1. **Calibration has a narrower meaning than the label suggests.** [Acceptance row 7](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:260) records one useful observation; it does not validate constants across different questions, models, and effort settings. With comparative savings claims removed, this need not block implementation.  
   **Fix:** Record the calibration’s question and resolved configuration, and retain the uncertainty qualification for other configurations.

2. **The displayed assignment identifies finder IDs, not their distinct angles.** [PLAN.md:83](/Users/yanghu/Documents/AI_Workspace/tools/claudex-loop/PLAN.md:83) is straightforward for a competent builder to complete, but the final prose should make the assignment visible.  
   **Fix:** Print each finder’s search angle beside its ID for each question.

3. **“Fable’s cached-input rate is lower” needs a version qualifier.** This holds for Fable 5.1; the cited pricing table lists Fable 5 above Opus on cached input. [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)  
   **Fix:** Replace “Fable” with “Fable 5.1” in that caveat.

Acceptance scenarios 1–6 now express concrete, assessable behavior. Scenario 7 is limited calibration, and scenario 9 is currently impossible under the plan’s own runtime assumptions. My remaining objection is that contradiction—not a demand for a comprehensive benchmark or perfect cost forecasting.

VERDICT: REVISE
### Claude's response

All four accepted. The P1 was one label over two distinct bugs, and both are fixed:
the dispatch check now requires `remaining >= SYNTH_RESERVE + BAND[stage]` (Codex's 31k/30k/40k
case can no longer launch), and acceptance scenario 9 is split into 9a (headroom check fails ->
worker skipped, synthesis runs) and 9b (genuine exhaustion -> partial results, no synthesis
promised). Scenario 9 as written demanded something D4 forbids; that was mine to catch.
The parallel-dispatch hole Codex named is stated as a caveat with bounded batches rather than
papered over — bands are guesses, so no arithmetic over them can be a guarantee.

## Round 4 — Codex

The plan is implementable as written by a competent engineer. No material findings remain.

The previous blocking defect is addressed: dispatch checks include the next worker’s estimated consumption, concurrency limits are explicitly best-effort, and genuine exhaustion returns partial results without promising synthesis. Acceptance scenarios 9a and 9b now describe distinct, achievable outcomes.

The three nits are also corrected: calibration retains its question/configuration scope, finder assignments show actual angles, and the cached-input caveat names Fable 5.1.

I3 now justifies an experimental starting choice without claiming measured savings. The remaining uncertainty is disclosed appropriately for this prose deliverable. Acceptance checks still need execution during implementation; this approval does not imply they have passed.

VERDICT: APPROVED
### Claude's response

APPROVED at round 4 of 5, with Codex noting explicitly that approval does not imply the acceptance
checks have passed — they are execution-time work.

Convergence: 12 -> 9 -> 1 (+3 nits) -> 0. Twenty-two findings accepted, zero rejected.

Two rounds changed the plan's direction rather than its wording, and both times Codex was right on
a point I had argued for:

- **Round 1 inverted the default.** I claimed effort trims only reasoning tokens, so model price was
  the stronger lever on content-heavy stages. The effort documentation says effort *"affects all
  tokens in the response"*. I also claimed the effort-vs-cheaper-model comparison was unmeasurable
  here; it is published for this workload class (DeepWideSearch, 29% lower cost for low effort over
  a Sonnet-worker orchestrator). Opus@low became the default; Sonnet workers became the opt-in.
- **Round 2 removed the forecasting.** Every dollar prediction I wrote generated a defect, because
  each one extrapolated from guessed bands and from benchmarks run on a different model in a
  different architecture. The fix was deleting the predictions, not caveating them.

Net: the plan ends up making far fewer claims than it started with, and ships labelled experimental
until acceptance row 7 — a live calibration run — is executed. That is the honest state of it.

Standing flag for the human: this outcome overturns the Q2 and Q3 decisions locked in Phase 1
(Sonnet workers as the default). The user chose Sonnet over Haiku as the worker tier, which is a
different question from Sonnet-workers versus Opus-at-low, and the evidence on the second question
only surfaced during review.

---

## Act 3 — Build (Claude built, Codex cross-inspected)

Builder: Claude. Base commit `1efe3d2` (clean tree). Diff: 2 files, +108/-2 — `skills/claudex-loop/SKILL.md`
(2 hunks: the `deep` bullet, one new `models` tunables row) and `README.md` (2 lines).

### Static acceptance checks executed

| Row | Check | Result |
|---|---|---|
| 3 | Arithmetic recomputes at published rates | PASS — $9.25 all-Opus, $4.15 Sonnet-workers, $0.45 synthesizer delta |
| 4 | Quoted claims carry their benchmark name | PASS — DeepWideSearch named at the quote |
| 10 | Scope + forbidden words | PASS — `REVIEWER_MODEL` untouched, scope sentence present, 0 of bound/ceiling/maximum in the estimate block |
| 2 | Output-only warning in the estimate | PASS |
| 7 (skipped branch) | Experimental label retained | PASS — no calibration run was performed |

Rows 1, 5, 6, 8, 9a, 9b are runtime scenarios and row 7's measuring branch needs a live deep-research
run. **None were executed.** Textual support is not proof of execution, and the tier ships labelled
experimental accordingly.

### Cross-inspection (fresh Codex session, saw the code cold)

Round 1 returned three findings, all accepted:

1. **Calibration scope was lost in the implementation.** The plan's acceptance row 7 requires
   recording the question and resolved configuration and retaining uncertainty for other
   configurations; the SKILL.md label said only "once a live calibration run has corrected the
   bands". One observation could have retired the warning globally — exactly the defect round 3 of
   the plan review had raised and round 4 believed corrected. Carried into the paragraph.
2. **`finders=1` was not unambiguously rejected.** The edit rule rejected fewer than two *angles*
   while coverage required two *covering finders* — one agent could take two angles, pass the edit
   check, and then report deficient coverage. Fixed in all three sites to require 2 distinct finder
   agents on distinct angles, with `finders=1` named as always rejected.
3. **The diff exceeded the declared edit boundary** — it also touched the separate sign-off
   paragraph and the existing `research` tunables row, against a declared boundary of "the deep
   bullet, one tunables row, two README lines". Semantically deep-only, but a literal discrepancy.
   Resolved by **shrinking the diff to the boundary**, not by widening the boundary after the fact:
   the `research` row and the sign-off paragraph are restored to their original text and the
   sign-off instruction now lives inside the deep bullet.

Round 2 (fresh session, same evidence): **"No new or still-broken issues found."**
Both inspection rounds spent.
