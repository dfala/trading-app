# Monday Morning Paper Runtime Plan

Date: Monday June 1, 2026

Scope: Alpaca paper trading only. No live-money trading, no shorts, no margin,
no options, no crypto, and no non-U.S. instruments.

## Objective

Use the first regular U.S. market session after Sunday setup to prove that the
paper app can connect to Alpaca, refresh real market data, sync broker state,
keep orders blocked when appropriate, and start the supervised always-on
runtime from a clean evidence folder.

This is not a profitability test. This is an operational readiness test.

## Preconditions

- `data/runtime` is clean and empty.
- Sunday evidence is archived under `data/runtime-archive/20260531-sunday-readiness`.
- `.env` contains Alpaca paper credentials.
- Alpaca account is paper-only for this app.
- Broker-side shorting and margin guardrails are restricted where Alpaca allows.
- The active runtime universe remains:

```text
XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY,SPY
```

## Terminal Setup

Run from the project root:

```bash
cd /Users/dfala/Documents/code/trading
set -a
. ./.env
set +a
```

Use `uv run python -m ...` for the commands below unless your shell already
activates the project virtual environment.

## Before Market Open

Run these before 09:30 ET:

```bash
uv run python -m trading_app.runtime.preflight --output-dir data/runtime --json
uv run python -m trading_app.runtime.dry_run --output-dir data/runtime --json
uv run python -m trading_app.runtime.security --output-dir data/runtime --json
```

Success criteria:

- Preflight can start.
- Runtime is `Alpaca Paper`.
- Broker provider is `alpaca-paper`.
- Dashboard binding is local-only.
- Dry run submits `0` paper orders.
- Secret scan finds `0` credential leaks.
- Any stale-price warning is treated as pre-market/off-hours behavior.

Stop if:

- Credentials are missing.
- Runtime mode is not `Alpaca Paper`.
- Any command submits paper orders during monitor-only dry run.
- Secret scan finds a credential value.
- Dashboard host is not local-only.

## After Market Open

Wait until roughly 09:35 ET to avoid opening-minute data noise. Then run:

```bash
uv run python -m trading_app.runtime.validation --output-dir data/runtime --json
uv run python -m trading_app.runtime.broker_history \
  --output-dir data/runtime \
  --symbols XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY,SPY \
  --limit 100 \
  --json
uv run python -m trading_app.runtime.security --output-dir data/runtime --json
```

Success criteria:

- Latest prices refresh from Alpaca.
- Latest price source records `alpaca`.
- Feed records `IEX`.
- Broker sync completes.
- Broker provider records `alpaca-paper`.
- Dashboard snapshot serializes.
- Monitor-only validation submits `0` paper orders.
- Broker history has no unexpected paper orders.
- Secret scan finds no credential values.

Important: IEX/free data is development-grade. If prices remain stale or
degraded, do not bypass the guardrail. The correct behavior is for orders to
remain blocked.

## Start The Supervised Runtime

If the market-hours checks are acceptable, start the always-on runtime:

```bash
uv run python -m trading_app.runtime.run_alpaca_paper --monitor-only-dry-run-first
```

Dashboard:

```text
http://127.0.0.1:8765
```

Monitor these dashboard areas:

- Runtime mode: `Alpaca Paper`
- Latest price freshness
- Broker connection
- Cash and positions
- Open orders
- Recent fills
- Risk state
- Reconciliation
- Operator controls
- Runtime alerts
- Daily report status
- Nightly learning status

## Morning Stop Conditions

Pause the runtime or enable the paper kill switch if any of these happen:

- Unexpected paper orders appear.
- Latest prices are missing or stale during regular market hours.
- Broker sync fails.
- Reconciliation is dirty.
- Runtime health becomes `critical`.
- Dashboard state does not match runtime state.
- Credentials appear in any local artifact.
- Any non-paper trading path appears reachable.

## Evidence To Preserve

Keep all Monday artifacts under `data/runtime`:

- `state/`
- `journal/`
- `reports/`
- `broker-history/`
- `learning/`

Do not delete `data/runtime` during the session. It is required for restart
recovery, post-run review, completion audit, and signoff.

## Midday Check

Around midday ET, run a read-only health review:

```bash
uv run python -m trading_app.runtime.broker_history \
  --output-dir data/runtime \
  --symbols XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY,SPY \
  --limit 100 \
  --json
uv run python -m trading_app.runtime.security --output-dir data/runtime --json
```

Success criteria:

- No unexpected broker orders.
- No credential leaks.
- Runtime dashboard still shows paper-only mode.

## What Not To Do Monday Morning

- Do not force completion audit green.
- Do not fake fresh prices.
- Do not run live-money trading.
- Do not enable shorts, margin, options, crypto, or non-U.S. instruments.
- Do not manually edit runtime evidence to satisfy an audit.
- Do not promote a model based on one morning of paper data.

## Monday Morning Done Criteria

Monday morning is successful when:

- Pre-market preflight and dry run are clean.
- Market-hours validation reaches Alpaca paper.
- Market-hours broker sync works.
- Dashboard snapshot serializes.
- Zero monitor-only orders are submitted.
- Any stale/degraded market data blocks trading instead of being ignored.
- Secret scan passes.
- The supervised runtime is either running locally or intentionally paused with
  clear evidence explaining why.
