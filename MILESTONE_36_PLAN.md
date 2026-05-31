# Milestone 36 Plan: Implemented Mean-Reversion Candidate Strategy

## Summary

Add the next executable research-only strategy family: short-horizon ETF mean
reversion. The strategy catalog already names mean reversion as a research idea;
this milestone turns it into a real candidate strategy with a strategy card,
lookahead-safe target generation, and tests. It does not change the active paper
trading model.

## Key Changes

- Add `MeanReversionETFStrategy`.
- Add `mean_reversion_etf_definition`.
- Promote the catalog's mean-reversion entry from `research_idea` to
  `implemented`.
- Keep authority `research_only` by default.
- Use only completed bars before the execution date.
- Select short-term oversold ETFs only when they remain above a longer-term
  trend filter.

## Non-Goals

- No paper authority for mean reversion.
- No automatic model promotion.
- No intraday trading.
- No options, shorts, margin, or live-money path.

## Test Plan

- Mean-reversion targets use only prior completed bars.
- Missing history and broken long-term trend exclude symbols.
- Strategy definition includes hypothesis, benchmark, data requirements,
  cadence, sizing, exits, risks, failure modes, and constraints.
- Default catalog lists mean reversion as implemented alongside existing
  implemented strategies.
- Full test and lint suite remain clean.
