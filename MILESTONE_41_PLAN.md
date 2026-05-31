# Milestone 41 Plan: Walk-Forward Warmup Evidence

## Summary

Fix walk-forward evaluation so each fold can use training-window history for indicators while measuring trades and returns only during the test window.

## Problem

The existing walk-forward evaluator split train/test dates, but the fold backtest only received test-window bars. Momentum, trend, volatility, and relative-strength strategies need prior completed bars to form signals. Without warmup data, folds can under-trade or evaluate the wrong behavior.

## Scope

- Add an optional `trading_start` boundary to `BacktestRunner.run`.
- Let the backtest ingest warmup bars before `trading_start`.
- Start order simulation and equity reporting at `trading_start`.
- Build benchmark return metrics from the evaluation period, not warmup history.
- Update `WalkForwardEvaluator` to pass train-plus-test bars with `trading_start=fold.test_start`.
- Add a regression test proving a fold can trade on test start using prior training history.

## Verification

- `.venv/bin/python -m pytest tests/test_learning.py tests/test_backtest.py`
- `.venv/bin/ruff check`
- `.venv/bin/ruff format --check`
