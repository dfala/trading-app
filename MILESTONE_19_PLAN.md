# Milestone 19 Plan: Functional Operator Dashboard Productization

## Summary

Turn the dashboard from a mostly static proof screen into a functional operator cockpit for the paper runtime. The dashboard should make the paper/live boundary obvious, show live runtime evidence, surface latest-price freshness, expose controls locally, and refresh important fields from the runtime snapshot API.

Critical boundary: the dashboard remains local-first and paper-only. It must not expose live-money actions.

## Key Changes

- Add stronger dashboard sections:
  - Paper boundary
  - Latest prices
  - Runtime proof
  - Reports and learning
- Add browser-side refresh for key visible fields from `/api/snapshot`.
- Persist the latest runtime snapshot every runtime cycle.
- Keep the dashboard server local-only by default.
- Update the operator runbook only through existing safe control paths.

## Dashboard Requirements

- Show runtime mode and broker.
- Show paper-only boundary and disabled live readiness.
- Show estimated equity, cash, realized P&L, open orders, and reconciliation.
- Show latest price freshness, feed, warning, and symbol price tape.
- Show runtime status, price refresh evidence, broker sync evidence, submitted orders, and applied fills.
- Show report and nightly learning status.
- Show operator controls for pause, resume, paper kill switch, reconciliation, and report generation.
- Continue showing health, incidents, alerts, model arena, positions, fills, rejected signals, and live-readiness gate.
- Refresh key fields from `/api/snapshot` without a full page reload.

## Server Requirements

- `create_dashboard_server()` rejects non-local hosts by default.
- Public binding is possible only with explicit `allow_public=True` for future controlled scenarios.
- The CLI keeps local-only binding by default.

## Test Plan

- Dashboard HTML renders the new sections and data-binding attributes.
- Interactive dashboard script updates visible fields from `/api/snapshot`.
- Snapshot API still serializes dashboard data.
- Server rejects public hosts unless explicitly allowed.
- Runtime cycles persist `latest-runtime-snapshot.json`.

## Verification

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`
- Browser verification of the local dashboard render.

## Assumptions

- The dashboard is an operator cockpit, not a trade-entry screen.
- Local controls remain paper-runtime controls only.
- The visual direction remains dark, precise, neon-accented, and non-casino-like.
