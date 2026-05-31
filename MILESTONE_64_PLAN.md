# Milestone 64 Plan: Statement Reconciliation Completion Evidence

## Summary

Promote broker statement reconciliation from a standalone post-run utility into
formal functional-completion evidence. The app should not be called functionally
complete for paper trading unless a saved broker statement can be compared to
the persisted paper ledger and the comparison is clean.

## Key Changes

- Persist statement reconciliation reports under runtime artifacts:
  - `data/runtime/state/latest-statement-reconciliation.json`
  - `data/runtime/state/latest-statement-reconciliation-path.json`
  - `data/runtime/journal/statement-reconciliation.jsonl`
- Update the statement reconciliation CLI to persist the JSON report and
  Markdown path.
- Extend the functional completion auditor with a broker-statement review
  requirement.
- Treat missing statement evidence as external-required, clean evidence as
  proven, and mismatched evidence as failed.
- Update the functional completion spec so the paper app definition includes
  post-run broker statement reconciliation evidence.

## Test Plan

- Persist and recover latest statement reconciliation reports.
- Completion audit passes only when clean statement evidence is present.
- Completion audit fails when statement reconciliation has cash or position
  mismatches.
- Statement reconciliation CLI still exits `0` for clean reports and `1` for
  mismatches while persisting evidence in both cases.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`

## Assumptions

- The statement reconciliation report is a post-run artifact, not a live broker
  reconciliation substitute.
- Real credentialed statement review still requires an operator-saved broker
  statement file from a real Alpaca paper session.
- This does not make tax reporting filing-grade.
