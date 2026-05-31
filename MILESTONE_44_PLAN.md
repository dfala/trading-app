# Milestone 44 Plan: Nightly Learning Recommendation Memo

## Summary

Make nightly learning output reviewable as a human-readable recommendation memo. The functional spec requires AI-assisted recommendations to cite evidence, show confidence, separate interpretation from proposed action, and remain reviewable before action.

## Scope

- Add confidence to `PromotionRecommendation`.
- Render `NightlyLearningRun` as a Markdown recommendation memo.
- Separate evidence, interpretation, and proposed action in the memo.
- Persist the latest learning memo path.
- Recover the memo path after restart.
- Surface the memo path in runtime and dashboard snapshots.
- Keep recommendations advisory only and preserve the active-model lock.

## Verification

- Learning rendering tests.
- Runtime persistence tests for JSON plus Markdown learning artifacts.
- Dashboard/runtime snapshot tests for memo path visibility.
- Full pytest and Ruff verification.
