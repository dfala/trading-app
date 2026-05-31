# Milestone 27 Plan: Research Evidence Evaluation Runner

## Summary

Add a reproducible research evaluation runner that turns implemented strategy cards into backtest evidence and champion/challenger comparisons. This makes strategy research more disciplined: implemented candidates must produce evidence before any promotion workflow can even begin.

## Key Changes

- Add a `trading_app.research` package.
- Add `StrategyResearchEvaluationRunner`.
- Convert strategy definitions into model registry records.
- Run implemented strategies through `BacktestRunner`.
- Convert backtest results into `ModelEvidenceRecord` entries.
- Compare each candidate against the active champion with `ModelArena`.
- Skip research-only idea cards that do not have implementation support yet.
- Keep active model unchanged.

## Non-Goals

- Do not promote any candidate.
- Do not change the active paper model.
- Do not submit paper orders.
- Do not add live-money authority.
- Do not require Alpaca credentials or network calls.

## Acceptance Criteria

- The active monthly sector momentum champion produces evidence.
- The implemented trend-following challenger produces evidence.
- Research idea cards are reported as skipped, not silently ignored.
- Candidate comparisons include after-cost metrics and benchmark-relative scoring.
- The active model remains unchanged.
- The report is JSON-serializable.

## Verification

- Research evaluation tests.
- Strategy catalog tests.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`
