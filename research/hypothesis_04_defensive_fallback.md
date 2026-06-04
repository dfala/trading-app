# Hypothesis 4 - Relative Momentum With Defensive Fallback

## Verdict

Do not promote as-is. The relative-momentum semiconductor sleeve remains powerful, but the defensive fallback tradeoff is unresolved: QQQ/XLK-style fallbacks preserve alpha and SOXX-retention, while cash-heavy defensive fallbacks reduce drawdown below the target area but give up too much SOXX-relative outperformance.

Best high-return variant: `rel_semis_l126` with XLK fallback returned 1726.56% net after 5 bps costs, +1385.79 percentage points versus SPY, and retained 0.82x of SOXX outperformance, but max drawdown was -40.04% and failed the drawdown gate.

Best defensive compromise tested: `rel_semis_l126` with 60/40 XLK/cash fallback returned 1281.95%, +941.18 percentage points versus SPY, stayed positive in every fold, and had stress-cost delta +854.59 points, but retained only 0.56x of SOXX outperformance. It passed the drawdown target by a thin margin at -34.99%, not the ideal < -30% target.

## Method

- Data: local SIP daily bars under `data/market_data/bars/feed=SIP/timeframe=1D/symbol=*/bars.parquet`.
- Test range: 2016-01-04 through 2026-05-29, using symbols with complete local bars.
- Decisions: monthly, on the first trading day of each month.
- Leakage control: every signal used only rows with `trading_date < decision_date`; no same-day or future bars were visible to the decision.
- Risky sleeve: equal-weight SOXX/SMH. Risk-on when its trailing lookback return beat both SPY and QQQ. Base lookback was 126 trading days; 63 and 252 days were used as robustness checks.
- Costs: base 5 bps and stress 25 bps applied to rebalance turnover. Cash was modeled as 0% local yield.
- Treasury availability: BIL and SHV were not present locally. TLT was present and tested, but it is long-duration, not a short-duration cash proxy.

## Baselines

| Baseline | Net return | CAGR | Max DD | Delta vs SPY pp |
| --- | --- | --- | --- | --- |
| SPY | 340.77% | 15.33% | -33.79% | +0.00 |
| QQQ | 627.82% | 21.03% | -35.00% | +287.05 |
| XLK | 906.99% | 24.87% | -33.56% | +566.21 |
| SOXX | 2030.32% | 34.20% | -45.76% | +1689.55 |
| SMH | 2393.26% | 36.25% | -45.30% | +2052.48 |
| 50/50 SOXX/SMH | 2211.79% | 35.26% | -45.53% | +1871.01 |
| TLT | -6.33% | -0.63% | -48.35% | -347.11 |
| Cash (0% local yield) | -0.05% | -0.00% | 0.00% | -340.82 |

## Main Variants

Base rule: `rel_semis_l126`; table shows 5 bps base results plus 25 bps stress delta versus SPY.

| Fallback | Net return | Delta vs SPY pp | Max DD | SOXX retention | Stress delta pp | Trades | Risk-on/fallback months |
| --- | --- | --- | --- | --- | --- | --- | --- |
| XLK | 1726.56% | +1385.79 | -40.04% | 0.82x | +1274.82 | 66 | 74/44 |
| 50/50 QQQ/XLK | 1660.31% | +1319.54 | -39.67% | 0.78x | +1212.16 | 88 | 74/44 |
| 90/10 XLK/cash | 1609.37% | +1268.60 | -38.77% | 0.75x | +1163.55 | 124 | 74/44 |
| QQQ | 1592.79% | +1252.01 | -39.48% | 0.74x | +1149.17 | 66 | 74/44 |
| SPY | 1311.58% | +970.81 | -36.83% | 0.57x | +885.05 | 66 | 74/44 |
| 60/40 XLK/cash | 1281.95% | +941.18 | -34.99% | 0.56x | +854.59 | 134 | 74/44 |
| 80/20 SPY/cash | 1189.41% | +848.64 | -34.96% | 0.50x | +769.02 | 124 | 74/44 |
| 50/50 XLK/cash | 1182.42% | +841.65 | -33.94% | 0.50x | +761.18 | 134 | 74/44 |
| 75/25 SPY/cash | 1159.63% | +818.86 | -34.49% | 0.48x | +740.86 | 126 | 74/44 |
| 50/50 QQQ/cash | 1130.73% | +789.96 | -33.94% | 0.47x | +712.84 | 140 | 74/44 |
| 50/50 SPY/cash | 1015.52% | +674.75 | -33.94% | 0.40x | +605.23 | 138 | 74/44 |
| 50/50 SPY/TLT | 959.57% | +618.79 | -38.50% | 0.37x | +552.88 | 128 | 74/44 |
| Cash | 755.86% | +415.09 | -33.94% | 0.25x | +363.10 | 66 | 74/44 |
| TLT | 670.25% | +329.48 | -43.35% | 0.20x | +282.68 | 66 | 74/44 |

## Fold Results

Fold values are delta versus SPY in percentage points at 5 bps.

| Fallback | 2016-2018 | 2019-2022 | 2023-2026-05-29 | All folds positive |
| --- | --- | --- | --- | --- |
| XLK | +21.75 | +49.52 | +360.86 | PASS |
| 50/50 QQQ/XLK | +21.51 | +42.23 | +359.64 | PASS |
| QQQ | +21.26 | +34.95 | +357.92 | PASS |
| SPY | +14.12 | +23.55 | +319.19 | PASS |
| 60/40 XLK/cash | +20.52 | +14.50 | +311.56 | PASS |
| 50/50 XLK/cash | +20.12 | +6.15 | +299.30 | PASS |
| 50/50 SPY/cash | +16.11 | -5.51 | +278.83 | FAIL |
| Cash | +17.54 | -32.62 | +238.83 | FAIL |

## Parameter Robustness

Cells show `delta vs SPY pp / max DD / SOXX retention / fold status`.

| Fallback | L63 | L126 | L252 |
| --- | --- | --- | --- |
| QQQ | +982.50 / -39.77% / 0.58x / fold+ | +1252.01 / -39.48% / 0.74x / fold+ | +562.97 / -37.47% / 0.33x / fold fail |
| XLK | +1097.60 / -37.60% / 0.65x / fold+ | +1385.79 / -40.04% / 0.82x / fold+ | +744.72 / -37.27% / 0.44x / fold fail |
| 50/50 QQQ/XLK | +1040.71 / -38.11% / 0.62x / fold+ | +1319.54 / -39.67% / 0.78x / fold+ | +651.22 / -37.26% / 0.39x / fold fail |
| 50/50 XLK/cash | +615.78 / -34.16% / 0.36x / fold+ | +841.65 / -33.94% / 0.50x / fold+ | +595.68 / -33.94% / 0.35x / fold+ |
| 60/40 XLK/cash | +703.46 / -34.53% / 0.42x / fold+ | +941.18 / -34.99% / 0.56x / fold+ | +627.77 / -33.94% / 0.37x / fold+ |
| 80/20 SPY/cash | +468.21 / -33.50% / 0.28x / fold+ | +848.64 / -34.96% / 0.50x / fold+ | +532.08 / -33.94% / 0.31x / fold+ |
| Cash | +244.23 / -32.90% / 0.14x / fold fail | +415.09 / -33.94% / 0.25x / fold fail | +425.23 / -33.94% / 0.25x / fold+ |

## Gate Check

| Variant | SPY delta > +800 pp | SOXX retention >= 0.70x | Max DD better than -35% | Positive every fold | Positive under 25 bps |
| --- | --- | --- | --- | --- | --- |
| XLK | PASS | PASS | FAIL | PASS | PASS |
| 50/50 QQQ/XLK | PASS | PASS | FAIL | PASS | PASS |
| QQQ | PASS | PASS | FAIL | PASS | PASS |
| 60/40 XLK/cash | PASS | FAIL | PASS | PASS | PASS |
| 50/50 XLK/cash | PASS | FAIL | PASS | PASS | PASS |
| 80/20 SPY/cash | PASS | FAIL | PASS | PASS | PASS |

## Interpretation

- QQQ, XLK, and 50/50 QQQ/XLK fallbacks passed the alpha, retention, fold, and stress-cost gates, but max drawdown stayed in the -39% to -40% range. That is not a meaningful enough improvement versus the current risk-managed semis drawdown band.
- Cash-heavy fallbacks did reduce drawdown. The useful area was 50/50 XLK/cash through 60/40 XLK/cash, with max drawdown near -34% to -35% and positive fold behavior. The cost was material: SOXX-retention fell to about 0.50x to 0.56x.
- Pure cash and TLT were poor fallbacks. Cash failed the full-period delta and fold gates. TLT had worse drawdown than cash because it is a long-duration bond ETF, not a local short-duration Treasury proxy.
- The 126-day lookback is materially better than 63 and 252 for the high-alpha versions. Defensive XLK/cash variants were more stable across lookbacks, but their lower retention means they are defensive compromises rather than clear champions.

## Recommendation

Reject this family as a promotion candidate for now. Keep `rel_semis_l126` with 60/40 XLK/cash fallback as a research watchlist variant because it passes SPY delta, fold, stress-cost, and target drawdown gates, but label it explicitly as failing the SOXX-retention gate. Do not use QQQ/XLK fallback variants to claim drawdown improvement; they preserve alpha but leave drawdown above the target range.
