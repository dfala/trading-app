# Milestone 56 Plan: Dashboard Data Quality Evidence

## Summary

Make market-data trust visible in the operator cockpit. The app already checks for missing, stale, duplicated, mixed-feed, and development-grade market data, and daily reports can carry that evidence. This milestone surfaces the same evidence in the dashboard so a non-technical operator can quickly understand whether paper-trading conclusions are currently usable.

## Goals

- Show market-data quality status directly in the dashboard.
- Make research/trading usability explicit.
- Display warning and failure counts.
- Show provenance: dataset type, source, feed, symbol count, and data window.
- Show top quality issues with severity, code, symbol/date context, and message.
- Keep the panel live-refreshable from `/api/snapshot`.
- Keep missing quality reports obvious instead of silently hiding the panel.

## Non-Goals

- No new market-data provider.
- No live-money behavior.
- No automatic strategy promotion.
- No IRS-grade accounting or tax changes.
- No change to trading cadence.

## Implementation Details

- Add a dashboard `Data Quality Evidence` panel.
- Read from `snapshot.daily_report.data_quality_report`.
- If a report is unavailable, render an explicit `unavailable` state.
- Add browser refresh logic for the panel.
- Add demo snapshot quality evidence using deterministic latest-price data.
- Update dashboard tests to assert the new static and interactive bindings.
- Update the functional completion spec so the product target includes dashboard-visible data quality.

## Acceptance Criteria

- Dashboard HTML includes the data-quality panel and stable data targets.
- Interactive dashboard JavaScript refreshes the data-quality panel from JSON snapshots.
- Demo dashboard snapshot serializes a data-quality report.
- IEX/free feed caveats remain visible.
- Existing dashboard, reporting, runtime, lint, and format checks continue to pass.

## Verification

- `pytest tests/test_dashboard.py`
- `pytest`
- `ruff check`
- `ruff format --check`
- Browser visual smoke check for desktop and mobile dashboard layout.
