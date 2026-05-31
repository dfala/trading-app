# Milestone 34 Plan: Unknown Broker Fill Reconciliation

## Summary

Make broker reconciliation explicitly detect filled or partially filled broker
orders that are missing from the internal ledger. The runtime already polls
broker orders and compares broker positions/cash, but an unknown filled broker
order should be visible as its own reconciliation issue so operators know the
problem is an untracked broker-side execution.

## Key Changes

- Add `UNKNOWN_BROKER_ORDER` reconciliation issue type.
- Reconciliation now inspects broker order state as well as portfolio state.
- Filled or partially filled broker orders with no matching ledger order produce
  a reconciliation issue.
- Existing order/fill sync remains conservative: it does not silently overwrite
  ledger state from broker state.
- Dirty reconciliation continues to block new paper orders.

## Non-Goals

- No automatic import of unknown broker fills.
- No silent ledger repair.
- No live trading.
- No network calls in tests.

## Test Plan

- Unit test proving an unknown broker-side fill creates a visible
  `UNKNOWN_BROKER_ORDER` issue.
- Runtime test proving unknown broker-side fills degrade/block the cycle and
  prevent new scheduled paper orders.
- Existing reconciliation, fill idempotency, restart, dashboard, and full suite
  checks remain green.
