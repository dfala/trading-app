# Milestone 21 Plan: Strategy Research Catalog And Strategy Cards

## Summary

Strengthen the model research layer by making every strategy a structured hypothesis. The platform should not treat a strategy as just executable code; it should carry its universe, benchmark, required data, cadence, signal logic, sizing logic, exit logic, risk assumptions, known failure modes, AI role, and promotion authority.

Critical boundary: strategy cards do not grant trading authority. Research ideas remain research-only until they pass backtest, shadow, paper, risk, data-quality, and human approval gates.

## Key Changes

- Add strict strategy catalog models:
  - `StrategyFamily`
  - `StrategyImplementationStatus`
  - `StrategyCadence`
  - `StrategyAuthority`
  - `StrategyDefinition`
  - `StrategyCatalog`
- Add the implemented `monthly_sector_momentum` strategy definition.
- Add research-only cards for candidate families:
  - ETF trend following
  - short-horizon mean reversion
  - volatility-aware allocation
  - benchmark relative strength
  - defensive regime switch
  - cash rotation
  - fundamentals-informed momentum
  - AI event classification overlay
- Add `MonthlySectorMomentumStrategy.definition()`.
- Add `strategy_definition_metadata()` so model records can carry their strategy card as evidence.
- Carry strategy-card metadata through nightly champion and candidate model records.

## Research Rules

- Every strategy definition must include:
  - hypothesis
  - universe
  - benchmark
  - data requirements
  - features
  - trading cadence
  - holding period
  - signal logic
  - sizing logic
  - exit logic
  - risk assumptions
  - failure modes
  - constraints
  - AI role
- U.S.-listed stocks and ETFs only.
- Research-only strategy cards cannot place paper or live orders.
- AI can explain, compare, and recommend, but cannot mutate active models.

## Test Plan

- Strategy definitions reject invalid/lowercase symbols.
- Monthly sector momentum exposes a complete implemented strategy card.
- Default catalog includes the implemented strategy and all research families.
- Research ideas are research-only and live disabled.
- Nightly learning copies candidate strategy-card metadata into trained model records.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- Monthly sector ETF momentum remains the only implemented active paper strategy for now.
- Other strategy families are cataloged as research hypotheses, not executable strategies.
- Strategy metadata is evidence for review and governance, not a substitute for validation.
