# Milestone 51 Plan: Soak Dashboard Evidence Tightening

## Summary

Update the full-day soak evidence analyzer so “dashboard snapshot evidence” means an actual dashboard-shaped snapshot artifact, not merely a backend runtime snapshot. This aligns soak review with the functional dashboard requirement and with the new persisted dashboard snapshot path.

## Scope

- Read `latest-dashboard-snapshot.json` during soak evidence analysis.
- Require the dashboard snapshot to identify `Alpaca Paper` mode.
- Require embedded runtime state to identify `Alpaca Paper` mode when present.
- Keep runtime snapshots as runtime evidence, not dashboard evidence.
- Update soak test fixtures to persist dashboard-shaped snapshots.

## Verification

- Soak evidence tests for present and missing dashboard artifacts.
- Full pytest and Ruff verification.
