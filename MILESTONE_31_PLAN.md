# Milestone 31 Plan: Operator Validation Evidence Report

## Summary

Strengthen the credentialed paper validation workflow by producing a human-readable
Markdown report every time the supervised validation sequence runs. The runtime
already persists structured validation JSON; this milestone makes that evidence
easier for a non-technical operator to review before starting or extending a
paper soak.

## Key Changes

- Add an optional `markdown_path` field to `RuntimeValidationReport`.
- Render a paper-only validation Markdown report with:
  - validation status and summary
  - paper/live boundary
  - preflight, dry-run, scheduled-order, soak, report, learning, and dashboard
    proof status
  - submitted order count
  - warnings and failures
  - step-by-step evidence
  - next action guidance
- Write validation reports under the ignored runtime reports directory.
- Persist the validation report JSON with its Markdown path.
- Update the operator runbook so the validation report becomes part of the
  review procedure.

## Non-Goals

- No real Alpaca network calls in tests.
- No change to strategy logic.
- No new trading authority.
- No live-money trading.

## Test Plan

- Validation report model includes a Markdown path after a run.
- Markdown report is written under the runtime reports folder.
- Markdown report contains the core proof fields.
- Markdown report does not leak credential values.
- Existing validation, runtime, completion, lint, and format checks remain clean.
