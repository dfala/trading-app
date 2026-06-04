# Hypothesis 6 - Adaptive Semiconductor Sleeve Composition

Worker: 6  
Date: 2026-06-01  
Scope: U.S. ETFs only, local SIP daily bars only, no live-trading recommendation.

## Verdict

**Pass as a research candidate, not as a deployment-ready strategy.** The best adaptive sleeve variant cleared the requested return gates and improved drawdown versus buy-and-hold SOXX/SMH, but it did not reach the ideal drawdown target and still has concentrated semiconductor timing risk.

Best tested variant:

`relative_strength_126d_top1_equal_fallback_SPY`

- Monthly chooses the strongest of `SMH`, `SOXX`, `XLK`, and `QQQ`.
- Signal uses 126 prior trading days, evaluated using only the close before the rebalance date.
- Risky asset is eligible only if trailing return is positive and current close is above its 126-day average.
- If no risky asset passes, allocation falls back to `SPY`.
- Cost model: base 5 bps and stress 25 bps applied to turnover.

This variant returned **+1,812.0%** from 2016-01-04 through 2026-05-29 at 5 bps, versus **+340.8%** for `SPY`, **+2,030.3%** for `SOXX`, and **+2,393.3%** for `SMH`. It captured **0.87x of SOXX's outperformance over SPY**, had **-33.6% max drawdown**, and remained positive versus SPY in all three folds.

## Data And Method

Data source was local adjusted SIP daily bars:

`data/market_data/bars/feed=SIP/timeframe=1D/symbol=*/bars.parquet`

Test period used all available common dates from **2016-01-04 through 2026-05-29**, 2,616 daily bars. Adjusted close fields were used. No external data or future bars were used.

Rebalance rules:

- Rebalance on the first trading day of each month.
- Compute the signal from data ending at the prior trading day's close.
- Apply weights to close-to-close returns from the rebalance day forward.
- Apply transaction costs only on rebalance turnover.
- If lookback history is unavailable or no risky asset passes the gate, use the configured fallback.

Variant grid:

- Risky universe: `SMH`, `SOXX`, `XLK`, `QQQ`.
- Ranking families: relative strength, volatility-adjusted momentum, drawdown-adjusted momentum.
- Lookbacks: 63, 126, 252 trading days.
- Selection: top-1 equal weight, top-2 equal weight, top-2 inverse-volatility weight.
- Fallbacks: `SPY` and cash. `BIL` was requested but was not available in local bars, so it was not tested.
- Costs: 5 bps base and 25 bps stress.

Static semiconductor basket availability was limited to ETF data in this local set. I used a monthly rebalanced 50/50 `SOXX`/`SMH` ETF basket as the static semiconductor basket.

## Baselines

5 bps cost for buy-and-hold entry or monthly rebalance where applicable.

| Baseline | Total return | CAGR | Max DD | Sharpe | Delta vs SPY |
|---|---:|---:|---:|---:|---:|
| Buy-and-hold SMH | +2,393.3% | 36.2% | -45.3% | 1.12 | +2,052 pp |
| Fixed 50/50 SOXX/SMH monthly | +2,212.1% | 35.3% | -45.5% | 1.09 | +1,871 pp |
| Static semis ETF basket | +2,212.1% | 35.3% | -45.5% | 1.09 | +1,871 pp |
| Buy-and-hold SOXX | +2,030.3% | 34.2% | -45.8% | 1.06 | +1,690 pp |
| Relative semis champion, 126d top-1 cash fallback | +1,008.0% | 26.0% | -38.8% | 1.03 | +667 pp |
| Buy-and-hold XLK | +907.0% | 24.9% | -33.6% | 1.04 | +566 pp |
| Buy-and-hold QQQ | +627.8% | 21.0% | -35.0% | 0.97 | +287 pp |
| Buy-and-hold SPY | +340.8% | 15.3% | -33.8% | 0.90 | 0 pp |

## Best Variant Table

Top 5 bps variants by full-period total return.

| Variant | Total return | CAGR | Max DD | Sharpe | Delta vs SPY | SOXX outperformance capture | Stress 25 bps return |
|---|---:|---:|---:|---:|---:|---:|---:|
| Relative strength 126d top-1, SPY fallback | +1,812.0% | 32.8% | -33.6% | 1.17 | +1,471 pp | 0.87x | +1,571.4% |
| Drawdown-adjusted 63d top-1, SPY fallback | +1,681.5% | 31.9% | -35.1% | 1.23 | +1,341 pp | 0.79x | +1,356.5% |
| Vol-adjusted 63d top-1, SPY fallback | +1,667.0% | 31.8% | -35.1% | 1.24 | +1,326 pp | 0.78x | +1,321.2% |
| Vol-adjusted 126d top-1, SPY fallback | +1,619.4% | 31.5% | -34.3% | 1.18 | +1,279 pp | 0.76x | +1,367.0% |
| Drawdown-adjusted 126d top-1, SPY fallback | +1,499.2% | 30.6% | -34.3% | 1.14 | +1,158 pp | 0.69x | +1,259.8% |
| Vol-adjusted 63d top-2 equal, SPY fallback | +1,467.3% | 30.3% | -34.7% | 1.20 | +1,127 pp | 0.67x | +1,246.4% |
| Drawdown-adjusted 63d top-2 equal, SPY fallback | +1,465.6% | 30.3% | -34.7% | 1.20 | +1,125 pp | 0.67x | +1,221.1% |
| Relative strength 126d top-2 inverse-vol, SPY fallback | +1,421.3% | 29.9% | -31.8% | 1.11 | +1,081 pp | 0.64x | +1,242.3% |
| Relative strength 126d top-2 equal, SPY fallback | +1,419.2% | 29.9% | -32.1% | 1.10 | +1,078 pp | 0.64x | +1,247.0% |
| Relative strength 126d top-1, cash fallback | +1,259.9% | 28.5% | -33.6% | 1.12 | +919 pp | 0.54x | +1,089.0% |

The best return variant was not the lowest drawdown variant. The best ideal-drawdown candidates were 63-day cash-fallback variants, around **-22% to -25% max drawdown**, but they only captured roughly **0.42x to 0.52x** of SOXX outperformance. That is a different objective: stronger capital preservation, weaker semiconductor participation.

## Fold Results

Returns by fold at 5 bps.

| Strategy | Full return | Max DD | 2016-2018 | 2019-2022 | 2023-2026-05-29 |
|---|---:|---:|---:|---:|---:|
| SPY | +340.8% | -33.8% | +30.7% | +63.5% | +106.4% |
| QQQ | +627.8% | -35.0% | +44.9% | +77.8% | +182.6% |
| XLK | +907.0% | -33.6% | +52.9% | +109.6% | +214.1% |
| SOXX | +2,030.3% | -45.8% | +82.8% | +132.0% | +402.2% |
| SMH | +2,393.3% | -45.3% | +72.5% | +141.6% | +498.3% |
| Fixed 50/50 SOXX/SMH | +2,212.1% | -45.5% | +77.7% | +136.9% | +449.2% |
| Relative semis champion, 126d top-1 cash fallback | +1,008.0% | -38.8% | +34.0% | +96.2% | +321.2% |
| Best adaptive sleeve: relative strength 126d top-1 SPY fallback | +1,812.0% | -33.6% | +68.9% | +118.4% | +418.5% |

Best adaptive sleeve fold deltas versus SPY:

| Fold | Adaptive sleeve | SPY | Delta |
|---|---:|---:|---:|
| 2016-2018 | +68.9% | +30.7% | +38 pp |
| 2019-2022 | +118.4% | +63.5% | +55 pp |
| 2023-2026-05-29 | +418.5% | +106.4% | +312 pp |

## Robustness Notes

The result is not dependent on a single narrow parameter, but the best return profile does depend on the fallback choice.

At 5 bps:

| Group | Median total return | Best total return | Median max DD | Positive-delta folds count |
|---|---:|---:|---:|---:|
| Relative strength family | +1,103% | +1,812% | -33.8% | 17 / 18 |
| Vol-adjusted family | +1,062% | +1,667% | -32.1% | 18 / 18 |
| Drawdown-adjusted family | +1,054% | +1,682% | -32.1% | 15 / 18 |
| 63d lookback | +1,246% | +1,682% | -29.6% | 17 / 18 |
| 126d lookback | +1,165% | +1,812% | -32.2% | 18 / 18 |
| 252d lookback | +845% | +1,169% | -32.5% | 15 / 18 |
| Top-1 | +1,190% | +1,812% | -34.0% | 16 / 18 |
| Top-2 | +1,054% | +1,467% | -32.1% | 34 / 36 |
| Cash fallback | +916% | +1,260% | -31.7% | 23 / 27 |
| SPY fallback | +1,269% | +1,812% | -34.3% | 27 / 27 |

Interpretation:

- `SPY` fallback improves returns and fold consistency because the strategy remains invested during periods when the semiconductor/tech sleeve fails its gate.
- Cash fallback is cleaner from a risk-control standpoint and produced several ideal drawdown profiles, but it materially reduces semiconductor upside capture.
- Top-1 variants were strongest on total return, while top-2 variants generally reduced drawdown modestly and reduced selection concentration.
- 126-day relative strength was the most attractive single variant. The broader grid still supports the general adaptive sleeve idea because vol-adjusted and drawdown-adjusted variants also produced strong positive deltas.

## Gate Evaluation

| Gate | Result | Evidence |
|---|---|---|
| Full-period delta vs SPY > +800 pp | Pass | Best adaptive sleeve: +1,471 pp at 5 bps |
| Retain at least 0.70x of SOXX outperformance if possible | Pass | Best adaptive sleeve: 0.87x |
| Max drawdown meaningfully below current ~38-45%, target < -35%, ideal < -30% | Partial pass | Best adaptive sleeve: -33.6%, below target but not ideal |
| Positive delta vs SPY in every fold | Pass | +38 pp, +55 pp, +312 pp |
| Positive under stress costs | Pass | 25 bps stress return +1,571.4%, delta vs SPY +1,231 pp |
| Not dependent on a single cherry-picked parameter | Pass with caveat | Multiple families and lookbacks worked, but best total return prefers SPY fallback |

## Recommendation

Promote **Hypothesis 6** to the next research stage as an adaptive ETF sleeve candidate, with two tracked profiles:

1. **Return profile:** 126-day relative strength, top-1, `SPY` fallback. This is the primary candidate because it passes the requested return, fold, stress-cost, and SOXX-capture gates while reducing semiconductor drawdown into the target range.
2. **Risk-control profile:** 63-day vol-adjusted or drawdown-adjusted top-1 with cash fallback. This is not the primary return candidate, but it is useful if the parent research objective prioritizes ideal drawdown under -30% over retaining SOXX upside.

Do not treat this as live-trading ready. Before any promotion beyond research, require an implementation-level replay with audit logs for each monthly decision, survivorship/data provenance checks, and a stricter turnover/slippage model. The result is encouraging, but the strongest decade-long performance still comes from a period where semiconductor ETFs were exceptional.
