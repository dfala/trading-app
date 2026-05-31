# Milestone 53 Plan: Broker And Active Model Visibility

## Summary

Make the operator dashboard clearer about two questions that matter during an always-on paper session: whether broker sync is currently healthy, and which model has paper-trading authority. The dashboard already shows broker provider, reconciliation, and runtime proof fields, but the operator should not need to infer broker connection state or active model identity from surrounding details.

## Scope

- Add dashboard fields for broker connection status.
- Add dashboard fields for active paper model key.
- Keep trading authority labeled as daily-close only.
- Refresh those fields from `/api/snapshot` in the browser-side update loop.
- Preserve the paper-only boundary and local-only controls.

## Verification

- Dashboard HTML includes broker/model proof fields.
- Interactive refresh script updates those fields from runtime snapshots.
- Full pytest and Ruff verification remain clean.
