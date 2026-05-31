# Milestone 43 Plan: Promotion Evidence Caveats

## Summary

Strengthen nightly learning recommendations so model promotion advice cites the evidence the functional spec requires: risk, drawdown, turnover, cost assumptions, fold coverage, and data caveats.

## Scope

- Keep AI/model recommendations advisory only.
- Do not change active model promotion rules.
- Expand `PromotionRecommendation.evidence` with:
  - aggregate excess return;
  - aggregate max drawdown;
  - average turnover;
  - fold count;
  - slippage/cost assumption;
  - feed/data-quality caveats.
- Add tests proving recommendations include these evidence fields.

## Verification

- `.venv/bin/python -m pytest tests/test_learning.py`
- `.venv/bin/ruff check`
- `.venv/bin/ruff format --check`
