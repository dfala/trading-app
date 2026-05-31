# Milestone 15 Plan: Runtime Health And Incident Command

## Summary

Add a first-class health and incident layer to the always-on Alpaca paper runtime. Milestone 14 gave the operator controls and alerts. Milestone 15 turns those signals into a prioritized health report, open incidents, and dashboard/API surfaces that answer the operational question: **is the paper runtime healthy, and what should I look at first?**

Critical boundary: this milestone remains paper-only. Health and incident reporting must never enable live-money trading, margin, shorts, options, or intraday strategy authority.

## Key Changes

- Add typed health models:
  - `RuntimeHealthStatus`
  - `RuntimeHealthCheck`
  - `RuntimeIncident`
  - `RuntimeHealthReport`
- Add a `RuntimeHealthEngine` that evaluates a `RuntimeSnapshot`.
- Track health from:
  - runtime loop freshness
  - latest price freshness
  - broker sync status
  - broker reconciliation
  - operator pause / paper kill switch
  - alert severity
  - daily report availability
  - nightly learning status
- Persist latest health and append a health journal under ignored local runtime data.
- Expose health through:
  - runtime snapshots
  - dashboard snapshot JSON
  - `/api/health`
  - operator dashboard health panel
- Generate open incident records from critical and degraded conditions with suggested operator action.

## Health Semantics

- `healthy`
  - Runtime loop is fresh, prices are fresh, broker sync is clean, reconciliation is clean, and no blocking alerts are active.
- `watch`
  - The runtime is intentionally paused, waiting for first cycle, or has informational conditions that do not block monitoring.
- `degraded`
  - Paper runtime is alive but paper orders should be treated cautiously or blocked, such as stale market data, warning alerts, or paper kill switch enabled.
- `critical`
  - Broker reconciliation is broken, runtime is blocked, error alerts are active, or the runtime loop heartbeat is stale.

## Incident Rules

- Reconciliation breaks create critical incidents.
- Runtime blocked/error alerts create critical incidents.
- Stale or missing market data creates degraded incidents.
- Risk rejections create degraded incidents.
- Paper kill switch creates degraded operator-control incidents.
- Pause creates watch-level operator-control incidents.
- Stale heartbeat creates critical incidents.

## Test Plan

- Health engine tests:
  - Healthy snapshots produce `healthy`.
  - Missing first cycle produces `watch`.
  - Stale heartbeat produces `critical`.
  - Stale latest prices produce `degraded`.
  - Reconciliation breaks produce `critical`.
  - Paused control state produces `watch`.
  - Paper kill switch produces `degraded`.
- Runtime tests:
  - `run_once` persists and exposes a health report.
  - Recovered runtime restores latest health.
- Dashboard tests:
  - Dashboard renders Runtime Health and Incident Command.
  - `/api/health` returns the real health report when provided.
  - `/api/health` falls back to demo snapshot health without a runtime.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- The app remains U.S.-listed stocks and U.S.-listed ETFs only.
- Alpaca paper runtime remains the only trading runtime.
- Intraday monitoring remains monitoring only.
- Incidents are local operational records, not external pager or email notifications yet.
