# Milestone 30 Plan: Functional Completion Evidence Auditor

## Summary

Add a machine-readable auditor for `FUNCTIONAL_APP_COMPLETION_SPEC.md`. The auditor inspects local runtime artifacts and reports which functional-app requirements are proven, missing, failed, or still require external runtime evidence.

This milestone does not claim the app is complete. It gives us a repeatable way to make that claim later only when the artifacts prove it.

## Key Changes

- Add completion audit models.
- Add `RuntimeCompletionAuditor`.
- Check the 17 functional paper-app requirements from the completion spec.
- Use existing evidence artifacts:
  - preflight report
  - dry-run report
  - validation report
  - runtime snapshot
  - latest prices
  - daily report
  - learning report
  - alerts and control state
  - soak evidence report
  - secret scan report
  - fill/order journals
- Add CLI:
  - `python -m trading_app.runtime.completion --output-dir data/runtime`
- Persist latest completion audit report under runtime state and journal folders.

## Non-Goals

- Do not mark the active thread goal complete.
- Do not fake credentialed Alpaca evidence.
- Do not make network calls.
- Do not enable live-money trading.

## Acceptance Criteria

- Missing artifacts produce missing/external-required statuses.
- Failed safety artifacts produce failed statuses.
- Complete fixture artifacts can prove all functional requirements.
- Duplicate fill/order journal issues fail relevant integrity checks.
- Auditor output is JSON-serializable and operator-readable.

## Verification

- Completion auditor unit tests.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`
