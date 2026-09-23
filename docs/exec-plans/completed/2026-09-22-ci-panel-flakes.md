---
status: completed
created: 2026-09-22
completed: 2026-09-23
---

# Plan: fix PR #1 CI failures (Windows path fixture, panel cancellation race)
_Locked via claudex-loop — by Claude + Yang Hu_

## Goal
Make PR #1's CI green on Linux, macOS and Windows by fixing the two failing panel tests at their root cause, without weakening any safety behaviour.

## Approach
1. **Cancellation race (runner).** In `run_panel`, when the aggregate deadline or an interrupt fires, cancel every not-yet-started future *before* killing live worker process groups, so a thread freed by a killed worker cannot pick up queued work. Then kill, then `pool.shutdown(wait=True, cancel_futures=True)` as today.
2. **Stop-before-launch status (runner).** In `run_panel_worker`, a worker that observes the stop signal before launching records `status: "cancelled"` (no process started) instead of `failed`. `cancelled` workers are already listed as non-completed, so the run outcome is unchanged: `failed` on a stop.
3. **Windows path fixture (test).** `test_denied_outside_read_is_recorded_but_not_fatal` asserts against `str(Path("/etc/hosts"))`, matching what the fixture produces on each platform.
4. **Deterministic regression tests.** (a) `run_panel_worker` called with the stop signal already set returns `cancelled` and launches nothing. (b) With concurrency 1, three sleeping workers and an interrupt raised in the coordinator as soon as the first worker is running, the two queued workers end `cancelled` and never launch. This relies on `Future.cancel()` semantics, not timing.

## Key decisions & tradeoffs
- Fix both ends of the race: cancel queued futures first (prevents the pickup), and treat stop-before-launch as `cancelled` (so any residual window still yields the truthful status).
- The test fix follows the platform instead of special-casing Windows in the runner; the runner already classifies `\etc\hosts` as outside the repo on Windows.

## Assumptions
1. Failure A is test-only (fixture uses `str(Path(...))`). — source: CI log, `tests/test_runner.py:577-579,801`
2. Failure B is a scheduling race in `run_panel` (`runner.py:1079-1082`) plus the stop-before-launch branch (`runner.py:940`). — source: CI log; reproduced once locally
3. No other test fails on any platform. — source: CI logs of runs 35809256973 and 35809260311

## Risks / open questions
- A worker could pass the stop check an instant before `stop` is set and then launch; the existing `execute()` self-kill-after-registration still covers that path. Unchanged.

## Out of scope
Any other runner behaviour; Windows descendant tracking; CI workflow changes.

## Verification
`python -m unittest discover -s tests -v` (all pass locally, deadline and interrupt tests repeated 25×); `python scripts/validate.py`; `git diff --check`; then CI on PR #1 green on all three platforms.
