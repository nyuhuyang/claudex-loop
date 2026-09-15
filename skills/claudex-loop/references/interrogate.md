# Interrogation technique

Expands Phase 1 of the skill. The skill states *what* to do — a visible decision map, questions
only where the outcome changes, recommendation plus cost of guessing wrong, batching, the escape
hatch. This is *how*. Nothing here overrides the skill.

## Tier every open decision before asking anything

A decision is **load-bearing** when a wrong answer costs a migration, a rewrite, a security hole,
or user trust. Schema shape, auth model, data ownership, concurrency, money, public API surface,
anything with a persisted artifact behind it.

It is **cosmetic** when it is renameable, refactorable, or swappable later at roughly the cost of
deciding it now. Names, file layout, log format, default flag values, ordering.

The tier is a property of the *reversal cost*, not of how interesting the decision is.

**Tier decides how much a question must justify itself; dependency decides when it is asked.** The
two are independent. Per the skill, batch independent questions and sequence dependent ones — that
holds inside both tiers. Two unrelated load-bearing decisions go out together; a cosmetic decision
that only makes sense after a load-bearing one waits for it.

```markdown
## Decision Map
### Load-bearing
- [ ] <decision> — <what a wrong answer costs>
### Cosmetic (recommendations, veto by exception)
- [ ] <decision>
```

Check items off as they resolve and add branches that corrections open, so the user can watch it
converge instead of guessing how many questions remain.

## The demotion rule

Draft the question in full — including the cost of guessing wrong — *before* deciding its tier. If
that line comes out weak ("we'd rename it"), the decision is cosmetic. Demote it to the batch.

This is the rule that keeps the interview short. Most questions that feel important fail it.

## Cosmetic decisions go out as one batch

Present the cosmetic tier with a recommendation and a one-line reason each. The user vetoes by
exception; silence accepts. Never drip independent cosmetic questions one at a time — it spends the
user's attention on the decisions that least deserve it. Hold back any cosmetic item whose
recommendation depends on an unresolved decision, and send it once its prerequisite lands.

Silence accepts a *recommendation already shown*. It never authorizes an action that needs
approval.

## Offer the escape hatch before the user needs it

When the load-bearing tier runs past roughly eight items, say so and offer "accept all remaining
recommendations" explicitly rather than waiting to be asked. Record every decision closed that way
as recommendation-locked in the plan, so a later reader can tell what was chosen from what was
merely not objected to.

## Answer it yourself when the repository can

If a question turns out answerable from code, configuration, or history mid-interview, answer it,
log it to the assumptions ledger with its source path, and do not ask. An interview that spends
questions on facts already on disk trains the user to stop reading them.

## Docs-aware probing

When `CONTEXT.md`, `CONTEXT-MAP.md`, or ADRs exist, four techniques earn their place:

- **Challenge against the glossary.** When the user's wording collides with a defined term, stop
  and resolve it on the spot: quote the definition, state the apparent meaning, make them pick.
  Do not carry the ambiguity forward and hope it resolves itself.
- **Pin loose words.** An overloaded term gets a proposed canonical replacement *before* the
  conversation builds on top of it.
- **Probe boundaries with a concrete scenario.** When two concepts blur, construct the specific
  edge case that forces the line to be drawn. Abstract questions about a boundary get abstract
  answers; a scenario gets a decision.
- **Check claims against the code.** When the user asserts how something behaves, verify it. A
  mismatch is surfaced as a question, not silently trusted in either direction.

## What the interview is not

It is not a requirements dump, and it is not a quiz. Every question spends the user's attention,
which is the scarcest input to the whole loop. A question that cannot name what it changes has no
claim on it.
