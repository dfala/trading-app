# Milestone 28 Plan: Runtime Artifact Secret Scanner

## Summary

Add a post-run security scanner that verifies local runtime artifacts do not contain Alpaca credential values. This directly supports the completion-spec security requirements: credentials must never be written to logs, reports, snapshots, dashboard HTML, persisted JSON, or test output.

## Key Changes

- Add runtime secret-scan models.
- Add `RuntimeSecretScanner`.
- Scan text runtime artifacts under `data/runtime/` by default.
- Detect actual configured secret values without rendering those values in findings.
- Ignore missing/placeholder/too-short secret values to reduce false positives.
- Skip binary files safely.
- Persist the latest secret scan report under local ignored runtime state and journal folders.
- Add CLI:
  - `python -m trading_app.runtime.security --output-dir data/runtime`
- Update operator runbook with post-run secret scan instructions.

## Non-Goals

- No external secret manager integration.
- No network calls.
- No scanning outside the requested local artifact directory.
- No claim that this replaces manual review.

## Acceptance Criteria

- Safe runtime artifacts pass.
- Artifacts containing an actual Alpaca API key or secret fail.
- Findings identify the file, line, and secret name without exposing the secret value.
- Binary files do not crash scanning.
- Reports persist under ignored runtime folders.
- CLI returns success for clean artifacts and failure for leaked secrets.

## Verification

- Runtime secret scanner unit tests.
- Runbook coverage test.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`
