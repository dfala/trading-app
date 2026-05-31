# Milestone 59 Plan: Defensive Regime Research Strategy

## Summary

Turn the defensive-regime placeholder into an actual research-only strategy. The functional spec calls for a mature model research layer with defensive regime switching and cash-aware behavior before any model is trusted for funding decisions. This milestone adds a deterministic, timestamp-safe ETF strategy that can be backtested and compared without gaining paper-trading authority.

## Goals

- Add `DefensiveRegimeSwitchETFStrategy`.
- Use SPY benchmark regime evidence from prior completed bars only.
- Stay risk-on when the benchmark trend is acceptable.
- Rotate toward defensive sector ETFs when benchmark trend, moving average, or drawdown conditions are weak.
- Hold cash when defensive candidates do not qualify.
- Add a complete strategy definition card and default catalog entry.
- Export the strategy from `trading_app.strategies`.
- Add focused strategy/catalog/backtest tests.

## Non-Goals

- No change to the active paper strategy.
- No real-money trading.
- No automatic model promotion.
- No intraday trading.
- No broker or dashboard changes.

## Acceptance Criteria

- The strategy generates targets using only data before `as_of`.
- Positive SPY regime selects broad momentum leaders.
- Weak SPY regime selects defensive ETF candidates.
- Weak SPY regime with no qualifying defensive candidates returns cash.
- The default catalog marks the strategy implemented and research-only.
- Backtest runner can evaluate it against fixture bars.

## Verification

- `pytest tests/test_strategy_catalog.py tests/test_backtest.py`
- `pytest`
- `ruff check`
- `ruff format --check`
