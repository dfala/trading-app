# Semiconductor Risk-Control Research Batch

Date: 2026-06-01

Scope: U.S. ETF research only. These reports use local SIP daily bars from `2016-01-04` through `2026-05-29` where available. They are not live-trading instructions and are not financial advice.

Winning-model criteria are documented in [`WINNING_MODEL_CRITERIA.md`](WINNING_MODEL_CRITERIA.md). Use that file as the source of truth for what qualifies as a real winner versus a high-return but fragile backtest.

## Paper-Tracking Activation

As of `2026-06-02T01:57Z`, the Alpaca paper runtime is armed for fake trading only with `market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk0-cash`.

This is a paper-tracking promotion, not a live-money recommendation. The active paper model holds the stronger of `SOXX` and `SMH` by trailing 126-day return, moves fully to cash when `QQQ` is at least 8% below its trailing 252-day high, and evaluates on the monthly market-open paper schedule. Live trading remains disabled, and promotion to real money still requires forward paper evidence, operator review, and explicit approval.

As of `2026-06-02T19:31Z`, the runtime supports multiple shadow ledgers and is tracking five non-broker challengers alongside the unchanged paper-order champion:

- `market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk050-cash`
- `benchmark_relative_strength_etf:grid-l126-t63-n1`
- `cash_rotation_model:grid-l63-n1-b040`
- `market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk025-cash`
- `risk_managed_semiconductor:vol-smh-v63-t020-off-cash`

These shadows are virtual ledgers only. They may generate target weights and simulated orders for comparison, but they do not submit Alpaca broker orders. The leaderboard winner, `benchmark_relative_strength_etf:grid-l126-t63-n1`, is now observable in paper runtime state, but it is not promoted to the broker-order champion.

Winning-model discipline: do not promote or crown a model because the latest 21-63 trading days spiked upward. Late-window surges are useful evidence, but they are also late-entry risk. Any champion recommendation should explicitly check whether 3-, 6-, and 12-month performance is consistent rather than being dominated by the most recent spike.

The shared replay evidence for this exact paper candidate showed positive behavior across 3/3 folds, approximately +433.2 percentage points full-period delta versus `SPY`, and approximately -24.8% worst drawdown. The older Hypothesis 2 report below still documents the broader 12% drawdown sensitivity batch.

## Reports

| Hypothesis | Report | Verdict | Best candidate | Key result |
| --- | --- | --- | --- | --- |
| 1. Broad risk-off regime gate | `hypothesis_01_broad_risk_off_regime_gate.md` | Fail | `XLK>150dma|fallback=XLK` | +1335.1 pp vs `SPY`, 0.83x `SOXX` retention, but -35.3% max drawdown missed the gate. |
| 2. Market drawdown circuit breaker | `hypothesis_02_market_drawdown_circuit_breaker.md` | Pass for research continuation | `top_semi_l126`, either `SPY` or `QQQ` down 12%, cash risk-off | +1759.9 pp vs `SPY`, 1.04x `SOXX` retention, -29.7% max drawdown. |
| 3. Fast-loss semiconductor sleeve gate | `hypothesis_03_fast_loss_sleeve_gate.md` | Marginal pass / watchlist | 50/50 `SOXX`/`SMH`, 42-day 10% loss, MA200 re-entry, `SPY` risk-off | +1607.0 pp vs `SPY`, 0.95x `SOXX` retention, -34.9% max drawdown. |
| 4. Relative momentum with defensive fallback | `hypothesis_04_defensive_fallback.md` | Reject as-is | `rel_semis_l126` with 60/40 `XLK`/cash fallback | Drawdown improved to -35.0%, but retention fell to 0.56x. |
| 5. Crash-reentry timing | `hypothesis_05_crash_reentry_timing.md` | Pass for research promotion | 50/50 `SOXX`/`SMH`, market-drawdown exit, `QQQ` above 200d re-entry, 2-month wait | +1451 pp vs `SPY`, 0.86x `SOXX` retention, -26.6% max drawdown. |
| 6. Adaptive semiconductor sleeve composition | `hypothesis_06_adaptive_sleeve_composition.md` | Secondary pass | 126-day relative strength top-1 among `SMH`, `SOXX`, `XLK`, `QQQ`, `SPY` fallback | +1471 pp vs `SPY`, 0.87x `SOXX` retention, -33.6% max drawdown. |

## Consolidated Read

The strongest signal from this batch is not a simple moving-average regime gate. The useful risk control appears to come from broad-market drawdown state and disciplined re-entry:

- Primary candidates to reproduce in the shared harness: Hypothesis 2 and Hypothesis 5.
- Secondary candidate: Hypothesis 6, because it keeps strong return and fold behavior, but does not reach the ideal drawdown target.
- Watchlist only: Hypothesis 3, because it barely clears the drawdown target and looks more parameter-fragile.
- Reject as-is: Hypothesis 1 and Hypothesis 4.

Next validation should reproduce the passing candidates in the shared replay harness with audit logs, threshold sensitivity, point-in-time execution assumptions, realistic cash yield, stress slippage, and walk-forward rules before any paper-tracking promotion.

## Autonomous Historical Rotation

As of 2026-06-02, the self-feeding learning service treats historical experiments as a novelty queue. Each queued historical hypothesis should run once per sweep; after the queue is exhausted, the service should stop historical reruns until new hypotheses are added or repeat sweeps are explicitly enabled.

Static buy-and-hold ideas such as "just hold QQQ" or "just hold SOXX" are not candidate models for future hypothesis searches. They may appear only as benchmark reference lines when useful for context, and they must not be ranked, promoted, or selected as challengers.

| Order | Profile | Question being tested |
| ---: | --- | --- |
| 1 | `semiconductor-risk-overlays` | Can the current semiconductor alpha sleeve keep its edge while reducing drawdown through trend, volatility, and drawdown controls? |
| 2 | `sector-etf-momentum-grid` | Do broad sector ETF momentum, relative-strength, volatility, cash, or defensive regime variants produce a stronger repeatable signal than the semiconductor sleeve? |
| 3 | `defensive-macro-regime` | Can macro and defensive assets improve drawdown control without destroying upside? |
| 4 | `growth-industry-rotation` | Does broader growth/industry ETF rotation beat concentrated semiconductor exposure with better consistency? |
| 5 | `broad-core-allocation` | Do broad liquid ETF allocation variants provide a more robust baseline than narrower sector or industry themes? |

Fresh market-data learning still runs after the market close. Strategy promotion remains slow and manual: the loop may generate evidence and recommendations, but it cannot grant paper or live trading authority.
