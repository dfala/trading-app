# Hypothesis 5 - Crash-Reentry Timing

## Verdict

**Pass for research promotion, not for trading deployment.** A monthly crash-reentry state machine can materially improve semiconductor drawdown control while retaining a large share of semiconductor upside. The best family is not broad market timing or relative-strength whipsaw avoidance; it is specifically **market-drawdown exit + QQQ 200-day trend recovery re-entry**, with 0-2 month waits all working.

The preferred variant passed all stated gates on local SIP daily bars from **2016-01-04 through 2026-05-29**:

- Full-period delta vs SPY: **+1,451 pp**, above the +800 pp gate.
- Retention of SOXX outperformance: **0.86x**, above the 0.70x gate.
- Max drawdown: **-26.6%**, better than the target < -35% and ideal < -30%.
- Fold deltas vs SPY: positive in all folds.
- Stress cost: still positive, **+1,414 pp vs SPY** at 25 bps turnover cost.
- Parameter dependence: partially passed. The result is not dependent on one wait value or one semiconductor exposure, but it is dependent on the market-drawdown exit family. Relative-momentum exits alone were much weaker.

## Data And Method

Input data was restricted to local adjusted SIP daily bars:

`data/market_data/bars/feed=SIP/timeframe=1D/symbol=*/bars.parquet`

Symbols used: `SPY`, `QQQ`, `XLK`, `SOXX`, `SMH`. A static semiconductor basket was available and defined as a 50/50 SOXX/SMH daily-return basket. No non-local or intraday data was used.

Signals were evaluated only at each month-end close and applied on the next trading day. Daily returns during the following month used the target exposure already determined from prior data. Long lookbacks were treated as unavailable until enough local bars existed; early missing 200-day signals did not create synthetic exits.

Costs were modeled as turnover costs on monthly exposure changes:

- Base cost: 5 bps.
- Stress cost: 25 bps.

Strategy exposure was either SOXX or the 50/50 semiconductor basket. Cash earned 0%.

Exit families tested:

- `trend_only`: SOXX below 200-day MA.
- `relmom_only`: 63-trading-day SOXX/SPY relative return <= 0.
- `marketdd_only`: SPY drawdown from 252-day high <= -10% or QQQ drawdown from 252-day high <= -12%.
- Pairwise OR combinations.
- `all_or`: any exit trigger.

Re-entry rules tested:

- SOXX/SPY 63-day relative momentum positive.
- QQQ above 200-day MA.
- SOXX above 50-day, 100-day, or 200-day MA.
- Combined rules: relative momentum + QQQ 200-day, relative momentum + SOXX 200-day, QQQ 200-day + SOXX 100-day, and all three.

Timing overlays tested:

- Minimum wait after exit: 0, 1, 2, or 3 monthly decision cycles.
- Full re-entry.
- Staged 25% / 50% / 100% re-entry.

## Baselines

| Asset | Total return | CAGR | Max DD | Sharpe |
|---|---:|---:|---:|---:|
| SPY | 341.0% | 15.3% | -33.8% | 0.90 |
| QQQ | 628.2% | 21.0% | -35.0% | 0.97 |
| XLK | 907.5% | 24.9% | -33.6% | 1.04 |
| SOXX buy-and-hold | 2,031.4% | 34.2% | -45.8% | 1.06 |
| SMH buy-and-hold | 2,394.5% | 36.3% | -45.3% | 1.12 |
| SOXX/SMH basket | 2,213.2% | 35.3% | -45.5% | 1.09 |

## Best Variants

All rows below use 5 bps base cost. `Retention` means `(strategy return - SPY return) / (SOXX return - SPY return)`.

| Exposure | Exit | Re-entry | Wait | Staging | Total return | Delta vs SPY | Retention | Max DD | Stress delta vs SPY |
|---|---|---|---:|---|---:|---:|---:|---:|---:|
| SOXX/SMH basket | market DD only | QQQ above 200d | 2 | full | 1,792.4% | +1,451 pp | 0.86x | -26.6% | +1,414 pp |
| SOXX | market DD only | QQQ above 200d | 2 | full | 1,729.0% | +1,388 pp | 0.82x | -28.8% | +1,352 pp |
| SOXX/SMH basket | market DD only | QQQ above 200d | 0 | full | 1,693.5% | +1,352 pp | 0.80x | -27.9% | +1,317 pp |
| SOXX/SMH basket | market DD only | QQQ above 200d | 1 | full | 1,693.5% | +1,352 pp | 0.80x | -27.9% | +1,317 pp |
| SOXX/SMH basket | market DD only | QQQ above 200d + SOXX above 100d | 2 | full | 1,600.7% | +1,260 pp | 0.75x | -26.6% | +1,226 pp |
| SOXX/SMH basket | market DD only | SOXX above 200d | 2 | full | 1,561.1% | +1,220 pp | 0.72x | -26.6% | +1,187 pp |
| SOXX/SMH basket | trend or market DD | QQQ above 200d | 2 | full | 1,545.5% | +1,204 pp | 0.71x | -24.9% | +1,153 pp |

The top variant had 5 exits and 5 re-entries, 10.0x total notional turnover, average exposure of 84.7%, and 84.7% of days invested. Its exposure changes were:

| Apply date | Target |
|---|---:|
| 2019-01-02 | 0% |
| 2019-03-01 | 100% |
| 2020-03-02 | 0% |
| 2020-05-01 | 100% |
| 2022-03-01 | 0% |
| 2023-02-01 | 100% |
| 2023-03-01 | 0% |
| 2023-05-01 | 100% |
| 2025-04-01 | 0% |
| 2025-06-02 | 100% |

## Fold Results

Preferred variant: SOXX/SMH basket exposure, market-drawdown exit, QQQ above 200-day re-entry, 2-month wait, full re-entry, 5 bps cost.

| Fold | Strategy return | SPY return | Delta vs SPY | Strategy max DD | SOXX return | SOXX max DD |
|---|---:|---:|---:|---:|---:|---:|
| 2016-2018 | 77.8% | 30.7% | +47.0 pp | -26.1% | 82.9% | -25.2% |
| 2019-2022 | 174.7% | 63.5% | +111.3 pp | -19.3% | 132.0% | -45.8% |
| 2023-2026-05-29 | 287.5% | 106.4% | +181.1 pp | -26.6% | 402.2% | -41.4% |

The fold profile is the main reason this hypothesis is useful: it did not merely win in the AI/semi boom fold. It also improved the 2019-2022 drawdown profile, where buy-and-hold semiconductors suffered the deepest pain.

## Family Observations

| Group | Best delta vs SPY | Median delta vs SPY | Best max DD | Notes |
|---|---:|---:|---:|---|
| Market-drawdown exits only | +1,451 pp | +776 pp | -26.6% | Dominant family; all 144 tested variants stayed positive under stress cost. |
| Trend or market-drawdown exits | +1,204 pp | +639 pp | -24.9% | Better drawdown, lower upside; still credible. |
| Trend-only exits | +985 pp | +548 pp | -33.9% | Useful but less consistent by fold. |
| Relative-momentum exits only | +821 pp | +219 pp | -33.9% | Marginal; does not justify primary use. |
| Trend or relative-momentum exits | +386 pp | +4 pp | -33.9% | Failed robustness; too much whipsaw or missed upside. |

Re-entry observations:

- QQQ above 200-day was the strongest single recovery signal.
- SOXX above 200-day and QQQ above 200-day + SOXX above 100-day were close enough to support the same conclusion.
- Relative-momentum re-entry was not the best standalone gate.
- Waits of 0, 1, and 2 months all produced strong top variants; 3 months gave up too much upside.
- Staged 25/50/100 re-entry reduced median drawdown somewhat but materially reduced the best and median return. Full re-entry after a confirmed monthly recovery worked better in this dataset.

## Gate Review

| Gate | Result |
|---|---|
| Full-period delta vs SPY > +800 pp | **Passed**: +1,451 pp for preferred variant. |
| Retains at least 0.70x SOXX outperformance | **Passed**: 0.86x. |
| Max drawdown below -35%, ideal below -30% | **Passed ideal**: -26.6%. |
| Positive delta vs SPY in every fold | **Passed**: +47.0 pp, +111.3 pp, +181.1 pp. |
| Positive under 25 bps stress costs | **Passed**: +1,414 pp vs SPY. |
| Not dependent on a single cherry-picked parameter | **Partial pass**: robust to 0-2 month waits, SOXX vs basket exposure, and related QQQ/SOXX trend re-entry rules; not robust to replacing market-drawdown exits with relative-momentum exits. |

## Recommendation

Promote this hypothesis to the next research batch as a **risk-control overlay candidate**, not as an allocation recommendation. The next step should be stricter validation:

1. Re-run with raw close data or point-in-time total-return handling to confirm adjusted-bar assumptions are not hiding implementation issues.
2. Add realistic cash yield, ETF borrow/friction assumptions if any short/cash alternatives are later considered, and explicit month-end execution slippage.
3. Test alternative but pre-declared market-drawdown thresholds, such as SPY -8%/-10%/-12% and QQQ -10%/-12%/-15%, without selecting thresholds after seeing returns.
4. Compare to a simpler rule: stay long semis unless QQQ is below its 200-day MA, then re-enter above it. This would isolate whether the market-drawdown exit trigger is truly necessary.
5. Keep this U.S.-only and paper-research-only until it survives out-of-sample or walk-forward review with predefined gates.

The current result is strong enough to preserve and consolidate, but the dependency on a market-drawdown exit trigger should be treated as a research risk rather than evidence of a durable trading edge.
