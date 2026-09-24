# Research skill packs (CCFA)

Most loops do not need this. It applies only to frontier research work: a paper, experiments meant to support publishable claims, a rebuttal or a submission, when a research skill pack such as CCFA (`ccf-*` skills) is installed on the host.

## Decide once, in Phase 0

Judge from the project itself, using common sense rather than keyword matching.

- **Research project (apply):** `ccfa.yaml` or `ccfa-workfiles/`, a LaTeX manuscript or venue template, a target venue or deadline, experiments or benchmarks backing claims, reviewer comments, or a literature/novelty question.
- **Not research (skip):** product, application, infrastructure or tooling code, including this repository, even when it contains benchmarks or cites papers.
- **Unsure:** add one Phase 1 question: "Is this frontier research work that should follow the CCFA research workflow?" Recommend an answer and explain the cost of guessing wrong: missed evidence standards versus needless overhead.

Record the decision and its source in the assumptions ledger. When the pack is not installed on the host, say so and continue without it.

## When it applies

- **Division of labor.** CCFA owns research content and standards; claudex-loop owns independent review, build/inspection and the execution plan. Run one orchestrator per task: if `ccf-pipeline-orchestrator` coordinates the project, use claudex-loop only at high-stakes gates such as experiment protocols, experiment or evaluation code, rebuttal and revision plans, or submission checklists. Content-only work such as polishing, figures or literature search goes straight to the CCFA specialist without a claudex loop.
- **Name skills in the plan.** List the `ccf-*` skills each provider must use (for example, the builder uses `ccf-experiment-designer`, and the host runs `ccf-integrity-auditor` before completion). The host and the builder can load them; CCFA's own preflights (`ccf-humanization`, then `ccf-common`) stay with the host.
- **Write standards into the plan.** Isolated reviewers do not reliably see user skills: the Claude reviewer runs in safe mode with no skills and reads only the repository. Copy the applicable CCFA evidence rules, review criteria or venue constraints into the plan's acceptance criteria, so that both review directions judge against the same text.
- **Link the state.** Keep CCFA artifacts in `ccfa-workfiles/` and project state in `ccfa.yaml`; keep the plan and log in `docs/exec-plans/`. Tag each Progress Checklist item with its `ccfa.yaml` gate, and record the plan path in `ccfa.yaml` when state maintenance is authorized. Checkboxes track progress; CCFA evidence decides whether a gate passes.
- **Do not substitute reviewers.** A claudex plan review or code inspection is not `ccf-paper-reviewer`, `ccf-idea-reviewer` or `ccf-integrity-auditor`. When the task needs one of those assessments, have the host run the specialist.
- **Privacy.** Plan review and inspection send the plan and repository files the reviewer reads to the other provider. Before a loop touches unpublished manuscripts, reviews or private data, confirm the user accepts that, or keep such material out of the plan and repository scope. Panel web workers never receive repository content.
