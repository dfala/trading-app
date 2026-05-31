# Milestone 35 Plan: Reconciliation Evidence In Daily Reports

## Summary

Make daily paper reports explain reconciliation problems instead of merely saying
that reconciliation has issues. This strengthens the audit trail for paper runs
and makes unknown broker-side executions reviewable without opening raw JSON.

## Key Changes

- Add optional broker/order context to `BrokerReconciliationIssue`.
- Populate broker order id, client order id, provider, provider status, and filled
  quantity for unknown broker-order reconciliation issues.
- Add a dedicated reconciliation details section to the daily Markdown report.
- Keep reconciliation behavior conservative: report issues, block new orders, and
  do not silently repair ledger state.

## Non-Goals

- No automatic ledger repair.
- No new broker network calls.
- No live trading.
- No dashboard redesign.

## Test Plan

- Unknown broker-order reconciliation issues include broker/order context.
- Daily Markdown reports list reconciliation issue type, symbol, values, message,
  and broker/order context.
- Clean reconciliation reports state that no issues were detected.
- Full test and lint suite remain clean.
