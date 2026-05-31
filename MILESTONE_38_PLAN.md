# Milestone 38 Plan: Benchmark-Relative Strength Candidate

## Summary

Add a second differentiated research candidate from the functional completion spec: a benchmark-relative strength ETF strategy. This candidate asks whether sector ETFs outperforming `SPY` on a risk-adjusted relative basis are better candidates than raw momentum leaders.

## Scope

- Add `BenchmarkRelativeStrengthETFStrategy`.
- Add a complete research-only strategy card.
- Register the strategy as implemented in the default catalog.
- Wire the strategy into reproducible research evaluation.
- Let the backtest runner provide benchmark bars to strategy inputs while still using the trading universe bars for execution prices.
- Keep the active paper model unchanged.

## Strategy Behavior

- Universe: U.S.-listed sector ETFs by default.
- Benchmark: `SPY`.
- Cadence: daily-close research evaluation.
- Inputs: adjusted daily OHLCV bars for the universe and benchmark.
- Lookahead rule: use only bars strictly before the execution date.
- Signal:
  - compute each symbol's trailing return;
  - compute `SPY` trailing return over the same lookback length;
  - require positive excess return versus `SPY`;
  - rank by excess return divided by recent average absolute daily excess return.
- Sizing:
  - equal weight the top `N` qualifying ETFs.
- Authority: research-only.

## Tests

- Prove the strategy ignores future benchmark and symbol data.
- Prove missing benchmark history or negative relative strength produces no target.
- Prove the catalog card is complete and research-only.
- Prove backtests can feed benchmark bars into strategy evaluation without changing trading authority.

## Verification

- `.venv/bin/python -m pytest tests/test_strategy.py tests/test_strategy_catalog.py tests/test_research_evaluation.py tests/test_backtest.py`
- `.venv/bin/ruff check`
- `.venv/bin/ruff format --check`
