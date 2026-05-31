# Milestone 13 Plan: Runtime Persistence And Recovery

## Summary

Make the always-on Alpaca paper runtime durable. The app should preserve the operational record of prices, broker syncs, orders, fills, reports, learning runs, reconciliation, and runtime events under the ignored `data/runtime/` tree. If the process restarts, it should rebuild the internal paper ledger from persisted orders and fills before it is allowed to evaluate new paper trades.

This milestone keeps the current risk boundary: Alpaca paper only, U.S.-listed stocks and ETFs only, no shorts, no margin, no options, and no live-money trading.

## Key Changes

- Add a local runtime persistence store using JSON snapshots and JSONL journals.
- Persist latest price snapshots, runtime cycle results, runtime events, paper order submissions, order statuses, fills, reconciliation reports, daily report JSON, nightly learning JSON, and the latest runtime snapshot.
- Add paper-service recovery support that replays accepted persisted orders and fills into a fresh ledger, restores order statuses/submissions, and remains idempotent.
- Wire the always-on runtime to persist every cycle and restore automatically during Alpaca startup.
- Keep generated runtime data under `data/runtime/`, which is already ignored by git.

## Recovery Behavior

- On startup, load persisted paper submissions, order statuses, and fills.
- Rebuild the ledger by replaying accepted broker-submitted orders and then fills in timestamp order.
- Restore the last latest-price snapshot, daily report, nightly learning run, runtime events, and last cycle when available.
- After recovery, broker synchronization still runs before any new strategy order evaluation.
- If recovered data is partial or missing, start with available records and preserve a runtime event describing degraded recovery.

## Test Plan

- Persist and reload latest price snapshots, cycle results, events, reports, and learning runs.
- Persist submissions/statuses/fills and restore a fresh paper service with the same cash, positions, fills, and order statuses.
- Prove recovery is idempotent when called multiple times.
- Prove the always-on runtime writes persistence records during a cycle.
- Prove a restarted runtime restores prior paper state and does not submit another same-day paper rebalance.
- Run full verification with `uv run pytest`, `uv run ruff check`, and `uv run ruff format --check`.

## Assumptions

- Local JSON/JSONL persistence is enough for Milestone 13; Postgres/DuckDB operational persistence can come later.
- Persistence is for paper-trading operations and research auditability, not broker-grade account reconciliation or tax accounting.
- The internal ledger remains rebuilt from project-owned orders and fills rather than blindly trusting broker portfolio state.
