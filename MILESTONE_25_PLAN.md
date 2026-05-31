# Milestone 25 Plan: Full-Day Soak Evidence Analyzer

## Summary

Add a post-run verifier that inspects persisted runtime artifacts and determines whether a supervised Alpaca paper session actually proves the completion-spec requirement for a full U.S. market day plus overnight soak.

This does not replace the real credentialed run. It gives us a strict way to review that run once the local `data/runtime/` evidence exists.

## Key Changes

- Add soak evidence report models.
- Add a `RuntimeSoakEvidenceAnalyzer` that reads local runtime journals and state.
- Verify:
  - enough runtime duration
  - regular-market cycle coverage
  - off-hours and overnight cycle coverage
  - market-hours and off-hours polling gaps
  - no submitted orders outside the approved daily-close window
  - daily report evidence
  - nightly learning evidence
  - latest dashboard snapshot evidence
  - final health state
  - captured runtime events
- Add CLI:
  - `python -m trading_app.runtime.soak --output-dir data/runtime`
- Persist latest soak evidence report under local runtime state and journal folders.
- Update the operator runbook with the post-soak review command.

## Non-Goals

- No fake claim that a real credentialed 24-hour run occurred.
- No live trading.
- No broker network calls during tests.
- No automatic model promotion.

## Acceptance Criteria

- A complete fixture soak passes.
- Too-short soak evidence fails.
- Off-schedule paper orders fail.
- Missing dashboard snapshot, report, learning, or health evidence fails.
- Report output is operator-readable and does not expose credentials.
- Soak evidence is persisted under ignored runtime folders.

## Verification

- Soak evidence analyzer unit tests.
- Runtime persistence tests.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`
