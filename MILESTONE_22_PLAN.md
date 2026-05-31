# Milestone 22 Plan: Paper Tax-Lot Accounting Scaffold

## Summary

Add paper tax-lot accounting evidence to the runtime and daily reports. The app already models cash, fees, realized P&L, and backtest tax buckets. This milestone adds a FIFO lot tracker for paper fills so reports can show active lots, realized short-term gains, realized long-term gains, and estimated-tax availability.

Critical boundary: this is research/reporting scaffolding only. It is not IRS-grade tax accounting and does not handle wash sales, dividends, tax-lot elections, broker 1099 reconciliation, or state taxes.

## Key Changes

- Add paper tax models:
  - `PaperTaxTerm`
  - `PaperTaxLot`
  - `PaperRealizedTaxLot`
  - `PaperTaxSummary`
- Add `PaperTaxLotTracker`.
- Integrate the tracker into `PaperTradingService`.
- Include `tax_summary` on `PaperPortfolioReport`.
- Add `DailyTaxReport` to daily reports.
- Render a `Tax Estimate` section in markdown reports.

## Accounting Rules

- Buy commissions are included in cost basis.
- Sell commissions reduce proceeds.
- Lots are matched FIFO.
- Holding periods of 365 days or more are long-term.
- Duplicate fills are ignored idempotently.
- Restored persisted fills rebuild tax-lot state.
- Estimated tax remains unavailable unless explicit rates are provided later.

## Test Plan

- Buy fills create active tax lots with commission-adjusted basis.
- Sell fills create realized lots and reduce active lot quantity.
- Sell commissions reduce realized gains.
- Long-term and short-term lots are classified by holding period.
- Duplicate fill ingestion does not duplicate lots.
- Runtime/persistence recovery rebuilds tax-lot evidence from persisted fills.
- Daily reports include tax evidence and markdown tax section.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- FIFO is enough for Milestone 22.
- Paper tax evidence is for model evaluation, not filing.
- Full tax-lot election logic, wash-sale handling, dividends, and broker tax reconciliation come later.
