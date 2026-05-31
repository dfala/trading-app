# Milestone 45 Plan: Daily Bar Ingestion Provenance

## Summary

Close the market-data audit gap by making every historical daily bar carry an explicit ingestion timestamp. The functional spec requires market data provenance to include source, feed, timeframe, adjustment status, and ingestion time, so this milestone promotes ingestion time into the core `DailyBar` schema and preserves it through fetch, storage, quality checks, and reports.

## Scope

- Add `ingested_at` to `DailyBar` as a required timezone-aware timestamp.
- Stamp fixture data deterministically and Alpaca data at fetch time.
- Persist and reload ingestion time in Parquet archives.
- Include ingestion-time windows in market-data quality provenance.
- Render ingestion windows in daily Markdown reports.
- Update schema, market-data, quality, strategy, backtest, learning, and dashboard tests.

## Verification

- Targeted pytest coverage for schemas, market data, data quality, reporting, strategies, backtests, learning, and research evaluation.
- Full pytest verification.
- Ruff lint and format checks.
