# Hypothesis 3 - Fast-Loss Semiconductor Sleeve Gate

Generated: 2026-06-01

## Verdict

Promising, but only as a research candidate with explicit risk controls. The best gate-passing variant was an available ETF semiconductor basket sleeve, equal-weight SOXX/SMH, that rotated to SPY after a fast semiconductor loss and re-entered only after price recovered above its 200-day moving average.

That variant passed the stated full-period return, fold, stress-cost, and target drawdown gates, but it only barely cleared the drawdown target at -34.9% and did not reach the ideal < -30% drawdown target. The pure SOXX sleeve has a cleaner drawdown result with a 21-day / 8% / MA100 / cash rule, but it retained only 0.66x of SOXX's SPY outperformance, below the 0.70x retention gate.

Recommendation: keep for a second-stage paper research pass, but do not promote as a trading recommendation. The next pass should verify execution assumptions, add total-return dividend handling checks, test a less ETF-specific semiconductor universe if point-in-time constituent data becomes available, and require the drawdown improvement to survive a broader robustness band.

## Data And Method

- Data source: local SIP daily adjusted bars only, `data/market_data/bars/feed=SIP/timeframe=1D/symbol=*/bars.parquet`.
- Test window: 2016-01-04 through 2026-05-29 where required ETF data exists.
- Available required baselines: SPY, QQQ, XLK, SOXX, SMH.
- BIL was not present in the SIP daily local data, so it was not tested as a risk-off destination.
- Static semiconductor basket: equal-weight SOXX/SMH, because no individual semiconductor constituent histories were present in the local SIP directory.
- Decisions: first trading day of each month.
- Leakage control: each monthly decision used only bars through the prior trading day. The decision-day close-to-close return was earned by the prior allocation; new allocation was applied after the decision-day close.
- Initial state: invested in the semiconductor sleeve. A fast-loss gate could not trigger until the required lookback window existed.
- Initial entry and reallocation costs: turnover multiplied by cost bps. A full switch from sleeve to risk-off has 200% turnover.
- Costs tested: base 5 bps and stress 25 bps.

## Variants Tested

Sleeves:

- SOXX
- Equal-weight SOXX/SMH semiconductor ETF basket

Fast-loss triggers:

- 10, 21, and 42 trading-day lookbacks
- 8%, 10%, and 12% loss thresholds

Re-entry rules after a triggered risk-off state:

- Immediate re-entry when the fast-loss trigger is no longer active
- 63-day relative momentum versus SPY
- Price above 50-day, 100-day, or 200-day moving average

Risk-off destinations:

- Cash
- SPY
- QQQ
- XLK

Total variants: 360 at base cost, plus the same 360 at stress cost.

## Baselines

Base cost: 5 bps initial entry.

| Asset | Total Return | CAGR | Max DD | Sharpe | Delta vs SPY pp |
| --- | ---: | ---: | ---: | ---: | ---: |
| SPY | 341.0% | 15.3% | -33.8% | 0.90 | 0.0 |
| QQQ | 628.2% | 21.0% | -35.0% | 0.97 | 287.2 |
| XLK | 907.5% | 24.9% | -33.6% | 1.04 | 566.5 |
| SOXX | 2031.4% | 34.2% | -45.8% | 1.06 | 1690.4 |
| SMH | 2394.5% | 36.3% | -45.3% | 1.12 | 2053.5 |
| SOXX/SMH Basket | 2213.2% | 35.3% | -45.5% | 1.09 | 1872.2 |

## Best And Relevant Variants

Base cost: 5 bps. Stress return uses 25 bps.

| Sleeve | Window | Loss | Re-entry | Risk-off | Return | CAGR | Max DD | Sharpe | Delta vs SPY pp | Retain SOXX Outperf | Stress Return | Stress Delta pp | All Folds Positive |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SOXX/SMH Basket | 42 | 10% | MA200 | SPY | 1948.0% | 33.7% | -34.9% | 1.13 | 1607.0 | 0.95x | 1867.5% | 1526.5 | Yes |
| SOXX/SMH Basket | 21 | 8% | MA200 | SPY | 1617.8% | 31.5% | -34.9% | 1.08 | 1276.9 | 0.76x | 1537.1% | 1196.1 | Yes |
| SOXX | 42 | 10% | MA100 | Cash | 1462.5% | 30.3% | -34.3% | 1.08 | 1121.6 | 0.66x | 1401.1% | 1060.1 | Yes |
| SOXX | 21 | 8% | MA100 | Cash | 1450.1% | 30.2% | -28.9% | 1.15 | 1109.1 | 0.66x | 1377.2% | 1036.2 | Yes |
| SOXX/SMH Basket | 42 | 10% | MA200 | Cash | 1418.6% | 29.9% | -33.9% | 1.08 | 1077.6 | 0.64x | 1358.9% | 1017.9 | Yes |
| SOXX | 42 | 12% | MA100 | Cash | 1386.3% | 29.6% | -34.3% | 1.06 | 1045.3 | 0.62x | 1327.9% | 986.9 | Yes |
| SOXX/SMH Basket | 42 | 8% | MA200 | SPY | 1364.9% | 29.5% | -34.9% | 1.04 | 1023.9 | 0.61x | 1273.8% | 932.9 | Yes |
| SOXX | 21 | 8% | MA200 | Cash | 1347.9% | 29.3% | -29.1% | 1.11 | 1006.9 | 0.60x | 1279.9% | 938.9 | Yes |

The best overall return variants often used 10-day triggers, but their drawdowns stayed near -39% to -46%. They preserved more upside by exiting less usefully or re-entering quickly, so they did not satisfy the risk-control purpose of this hypothesis.

## Fold Results For Best Gate-Passing Variant

Variant: SOXX/SMH basket sleeve, 42-day loss <= -10%, re-enter above MA200, risk-off SPY, 5 bps base cost.

| Fold | Strategy Return | SPY Return | SOXX Return | Basket Return | Delta vs SPY pp | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2016-2018 | 78.6% | 30.7% | 82.9% | 77.8% | 47.9 | -24.9% |
| 2019-2022 | 147.3% | 63.4% | 130.5% | 135.3% | 84.0 | -33.9% |
| 2023-2026-05-29 | 367.4% | 107.2% | 407.2% | 454.1% | 260.1 | -34.9% |

## Robustness Check

Same sleeve/re-entry/risk-off family: SOXX/SMH basket, MA200 re-entry, SPY risk-off.

| Window | Loss | Return | Max DD | Delta vs SPY pp | Retain SOXX Outperf |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 8% | 2278.5% | -38.6% | 1937.5 | 1.15x |
| 10 | 10% | 2443.9% | -38.6% | 2102.9 | 1.24x |
| 10 | 12% | 2176.0% | -45.5% | 1835.1 | 1.09x |
| 21 | 8% | 1617.8% | -34.9% | 1276.9 | 0.76x |
| 21 | 10% | 2187.6% | -38.6% | 1846.6 | 1.09x |
| 21 | 12% | 2035.2% | -38.6% | 1694.2 | 1.00x |
| 42 | 8% | 1364.9% | -34.9% | 1023.9 | 0.61x |
| 42 | 10% | 1948.0% | -34.9% | 1607.0 | 0.95x |
| 42 | 12% | 2217.8% | -38.6% | 1876.8 | 1.11x |

Interpretation: return strength is not isolated, but the drawdown gate is fragile. Only the 21-day / 8% and 42-day / 8-10% combinations in this neighborhood cleared the -35% target. The 42-day / 10% variant has better upside retention than 42-day / 8%, but it is close to the drawdown cutoff.

## Gate Evaluation

| Gate | Result |
| --- | --- |
| Full-period delta vs SPY > +800 pp | Pass. Best gate-passing variant: +1607.0 pp. |
| Retain at least 0.70x of SOXX outperformance | Pass for best gate-passing basket variant: 0.95x. Pure SOXX risk-target variants were below this, around 0.60x to 0.66x. |
| Max drawdown meaningfully below ~38-45%, target < -35%, ideal < -30% | Partial pass. Best basket variant reached -34.9%, barely passing target but failing ideal. Pure SOXX 21-day / 8% / MA100 / cash reached -28.9% but missed the 0.70x retention gate. |
| Positive delta vs SPY in every fold | Pass for the best gate-passing variant. |
| Positive under stress costs | Pass. Best gate-passing stress delta vs SPY: +1526.5 pp. |
| Not dependent on a single cherry-picked parameter | Partial. Return edge is broad, but target drawdown improvement is narrow. |

Grid counts at base cost:

| Gate Count | Variants Passing |
| --- | ---: |
| Delta vs SPY > +800 pp | 339 / 360 |
| Retain SOXX outperformance >= 0.70x | 277 / 360 |
| Max DD better than -35% | 14 / 360 |
| Max DD better than -30% | 4 / 360 |
| Positive delta vs SPY in all folds | 332 / 360 |
| Positive delta vs SPY under 25 bps stress cost | 360 / 360 |

## Decision Audit For Best Variant

Each listed decision used bars only through `visible_end`.

| Decision Date | Visible End | New State | 42d Sleeve Return | Turnover |
| --- | --- | --- | ---: | ---: |
| 2018-11-01 | 2018-10-31 | Risk-off | -14.1% | 200% |
| 2019-03-01 | 2019-02-28 | Sleeve | 19.3% | 200% |
| 2020-04-01 | 2020-03-31 | Risk-off | -18.1% | 200% |
| 2020-05-01 | 2020-04-30 | Sleeve | -1.9% | 200% |
| 2022-03-01 | 2022-02-28 | Risk-off | -14.1% | 200% |
| 2022-12-01 | 2022-11-30 | Sleeve | 22.4% | 200% |
| 2023-10-02 | 2023-09-29 | Risk-off | -10.5% | 200% |
| 2023-12-01 | 2023-11-30 | Sleeve | 8.8% | 200% |
| 2025-04-01 | 2025-03-31 | Risk-off | -11.9% | 200% |
| 2025-07-01 | 2025-06-30 | Sleeve | 31.9% | 200% |

## Research Notes

- SPY was a better risk-off destination for the best basket variant than cash because it preserved market beta during semiconductor recoveries while still avoiding some sleeve-specific drawdowns.
- Cash was better when the objective was maximum drawdown compression in the pure SOXX sleeve, but that came with more lost semiconductor outperformance.
- XLK and QQQ risk-off destinations generally preserved technology exposure but did not improve the core drawdown tradeoff enough to displace SPY or cash in the reported candidates.
- The strongest-looking returns are still dominated by the semiconductor bull market in this sample. The result should be treated as a sleeve risk-control rule, not evidence that future semiconductor exposure should be levered or given unconstrained authority.
