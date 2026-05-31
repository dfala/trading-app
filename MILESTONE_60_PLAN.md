# Milestone 60 Plan: Cash Rotation Research Strategy

## Summary

Promote the cash-rotation strategy family from a catalog idea into an implemented research-only strategy. The model explicitly permits cash when the opportunity set is weak, which helps the research platform avoid forcing exposure just because a strategy is running.

## Goals

- Add `CashRotationETFStrategy`.
- Score ETF opportunity using prior completed bars only.
- Require enough positive breadth and top-candidate return before investing.
- Equal-weight top qualifying ETFs when opportunity is strong.
- Return empty targets, meaning cash, when opportunity is weak.
- Add a complete strategy definition card and default catalog entry.
- Register the strategy with the research evaluation factory.
- Add focused strategy, catalog, backtest, and research-evaluation tests.

## Non-Goals

- No change to active paper trading authority.
- No automatic model promotion.
- No live-money path.
- No intraday trading.
- No fundamental or AI-event data integration.

## Acceptance Criteria

- The strategy uses only data before `as_of`.
- Strong breadth/returns produce ETF targets.
- Weak breadth or weak average opportunity returns cash.
- The default catalog marks the strategy implemented and research-only.
- The research evaluation runner can instantiate it.
- Backtest runner can evaluate it with fixture bars.

## Verification

- `pytest tests/test_strategy.py tests/test_strategy_catalog.py tests/test_backtest.py tests/test_research_evaluation.py`
- `pytest`
- `ruff check`
- `ruff format --check`
