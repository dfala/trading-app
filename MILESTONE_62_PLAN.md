# Milestone 62 Plan: Broker Statement And Accounting Export Evidence

## Summary

Strengthen post-run accounting review by adding explicit broker statement reconciliation and paper tax-lot CSV export. This moves the app closer to the functional spec's requirement that paper-trading history can be audited against broker evidence and reviewed outside the Python object model.

## Goals

- Add a typed `BrokerStatementSnapshot`.
- Add a typed `BrokerStatementReconciliationReport`.
- Add `PaperTradingService.reconcile_statement(...)`.
- Reuse existing cash and position mismatch logic against saved statements.
- Add a paper tax-lot CSV export with active and realized lots.
- Keep all accounting language research-grade and non-filing-grade.

## Non-Goals

- No live-money trading.
- No automatic broker statement download.
- No filing-grade tax accounting.
- No wash-sale, dividend, or state-tax handling.
- No mutation of ledger state from broker statements.

## Acceptance Criteria

- Clean statement snapshots reconcile successfully against matching ledger state.
- Statement mismatches report cash and position issues.
- Statement reconciliation reports serialize cleanly.
- Tax-lot CSV includes active lots, realized lots, lot method, source fills, gains, terms, and non-filing-grade notes.
- Full verification remains green.

## Verification

- `pytest tests/test_paper_trading.py tests/test_paper_tax.py`
- `pytest`
- `ruff check`
- `ruff format --check`
