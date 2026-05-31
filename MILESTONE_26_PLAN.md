# Milestone 26 Plan: First Implemented Challenger Strategy

## Summary

Move the research layer beyond one active model by implementing the first non-momentum challenger strategy: a research-only ETF trend-following model. The strategy can generate timestamp-safe targets, run through the existing backtest runner, and appear in the strategy catalog with a full strategy card.

The active paper model remains unchanged. This milestone gives the nightly learning and model arena surfaces a real second implemented family to evaluate before any future promotion discussion.

## Key Changes

- Add `TrendFollowingETFStrategy`.
- Add a complete `trend_following_etf_definition()` strategy card.
- Keep the new strategy `research_only` by default.
- Update the default strategy catalog so trend following is an implemented research candidate, not just an idea.
- Export the new strategy and definition from `trading_app.strategies`.
- Add tests for:
  - timestamp-safe target generation
  - missing-data exclusion
  - downtrend filtering
  - catalog completeness
  - backtest compatibility

## Non-Goals

- Do not make trend following the active paper model.
- Do not submit paper orders from the new strategy.
- Do not add live-money authority.
- Do not auto-promote the candidate.
- Do not add external data requirements beyond adjusted daily bars.

## Acceptance Criteria

- Trend following can run through `BacktestRunner`.
- Strategy target generation uses only bars before `as_of`.
- The strategy card defines universe, benchmark, data requirements, cadence, signal logic, sizing, exit logic, risks, failure modes, and AI role.
- The default catalog contains at least two implemented strategies.
- The new strategy defaults to research-only authority.

## Verification

- Strategy unit tests.
- Strategy catalog tests.
- Backtest compatibility tests.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`
