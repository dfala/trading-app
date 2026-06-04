# Overnight Autonomous Learning Review - 2026-06-02

> Research evidence only. This is not a live-trading instruction, not financial advice, and not authority to change paper or live trading without the project promotion gates.

## Executive Read

The overnight autonomous loop generated a lot of reports, but not a lot of new independent information. From `2026-06-02T00:36:49Z` through the paused run at `2026-06-02T13:10:15Z`, it produced `196` top-level autonomous cycle reports and `980` comparison-report pairs (`980` JSON files plus `980` markdown files).

The key learning is consistent: the only repeated challenger worth continuing to paper-track is still `market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk0-cash`. It was recommended in every `semiconductor-risk-overlays` run overnight, with the latest cycle showing:

| Metric | Value |
| --- | ---: |
| Full-period delta vs `SPY` | `+433.19%` |
| Stress-slippage delta vs `SPY` | `+370.83%` |
| Minimum fold delta | `+10.89%` |
| Average fold delta | `+48.62%` |
| Worst drawdown | `-24.82%` |
| Status | `all folds positive` |

That is a good paper-tracking candidate. It is not enough by itself for live-money promotion, because the overnight observations all occurred on the same trading day and are repeated backtests over the same historical data.

## What We Learned

1. The strongest usable signal remains semiconductor relative strength plus a broad-market drawdown circuit breaker.
2. Pure semiconductor exposure produces much larger returns, but the drawdown is too deep for the project objective.
3. Sector ETF, growth-industry, defensive-macro, and broad-core rotations did not produce a better candidate. They had positive headline deltas in some cases, but failed fold consistency or drawdown behavior.
4. Defensive and broad-core tests are useful as negative evidence: they reduce some risk, but they do not preserve enough upside or consistency versus the semiconductor candidate.
5. The overnight loop confirmed the current paper candidate, but it mostly repeated the same deterministic experiments. Treat this as repeated harness confirmation, not new forward evidence.

## Overnight Inventory

| Hypothesis profile | Runs | Repeated recommendation | Latest status |
| --- | ---: | --- | --- |
| `semiconductor-risk-overlays` | `39` | `market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk0-cash` in `39/39` runs | Completed |
| `sector-etf-momentum-grid` | `40` | None | Completed |
| `defensive-macro-regime` | `39` | None | Completed |
| `growth-industry-rotation` | `39` | None | Completed |
| `broad-core-allocation` | `39` | None | Completed |

The final completed cycle before pause was `learning-cycle-historical-sector-etf-momentum-grid-20260602T131015Z`.

## Profile Findings

### Semiconductor Risk Overlays

The raw leader was consistently `market_drawdown_circuit_breaker:top-semi-l126-no-breaker`, with `+1809.61%` full-period delta and `+19.57%` minimum fold delta. That looks impressive, but the worst drawdown was `-46.24%`, which violates the project's risk objective. This is not a promotion candidate.

The better candidate is the lower-return risk-controlled variant:

| Candidate | Full delta | Stress delta | Min fold | Worst drawdown | Read |
| --- | ---: | ---: | ---: | ---: | --- |
| `top-semi-l126-qqq-dd08-risk0-cash` | `+433.19%` | `+370.83%` | `+10.89%` | `-24.82%` | Best current paper candidate |
| `top-semi-l126-no-breaker` | `+1809.61%` | `+1691.31%` | `+19.57%` | `-46.24%` | Reject for risk |
| `top-semi-l126-qqq-dd08-risk050-cash` | `+945.72%` | not selected | `+5.37%` | `-30.54%` | Watchlist; misses ideal drawdown |
| `top-semi-l126-any-dd08-risk050-cash` | `+837.32%` | not selected | `+5.37%` | `-30.54%` | Watchlist; misses ideal drawdown |

Interpretation: the signal is real enough for continued fake-money tracking, but the strategy should remain constrained by the 8% `QQQ` drawdown breaker and full cash risk-off rule until forward paper evidence says otherwise.

### Sector ETF Momentum Grid

The recurring leader was `benchmark_relative_strength_etf:grid-l252-t21-n1`.

| Metric | Value |
| --- | ---: |
| Full-period delta vs `SPY` | `+109.38%` |
| Stress delta vs `SPY` | `+8.72%` |
| Minimum fold delta | `-38.69%` |
| Worst drawdown | `-31.10%` |

Interpretation: the headline return is not enough. The model fails fold consistency badly and does not improve drawdown enough. No promotion or paper-tracking change.

### Defensive Macro Regime

The latest valid leader was `defensive_regime_switch:grid-r252-n1`.

| Metric | Value |
| --- | ---: |
| Full-period delta vs `SPY` | `-31.75%` |
| Stress delta vs `SPY` | `-85.26%` |
| Minimum fold delta | `-20.59%` |
| Worst drawdown | `-34.84%` |

Interpretation: the defensive macro profile failed. It did not beat the benchmark and did not deliver a sufficiently attractive drawdown improvement. Some early overnight reports showed static `QQQ` as a leader, but static allocation is benchmark context only and is not a valid candidate.

### Growth Industry Rotation

The recurring leader was `benchmark_relative_strength_etf:grid-l126-t21-n2`.

| Metric | Value |
| --- | ---: |
| Full-period delta vs `SPY` | `+160.19%` |
| Stress delta vs `SPY` | `+35.00%` |
| Minimum fold delta | `-30.30%` |
| Worst drawdown | `-31.43%` |

Interpretation: this is not robust enough. It can work in favorable windows, but it fails at least one fold by a large amount and drawdown remains above the target range.

### Broad Core Allocation

The latest valid leader was `monthly_sector_momentum:grid-l252-n1`.

| Metric | Value |
| --- | ---: |
| Full-period delta vs `SPY` | `+300.15%` |
| Stress delta vs `SPY` | `+212.41%` |
| Minimum fold delta | `-10.18%` |
| Worst drawdown | `-26.03%` |

Interpretation: this is the most interesting non-semiconductor negative/secondary finding. Drawdown is acceptable, but the negative fold means it is not a clear challenger. It may deserve future research as a diversifier or fallback sleeve, not as a replacement for the current semiconductor circuit-breaker model.

## Candidate Status

| Candidate | Current decision |
| --- | --- |
| `market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk0-cash` | Continue paper tracking. This is the current best fake-money model. |
| `market_drawdown_circuit_breaker:top-semi-l126-no-breaker` | Reject for promotion despite high return because drawdown is too deep. |
| `market_drawdown_circuit_breaker:*dd08*risk050*cash` | Watchlist only; higher return, but drawdown is around `-30.54%`. |
| Sector ETF relative-strength variants | Reject as current challengers due to fold failures. |
| Defensive macro variants | Reject as current challengers due to underperformance. |
| Growth industry relative-strength variants | Reject as current challengers due to fold failures and drawdown. |
| Broad-core monthly momentum | Keep as a future diversification research idea, not a current challenger. |

## Caveats And Process Issues

- The 39 semiconductor recommendations are not 39 independent market observations. They are repeated backtests on the same historical data and same trading day.
- Promotion observations should not be treated as cross-day forward evidence until distinct live/paper market days accumulate.
- Some reports generated before the static-allocation policy fix list `static_etf_allocation:*` as leaders. Those are invalid as models and should be read only as benchmark context.
- Some older reports label real candidates with `gate_status: static baseline`; that was a labeling bug later corrected to `general evidence only`.
- The scorer still lets high-return, high-drawdown variants appear above safer candidates. The recommendation gate catches this, but the UI should emphasize the gate-qualified candidate, not only the raw top scorer.

## Bottom Line

We have one model that is good enough for continued fake-money tracking: `market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk0-cash`.

We do not yet have enough evidence for live-money promotion. The next useful evidence is forward paper behavior across distinct market days, especially whether the model behaves correctly around real drawdown/re-entry conditions and whether it avoids the deep semiconductor drawdowns that the no-breaker variant suffers.
