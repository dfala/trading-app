# Milestone 66 Plan: Paper Runtime Evidence Bundle

## Summary

Create a single operator-facing evidence bundle that pulls together the runtime
artifacts needed to judge whether the paper app is ready for functional review.
The project already writes preflight, dry-run, validation, soak, secret scan,
statement reconciliation, dashboard, health, daily report, learning, and
completion-audit artifacts. This milestone gives the operator one dossier that
indexes those artifacts and makes missing evidence obvious.

This is not a substitute for real Alpaca paper evidence. It is the review packet
that should be generated after that evidence exists.

## Key Changes

- Add `RuntimeEvidenceBundleItem` and `RuntimeEvidenceBundleReport` models.
- Add a `RuntimeEvidenceBundleBuilder` that reads local runtime artifacts and
  creates a statused evidence inventory.
- Render a Markdown dossier under `data/runtime/reports/`.
- Persist the latest bundle report under:
  - `data/runtime/state/latest-evidence-bundle-report.json`
  - `data/runtime/state/latest-evidence-bundle-report-path.json`
  - `data/runtime/journal/evidence-bundles.jsonl`
- Add CLI:

```bash
python -m trading_app.runtime.evidence --output-dir data/runtime
```

- Update the operator runbook and functional spec to make the evidence bundle
  the final review packet after the completion audit.

## Test Plan

- Complete fixture evidence produces a passed, ready-for-review bundle.
- Missing artifacts produce a failed bundle with missing required evidence.
- CLI returns `0` for complete evidence and `1` for incomplete evidence.
- Markdown and JSON outputs do not leak credential values.
- Full verification:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check`
  - `.venv/bin/ruff format --check`

## Assumptions

- The bundle is an index and review dossier, not an independent proof engine.
- The functional completion audit remains the stricter requirement-by-requirement
  proof.
- Real external evidence still requires Alpaca paper credentials and a real run.
