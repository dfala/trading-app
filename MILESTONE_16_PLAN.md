# Milestone 16 Plan: Paper Runtime Startup Preflight

## Summary

Add an offline startup preflight gate for the always-on Alpaca paper runtime. The runtime now has persistence, recovery, controls, alerts, health, and incident command. Milestone 16 makes startup deliberate: before the process begins cycling, it should produce a local preflight report that confirms the runtime is configured for paper mode, has credentials present, writes local state safely, can recover persisted state, and preserves our daily-close trading boundary.

Critical boundary: preflight does **not** connect to Alpaca or place orders. It is an offline local gate. Real broker connectivity is still exercised by the paper runtime after the gate passes.

## Key Changes

- Add typed preflight models:
  - `RuntimePreflightStatus`
  - `RuntimePreflightCheck`
  - `RuntimePreflightReport`
- Add `AlpacaPaperRuntimePreflight`.
- Add command-line entry point:
  - `python -m trading_app.runtime.preflight_alpaca_paper` is not needed because the module itself is executable:
  - `python -m trading_app.runtime.preflight`
- Persist latest preflight and append a preflight journal:
  - `data/runtime/state/latest-preflight-report.json`
  - `data/runtime/journal/preflight.jsonl`
- Wire preflight into `python -m trading_app.runtime.run_alpaca_paper` before runtime startup.
- Add `--skip-preflight` only for tests or emergency local debugging.

## Preflight Checks

- Credentials:
  - `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` must be present.
  - Values must never be written to logs or reports.
- Paper boundary:
  - Runtime remains Alpaca paper only.
  - Fail if a live-trading environment flag is enabled.
- Symbol scope:
  - Symbols must pass the project’s uppercase U.S. stock/ETF ticker format.
  - No non-U.S. markets, crypto, futures, options, or lowercase symbols.
- Market data feed:
  - Allow Alpaca `IEX` and `SIP`.
  - Warn on `IEX` because it is development-grade/free data.
  - Fail unsupported feeds.
- Storage:
  - Runtime output directory must be writable.
  - State remains under ignored local runtime data.
- Recovery:
  - Persisted runtime JSON/JSONL must be readable before restart.
- Dashboard binding:
  - Operator dashboard must bind to local-only hosts by default.
  - Fail public network bindings.
- Schedule:
  - Paper trading must remain after regular close.
  - Nightly learning must run after trading/report generation.

## Test Plan

- Valid paper runtime preflight passes with warnings for IEX.
- Missing credentials fail when credentials are required.
- Missing credentials warn when explicitly not required.
- Live-trading flag fails.
- Invalid symbols fail.
- Public dashboard host fails.
- Bad schedule fails.
- Preflight persists and recovers its latest report.
- CLI returns success/failure appropriately without making network calls.
- `run_alpaca_paper` blocks startup when preflight fails.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- Trading remains U.S.-listed stocks and U.S.-listed ETFs only.
- Runtime remains Alpaca paper only.
- No live-money path is enabled by this milestone.
- Offline preflight is a safety gate, not a broker connectivity test.
