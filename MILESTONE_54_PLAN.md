# Milestone 54 Plan: Active Model Explanation Panel

## Summary

Make the dashboard explain the active paper model in operator-facing language. The app already has structured strategy definitions with hypothesis, cadence, signal logic, sizing, exits, failure modes, and AI role. This milestone surfaces that existing truth in the dashboard so the operator can answer: what is the model trying to do, why is it allowed to act, and what can go wrong?

## Scope

- Add active strategy definition data to dashboard snapshots.
- Populate active strategy definition from the real always-on runtime strategy.
- Populate demo dashboard snapshots from the same strategy-card source.
- Render an active model explanation panel with:
  - model name and authority
  - hypothesis
  - cadence, benchmark, universe
  - signal, sizing, and exit logic
  - key failure modes
  - AI role as copilot/reviewer only
- Refresh the active model explanation from `/api/snapshot`.

## Verification

- Dashboard snapshot API includes active strategy definition data.
- Dashboard rendering tests prove the explanation fields exist.
- Interactive dashboard tests prove the browser refresh path updates the model explanation.
- Full pytest and Ruff verification remain clean.
