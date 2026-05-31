# Milestone 58 Plan: Local Supervisor Templates

## Summary

Make the always-on paper runtime easier to operate as a durable local process by generating reviewable process-supervision templates. This does not start anything automatically and does not enable live trading; it gives the operator safe macOS `launchd` and Linux `systemd` templates that run the same paper-only, dry-run-first startup command.

## Goals

- Generate macOS `launchd` template text.
- Generate Linux `systemd --user` template text.
- Keep templates paper-only and local-dashboard-only by default.
- Load secrets from a local env file path without writing credential values into generated artifacts.
- Add CLI support to write both templates under a chosen directory.
- Document the templates in the paper runtime runbook.

## Non-Goals

- No automatic installation into `~/Library/LaunchAgents` or systemd user units.
- No automatic service start.
- No real-money trading.
- No secrets in generated templates.

## Implementation Details

- Add `render_launchd_plist`.
- Add `render_systemd_unit`.
- Add `write_supervisor_templates`.
- Extend `python -m trading_app.runtime.ops` with:
  - `--write-supervisor-dir`
  - `--working-dir`
  - `--env-file`
- Update runtime exports and tests.
- Update the operator runbook with a cautious process-supervision section.

## Acceptance Criteria

- Templates contain the existing paper runtime startup command.
- Templates keep `--monitor-only-dry-run-first`.
- Templates reference the local env file path but do not contain Alpaca secret values.
- CLI writes both template files.
- Tests, lint, and format checks pass.

## Verification

- `pytest tests/test_runtime_ops.py`
- `pytest`
- `ruff check`
- `ruff format --check`
