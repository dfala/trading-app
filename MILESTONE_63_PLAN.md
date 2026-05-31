# Milestone 63 Plan: Broker Statement File Reconciliation

## Summary

Add an operator-friendly post-run reconciliation workflow for saved broker
statement files. The app already has typed broker statement snapshots and
internal ledger comparison logic; this milestone makes that usable from local
JSON or CSV files after a real Alpaca paper session.

This remains paper/research accounting only. It does not mutate the internal
ledger, does not infer missing trades, and does not attempt filing-grade tax
accounting.

## Key Changes

- Add file loaders for saved broker statement snapshots:
  - JSON: strict `BrokerStatementSnapshot` validation.
  - CSV: a simple local interchange format with one `account` row and zero or
    more `position` rows.
- Add a pure reconciliation helper that compares a `PortfolioSnapshot` to a
  `BrokerStatementSnapshot`.
- Add Markdown rendering for statement reconciliation reports.
- Add a command-line entry point:

```bash
python -m trading_app.paper.reconcile_statement \
  --runtime-dir data/runtime \
  --statement data/runtime/statements/statement.csv
```

- The CLI reads `data/runtime/state/latest-runtime-snapshot.json`, compares the
  snapshot paper ledger to the saved statement, writes a Markdown review report,
  and exits nonzero when mismatches are found.
- Keep the workflow generic and local. Alpaca-specific statement export parsing
  can be added later if needed.

## CSV Format

The CSV file uses these columns:

- `record_type`: `account` or `position`
- Account row fields:
  - `statement_id`
  - `as_of`
  - `provider`
  - `account_id`
  - `cash`
  - `source`
- Position row fields:
  - `symbol`
  - `quantity`
  - `average_entry_price`
  - `market_value`
  - `current_price`

Only one account row is allowed. Position rows are optional for all-cash
portfolios.

## Test Plan

- Load valid JSON statement files.
- Load valid CSV statement files with account and position rows.
- Reject unsupported statement file extensions.
- Render reconciliation Markdown with paper/research-only caveats.
- Reuse the pure reconciliation helper from `PaperTradingService`.
- CLI exits `0` for clean statement reconciliation.
- CLI exits `1` and writes mismatch evidence for cash/position differences.

## Assumptions

- The runtime snapshot is the source of local paper ledger truth for this CLI.
- Statement files are saved locally by the operator after a paper session.
- This milestone does not fetch statements from Alpaca directly.
- Filing-grade tax and broker election reconciliation remain future work.
