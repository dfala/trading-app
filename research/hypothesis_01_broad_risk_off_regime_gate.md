# Hypothesis 1: Broad Risk-Off Regime Gate

## Verdict

Fail. The tested gate does not meet the promotion bar.

No variant passed all success gates. The best total-return variants preserve semiconductor upside only by falling back to high-beta QQQ or XLK, and those variants still breach the -35% max drawdown gate. Safer cash or SPY fallbacks improve drawdown, but they give up too much SOXX retention and, for cash, fail the 2019-2022 validation fold.

Closest gated variant: `XLK>150dma|fallback=XLK` returned +1676.1% with 0.83x SOXX retention and positive SPY-relative returns in every validation fold, but max drawdown was -35.3%, just worse than the -35% gate. It also underperformed SPY during the 2022 bear window.

## Data And Methodology

- Data: local adjusted SIP daily bars from `data/market_data/bars/feed=SIP/timeframe=1D/symbol=*/bars.parquet`.
- Symbols used: `SPY`, `QQQ`, `XLK`, `SOXX`, `SMH`.
- Common test range: 2016-01-04 through 2026-05-29, 2616 common trading days.
- All loaded rows were `data_feed=SIP`, `timeframe=1D`, `adjustment=ALL`.
- BIL and short-duration Treasury proxies were not locally available in the SIP daily folder, so Treasury fallback was not tested.
- Static benchmark returns are reference buy-and-hold series, except the static `50/50 SMH/SOXX` benchmark is monthly rebalanced with no transaction-cost deduction.

Monthly decision rule:

- Decide on the first available trading day of each month.
- Use only bars completed before the decision day.
- Hold 50% `SMH` / 50% `SOXX` when the 50/50 sleeve's trailing 126-trading-day return is greater than both `SPY` and `QQQ`.
- Otherwise hold the configured fallback: cash, `SPY`, `QQQ`, or `XLK`.
- Regime variants also require `SPY`, `QQQ`, or `XLK` to close above its 150-day or 200-day moving average, computed as of the prior completed bar.

Cost model:

- Base cost: 5 bps per one-way ETF notional traded on monthly rebalance days.
- Stress cost: 25 bps per one-way ETF notional traded on monthly rebalance days.
- Cash earns 0% and has no slippage.
- Because only daily OHLC bars are available, execution is approximated close-to-close: the new monthly target is applied to the decision day's close-to-close return, using the prior close signal, and cost is deducted on the rebalance day.

## Grid

Relative momentum was always required. The 28 tested variants were:

- Regime gates: none, `SPY>150dma`, `SPY>200dma`, `QQQ>150dma`, `QQQ>200dma`, `XLK>150dma`, `XLK>200dma`.
- Fallbacks: cash, `SPY`, `QQQ`, `XLK`.
- Costs: 5 bps base and 25 bps stress.

## Benchmarks

| Benchmark | Total return | CAGR | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|
| SPY | +341.0% | 15.3% | -33.8% | 0.90 |
| QQQ | +628.2% | 21.0% | -35.0% | 0.97 |
| XLK | +907.5% | 24.9% | -33.6% | 1.04 |
| SOXX | +2031.4% | 34.2% | -45.8% | 1.06 |
| SMH | +2394.5% | 36.3% | -45.3% | 1.12 |
| 50/50 SMH/SOXX monthly | +2212.2% | 35.3% | -45.5% | 1.09 |

## Best Results

All rows below fail at least one success gate.

| Variant | Total return | CAGR | Max drawdown | Delta vs SPY | SOXX retention | 25 bps return | Fold deltas vs SPY | Sleeve months |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `relmom_only|fallback=XLK` | +1916.3% | 33.5% | -40.0% | +1575.3 pp | 0.94x | +1793.5% | +37.6 / +49.5 / +360.9 pp | 74/125 |
| `relmom_only|fallback=QQQ` | +1691.4% | 32.0% | -39.5% | +1350.4 pp | 0.83x | +1582.3% | +30.1 / +34.9 / +357.9 pp | 74/125 |
| `XLK>150dma|fallback=XLK` | +1676.1% | 31.9% | -35.3% | +1335.1 pp | 0.83x | +1554.8% | +32.3 / +66.4 / +271.5 pp | 68/125 |
| `SPY>150dma|fallback=XLK` | +1605.0% | 31.4% | -38.3% | +1264.0 pp | 0.79x | +1475.8% | +32.3 / +62.0 / +261.3 pp | 69/125 |
| `QQQ>150dma|fallback=XLK` | +1585.0% | 31.2% | -37.3% | +1244.0 pp | 0.78x | +1469.9% | +32.3 / +59.3 / +261.3 pp | 68/125 |
| `XLK>150dma|fallback=SPY` | +1120.9% | 27.2% | -33.9% | +779.9 pp | 0.55x | +1037.5% | +20.0 / +44.3 / +184.6 pp | 68/125 |

The best drawdown-valid, fold-positive candidate is `XLK>150dma|fallback=SPY`, but it misses the +800 pp SPY-delta gate by about 20 pp and captures only 0.55x of SOXX.

## Full Grid Results

5 bps base cost. Fold deltas are 2016-2018 / 2019-2022 / 2023-forward versus SPY.

| Variant | Return | MDD | Delta vs SPY | SOXX retention | 25 bps return | Fold deltas | Pass |
|---|---:|---:|---:|---:|---:|---:|---:|
| `QQQ>150dma|fallback=QQQ` | +1341.2% | -37.5% | +1000.2 pp | 0.66x | +1242.7% | +24.8 / +41.5 / +246.5 pp | No |
| `QQQ>200dma|fallback=QQQ` | +1310.6% | -37.5% | +969.6 pp | 0.65x | +1214.3% | +21.5 / +41.5 / +246.5 pp | No |
| `SPY>150dma|fallback=QQQ` | +1416.4% | -37.0% | +1075.4 pp | 0.70x | +1301.6% | +24.8 / +52.2 / +246.5 pp | No |
| `SPY>200dma|fallback=QQQ` | +1314.3% | -37.0% | +973.3 pp | 0.65x | +1196.8% | +21.5 / +42.1 / +246.5 pp | No |
| `XLK>150dma|fallback=QQQ` | +1401.2% | -35.8% | +1060.2 pp | 0.69x | +1298.7% | +24.8 / +47.1 / +252.8 pp | No |
| `XLK>200dma|fallback=QQQ` | +1321.7% | -37.0% | +980.7 pp | 0.65x | +1214.0% | +21.5 / +43.1 / +246.5 pp | No |
| `relmom_only|fallback=QQQ` | +1691.4% | -39.5% | +1350.4 pp | 0.83x | +1582.3% | +30.1 / +34.9 / +357.9 pp | No |
| `QQQ>150dma|fallback=SPY` | +1091.9% | -33.9% | +750.9 pp | 0.54x | +1010.5% | +20.0 / +42.0 / +179.6 pp | No |
| `QQQ>200dma|fallback=SPY` | +1038.2% | -33.9% | +697.2 pp | 0.51x | +960.5% | +13.2 / +42.0 / +179.6 pp | No |
| `SPY>150dma|fallback=SPY` | +1002.1% | -34.8% | +661.1 pp | 0.49x | +918.6% | +20.0 / +26.5 / +179.6 pp | No |
| `SPY>200dma|fallback=SPY` | +896.9% | -34.8% | +555.9 pp | 0.44x | +814.0% | +13.2 / +16.5 / +179.6 pp | No |
| `XLK>150dma|fallback=SPY` | +1120.9% | -33.9% | +779.9 pp | 0.55x | +1037.5% | +20.0 / +44.3 / +184.6 pp | No |
| `XLK>200dma|fallback=SPY` | +969.5% | -34.8% | +628.5 pp | 0.48x | +888.5% | +13.2 / +29.6 / +179.6 pp | No |
| `relmom_only|fallback=SPY` | +1432.5% | -36.8% | +1091.5 pp | 0.71x | +1339.2% | +26.5 / +23.5 / +319.2 pp | No |
| `QQQ>150dma|fallback=XLK` | +1585.0% | -37.3% | +1244.0 pp | 0.78x | +1469.9% | +32.3 / +59.3 / +261.3 pp | No |
| `QQQ>200dma|fallback=XLK` | +1559.0% | -37.3% | +1218.0 pp | 0.77x | +1445.7% | +29.8 / +59.3 / +261.3 pp | No |
| `SPY>150dma|fallback=XLK` | +1605.0% | -38.3% | +1264.0 pp | 0.79x | +1475.8% | +32.3 / +62.0 / +261.3 pp | No |
| `SPY>200dma|fallback=XLK` | +1521.5% | -38.3% | +1180.5 pp | 0.75x | +1386.7% | +29.8 / +54.3 / +261.3 pp | No |
| `XLK>150dma|fallback=XLK` | +1676.1% | -35.3% | +1335.1 pp | 0.83x | +1554.8% | +32.3 / +66.4 / +271.5 pp | No |
| `XLK>200dma|fallback=XLK` | +1530.4% | -38.3% | +1189.4 pp | 0.75x | +1406.9% | +29.8 / +55.5 / +261.3 pp | No |
| `relmom_only|fallback=XLK` | +1916.3% | -40.0% | +1575.3 pp | 0.94x | +1793.5% | +37.6 / +49.5 / +360.9 pp | No |
| `QQQ>150dma|fallback=cash` | +521.8% | -33.9% | +180.8 pp | 0.26x | +500.6% | +11.4 / -6.5 / +71.6 pp | No |
| `QQQ>200dma|fallback=cash` | +504.2% | -33.9% | +163.2 pp | 0.25x | +483.7% | +7.4 / -6.5 / +71.6 pp | No |
| `SPY>150dma|fallback=cash` | +483.0% | -28.6% | +142.0 pp | 0.24x | +460.9% | +11.4 / -16.3 / +71.6 pp | No |
| `SPY>200dma|fallback=cash` | +402.3% | -28.6% | +61.3 pp | 0.20x | +381.3% | +7.4 / -33.0 / +71.6 pp | No |
| `XLK>150dma|fallback=cash` | +550.2% | -33.9% | +209.2 pp | 0.27x | +528.1% | +11.4 / -9.5 / +89.9 pp | No |
| `XLK>200dma|fallback=cash` | +403.1% | -33.9% | +62.1 pp | 0.20x | +384.1% | +7.4 / -32.8 / +71.6 pp | No |
| `relmom_only|fallback=cash` | +762.7% | -33.9% | +421.7 pp | 0.38x | +736.7% | +17.8 / -32.2 / +239.7 pp | No |

## Stress And Event Behavior

All 28 variants remained positive under the 25 bps stress-cost model, so costs are not the failure point. The failure is the drawdown/retention tradeoff.

| Variant | 2020 crash | 2022 bear | Read |
|---|---:|---:|---|
| `relmom_only|fallback=XLK` | -31.5% vs SPY -33.8% | -39.7% vs SPY -24.3% | Preserves upside, fails risk control. |
| `XLK>150dma|fallback=XLK` | -31.5% vs SPY -33.8% | -34.9% vs SPY -24.3% | Best gated result, still weak in 2022. |
| `XLK>150dma|fallback=SPY` | -31.5% vs SPY -33.8% | -29.4% vs SPY -24.3% | Drawdown-valid full period, but low retention. |
| `SPY>150dma|fallback=QQQ` | -28.3% vs SPY -33.8% | -36.7% vs SPY -24.3% | Better 2020, poor 2022. |
| `relmom_only|fallback=cash` | -31.5% vs SPY -33.8% | -27.3% vs SPY -24.3% | Safer, but fails retention and 2019-2022 fold. |

## Success Gates

Interpreting the SPY delta gate as total-return percentage-point delta versus SPY:

| Gate | Result |
|---|---:|
| Full-period delta vs SPY > +800 pp | 15/28 pass |
| SOXX retention >= 0.70x | 9/28 pass |
| Max drawdown better than -35% | 13/28 pass |
| Positive delta vs SPY in every validation fold | 21/28 pass |
| 25 bps stress-cost return positive | 28/28 pass |
| All gates simultaneously | 0/28 pass |

## Recommendation

Do not promote Hypothesis 1 as a trading candidate.

The 126-day semiconductor relative momentum signal is useful for capturing upside, and the return behavior is not dependent on one narrow MA threshold: XLK, SPY, and QQQ gates with 150-day and 200-day MAs all produced similar high-return patterns when paired with an XLK fallback. But the risk failure is also robust. High-retention variants keep too much tech beta during broad drawdowns, especially 2022. Defensive fallbacks reduce drawdown but no longer preserve enough semiconductor alpha.

If this line of research continues, the next test should not be another simple broad MA gate. It should add a stronger risk-control mechanism such as partial sleeve sizing, volatility targeting, faster de-risking than monthly, or a true short-duration Treasury/cash-equivalent fallback once local data is available.
