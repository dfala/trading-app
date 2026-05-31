# Milestone 50 Plan: Dashboard Snapshot Evidence

## Summary

Make dashboard-shaped runtime state a persisted artifact and completion-audit input. The functional spec requires the operator dashboard to show real runtime state, not demo state; proving that from only a backend runtime snapshot is too indirect. This milestone stores the actual dashboard snapshot returned by the runtime dashboard provider and teaches the completion audit to verify that evidence directly.

## Scope

- Persist the latest dashboard snapshot under runtime state.
- Append dashboard snapshots to a local dashboard snapshot journal.
- Keep dashboard snapshots local and ignored under `data/runtime/`.
- Recover dashboard snapshot evidence through the runtime persistence store.
- Update the completion audit to prefer dashboard-shaped evidence for dashboard readiness.
- Preserve the static demo dashboard as an explicit demo-only preview path.

## Verification

- Runtime persistence tests for dashboard snapshot artifacts.
- Completion audit tests proving dashboard evidence is required for full fixture completion.
- Runtime dashboard tests.
- Full pytest and Ruff verification.
