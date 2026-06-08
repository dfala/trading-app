# Portfolio Governance Approach

The replay leaderboard is evidence, not a champion-selection rule. A model can be a strong research candidate while still being too concentrated to run as the whole paper portfolio.

This policy separates three decisions:

- Is the model worth studying?
- Is the model worth shadow tracking?
- Is the model eligible to become the portfolio champion or pilot candidate?

## Classifications

- `portfolio_candidate`: Broad enough to be reviewed as a whole-portfolio champion candidate if it also passes return, fold, stress, drawdown, and late-entry gates.
- `sector_sleeve`: Useful as a capped thematic sleeve, but not eligible to become the whole-portfolio champion by itself.
- `late_entry_review`: Blocked from promotion because too much of the edge is concentrated in the latest 21/63/126/252 trading-day windows.
- `research_only`: Benchmark, control, or diagnostic model. It can appear in reports, but it is not a trading authority candidate.
- `unknown`: Legacy or incomplete evidence where governance metrics were not computed.

## Semiconductor Concentration Rule

Semiconductor-heavy models are treated as sector sleeves unless they prove they are broad portfolio allocators.

The current semiconductor proxy set includes:

`SMH`, `SOXX`, `SOXQ`, `PSI`, `XSD`, `SOXL`, `SOXS`, `NVDA`, `AMD`, `AVGO`, `MU`, `MRVL`, `QCOM`, `INTC`, `AMAT`, `LRCX`, `KLAC`, `TSM`, and `ASML`.

A model is classified as a `sector_sleeve` when any of these are true:

- The model key is explicitly semiconductor-focused, such as `risk_managed_semiconductor:*`.
- The model key is a semiconductor market-drawdown circuit breaker candidate, such as `market_drawdown_circuit_breaker:*`.
- Average semiconductor proxy exposure is at least 25%.
- Peak semiconductor proxy exposure is at least 50% and at least 35% of replay decisions have material semiconductor exposure.

Material semiconductor exposure currently means at least 25% target exposure to the proxy set on a replay decision.

## Promotion Rules

Only `portfolio_candidate` models can enter champion or pilot review.

`sector_sleeve` models can still be valuable. During the paper phase they should move quickly into shadow tracking when they clear basic sanity gates, but they must be reviewed as capped sleeves, not as the full portfolio. Their comparison set must include `SMH`, `SOXX`, `QQQ`, `XLK`, `SPY`, the semis basket benchmark, and the current paper champion.

`late_entry_review` models should not be promoted from a recent spike. They can remain in research or shadow tracking while the system collects 3-, 6-, and 12-month consistency evidence.

`research_only` models remain benchmarks or controls.

## Practical Interpretation

If a semiconductor sleeve has higher raw return than the current champion, that does not automatically make it better. The correct question is whether it delivers enough excess return over semiconductor benchmarks to justify concentrated sector risk.

If it is only a better-timed version of owning semiconductors, it belongs in a capped sleeve. If it also survives broader benchmark, fold, stress-cost, drawdown, and late-entry checks, then it can influence portfolio construction through a governed sleeve allocation rather than replacing the whole portfolio.

## Implementation

Replay comparison rows now carry portfolio governance fields:

- `portfolio_governance_classification`
- `champion_eligible`
- `average_semiconductor_exposure`
- `peak_semiconductor_exposure`
- `material_semiconductor_exposure_ratio`
- `portfolio_governance_notes`

The autonomous learning leaderboard preserves these fields. Promotion and pilot-readiness gates require `champion_eligible=true`; shadow tracking remains available for non-late-entry sector sleeves so the paper phase can still learn quickly.
