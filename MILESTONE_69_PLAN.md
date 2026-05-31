# Milestone 69 Plan: Dashboard Consistency Audit

## Summary

Add a dashboard consistency audit that compares the latest persisted dashboard
snapshot against the latest runtime snapshot. The dashboard is the operator's
main source of truth; it should not pass functional review if it is stale,
demo-shaped, or inconsistent with runtime state.

## Key Changes

- Add dashboard consistency models:
  - `RuntimeDashboardConsistencyCheck`
  - `RuntimeDashboardConsistencyReport`
- Add `RuntimeDashboardConsistencyAuditor`.
- Add CLI:

```bash
python -m trading_app.runtime.dashboard_audit --output-dir data/runtime
```

- The audit checks:
  - dashboard and runtime snapshots exist
  - both are Alpaca Paper runtime state
  - embedded dashboard runtime state matches latest runtime snapshot
  - dashboard cash/equity/P&L/open orders/fills match runtime paper report
  - active model and data-quality evidence are present
  - optional statement/completion evidence is surfaced when persisted
- Persist latest dashboard consistency reports under runtime state/journal.
- Require dashboard consistency in the functional completion audit.
- Include dashboard consistency in the operator evidence bundle and post-run
  review flow.

## Test Plan

- Matching runtime/dashboard snapshots pass consistency audit.
- Missing dashboard snapshot fails.
- Cash or runtime-mode mismatches fail.
- Completion audit requires a passing dashboard consistency report.
- Evidence bundle and post-run review include dashboard consistency.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`

## Assumptions

- This audit proves persisted snapshot consistency, not live browser rendering.
- Real credentialed dashboard proof still requires a supervised Alpaca paper run.
- The dashboard remains local-only and paper-only.
