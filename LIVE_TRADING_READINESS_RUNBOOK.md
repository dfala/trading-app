# Live Trading Readiness Runbook

Last updated: 2026-05-30

This runbook is for future live-limited readiness review only. It does not authorize live trading.

## Required Pre-Flight Checks

- Confirm the system is still limited to U.S.-listed stocks and U.S.-listed ETFs.
- Confirm the target model is in `candidate_live` state.
- Confirm paper trading history is long enough to evaluate behavior.
- Confirm paper results are directionally consistent with backtests and walk-forward tests.
- Confirm the risk engine is active.
- Confirm the kill switch has been tested.
- Confirm broker reconciliation is clean.
- Confirm market data freshness checks are working.
- Confirm live limits are configured and stricter than paper limits.
- Confirm fees, slippage, taxes, and drawdown assumptions have been reviewed.
- Confirm explicit human approval has been recorded.

## Stop Conditions

Do not submit live orders if any of these are true:

- Kill switch is enabled.
- Broker reconciliation has unresolved mismatches.
- Market data is stale or unavailable.
- The model is not approved for `candidate_live`.
- The order lacks an unexpired approval record.
- The symbol is outside the live allowlist.
- The order exceeds max live notional.
- The daily loss stop has been reached.
- Paper and live account configuration appear mixed.

## Incident Response

If live-readiness checks fail:

1. Leave live trading disabled.
2. Record the failed check and evidence.
3. Freeze new promotion or live-limited requests.
4. Reconcile broker state against the internal ledger.
5. Review data freshness and source provenance.
6. Write a short incident note before resuming review.

Live trading should remain a deliberate, manually approved operating mode, not a default application behavior.
