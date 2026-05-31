# Milestone 17 Plan: Credentialed Paper Runtime Dry Run And Operator Runbook

## Summary

Build a supervised paper-runtime dry run that proves the real always-on runtime path can start, preflight, refresh real Alpaca paper state, update health, serialize a dashboard snapshot, and persist evidence without accidentally placing paper orders. Pair it with an operator runbook so the startup and response procedure is clear before any longer always-on session.

Critical boundary: the default dry run is **monitor-only**. It applies a paper kill switch before the runtime cycle. Operators must explicitly opt in if they want the normal daily-close paper order schedule to be allowed during a smoke run.

## Key Changes

- Add typed dry-run models:
  - `RuntimeDryRunStep`
  - `RuntimeDryRunReport`
- Add `AlpacaPaperRuntimeDryRun`.
- Add CLI:
  - `python -m trading_app.runtime.dry_run`
- Persist dry-run reports under ignored local runtime state:
  - `data/runtime/state/latest-dry-run-report.json`
  - `data/runtime/journal/dry-runs.jsonl`
- Add an operator runbook:
  - `PAPER_RUNTIME_OPERATOR_RUNBOOK.md`

## Dry-Run Behavior

- Run offline preflight first.
- Stop immediately if preflight has failures.
- Construct the real Alpaca paper runtime only after preflight can start.
- By default, enable the paper kill switch before running the cycle.
- Run one runtime cycle.
- Confirm:
  - latest prices refreshed
  - broker sync completed
  - paper order safety held
  - health report was generated
  - dashboard snapshot serialized
  - dry-run evidence persisted
- Mark the dry run failed if paper orders were submitted while monitor-only mode was active.

## Operator Flow

1. Export Alpaca paper credentials locally.
2. Run `python -m trading_app.runtime.preflight`.
3. Run `python -m trading_app.runtime.dry_run`.
4. Review preflight, dry-run, health, and incident evidence.
5. Start the always-on paper runtime only if the dry run is acceptable.
6. Use pause, paper kill switch, force reconciliation, and report generation controls as needed.

## Test Plan

- Dry run fails before runtime construction when preflight fails.
- Monitor-only dry run applies paper kill switch and submits zero paper orders.
- Explicit scheduled-orders dry run allows the runtime’s daily-close paper order path.
- Dry run generates health and dashboard evidence.
- Dry run persists and recovers its latest report.
- Dry-run text rendering does not leak secrets.
- Operator runbook exists and includes start, stop, alert, health, reconciliation, and restart guidance.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- Trading remains U.S.-listed stocks and U.S.-listed ETFs only.
- Runtime remains Alpaca paper only.
- The default smoke path must not place even paper orders.
- Network access and real Alpaca credentials are operator-provided outside automated tests.
