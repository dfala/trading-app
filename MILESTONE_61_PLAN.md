# Milestone 61 Plan: Configurable Paper Tax-Lot Methods

## Summary

Strengthen paper accounting by making tax-lot selection explicit. The app previously assumed FIFO everywhere. This milestone keeps the accounting clearly research-grade, but adds configurable FIFO, LIFO, and HIFO lot matching so reports and dashboards show the assumption behind estimated gains.

## Goals

- Add `PaperTaxLotMethod` enum.
- Keep FIFO as the default.
- Support LIFO and HIFO research lot matching.
- Record the selected lot method in `PaperTaxSummary`.
- Let `PaperTradingService` accept a tax-lot method.
- Carry the method into daily reports and the dashboard.
- Add focused tests for FIFO, LIFO, HIFO, report serialization, and dashboard rendering.

## Non-Goals

- No filing-grade tax accounting.
- No wash-sale handling.
- No dividend handling.
- No state tax modeling.
- No broker 1099 reconciliation.
- No live-money behavior.

## Acceptance Criteria

- FIFO behavior remains unchanged by default.
- LIFO matches the newest active lot first.
- HIFO matches the highest cost-basis active lot first.
- Daily reports show the lot method used.
- Dashboard shows the lot method used.
- Full verification remains green.

## Verification

- `pytest tests/test_paper_tax.py tests/test_daily_reporting.py tests/test_dashboard.py`
- `pytest`
- `ruff check`
- `ruff format --check`
