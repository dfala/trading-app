# Milestone 14 Plan: Operator Controls And Alerts

## Summary

Build the first real operator safety layer for the always-on Alpaca paper runtime. The runtime already monitors prices, broker state, reports, learning, and dashboard snapshots. Milestone 14 adds local controls and loud alerts so a human operator can pause paper trading, enable a paper-only kill switch, force reconciliation, generate a report, and see degraded or blocked conditions immediately.

Critical boundary: these controls are for **Alpaca paper mode only**. They must not enable real-money trading, margin, shorts, options, or intraday strategy authority.

## Key Changes

- Add typed operator-control models:
  - `OperatorControlAction`
  - `OperatorControlState`
  - `OperatorControlRequest`
  - `OperatorControlResult`
- Add typed alert models:
  - `RuntimeAlertCode`
  - `RuntimeAlert`
  - `RuntimeAlertEngine`
- Add a `RuntimeControlCenter` used by the always-on runtime.
- Persist control state, control action history, and latest alerts under ignored local runtime data folders.
- Add local dashboard API support for control actions:
  - `POST /api/control`
  - Accepted actions: pause, resume, enable paper kill switch, disable paper kill switch, force reconciliation, generate report.
- Update dashboard snapshots and HTML so the operator can see:
  - runtime paused state
  - paper kill switch state
  - latest accepted control action
  - active alerts
  - local control buttons

## Runtime Behavior

- `pause_runtime`
  - Keeps monitoring, latest prices, broker sync, reconciliation, reporting, and dashboard updates alive.
  - Blocks scheduled strategy evaluation and new paper orders while paused.
- `resume_runtime`
  - Re-enables scheduled paper strategy evaluation.
  - Does not place immediate catch-up orders unless the normal daily-close schedule is currently eligible.
- `enable_paper_kill_switch`
  - Blocks new Alpaca paper order submission.
  - Does not cancel open paper orders automatically in v1.
- `disable_paper_kill_switch`
  - Removes the runtime-level paper order block.
  - Broker reconciliation and risk checks still have final authority.
- `force_reconciliation`
  - Immediately refreshes internal-vs-broker reconciliation and persists the evidence.
- `generate_report`
  - Immediately writes a local daily markdown report using the current paper state.

## Alert Rules

- Alert when runtime status is degraded or blocked.
- Alert when latest prices are missing or stale.
- Alert when broker reconciliation is not clean.
- Alert when risk rejects an order.
- Alert when the paper kill switch is enabled.
- Alert when the runtime is paused.
- Alert on recent runtime errors from market data, broker sync, report generation, or nightly learning.

## Test Plan

- Control model tests validate strict action/state/result behavior.
- Control-center tests prove pause/resume and paper kill switch transitions.
- Runtime tests prove pause and kill switch block scheduled paper orders without stopping monitoring.
- Runtime tests prove force reconciliation and generate report controls perform side effects and persist evidence.
- Alert tests prove stale prices, reconciliation breaks, risk rejections, paused state, kill switch state, and blocked/degraded status produce alerts.
- Dashboard tests prove control API route behavior and alert/control rendering.
- Persistence tests prove control state, control action history, and alerts recover after restart.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- The app remains U.S.-listed stocks and U.S.-listed ETFs only.
- The runtime remains Alpaca paper only.
- The active model remains monthly sector ETF momentum unless changed in a future milestone.
- Intraday monitoring does not become intraday trading.
- Manual controls are local runtime controls, not broker account permissions.
