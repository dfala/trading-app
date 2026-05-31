# Milestone 32 Plan: Consolidated Validation Evidence In Completion Audit

## Summary

Make the functional completion audit understand evidence produced by the
supervised validation sequence. The validation command intentionally stores
monitor-only dry-run proof inside `RuntimeValidationReport`; the audit should
credit that evidence instead of requiring operators to run and persist a second
standalone dry-run artifact.

## Key Changes

- Treat `validation.monitor_dry_run_report` as valid proof for:
  - credentialed monitor-only dry run
  - zero submitted monitor-only paper orders
  - order-blocking guard evidence
- Treat validation freshness facts as valid proof for latest-price refresh when
  a runtime snapshot is not available yet.
- Surface the latest completion audit in the operator dashboard when available.
- Keep stronger requirements strict:
  - dashboard runtime state still requires a runtime snapshot
  - broker/portfolio visibility still requires a snapshot with paper report
  - full-day soak still requires soak evidence
  - fill/restart integrity still requires order/fill journals

## Non-Goals

- No weakening of the completion definition.
- No fake proof for the full-day Alpaca paper soak.
- No real Alpaca network calls in tests.

## Test Plan

- Completion audit credits validation-embedded monitor-only dry-run evidence.
- Completion audit credits validation latest-price freshness evidence.
- Dashboard shows functional readiness counts when a completion audit exists.
- Completion audit still reports missing/external requirements for runtime
  snapshot, soak, and fill evidence when those artifacts are absent.
- Full test and lint suite remain clean.
