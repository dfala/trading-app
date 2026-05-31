# Milestone 65 Plan: Dashboard Statement Review Visibility

## Summary

Surface broker statement reconciliation in the operator dashboard. The operator
should not need to know which JSON file to open to see whether the latest saved
broker statement matches the internal paper ledger.

## Key Changes

- Add dashboard snapshot fields for:
  - latest statement reconciliation report
  - latest statement reconciliation report path
- Populate those fields in both demo dashboard data and the always-on runtime
  dashboard snapshot.
- Render a `Statement Review` dashboard panel with:
  - reconciled/mismatch/awaiting status
  - statement id
  - provider
  - issue count
  - report path
  - paper/research-only caveat
  - top issue rows when mismatched
- Update browser-side snapshot refresh logic to keep the panel live.

## Test Plan

- Dashboard snapshot contains statement reconciliation evidence.
- HTML includes the statement review panel and data attributes.
- JSON snapshot serializes statement reconciliation state.
- Interactive shell refreshes statement review fields from `/api/snapshot`.
- Browser smoke-check the local dashboard after rendering changes.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`

## Assumptions

- Statement review is a post-run evidence panel, not a live broker sync panel.
- The panel must stay visibly awaiting/review-needed when no statement artifact
  exists yet.
- The current dashboard remains paper-only and local-only.
