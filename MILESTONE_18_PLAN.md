# Milestone 18 Plan: Credentialed Paper Runtime Validation And First Full-Day Soak

## Summary

Prove the current Alpaca paper runtime end to end before adding more product surface or strategy complexity. This milestone adds a supervised validation sequence that runs preflight, a monitor-only dry run, an optional scheduled-order dry run, and an optional soak loop while persisting a single operator-readable validation report.

Critical boundary: validation is still Alpaca paper only. The safe default does not allow paper orders during the soak and does not enable real-money trading.

## Key Changes

- Add typed validation artifacts:
  - `RuntimeValidationStep`
  - `RuntimeValidationReport`
- Add `AlpacaPaperRuntimeValidation`.
- Add CLI:
  - `python -m trading_app.runtime.validation`
- Persist validation reports under ignored local runtime state:
  - `data/runtime/state/latest-validation-report.json`
  - `data/runtime/journal/validation.jsonl`
- Isolate dry-run local state under per-validation subfolders so the monitor-only kill switch does not contaminate the explicit scheduled-order dry-run evidence.

## Validation Sequence

1. Run offline preflight.
2. Stop immediately if preflight has failures.
3. Run monitor-only dry run.
4. Prove zero paper orders were submitted in monitor-only mode.
5. Optionally run the scheduled-order dry run with explicit operator opt-in.
6. Optionally run a supervised soak for a configured number of cycles.
7. During soak, apply the paper kill switch unless the operator explicitly allows paper orders.
8. Persist a validation report with proof fields:
   - latest prices refreshed
   - latest prices fresh
   - broker synced
   - dashboard snapshot serialized
   - daily report written
   - nightly learning ran
   - orders submitted
   - soak cycle count

## CLI

Safe default:

```bash
python -m trading_app.runtime.validation
```

Explicit scheduled-order check:

```bash
python -m trading_app.runtime.validation --include-scheduled-order-check
```

Monitor-only soak:

```bash
python -m trading_app.runtime.validation --soak-cycles 390 --soak-sleep-seconds 60
```

Explicit paper-order soak:

```bash
python -m trading_app.runtime.validation \
  --include-scheduled-order-check \
  --soak-cycles 390 \
  --soak-sleep-seconds 60 \
  --allow-paper-orders-during-soak
```

## Test Plan

- Validation fails before dry-run/runtime construction when preflight fails.
- Monitor-only validation submits zero paper orders and persists evidence.
- Explicit scheduled-order validation uses isolated state and can submit paper orders.
- Soak validation applies paper kill switch by default and blocks orders.
- Report and learning proof can be required when a soak cycle covers the nightly window.
- Validation text does not leak credential values.
- Persistence recovers the latest validation report.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`

## Assumptions

- Trading remains U.S.-listed stocks and U.S.-listed ETFs only.
- Runtime remains Alpaca paper only.
- The default validation command is safe to run without placing paper orders.
- Network access and real Alpaca credentials are operator-provided outside automated tests.
