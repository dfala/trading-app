# Milestone 46 Plan: Current-Cycle Order Guards

## Summary

Prevent scheduled paper orders from using stale in-memory evidence when the current cycle cannot refresh market data or sync broker state. The always-on runtime already records those failures, but the order path must also be explicitly gated on successful current-cycle price refresh and broker sync.

## Scope

- Clear cached latest prices when the current latest-price refresh fails.
- Skip scheduled strategy evaluation when the current cycle did not refresh prices.
- Skip scheduled strategy evaluation when the current cycle did not sync broker state.
- Preserve existing stale-price behavior: stale or missing latest-price snapshots still mark the cycle degraded and block orders.
- Add regression tests proving cached prices and broker-sync failures cannot submit paper orders.

## Verification

- Runtime unit tests for market-data failure and broker-sync failure.
- Targeted runtime pytest coverage.
- Full pytest and Ruff verification.
