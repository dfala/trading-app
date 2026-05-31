# Milestone 37 Plan: Volatility-Aware ETF Candidate

## Summary

Add the next research-only strategy family from the functional completion spec: a volatility-aware U.S. sector ETF allocation candidate. This expands the model research layer without changing the active paper-trading strategy or granting any new trading authority.

## Scope

- Add a `VolatilityAwareETFStrategy`.
- Add a complete strategy card for the candidate.
- Register the strategy in the default catalog as implemented but research-only.
- Add strategy research factories so every implemented default catalog strategy can produce reproducible backtest evidence.
- Keep the active paper strategy unchanged: `monthly_sector_momentum`.

## Strategy Behavior

- Universe: U.S.-listed sector ETFs by default.
- Benchmark: `SPY`.
- Cadence: daily-close research evaluation.
- Inputs: adjusted daily OHLCV bars only.
- Lookahead rule: use only bars strictly before the execution date.
- Signal:
  - require positive trailing return over a configurable lookback;
  - compute a volatility proxy from recent absolute daily returns;
  - optionally exclude symbols above a maximum volatility proxy;
  - rank remaining symbols by return divided by volatility proxy.
- Sizing:
  - select the top `N` candidates;
  - allocate by inverse volatility among selected ETFs.
- Authority: research-only.

## Tests

- Prove the strategy uses only prior completed bars.
- Prove it excludes missing-history and high-volatility symbols.
- Prove the catalog strategy card is complete and research-only.
- Prove default research factories cover every implemented default catalog strategy.

## Verification

- `.venv/bin/python -m pytest tests/test_strategy.py tests/test_strategy_catalog.py tests/test_research_evaluation.py`
- `.venv/bin/ruff check`
- `.venv/bin/ruff format --check`
