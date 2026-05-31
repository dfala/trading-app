# Milestone 24 Plan: Operator Startup Profile And Environment Template

## Summary

Make the always-on paper app easier to start, stop, and inspect from a clean local machine. This milestone turns the current collection of runtime commands into a documented local operations profile with an environment template, artifact layout, and a one-command startup path that can run monitor-only dry-run validation before entering the always-on loop.

## Key Changes

- Add a safe `.env.example` with placeholder Alpaca paper variables and local runtime defaults.
- Add a runtime operations profile model that describes:
  - startup command
  - preflight command
  - monitor-only dry-run command
  - shutdown steps
  - dashboard URL
  - runtime artifact directories
  - process supervision recommendation
- Add a small CLI to render the operations profile.
- Add an optional `--monitor-only-dry-run-first` startup flag to `run_alpaca_paper`.
- Update the operator runbook with the one-command startup path and artifact layout.
- Add tests proving the profile is local-only, secrets are not present, artifact paths are under ignored runtime folders, and the runbook covers the profile.

## Non-Goals

- No production deployment.
- No public dashboard binding.
- No background daemon installation.
- No real Alpaca network calls in tests.
- No live-money trading path.

## Acceptance Criteria

- Operator has one recommended startup command.
- Operator has one shutdown path.
- Environment template exists without secret values.
- Runtime artifact locations are documented and test-covered.
- Dashboard remains local-only by default.
- The app can still be started without manual command chaining when the operator chooses the dry-run-first flag.

## Verification

- Runtime operations profile tests.
- Existing preflight/runtime CLI tests.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`
