# Milestone 39 Plan: Cash Target Semantics In Backtests

## Summary

Fix the backtest rebalance semantics so an empty target allocation means "move to cash" when positions already exist. This is required before defensive, cash-rotation, and no-qualified-symbol research models can be evaluated honestly.

## Scope

- Remove the backtest shortcut that skips rebalancing when targets are empty.
- Preserve no-op behavior when targets are empty and the ledger has no positions.
- Add a focused regression test proving a strategy can buy first, then sell to cash on a later rebalance.
- Keep the Alpaca paper runtime unchanged; the active paper strategy still treats missing targets as no paper order.

## Verification

- `.venv/bin/python -m pytest tests/test_backtest.py`
- `.venv/bin/ruff check`
- `.venv/bin/ruff format --check`
