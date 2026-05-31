# Milestone 52 Plan: Live Dashboard Panel Refresh

## Summary

Make the local operator dashboard refresh the panels an operator actually uses during a live paper session. The dashboard already polls `/api/snapshot`, but the browser refresh path only updated top-line fields and latest prices. This milestone extends the live refresh loop to update alerts, controls, health, report paths, positions, and fills from each runtime snapshot.

## Scope

- Add stable DOM targets for operator-critical dashboard panels.
- Refresh operator control state, button disabled states, and latest action metadata.
- Refresh runtime alerts and incident/health rows.
- Refresh positions and recent fills.
- Refresh report path, learning memo path, trading day, and live-readiness status.
- Preserve the existing local-only dashboard server and paper-only boundary.

## Verification

- Dashboard rendering tests for dynamic panel targets.
- Interactive dashboard tests for browser refresh functions.
- Full pytest and Ruff verification.
