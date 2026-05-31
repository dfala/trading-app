# Milestone 42 Plan: Incident Review Artifacts

## Summary

Make runtime incidents reviewable as operator-facing artifacts, not just JSON embedded in health state. This supports the functional spec's operator safety and incident-response requirements.

## Scope

- Render runtime health reports as Markdown incident review reports.
- Persist the latest health Markdown path under local runtime state.
- Recover the latest health report path after restart.
- Surface the health report path in the dashboard snapshot.
- Keep the report paper-only and action-oriented.

## Verification

- Unit tests for incident review Markdown.
- Runtime persistence tests for the latest health report path.
- Dashboard snapshot test for the review path.
- Full pytest and Ruff verification.
