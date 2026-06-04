# Winning Model Criteria

This project should not define a winning trading model as "the model with the highest backtest return." A winning model is one that produces durable excess return, survives realistic validation, can be operated safely, and does not rely on a very recent spike to look good.

## Primary Standard

A model is a serious winner only if it can answer all of these questions well:

- Does it beat the market benchmark over the full available replay window?
- Does it beat stronger relevant benchmarks, not only `SPY`? For semiconductor strategies, compare against `QQQ`, `XLK`, `SOXX`, `SMH`, and the current paper champion.
- Does it win across validation folds instead of one cherry-picked period?
- Does it still work after stress slippage and realistic trading friction?
- Does it keep max drawdown within the current risk target?
- Does it remain strong over the latest 3, 6, and 12 months without depending on only the latest 21 or 63 trading days?
- Can the runtime actually build it, shadow-track it, explain its targets, and enforce rollback/kill-switch controls?

## Mandatory Gates

Use these gates before recommending a champion change:

- Positive excess return versus `SPY` over the full replay window.
- Positive validation folds, preferably all folds positive.
- Positive stress-cost delta after higher slippage.
- Worst fold cushion is meaningfully positive, not barely above zero.
- Max drawdown is acceptable for the current strategy class.
- Beats or closely challenges the current champion on risk-adjusted evidence.
- No single recent window explains most of the model's apparent edge.
- Reproducible in the shared replay harness using point-in-time data.
- Runtime adapter support exists for paper/shadow tracking.

## Recent-Spike Discipline

Very recent performance is useful evidence, but it is also late-entry risk. Do not crown a model because it surged over the latest 21 or 63 trading days.

Before promotion, explicitly check:

- Latest 21 trading days.
- Latest 63 trading days.
- Latest 126 trading days.
- Latest 252 trading days.
- Whether the latest 21/63-day window explains an outsized share of the full-period excess return.
- Whether 3-, 6-, and 12-month returns are consistent or whether the model only looks good after a sharp recent acceleration.

If a model's edge is concentrated in the most recent 1-3 months, keep it in shadow tracking or late-entry review instead of promoting it directly.

## Paper Phase Bias

During fake-money paper trading, the system should move quickly:

- Strong candidates should enter shadow tracking quickly.
- Missing promotion checks should run promptly.
- Finalists should be tuned aggressively with nearby parameter sweeps.
- Paper authority can change faster than live-money authority when runtime safety checks pass.

This fast-learning bias does not apply to real-money trading. Live-money pilots require separate manual approval, explicit position limits, clean paper evidence, and kill switches.

## Not Candidate Models

Static buy-and-hold ideas such as "just hold `SOXX`" or "just hold `QQQ`" are benchmarks, not candidate models. They can appear as comparison lines, but they should not be ranked as trading strategies or promoted as champions.

## Promotion States

Use these states consistently:

- `research`: interesting in historical replay only.
- `shadow`: tracked in a virtual ledger with no broker orders.
- `paper`: allowed to submit fake-money Alpaca paper orders.
- `live pilot`: limited real-money test with explicit manual approval.
- `retired`: no longer considered because evidence degraded or a better model replaced it.

The current goal is to find models worthy of `shadow` and `paper` quickly, while treating `live pilot` as a stricter later decision.
