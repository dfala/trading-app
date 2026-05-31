# Milestone 33 Plan: Completion Audit Dossier Report

## Summary

Turn the functional completion audit into a durable operator dossier. The audit
already proves, fails, or marks each functional requirement as needing external
evidence. This milestone writes a Markdown report alongside the JSON state so a
human can review the full readiness picture after a credentialed paper run.

## Key Changes

- Add `markdown_path` to `FunctionalCompletionAuditReport`.
- Render a Markdown completion dossier with:
  - paper-only boundary
  - status and readiness counts
  - requirement-by-requirement evidence
  - remediation guidance
  - explicit next action
- Persist the Markdown dossier under ignored runtime reports.
- Surface the report path in the CLI text output.
- Document the dossier in the paper runtime operator runbook.

## Non-Goals

- No weakening of the completion audit.
- No fake proof for external Alpaca paper evidence.
- No real broker/network calls in tests.
- No live-money enablement.

## Test Plan

- Completion audit writes a Markdown report when persisted.
- Report path is stored in the JSON model.
- Markdown includes all requirement evidence and no credential values.
- CLI text includes the report path.
- Existing completion, validation, dashboard, and full repo checks remain clean.
