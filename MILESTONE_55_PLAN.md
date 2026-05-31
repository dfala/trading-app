# Milestone 55 Plan: Daily Report Active Model Dossier

## Summary

Make the daily report explain the active paper model, not just the orders. The dashboard now surfaces the active model card, but the daily Markdown report is the durable audit artifact operators review after market close. This milestone adds the same structured model hypothesis and authority to that report so the evidence packet answers what model was active, what it was trying to do, what data it required, what logic it used, and what failure modes were known.

## Scope

- Add optional active strategy definition evidence to `DailyTradingReport`.
- Allow `DailyReportGenerator.build()` to receive the active strategy definition.
- Include active model evidence in report metadata and AI governance summaries.
- Render an `Active Model Dossier` section in daily Markdown reports.
- Wire the always-on runtime daily report path to pass the active paper strategy definition.
- Keep the active model immutable; this is reporting only, not model promotion.

## Verification

- Daily-report tests prove the active model definition is captured and rendered.
- Runtime/dashboard tests keep passing with the expanded report schema.
- Full pytest and Ruff verification remain clean.
