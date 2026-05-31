# Milestone 49 Plan: Runtime Dashboard Demo-State Removal

## Summary

Remove demo-derived state from the live Alpaca paper dashboard snapshot. The functional spec requires dashboard state to come from live runtime data, not static demo data. The runtime dashboard already uses live paper portfolio, report, health, alerts, controls, and completion evidence, but its live-readiness panel was still borrowed from the demo snapshot.

## Scope

- Build live-readiness report evidence directly from the current Alpaca paper runtime snapshot.
- Keep live trading disabled and blocked in the runtime dashboard.
- Base readiness checks on real runtime facts: reconciliation, data freshness, risk engine presence, controls, symbols, and active paper model.
- Remove the runtime dependency on `build_demo_dashboard_snapshot`.
- Add regression coverage proving runtime dashboard live-readiness is not demo-derived.

## Verification

- Runtime dashboard snapshot tests.
- Dashboard rendering tests.
- Full pytest and Ruff verification.
