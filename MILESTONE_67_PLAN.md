# Milestone 67 Plan: Paper Broker Statement Capture

## Summary

Add a paper-only broker statement capture command so the operator can save the
current Alpaca paper account cash and positions as a strict
`BrokerStatementSnapshot`. The captured JSON can then be reconciled with the
internal paper ledger using the existing statement reconciliation command.

This closes a practical post-run evidence gap: we no longer require the operator
to hand-create the statement file before reconciliation.

## Key Changes

- Add statement capture helpers:
  - `capture_broker_statement_snapshot`
  - `write_broker_statement_json`
- Add CLI:

```bash
python -m trading_app.paper.capture_statement --output-dir data/runtime/statements
```

- The CLI uses `AlpacaPaperBrokerAdapter` by default, which requires
  `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` and always uses `paper=True`.
- Captured files are JSON `BrokerStatementSnapshot` records under ignored local
  runtime folders.
- No credential values are rendered or persisted.

## Test Plan

- Capture from deterministic in-memory paper broker.
- Validate captured statement cash, provider, account, and positions.
- Write captured statement JSON and load it through the existing strict loader.
- CLI writes JSON and returns a non-secret path/status.
- CLI fails cleanly when broker construction or capture fails.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`

## Assumptions

- This is a paper-account evidence capture, not a tax statement downloader.
- Alpaca paper credentials must be supplied by the operator's environment.
- Filing-grade broker statements and tax election reconciliation remain future
  work.
