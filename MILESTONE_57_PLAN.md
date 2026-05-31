# Milestone 57 Plan: Completion Auditor Evidence Hardening

## Summary

Tighten the functional completion audit so it validates the evidence surfaces we just made visible: active-model context and market-data quality. The app should not claim dashboard, price-refresh, or daily-report readiness if those artifacts exist but omit the evidence that lets an operator trust them.

## Goals

- Require dashboard snapshots to include active-model explanation evidence.
- Require dashboard snapshots to include daily-report data-quality evidence.
- Require latest-price completion proof to include a market-data quality report with no failures.
- Require daily-report proof to include both data-quality evidence and an active-model dossier.
- Keep external Alpaca paper validation and full-day soak as explicit external requirements when those artifacts are missing.

## Non-Goals

- No new trading behavior.
- No new broker integration.
- No change to live-money boundaries.
- No change to strategy selection or nightly learning behavior.

## Implementation Details

- Update `RuntimeCompletionAuditor` requirement checks:
  - `FR-05` dashboard real runtime state now also checks dashboard active-model and data-quality evidence.
  - `FR-06` latest price refresh now checks associated market-data quality evidence when runtime prices are present.
  - `FR-12` daily report written now also checks data-quality evidence and active-model dossier.
- Add tests for complete evidence and degraded/missing evidence.
- Keep the functional requirement count stable; this milestone strengthens evidence quality instead of adding new completion categories.

## Acceptance Criteria

- Complete fixture artifacts still pass the audit.
- Removing data-quality evidence from dashboard/report artifacts prevents false completion.
- Removing active-model dossier evidence prevents false daily-report completion.
- Audit markdown remains paper-only and secret-safe.
- Full verification remains green.

## Verification

- `pytest tests/test_runtime_completion.py`
- `pytest`
- `ruff check`
- `ruff format --check`
