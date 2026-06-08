# Live Sandbox Pilot

This project is still paper-first. The live sandbox is a separately armed,
hard-capped pilot for one approved champion, not a general live-trading mode.

## Approved Model

- Model: `benchmark_relative_strength_etf:grid-l252-t21-n2`
- Universe: `macro-defensive`
- Symbols: `DIA`, `QQQ`, `IWM`, `MDY`, `TLT`, `GLD`, `XLP`, `XLU`, `XLV`, `XLE`
- Benchmark input: `SPY`
- Order tag prefix: `live-sandbox-`

The sandbox deliberately rejects other model keys, universes, and symbol sets.

## Hard Limits

- Max live allocation: `$100`
- Max order notional: `$100`
- Max orders per day: `4`
- Max loss stop: `$10`
- Products: long-only U.S. equities/ETFs
- Disallowed: margin, short selling, options, crypto, extended-hours trading
- Trading window: regular U.S. market hours only

The kill switch defaults on. Autonomy defaults off.

## Environment Arming

Paper credentials stay paper-only. Do not set the global
`ALPACA_LIVE_TRADING_ENABLED` flag for this runtime.

Live sandbox variables:

```sh
TRADING_APP_LIVE_SANDBOX_ENABLED=true
TRADING_APP_LIVE_SANDBOX_CONFIRMATION=I_UNDERSTAND_LIVE_RISK
APCA_LIVE_API_KEY_ID=...
APCA_LIVE_API_SECRET_KEY=...
```

Optional live-sandbox limits:

```sh
TRADING_APP_LIVE_SANDBOX_MAX_ALLOCATION=100
TRADING_APP_LIVE_SANDBOX_MAX_ORDER_NOTIONAL=100
TRADING_APP_LIVE_SANDBOX_MAX_ORDERS_PER_DAY=4
TRADING_APP_LIVE_SANDBOX_MAX_DAILY_LOSS=10
TRADING_APP_LIVE_SANDBOX_ACCOUNT_ID=alpaca-live-sandbox
```

## Controls

The web dashboard exposes a `Live` tab.

- `Arm autonomy`: permits the sandbox to submit tagged live orders if every gate
  is clear.
- `Pause`: stops new autonomous live orders.
- `Kill switch`: pauses autonomy and cancels open tagged sandbox orders.
- `Reconcile`: records the current broker/ledger state for review.

The kill switch cancels only orders whose client order IDs start with
`live-sandbox-`. It does not liquidate positions by default.

## Blocking Rules

The sandbox blocks itself when:

- Live-sandbox env arming or live credentials are missing.
- The kill switch is enabled or autonomy is paused.
- Latest prices are missing or stale.
- The market is outside regular hours.
- Any tagged live sandbox order is still open.
- Any outside open order exists in a sandbox symbol.
- Broker positions in sandbox symbols do not match the sandbox ledger.
- Planned orders exceed the remaining daily order count or per-order notional cap.
- The sandbox equity breaches the loss stop.

## Current Judgment

This is a learning pilot with real money capped at `$100`. It is not evidence
that the model is ready for larger capital. Promotion beyond this cap requires a
separate live-money review, clean broker reconciliation, and fresh evidence that
recent returns are not just late-entry concentration.
