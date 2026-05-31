# Milestone 68 Plan: One-Command Post-Run Review

## Summary

Create a single post-run review command that runs the required local evidence
checks after a supervised Alpaca paper session. The operator should not have to
manually remember every post-run command in the right order.

The command does not replace the external requirement for a real credentialed
paper session. It reviews and packages the artifacts produced by that session.

## Key Changes

- Add runtime post-run review models:
  - `RuntimePostRunReviewStep`
  - `RuntimePostRunReviewReport`
- Add `RuntimePostRunReviewer`.
- Add CLI:

```bash
python -m trading_app.runtime.review --output-dir data/runtime
```

- The review flow:
  - analyzes soak evidence
  - captures an Alpaca paper broker statement, unless `--statement` supplies a
    saved JSON/CSV statement
  - reconciles broker statement to the persisted paper ledger
  - runs the secret scanner
  - runs the completion audit
  - builds the operator evidence bundle
  - writes a Markdown review report
- Persist latest review evidence under:
  - `data/runtime/state/latest-post-run-review-report.json`
  - `data/runtime/state/latest-post-run-review-report-path.json`
  - `data/runtime/journal/post-run-reviews.jsonl`

## Test Plan

- Complete fixture artifacts plus a fake broker pass post-run review.
- Missing artifacts fail post-run review with actionable steps.
- A mismatched supplied statement fails post-run review.
- CLI returns `0` for clean fixture review and `1` for incomplete review.
- Review text/Markdown do not leak credential values.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`

## Assumptions

- Default statement capture uses Alpaca paper credentials only.
- `--statement` lets the operator review a previously saved broker statement.
- This command does not start or stop the always-on runtime.
- Live-money trading remains unreachable.
