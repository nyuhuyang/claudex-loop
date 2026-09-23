# Repository Guidelines

## Project Structure & Module Organization

This repository distributes skills for coordinating Claude Code and Codex.

- `skills/claudex-loop/`: workflow instructions, references, and the standard-library runner in `scripts/runner.py`.
- `skills/claudex-route/`: independent routing skill; `skills/codex-review/` and `skills/codex-build/`: compatibility commands using the shared workflow.
- `tests/test_runner.py`: runner contract tests; `scripts/validate.py`: metadata, link, and manifest validation.
- `.claude-plugin/` and `.codex-plugin/`: distribution manifests; `assets/`: README SVGs; `legacy/`: historical skills and notices.
- `docs/plans/`: dated plans and review logs. See `README.md` for usage and `VALIDATION.md` for live evidence.

## Build, Test, and Development Commands

Use Python 3.10+ and Git; there is no build step.

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate.py
python -m unittest discover -s tests -v
python skills/claudex-loop/scripts/runner.py --help
```

These install PyYAML, validate distribution files, run contract tests, and show runner options. Use `python3` if needed. Live workflows require authenticated CLIs; CI covers Linux, macOS, and Windows.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants. Keep the runtime standard-library-only and cross-platform; prefer `pathlib` and explicit UTF-8 handling.

Skill directories use lowercase hyphenated names. `SKILL.md` frontmatter names must match their directories; descriptions must be nonempty and at most 1,024 characters. Keep relative Markdown links valid. No formatter or general-purpose linter is configured.

## Testing Guidelines

Use `unittest`, files named `test_*.py`, and methods named `test_*`. Tests use disposable Git repositories and fake CLIs without consuming quota. Cover changed runner behavior, provider differences, failure paths, evidence binding, and misleading assurance states. Run validation and the full test suite before submitting changes; no numeric coverage threshold is configured.

## Review Fallback Invariants

Cross-provider review remains preferred. Same-provider fallback requires a recorded `provider_unavailable` failure from quota, authentication, missing CLI, service failure, or timeout. Start fresh and record `assurance=degraded_same_provider`, source result, reason, and session state. `REVISE`, `BLOCKED`, malformed output, repository mutation, and user interruption are ineligible. Inspection fallback must match the failed base and code snapshot. A live coordinator is required; an exited host cannot transfer control.

## Commit & Pull Request Guidelines

History mixes imperative subjects with prefixes such as `docs:` and `feat:`. Use a short, specific subject. PRs should explain the problem, resulting behavior, related issues, and verification. Update skill references and README examples when behavior changes.

## Authorization Boundaries

Follow user authorization for implementation, commits, pushes, and publication. A plan-review request alone does not authorize implementation; obtain authorization before starting it.
