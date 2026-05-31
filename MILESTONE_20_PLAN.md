# Milestone 20 Plan: Market Data Quality And Provenance

## Summary

Make market-data quality a first-class artifact across research, backtesting, reports, and runtime snapshots. The app should not merely consume bars and latest prices; it should produce evidence about whether those inputs were complete, fresh, timestamp-safe, and appropriate for paper trading or model research.

Critical boundary: data quality warnings do not magically make weak data safe for funding decisions. IEX/free data remains development-grade.

## Key Changes

- Add strict market-data quality models:
  - `DataQualityStatus`
  - `DataQualityIssueCode`
  - `DataQualityIssue`
  - `MarketDataProvenance`
  - `MarketDataQualityReport`
- Add `MarketDataQualityChecker`.
- Check daily bars for:
  - empty datasets
  - invalid symbols
  - missing expected bars
  - duplicate bars
  - out-of-order bars
  - mixed feeds
  - mixed timeframes
  - mixed adjustment modes
  - unexpected feed
  - IEX development-grade warnings
  - lookahead bars after the decision date
- Check latest-price snapshots for:
  - unavailable snapshots
  - invalid symbols
  - missing latest prices
  - stale latest prices
  - IEX development-grade warnings
- Attach data-quality reports to:
  - backtest results
  - daily trading reports
  - runtime-generated daily reports

## Reporting Behavior

- Daily markdown reports include a `Data Quality` section.
- AI governance summaries cite `data_quality_report` when one is attached.
- Backtest results include both the existing simple `data_warning` and the structured quality report.

## Test Plan

- Valid SIP daily bars pass cleanly.
- IEX daily bars warn but remain research-usable.
- Missing bars warn.
- Duplicate bars fail.
- Mixed feeds fail.
- Out-of-order bars warn.
- Lookahead bars fail.
- Latest-price snapshots fail on missing or stale required prices.
- Backtests include structured data-quality evidence.
- Daily reports render and summarize data-quality evidence.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- Business-day completeness is enough for this milestone; a dedicated exchange-calendar integration can come later.
- Data-quality reports are decision support, not proof that a dataset is institutionally complete.
- IEX/free data remains useful for development but not final funding decisions.
