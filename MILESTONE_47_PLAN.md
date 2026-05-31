# Milestone 47 Plan: Strategy Evaluation Fault Containment

## Summary

Keep the always-on paper runtime alive when scheduled strategy evaluation fails. Historical data fetches, strategy target generation, or order planning can fail in real conditions; those failures must block orders for that cycle, surface as runtime evidence, and allow a later retry after the transient issue clears.

## Scope

- Wrap scheduled strategy evaluation in runtime-level exception handling.
- Record strategy failures as blocking runtime events.
- Submit zero paper orders on strategy-evaluation failure.
- Do not mark the daily strategy date complete when evaluation fails before producing a result.
- Preserve current behavior for stale prices, reconciliation blocks, operator pause, and paper kill switch.
- Add regression coverage proving a failed evaluation does not crash and a later cycle can retry successfully.

## Verification

- Runtime unit tests for strategy-evaluation failure and retry.
- Targeted runtime pytest coverage.
- Full pytest and Ruff verification.
