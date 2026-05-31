# Milestone 40 Plan: Daily Bar Integrity Guardrails

## Summary

Strengthen the market-data trust layer by rejecting structurally impossible daily bars at the schema boundary and warning on zero-volume daily bars in data-quality reports.

## Scope

- Validate `DailyBar` OHLC relationships:
  - high must be at least open, low, and close;
  - low must be no greater than open, high, and close.
- Validate daily bar timestamps:
  - the timezone-aware bar timestamp must match the declared trading date.
- Add a `zero_volume` data-quality warning for daily bars.
- Preserve the current distinction:
  - schema rejects impossible bars;
  - data-quality report warns on suspicious but representable bars.

## Verification

- Schema tests for OHLC and timestamp mismatch rejection.
- Data-quality tests for zero-volume warnings.
- Full verification with pytest and Ruff.
