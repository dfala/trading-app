# Milestone 48 Plan: Partial Order-Submission Failure Evidence

## Summary

Make partial broker-submission failures explicit and accurately counted. If one paper order is accepted and a later order in the same rebalance fails, the runtime must stop submitting the remaining rebalance orders, preserve the submitted-order count, and surface the broker-submission failure as blocking evidence.

## Scope

- Pass runtime event collection into scheduled strategy order planning.
- Catch broker-submission failures at each planned paper order.
- Record a blocking broker-order-submission event with symbol and side evidence.
- Return the number of paper orders already submitted before the failure.
- Stop the remaining rebalance after the first broker-submission failure.
- Add regression coverage for a two-order rebalance where the second submission fails.

## Verification

- Runtime unit test for partial order-submission failure.
- Targeted runtime pytest coverage.
- Full pytest and Ruff verification.
