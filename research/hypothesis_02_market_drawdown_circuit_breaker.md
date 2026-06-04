# Hypothesis 2 - Market Drawdown Circuit Breaker

## Paper-Tracking Update

As of `2026-06-02T01:57Z`, the fake-trading paper runtime is armed with the stricter shared-replay variant `market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk0-cash`.

That paper candidate uses the same semiconductor sleeve idea but trips on an 8% `QQQ` drawdown and moves fully to cash. It is being tracked in Alpaca paper only at the monthly market-open decision point. This does not change the live-trading status: live trading remains disabled and still requires forward evidence plus explicit operator approval.

## Verdict

Pass for research continuation, not for live trading.

The strongest balanced variant was a monthly semiconductor momentum sleeve with a 12% market drawdown circuit breaker:

- Sleeve: hold the stronger of `SOXX` and `SMH` by trailing 126 trading-day return.
- Breaker: if either `SPY` or `QQQ` is at least 12% below its trailing 252 trading-day high, move the sleeve fully to cash.
- Re-entry: monthly, using only bars available before the decision date.

At 5 bps turnover cost it returned 2,100.9%, beat SPY by 1,759.9 percentage points, retained 1.04x of SOXX's SPY-relative outperformance, and reduced max drawdown to -29.7%. Under 25 bps stress cost it still returned 1,956.3%, beat SPY by 1,615.3 percentage points, retained 0.96x of SOXX's outperformance, and kept max drawdown near -30.0%.

This is not a live-trading recommendation. It is a promising risk-control research result that should be reproduced in the shared harness and paper-tested before any promotion.

## Data And Method

Local data only:

- Path: `data/market_data/bars/feed=SIP/timeframe=1D/symbol=*/bars.parquet`
- Test window: 2016-01-04 through 2026-05-29
- Available required symbols: `SPY`, `QQQ`, `XLK`, `SOXX`, `SMH`
- Also present: `TLT`, `GLD`
- Not present: `BIL`
- Prices used: adjusted daily closes from local SIP parquet files with `adjustment=ALL`

Decision discipline:

- Decisions are monthly on the first trading day of the month.
- Signals use bars strictly before the decision date.
- New weights become active on the next daily close-to-close return.
- Transaction cost is charged on turnover when the new weight becomes active.
- Cash earns 0%.
- Initial allocation cost is included.

Variants tested:

- 2 sleeves:
  - `top_semi_l126`: stronger of `SOXX` and `SMH` by 126-day return.
  - `rel_semis_l126_vs_spy_qqq`: stronger semiconductor ETF unless it trails the average of `SPY` and `QQQ`; then fallback to the stronger of `SPY` and `QQQ`.
- Drawdown sources: `SPY`, `QQQ`, either, both.
- Drawdown thresholds: 8%, 12%, 15% below 252-day rolling high.
- Risk-on exposure during breaker: 75%, 50%, 0%.
- Risk-off destinations: cash, `SPY`, `QQQ`, `XLK`. `BIL` was unavailable.
- Costs: base 5 bps and stress 25 bps.

That is 290 strategy configurations, evaluated under both cost assumptions.

## Baselines

| Portfolio | Total Return | CAGR | Vol | Sharpe | Max DD |
|---|---:|---:|---:|---:|---:|
| SPY | 341.0% | 15.3% | 17.6% | 0.90 | -33.8% |
| QQQ | 628.2% | 21.0% | 22.2% | 0.97 | -35.0% |
| XLK | 907.5% | 24.9% | 24.3% | 1.04 | -33.6% |
| SOXX buy-and-hold | 2,031.4% | 34.2% | 33.1% | 1.06 | -45.8% |
| SMH buy-and-hold | 2,394.5% | 36.3% | 32.2% | 1.12 | -45.3% |
| Static semis 50/50 buy-and-hold | 2,212.9% | 35.3% | 32.5% | 1.09 | -45.5% |

## Best Variants

All rows below include 5 bps costs unless marked stress. Delta is total-return percentage-point delta versus SPY.

| Variant | Total Return | Delta vs SPY | SOXX Capture | CAGR | Max DD | Stress Total | Stress Max DD | Gate Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Top semis, QQQ 12% DD, 0% risk/cash | 2,329.7% | +1,988.7 pp | 1.18x | 35.9% | -29.7% | 2,161.2% | -30.0% | Best total with ideal drawdown, but QQQ-only source |
| Top semis, either 12% DD, 0% risk/cash | 2,100.9% | +1,759.9 pp | 1.04x | 34.6% | -29.7% | 1,956.3% | -30.0% | Recommended balance |
| Rel semis, either 12% DD, 50% risk/cash | 2,166.9% | +1,825.9 pp | 1.08x | 35.0% | -30.7% | 1,930.7% | -31.0% | Strong relative-sleeve confirmation |
| Top semis, either 8% DD, 50% risk/cash | 1,653.9% | +1,312.9 pp | 0.78x | 31.7% | -30.5% | 1,541.8% | -30.7% | Nearby conservative threshold passes |
| Top semis, either 15% DD, 0% risk/cash | 1,821.4% | +1,480.4 pp | 0.88x | 32.9% | -35.7% | 1,702.3% | -35.7% | Return passes, drawdown target fails |
| Top semis, no breaker | 2,585.4% | +2,244.4 pp | 1.33x | 37.2% | -46.2% | 2,439.2% | -46.4% | Return high, drawdown fails |
| Rel semis, no breaker | 2,405.0% | +2,064.0 pp | 1.22x | 36.3% | -35.3% | 2,148.6% | -35.5% | Nearly improves DD, but target fails |
| Top semis, either 12% DD, 0% risk/SPY | 2,421.1% | +2,080.1 pp | 1.23x | 36.4% | -35.0% | 2,208.8% | -35.3% | More return, but drawdown target fails |
| Top semis, either 12% DD, 0% risk/XLK | 2,735.3% | +2,394.3 pp | 1.42x | 37.9% | -37.2% | 2,496.0% | -38.0% | High return, insufficient circuit break |

Interpretation: moving fully to cash is the only tested risk-off destination that consistently delivered the desired drawdown reduction. Risk-off to `SPY`, `QQQ`, or `XLK` preserved more upside but left drawdowns around or above the target.

## Fold Results

Recommended variant: `top_semi_l126 / either 12% drawdown / 0% risk / cash`.

| Fold | SPY Return | Recommended 5 bps | Delta vs SPY | Recommended 25 bps | Stress Delta vs SPY |
|---|---:|---:|---:|---:|---:|
| 2016-2018 | 30.7% | 79.3% | +48.6 pp | 76.5% | +45.7 pp |
| 2019-2022 | 63.5% | 129.3% | +65.9 pp | 120.0% | +56.5 pp |
| 2023-2026-05-29 | 106.4% | 435.1% | +328.7 pp | 429.7% | +323.4 pp |

The fold gate passes under both base and stress costs.

## Gate Evaluation

| Gate | Result |
|---|---|
| Full-period delta vs SPY > +800 pp | Pass: +1,759.9 pp base, +1,615.3 pp stress |
| Retain at least 0.70x SOXX outperformance | Pass: 1.04x base, 0.96x stress |
| Max drawdown meaningfully below -38% to -45%, target shallower than -35% | Pass: -29.7% base, -30.0% stress |
| Ideal drawdown shallower than -30% | Pass base; stress is approximately at the line and fractionally worse than -30% |
| Positive delta vs SPY in every fold | Pass |
| Positive under stress costs | Pass |
| Not dependent on one cherry-picked parameter | Mostly pass: 12% cash variants are strongest, but 8% with 50% risk and relative-sleeve 12% variants also pass. The 15% threshold does not reliably meet the drawdown target. |

## Recommendation

Carry forward this family, centered on:

`top_semi_l126 / either SPY-or-QQQ drawdown >= 12% / 0% risk / cash`

Do not treat the QQQ-only 12% result as the preferred production candidate despite higher return. It is a useful robustness check, but the either-SPY-or-QQQ trigger is more defensible because it does not rely on choosing the better trigger source after the fact.

Next research gates:

- Reproduce inside the project research harness rather than an ad hoc notebook-style run.
- Add explicit month-end versus first-trading-day decision sensitivity.
- Add execution assumptions beyond close-to-close daily bars if intraday/open data becomes available.
- Keep U.S.-only ETF scope unless the project scope changes.
- Paper-trade with audit logs before any live consideration.
