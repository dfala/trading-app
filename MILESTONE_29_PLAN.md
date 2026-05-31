# Milestone 29 Plan: Dashboard Accounting And Tax Estimate Surface

## Summary

Expose paper accounting and tax-lot estimate status directly in the operator dashboard. The daily Markdown report already includes tax estimate scaffolding; this milestone makes the cockpit itself show short-term/long-term realized gains, active lots, realized lots, estimated tax availability, and clear non-filing-grade language.

## Key Changes

- Add a dashboard accounting/tax panel.
- Show:
  - active tax lots
  - realized tax lots
  - short-term realized gains
  - long-term realized gains
  - total realized gains
  - estimated tax or unavailable
- Label tax output as a research estimate, not filing-grade accounting.
- Add live-refresh data fields for the panel.
- Update the generated dashboard artifact.

## Non-Goals

- No filing-grade tax reporting.
- No wash-sale logic.
- No dividend handling.
- No accountant export.
- No live-money trading.

## Acceptance Criteria

- Dashboard HTML visibly includes tax estimate status.
- Dashboard API payload includes tax report fields.
- Interactive dashboard refresh updates tax counts and gain values.
- The panel clearly says the tax output is an estimate.

## Verification

- Dashboard rendering/API tests.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`
