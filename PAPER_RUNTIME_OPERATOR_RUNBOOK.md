# Alpaca Paper Runtime Operator Runbook

Last updated: 2026-05-31

This runbook is for Alpaca paper trading only. It does not authorize live-money trading.

## Operating Boundaries

- Trade U.S.-listed stocks and U.S.-listed ETFs only.
- Do not trade options, futures, crypto, forex, or non-U.S. markets.
- Keep live trading disabled.
- Keep the dashboard bound to `127.0.0.1`, `localhost`, or `::1`.
- Treat `IEX` data as development-grade.
- Intraday monitoring is allowed; intraday strategy authority is not.
- The active strategy may submit paper orders only on the approved daily-close schedule.
- Enter ticker symbols in uppercase. Startup commands validate symbol casing as
  supplied and do not silently normalize lowercase input.

## Required Local Credentials

Set Alpaca paper credentials in the shell that will run the runtime:

```bash
export ALPACA_API_KEY="..."
export ALPACA_SECRET_KEY="..."
```

The values must be real non-blank Alpaca paper credential values. Empty strings
or whitespace-only values are treated as missing and will fail preflight and
client construction.

Never commit credentials, paste them into reports, or put them in Markdown files.

Use `.env.example` as the safe template for local setup. Replace placeholder values
only in your local shell or local secret manager; do not write real credential values
into tracked Markdown files.
The operations-readiness audit verifies the active template assignments still
use placeholders and will fail if a real-looking credential assignment is added
to the template.

Do not set Alpaca endpoint overrides to live endpoints. If an override such as
`APCA_API_BASE_URL`, `ALPACA_API_BASE_URL`, or `ALPACA_BASE_URL` is needed during
this paper phase, it must point to `https://paper-api.alpaca.markets`; live
endpoint values fail preflight and broker construction, even when quoted by a
local env-file loader.

## Dependency Installation

Use Python 3.12 or newer. Do not downgrade the runtime to an older system Python.

Recommended local setup from the project root:

```bash
python --version
uv sync --dev
uv run pytest
uv run ruff check
```

If `uv` is not installed, install `uv` first, then rerun the commands above.
The project is intentionally pinned to Python `>=3.12` in `pyproject.toml` and
uses `uv.lock` for repeatable local dependency resolution.

Keep Alpaca paper credentials outside tracked files. Use shell exports or a
local-only env file referenced by your process supervisor template.
Local env files such as `.env`, `.env.local`, `.env.paper`, `.env.*.local`, and
`*.local.env` are ignored by git; `.env.example` stays tracked as the safe
placeholder template.

## Recommended One-Command Startup

The easiest local startup path from the project root is:

```bash
uv run dev
```

or, if you prefer Make-style commands:

```bash
make dev
```

The shortcut loads `.env` when present, leaves already-exported shell values in
place, honors the `TRADING_APP_*` runtime defaults from that file, runs the
required monitor-only dry run first, and then starts the always-on Alpaca paper
runtime only if the safety checks pass. The Python backend stays on
`http://127.0.0.1:8765`; the operator dashboard is the Next.js service at
`http://127.0.0.1:3003`. If the backend port is already in use, the shortcut
automatically tries the next local port and prints the URL it selected.

The equivalent explicit supervised startup path is:

```bash
python -m trading_app.runtime.run_alpaca_paper --monitor-only-dry-run-first
```

This single command runs preflight, runs a monitor-only dry run with paper orders
blocked, and then starts the always-on Alpaca paper runtime only if the safety
checks pass.

To print the current local operations profile:

```bash
python -m trading_app.runtime.ops
```

## Preflight

Run the offline startup gate before every supervised session:

```bash
python -m trading_app.runtime.preflight
```

Do not continue if preflight reports `failed`.

Review warnings before continuing. `IEX` warnings are expected for development-grade paper runs, but they must remain visible.

## Monitor-Only Dry Run

Run a one-cycle smoke test with paper orders blocked:

```bash
python -m trading_app.runtime.dry_run
```

Expected result:

- Preflight can start.
- Runtime constructs after preflight.
- Paper kill switch is enabled for the dry run.
- Latest prices refresh.
- Broker sync completes.
- Zero paper orders are submitted.
- Health report is generated.
- Dashboard snapshot serializes.
- Evidence is persisted under `data/runtime/`.

Do not start a longer runtime session if the dry run reports `failed`.

## Supervised Validation Sequence

Before the first full-day paper session, run the consolidated validation command:

```bash
python -m trading_app.runtime.validation
```

Expected result:

- Offline preflight passes or passes with reviewed warnings.
- Monitor-only dry run submits zero paper orders.
- Latest-price refresh evidence is captured.
- Broker sync evidence is captured.
- Dashboard snapshot evidence is captured.
- Validation evidence is persisted under `data/runtime/state/` and `data/runtime/journal/`.
- A Markdown validation report is written under `data/runtime/reports/`.

The validation command may report a warning when a full-day soak was not run. That warning is acceptable for the first smoke pass; it is a reminder that a longer supervised run is still required.

Review the Markdown validation report before starting or extending a soak. It is
the operator-facing evidence summary for preflight, dry run, broker sync,
latest prices, dashboard serialization, report generation, learning, and order
counts.

To explicitly test the scheduled paper-order path:

```bash
python -m trading_app.runtime.validation --include-scheduled-order-check
```

Use this only when paper orders are acceptable and the current market schedule is understood.

## Sunday And Market-Closed Validation

When U.S. markets are closed, the operator can still prove the runtime is safe
and connected. The goal is not a green functional-completion report; the goal is
evidence that the app stays paper-only, reaches Alpaca paper, blocks trading on
stale data, and records review artifacts.

From the project root, load the local `.env` file into the current shell:

```bash
set -a
. ./.env
set +a
```

Run the Sunday-safe checks:

```bash
python -m trading_app.runtime.ops --audit --output-dir data/runtime
python -m trading_app.runtime.lifecycle --output-dir data/runtime
python -m trading_app.runtime.dashboard_visual --output-dir data/runtime
python -m trading_app.runtime.schedule --output-dir data/runtime
python -m trading_app.runtime.guardrails --output-dir data/runtime
python -m trading_app.runtime.fills --output-dir data/runtime
python -m trading_app.runtime.data_quality --output-dir data/runtime
python -m trading_app.runtime.governance --output-dir data/runtime
python -m trading_app.runtime.broker_history \
  --output-dir data/runtime \
  --symbols XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY,SPY \
  --limit 100
python -m trading_app.runtime.validation --output-dir data/runtime
python -m trading_app.runtime.security --output-dir data/runtime
python -m trading_app.runtime.completion --output-dir data/runtime
```

Expected Sunday result:

- Operations, lifecycle, dashboard visual, schedule, order-guardrail, fill-sync,
  data-quality, model-governance, broker-history, and secret-scan audits should
  pass.
- Validation may exit with code `1` because latest prices are stale while the
  market is closed. That is acceptable only when the report still shows broker
  sync passed, dashboard snapshot serialized, zero orders submitted, and stale
  prices blocked new paper orders.
- Completion audit should remain incomplete until market-hours validation,
  scheduled paper-order evidence, real fill/restart evidence, after-close daily
  report, nightly learning, statement reconciliation, full-day soak,
  credentialed-session proof, evidence bundle, operator signoff, and final
  acceptance are complete.

For Sunday May 31, 2026, Alpaca clock should show the next regular U.S. market
open as Monday June 1, 2026 at 09:30 ET and next close as Monday June 1, 2026 at
16:00 ET. Do not try to force a Sunday order to make completion green.

## Monday Market-Hours Procedure

Use this procedure on Monday June 1, 2026. It is the first real market-hours
proof step after Sunday setup.

Before 09:30 ET:

```bash
set -a
. ./.env
set +a
python -m trading_app.runtime.preflight --output-dir data/runtime --json
python -m trading_app.runtime.dry_run --output-dir data/runtime --json
python -m trading_app.runtime.security --output-dir data/runtime --json
```

Success criteria before market open:

- Preflight can start.
- Dry run reaches Alpaca paper, syncs broker state, serializes dashboard state,
  and submits zero orders.
- Any stale-price warning is understood as pre-market/off-hours behavior.
- Secret scan reports zero findings.

After 09:30 ET, while the regular U.S. session is open:

```bash
python -m trading_app.runtime.validation --output-dir data/runtime --json
python -m trading_app.runtime.broker_history \
  --output-dir data/runtime \
  --symbols XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY,SPY \
  --limit 100 \
  --json
```

Market-hours success criteria:

- Latest prices refresh from Alpaca and record `latest_price_source=alpaca`.
- Broker sync records provider `alpaca-paper`.
- Dashboard snapshot serializes from the runtime provider.
- Monitor-only validation submits zero paper orders.
- No live-money, margin, short, option, crypto, or non-U.S. instrument path is
  used.
- If IEX data is delayed or stale, orders remain blocked and the warning remains
  visible. Do not override that guardrail.

To start the supervised always-on runtime:

```bash
uv run dev
```

Keep the Python backend/API local at:

```text
http://127.0.0.1:8765
```

Use the Next.js operator dashboard at:

```text
http://127.0.0.1:3003
```

After 16:00 ET, wait for the regular close path, daily report, and nightly
learning evidence. Then run:

```bash
python -m trading_app.runtime.review --output-dir data/runtime
python -m trading_app.runtime.completion --output-dir data/runtime
python -m trading_app.runtime.evidence --output-dir data/runtime
python -m trading_app.runtime.security --output-dir data/runtime
```

Post-close success criteria:

- Daily report is generated after the regular market close.
- Nightly learning runs after the daily report and remains recommendation-only.
- Broker order history matches local submissions and fills.
- Broker statement reconciliation is clean.
- Dashboard consistency and visual-readiness pass.
- Completion audit has no `failed` or `missing` items. Any remaining
  `external_required` item must be tied to a known unperformed step, not a hidden
  error.
- No secrets are found in runtime artifacts.

To run a monitor-only soak:

```bash
python -m trading_app.runtime.validation --soak-cycles 390 --soak-sleep-seconds 60
```

The soak keeps the paper kill switch enabled unless `--allow-paper-orders-during-soak` is explicitly provided.

## Post-Soak Evidence Review

The preferred post-run review path is the single review command:

```bash
python -m trading_app.runtime.review --output-dir data/runtime
```

When using saved statement and order-history files:

```bash
python -m trading_app.runtime.review \
  --output-dir data/runtime \
  --statement path/to/broker-statement.json \
  --broker-order-history path/to/broker-order-history.json
```

When reviewing Next build artifacts, browser captures, or local supervisor logs,
include those paths in the one-command review secret scan:

```bash
python -m trading_app.runtime.review \
  --output-dir data/runtime \
  --include-secret-scan-path path/to/next-dashboard-capture.html \
  --include-secret-scan-path path/to/runtime.log
```

Expected result:

- Operations readiness is audited: startup path, dashboard binding, artifact
  layout, env template, runbook, and supervisor templates are checked for a
  paper-only local posture.
- Lifecycle drill audit confirms startup evidence exists, operator controls
  were exercised, emergency-stop controls were tested, and shutdown procedures
  are documented.
- Soak evidence is analyzed, and warning-status soak evidence remains a warning
  in the post-run review until an operator reviews it.
- Restart recovery audit confirms persisted order/fill journals can be
  rehydrated without duplicate submissions or fills.
- A current Alpaca paper statement snapshot is captured unless `--statement`
  supplies a saved statement file.
- Broker statement reconciliation runs against the persisted paper ledger.
- Runtime artifacts are scanned for credential leaks.
- Explicitly included dashboard/log artifacts are scanned for credential leaks.
- The saved broker statement source used for reconciliation is scanned for
  credential leaks, even when it lives outside `data/runtime/`.
- Model-governance audit confirms nightly learning remained advisory, active
  model keys did not change, recommendations require manual review, and no
  model gained authority without approval evidence.
- Completion and evidence-bundle checks confirm nightly learning ran after the
  daily report and stayed recommendation-only.
- Completion and evidence-bundle checks confirm the daily report is a persisted
  Markdown artifact generated after the regular market close.
- Schedule-guardrail audit confirms strategy authority stays daily-close only
  and does not run during regular hours, before the trade window, twice in the
  same day, or on weekends.
- Order-guardrail audit confirms stale or missing prices, risk rejection, dirty
  reconciliation, paper kill switch, and operator pause all block paper orders.
- Fill-sync audit confirms partial broker fills, repeat syncs, second partial
  fills, and restarted syncs update the internal ledger exactly once.
- Data-quality audit confirms fresh SIP data passes, IEX/free data is labeled
  development-grade, and stale, missing, duplicate, mixed-feed, and lookahead
  data are caught before trust.
- Broker order-history audit confirms Alpaca paper order history matches
  persisted local submissions and fills.
- Credentialed-session proof ties preflight, validation, runtime snapshot,
  dashboard snapshot, latest-price provenance, soak evidence, statement
  reconciliation, broker order-history, and secret scan evidence to one Alpaca
  paper account without persisting credential values.
- Evidence coherence checks confirm artifact timing, Alpaca provider/source
  provenance, broker order-history, and local order/fill evidence align across
  the reviewed paper session.
- Dashboard consistency confirms operator controls, alerts, and health state
  match the persisted runtime snapshot.
- Dashboard visual-readiness confirms the Next dashboard handoff and persisted
  snapshot expose the paper boundary, runtime surfaces, controls, alerts,
  data-quality evidence, active model, live-readiness gate, financial visuals,
  and responsive layout structure.
- Functional completion audit runs.
- Artifact integrity manifest hashes the reviewed local evidence files.
- The operator evidence bundle is generated.
- A Markdown post-run review is written under `data/runtime/reports/`.

Exit code `0` means the local post-run review passed. Exit code `1` means at
least one required evidence step failed or is missing. The sections below remain
useful when you want to run or debug an individual review step.

After a supervised full-day plus overnight run, analyze the persisted evidence:

```bash
python -m trading_app.runtime.soak --output-dir data/runtime
```

Expected result:

- Soak duration meets the configured minimum.
- Regular-market, off-hours, and overnight cycle evidence is present.
- Polling gaps stay within the configured market-hours and off-hours limits.
- Every persisted runtime cycle shows latest-price refresh evidence.
- Every persisted runtime cycle shows broker sync evidence.
- Runtime warning and error event counts are visible; error-severity runtime
  events fail the soak evidence review until they are investigated.
- No paper orders were submitted outside the approved daily-close window.
- Daily report evidence is present.
- Nightly learning evidence is present.
- Latest runtime dashboard snapshot evidence is present.
- Final health is not `critical`.

This command does not prove a real run happened by itself. It reviews the
artifacts produced by the real supervised runtime session.

## Post-Run Secret Scan

After every credentialed paper session, scan local runtime artifacts for leaked
credential values:

```bash
python -m trading_app.runtime.security --output-dir data/runtime
```

When you collect Next dashboard captures, local supervisor logs, or other
session artifacts outside `data/runtime`, include them explicitly:

```bash
python -m trading_app.runtime.security \
  --output-dir data/runtime \
  --include-path path/to/next-dashboard-capture.html \
  --include-path path/to/runtime.log
```

Expected result:

- The scan passes.
- No Alpaca API key or secret value appears in JSON, JSONL, Markdown, HTML, log,
  or text artifacts.
- Quoted or whitespace-padded local credential values are normalized before
  matching, so artifacts are scanned for the real credential value.
- Explicitly included dashboard/log paths are scanned alongside `data/runtime`.
- Findings, if any, name the file and secret variable but do not print the secret
  value.
- The latest secret scan report is persisted under `data/runtime/state/` and the
  scan journal is appended under `data/runtime/journal/`.

If the scan fails, stop the runtime, remove or quarantine the leaked artifacts,
rotate the affected Alpaca paper credential, and rerun preflight before starting
again.

## Post-Run Broker Statement Reconciliation

After a credentialed paper session, capture a local broker statement snapshot
under `data/runtime/statements/`:

```bash
python -m trading_app.paper.capture_statement \
  --output-dir data/runtime/statements
```

Then compare it with the latest persisted paper runtime snapshot:

```bash
python -m trading_app.paper.reconcile_statement \
  --runtime-dir data/runtime \
  --statement data/runtime/statements/broker-statement-STATEMENT_ID.json
```

The statement file can be the captured JSON matching `BrokerStatementSnapshot`,
or a simple CSV with one `record_type=account` row and optional
`record_type=position` rows.
The CSV account row should include `statement_id`, `as_of`, `provider`, `cash`,
and optionally `account_id` and `source`. Position rows should include `symbol`,
`quantity`, `average_entry_price`, and optionally `market_value` and
`current_price`.

Expected result:

- The command writes a Markdown reconciliation report under
  `data/runtime/reports/`.
- The reconciliation report records the saved statement source file, and the
  SHA-256 fingerprint captured at reconciliation time.
- The artifact-integrity manifest fingerprints that raw statement source again
  and fails if it no longer matches the reconciliation-time fingerprint.
- Exit code `0` means statement cash and position quantities match the latest
  local paper ledger within tolerance.
- Exit code `1` means mismatches or missing evidence require review.
- The command does not mutate ledger state.
- The report remains paper/research-only evidence and is not filing-grade tax
  accounting.

## Functional Completion Audit

After preflight, dry run, full-day plus overnight soak, reporting, learning, and
secret scanning have all produced evidence, confirm the local operating posture:

```bash
python -m trading_app.runtime.ops --audit --output-dir data/runtime
```

Expected result:

- Startup uses the Alpaca paper runtime and `--monitor-only-dry-run-first`.
- Dashboard binding is local-only.
- Runtime artifacts are under ignored local `data/runtime/` paths.
- Dependency setup is pinned to Python 3.12 or newer and uses `uv sync --dev`.
- `.env.example` contains placeholders and keeps live trading disabled.
- The operator runbook includes startup, shutdown, review, and recovery steps.
- Supervisor templates render without credential values.

Then confirm the startup/shutdown and operator-control lifecycle was exercised:

```bash
python -m trading_app.runtime.lifecycle --output-dir data/runtime
```

Expected result:

- The documented startup command is the supervised Alpaca paper runtime.
- Runtime cycle or snapshot evidence exists.
- Pause, resume, paper kill switch on/off, force reconciliation, and report
  generation controls were persisted.
- Force reconciliation and report generation produced local evidence.
- Emergency-stop controls and shutdown procedure evidence are present.
- A Markdown lifecycle drill report is written under `data/runtime/reports/`.

Then confirm the persisted dashboard is still aligned with the latest runtime state:

```bash
python -m trading_app.runtime.dashboard_audit --output-dir data/runtime
```

Expected result:

- The latest runtime snapshot and dashboard snapshot both exist.
- Both snapshots are fresh relative to the audit time.
- The dashboard is in `Alpaca Paper` mode and embeds the latest runtime state.
- The dashboard broker label matches the broker provider in the runtime paper
  portfolio report.
- Cash, estimated equity, realized P&L, open orders, fills, positions, active
  model, and data-quality status match the runtime snapshot.
- A Markdown dashboard-consistency report is written under
  `data/runtime/reports/`.

Then confirm the Next dashboard handoff exposes the critical operator surfaces:

```bash
python -m trading_app.runtime.dashboard_visual --output-dir data/runtime
```

Expected result:

- The persisted dashboard snapshot shows `Alpaca Paper`, the paper/live
  boundary, and live readiness as gated.
- Latest prices, broker connection, cash, positions, orders, fills, risk,
  reconciliation, reports, learning, alerts, and incidents are visible.
- Next operator controls are present and wired to the local control endpoint.
- Data-quality evidence and active-model explanation panels are present.
- Responsive CSS, financial visuals, and the neon future-finance visual tokens
  are present in the Next source.
- A Markdown dashboard visual-readiness report is written under
  `data/runtime/reports/`.

Then run the restart recovery audit:

```bash
python -m trading_app.runtime.recovery --output-dir data/runtime
```

Expected result:

- Submission, order-status, and fill journals parse cleanly.
- Recovered runtime state can be rebuilt from persisted journals.
- Client order IDs, broker order IDs, and fill IDs do not contain duplicates.
- Recovered submissions, order statuses, and fills align with the latest
  runtime paper snapshot.
- A Markdown restart-recovery report is written under
  `data/runtime/reports/`.

Then run the model-governance audit:

```bash
python -m trading_app.runtime.governance --output-dir data/runtime
```

Expected result:

- The latest nightly learning run is present.
- Active model keys are unchanged.
- Recommendations require manual review and include evidence.
- No model state gains authority without approval evidence.
- The learning memo clearly states the AI/advisory and live-money boundaries.
- A Markdown model-governance report is written under
  `data/runtime/reports/`.

Then run the schedule-guardrail audit:

```bash
python -m trading_app.runtime.schedule --output-dir data/runtime
```

Expected result:

- Regular-hours monitoring refreshes prices and syncs broker state without
  strategy authority.
- The pre-trade daily-close window does not evaluate strategy or submit orders.
- The approved daily-close window evaluates strategy exactly once.
- A second same-day cycle and weekend cycle do not evaluate strategy.
- A Markdown schedule-guardrail report is written under `data/runtime/reports/`.

Then run the order-guardrail audit:

```bash
python -m trading_app.runtime.guardrails --output-dir data/runtime
```

Expected result:

- Missing latest prices block scheduled paper orders.
- Stale latest prices block scheduled paper orders.
- Risk rejection blocks broker paper submission.
- Dirty reconciliation blocks scheduled paper orders.
- Paper kill switch and operator pause both block scheduled paper orders.
- A Markdown order-guardrail report is written under `data/runtime/reports/`.

Then run the fill-sync audit:

```bash
python -m trading_app.runtime.fills --output-dir data/runtime
```

Expected result:

- A first partial broker fill updates the internal ledger once.
- A repeat broker sync creates no duplicate fill.
- A second partial broker fill applies only the incremental quantity.
- A restarted runtime recovers filled quantity and creates no duplicate fill.
- A Markdown fill-sync report is written under `data/runtime/reports/`.

Then run the data-quality audit:

```bash
python -m trading_app.runtime.data_quality --output-dir data/runtime
```

Expected result:

- Fresh SIP latest-price and daily-bar data passes quality checks.
- IEX latest-price and daily-bar data is labeled development-grade.
- Stale, missing, duplicate, mixed-feed, and lookahead data are caught.
- Invalid symbol-universe input is caught before data is trusted for runtime use.
- A Markdown data-quality audit report is written under
  `data/runtime/reports/`.

Then compare broker-reported order history to local paper orders and fills:

```bash
python -m trading_app.runtime.broker_history --output-dir data/runtime
```

To scope broker history to the reviewed session window:

```bash
python -m trading_app.runtime.broker_history \
  --output-dir data/runtime \
  --session-start 2026-05-29T09:30:00-04:00 \
  --session-end 2026-05-30T09:30:00-04:00 \
  --symbols SPY,XLK
```

If you exported broker order history separately, provide it explicitly:

```bash
python -m trading_app.runtime.broker_history \
  --output-dir data/runtime \
  --orders path/to/broker-order-history.json
```

Expected result:

- Broker order history identifies provider `alpaca-paper`.
- Broker order IDs match persisted local paper submissions.
- Broker order symbols, sides, quantities, and client order IDs match local
  orders.
- Broker filled quantities match persisted local fills.
- Session-window filters exclude unrelated Alpaca paper orders outside the
  reviewed run.
- A Markdown broker order-history audit report is written under
  `data/runtime/reports/`.

Then run the credentialed-session proof:

```bash
python -m trading_app.runtime.session_proof --output-dir data/runtime
```

If you want the proof to fail unless it matches a specific Alpaca paper account,
pass the expected account identifier:

```bash
python -m trading_app.runtime.session_proof \
  --output-dir data/runtime \
  --expected-paper-account-id PAPER_ACCOUNT_ID
```

Expected result:

- Preflight credential evidence, supervised validation, runtime snapshot,
  dashboard snapshot, latest-price provenance, soak evidence, broker statement,
  broker order-history, and secret scan evidence all pass together.
- The report records validation ID, session window, broker providers,
  latest-price sources, feed, and paper account identifier without recording
  credential values.
- Fixture/demo/provided-only provenance is rejected before completion audit.
- A Markdown credentialed-session proof report is written under
  `data/runtime/reports/`.
- Downstream coverage checks require that Markdown proof artifact to still
  exist before treating credentialed-session proof as clean.

Then run the evidence coherence audit:

```bash
python -m trading_app.runtime.coherence --output-dir data/runtime
```

Expected result:

- Validation, soak, runtime snapshot, dashboard snapshot, dashboard
  consistency, broker order-history, statement reconciliation, and
  credentialed-session proof artifacts are present.
- Validation starts before the reviewed soak window.
- The latest runtime snapshot falls inside the reviewed evidence window.
- Alpaca paper broker/provider evidence, broker order-history evidence, and
  Alpaca latest-price source evidence are aligned across validation, runtime,
  dashboard, statement, and order-history artifacts.
- Credentialed-session proof matches the reviewed validation ID, soak window,
  and statement paper account.
- A Markdown evidence-coherence report is written under
  `data/runtime/reports/`.

Then run the completion audit:

```bash
python -m trading_app.runtime.completion --output-dir data/runtime
```

Expected result:

- All functional paper-app requirements are marked `proven`.
- No requirement is marked `failed`.
- No requirement is marked `missing`.
- No requirement still requires external runtime evidence.
- Broker portfolio and statement evidence identify `alpaca-paper`, not a local
  fixture or in-memory broker.
- A Markdown completion-audit dossier is written under `data/runtime/reports/`.
- The latest completion audit report is persisted under `data/runtime/state/`
  and appended under `data/runtime/journal/`.
- Downstream completion coverage rejects the audit if the Markdown dossier path
  is missing or the dossier file no longer exists.

If any item remains `external_required`, that is usually honest evidence that a
real credentialed paper run, scheduled paper-order exercise, fill, report,
learning run, or full-day plus overnight soak has not happened yet.

Review the Markdown completion-audit dossier as the final local evidence packet
before calling the paper app functional. The dashboard also surfaces the latest
completion-audit status when the report exists.

After completion audit, write an artifact integrity manifest:

```bash
python -m trading_app.runtime.integrity --output-dir data/runtime
```

Expected result:

- Required latest state artifacts exist and are SHA-256 hashed.
- Optional Markdown report artifacts are hashed when present.
- The raw broker statement source still matches the SHA-256 fingerprint recorded
  by statement reconciliation.
- Current required artifacts are rechecked against the manifest, so deleted or
  changed files invalidate the review packet.
- A Markdown integrity manifest is written under `data/runtime/reports/`.

The one-command post-run review reruns artifact integrity after generating the
evidence bundle. If you run the individual commands manually, rerun integrity
after the evidence bundle command so the final manifest hashes the bundle state
and Markdown report before signoff.

## Operator Evidence Bundle

After completion audit, generate the single operator review dossier:

```bash
python -m trading_app.runtime.evidence --output-dir data/runtime
```

Expected result:

- The command writes a Markdown evidence bundle under `data/runtime/reports/`.
- The bundle inventories preflight, operations readiness, lifecycle drill, dry
  run, validation, soak, runtime snapshot, restart recovery, dashboard snapshot,
  dashboard consistency, data-quality audit, evidence coherence, artifact
  integrity, broker order-history audit, credentialed-session proof, health,
  daily report, learning, model governance, schedule guardrails, order
  guardrails, fill sync, secret scan, broker statement reconciliation, and
  completion audit evidence.
- Every passed required item points to a local review artifact that still
  exists.
- Bundle items do not point back to the bundle itself as circular evidence.
- Standalone audit reports must still have their Markdown review files on disk;
  missing Markdown reports make the affected evidence incomplete.
- Exit code `0` means all required evidence artifacts are present and clean.
- Exit code `1` means at least one required artifact is missing, failed, or not
  yet ready for operator review.
- The latest evidence bundle report is persisted under `data/runtime/state/`
  and appended under `data/runtime/journal/`.

This bundle is the operator packet for review. It is not a replacement for the
real credentialed Alpaca paper run, full-day plus overnight soak, or completion
audit; it simply puts those artifacts in one place.

## Operator Signoff

After reviewing the evidence bundle and confirming the Alpaca paper account
history directly in Alpaca, record the manual paper-only signoff:

```bash
python -m trading_app.runtime.signoff \
  --output-dir data/runtime \
  --reviewer "YOUR NAME" \
  --paper-account-id "ALPACA PAPER ACCOUNT ID" \
  --confirm-evidence-reviewed \
  --confirm-alpaca-paper-account-history \
  --confirm-no-unintended-orders \
  --confirm-fills-and-reconciliation-reviewed \
  --confirm-dashboard-reviewed \
  --confirm-paper-only-boundary \
  --confirm-limitations-acknowledged
```

Expected result:

- The latest evidence bundle is ready for operator review.
- The latest completion audit passed.
- The latest artifact integrity manifest passed, includes the evidence bundle
  state and Markdown report, and was generated at or after the evidence bundle.
- The reviewed artifacts still match the SHA-256 hashes recorded in that final
  integrity manifest.
- The reviewed Markdown reports still match the latest persisted completion
  audit, evidence bundle, artifact-integrity, and credentialed-session state.
- The signoff is timestamped at or after the reviewed evidence packet.
- The reviewer name and Alpaca paper account ID are both non-blank.
- The latest credentialed-session proof passed, and its paper account ID matches
  the `--paper-account-id` supplied for signoff.
- The operator explicitly confirms Alpaca paper account history, no unintended
  orders, fill/reconciliation review, dashboard review, paper-only boundaries,
  and known data/tax limitations.
- A Markdown operator signoff is written under `data/runtime/reports/` and
  persisted under `data/runtime/state/`.

This signoff is a paper-trading review artifact only. It does not authorize
live-money trading.

## Final Acceptance

After operator signoff, run the final post-signoff acceptance gate:

```bash
python -m trading_app.runtime.acceptance --output-dir data/runtime
```

Expected result:

- The latest operator signoff is accepted.
- The operator signoff includes every required named signoff check.
- The operator signoff state and Markdown report still exist and agree.
- Every required operator confirmation is present.
- The signed review artifact paths still exist.
- The signed review artifact paths match the latest persisted evidence paths.
- Coverage checks reject non-empty signed paths when the underlying file is
  missing from disk.
- The reviewed artifacts still match the SHA-256 hashes recorded in the final
  integrity manifest.
- Completion audit, evidence bundle, artifact integrity, and
  credentialed-session proof remain complete.
- The signed paper account matches credentialed-session proof.
- The final acceptance timestamp is at or after signoff, and the signoff
  happened after the completion audit, credentialed-session proof, evidence
  bundle, and final integrity manifest.
- The signed review Markdown artifacts still match their persisted state.
- Paper-only boundaries and known limitations were explicitly accepted.
- A Markdown final acceptance report is written under `data/runtime/reports/`
  and persisted under `data/runtime/state/`.
- Dashboard consistency will reject final-acceptance evidence that is missing
  any required named acceptance check, even if a partial report claims `passed`.
- Dashboard consistency will also reject final-acceptance evidence whose
  Markdown report is missing or stale.
- Dashboard consistency will also reject evidence-bundle reports whose Markdown
  report is missing or stale.
- Dashboard consistency will also reject artifact-integrity and
  credentialed-session reports whose Markdown reports are missing or stale.
- Dashboard consistency will also reject completion-audit evidence whose
  Markdown report is missing or stale.
- Dashboard consistency will also reject completion-audit evidence that is
  missing any required functional requirement, even if the report claims
  `passed`.

Exit code `0` means the signed paper evidence packet is internally complete.
It still does not authorize live-money trading.

## Optional Scheduled-Order Smoke

Only use this when you intentionally want the normal daily-close paper order path to be allowed:

```bash
python -m trading_app.runtime.dry_run --allow-scheduled-paper-orders
```

Use this only when:

- You are comfortable with paper orders being submitted.
- Preflight passed.
- You understand the current time relative to the daily-close schedule.
- You have reviewed current active model assumptions.

## Start The Always-On Paper Runtime

Start the runtime only after preflight and dry run are acceptable:

```bash
uv run dev
```

Local Python backend/API default:

```text
http://127.0.0.1:8765
```

Canonical operator dashboard:

```text
http://127.0.0.1:3003
```

The runtime runs continuously until interrupted.

## Next.js Operator UI

The incremental React/Next.js operator UI lives in `web/`. It is a frontend and
backend-for-frontend proxy only; Python remains the paper-runtime authority.

Run the Python backend first:

```bash
uv run dev
```

Then run the Next.js UI. The Next dashboard carries the Python cockpit screens
over as React tabs while keeping the Python runtime as the only trading
authority:

```bash
make web-install
make web-dev
```

The Next.js route handlers proxy `/api/snapshot`, `/api/health`, and
`/api/control` to the Python backend URL from server-only
`TRADING_APP_BACKEND_URL`, defaulting to `http://127.0.0.1:8765`.

Before relying on frontend changes, run:

```bash
make web-check
```

For a production-style local Next.js run, use:

```bash
make web-start
```

This runs `next start` on `http://127.0.0.1:3003/` after building the app and
continues to proxy browser API calls to the Python backend.

## macOS Automatic Startup

After manual startup and market-hours validation are clean, install the local
macOS LaunchAgent:

```bash
scripts/install_alpaca_paper_launchd.sh
```

This writes:

```text
~/Library/LaunchAgents/com.trading-app.alpaca-paper.plist
```

and starts the same paper-only runtime command through:

```text
~/Library/Application Support/trading-app/run_alpaca_paper_runtime.sh
```

The installer copies `.env` into:

```text
~/Library/Application Support/trading-app/alpaca-paper.env
```

with owner-only permissions. The repo `.env` remains the source file, but
launchd reads the App Support copy because shell jobs launched from macOS may
not be allowed to read files directly under `Documents`.

The Python LaunchAgent uses one canonical backend URL:

```text
http://127.0.0.1:8765/
```

It does not auto-select a different port. If `8765` is occupied, startup fails
loudly and writes logs under `data/runtime/logs/`. Stop the old process and
restart the service rather than letting the backend move to a surprise URL.

Install the Next.js operator dashboard as a separate LaunchAgent after the
Python backend service is in place:

```bash
scripts/install_operator_web_launchd.sh
```

This writes:

```text
~/Library/LaunchAgents/com.trading-app.operator-web.plist
```

and starts production Next.js through:

```text
~/Library/Application Support/trading-app/run_operator_web.sh
```

The web service listens at:

```text
http://127.0.0.1:3003/
```

and proxies to:

```text
http://127.0.0.1:8765/
```

The web LaunchAgent writes only non-secret web service config to:

```text
~/Library/Application Support/trading-app/operator-web.env
```

Do not move Alpaca credentials into the web service. Python remains the paper
runtime authority and owns broker credentials, scheduling, and operator
controls.

Check service status:

```bash
scripts/status_alpaca_paper_launchd.sh
scripts/status_operator_web_launchd.sh
```

Uninstall the LaunchAgent:

```bash
scripts/uninstall_alpaca_paper_launchd.sh
scripts/uninstall_operator_web_launchd.sh
```

Restart after changing `.env` or code:

```bash
scripts/install_alpaca_paper_launchd.sh
scripts/install_operator_web_launchd.sh
```

Rerunning the Python installer refreshes the App Support wrapper and env copy,
stops the existing LaunchAgent if it is already loaded, then starts it again on
the same fixed backend port. Rerunning the web installer refreshes the Next.js
build and restarts the operator dashboard on the same fixed web port.

The first launchd version uses `KeepAlive=false`. If either service exits,
inspect logs before starting it again:

```bash
tail -100 data/runtime/logs/launchd.out.log
tail -100 data/runtime/logs/launchd.err.log
tail -100 data/runtime/logs/operator-web.launchd.out.log
tail -100 data/runtime/logs/operator-web.launchd.err.log
```

After several clean supervised soaks, we can deliberately change the plist to
restart on failure. Do not enable automatic restarts before the failure modes are
well understood.

## Optional Process Supervision Templates

If you only want reviewable templates without installing a service, generate
them locally:

```bash
python -m trading_app.runtime.ops --write-supervisor-dir data/runtime/supervision
```

This writes:

- `data/runtime/supervision/com.trading-app.alpaca-paper.plist` for macOS `launchd`.
- `data/runtime/supervision/trading-app-alpaca-paper.service` for Linux `systemd --user`.

The generated templates run the same paper-only startup command with
`--monitor-only-dry-run-first`. They reference a local env file path but do not
include Alpaca credential values. Treat these as review artifacts; use the
scripts above for the actual macOS LaunchAgent install.

## Runtime Artifact Layout

Runtime artifacts are local-only and ignored by git under `data/runtime/`:

- `data/runtime/state/`: latest snapshot, latest health report, latest alerts,
  latest preflight, latest operations-readiness audit, latest dry-run, latest
  validation, latest recovery audit, latest completion audit, latest evidence
  bundle, latest operator signoff, latest final acceptance, and latest report
  metadata.
- `data/runtime/journal/`: append-only cycle, event, fill, order-status,
  control-action, alert, health, preflight, operations-readiness, dry-run,
  validation, recovery, completion, evidence, signoff, and final acceptance
  journals.
- `data/runtime/reports/`: daily Markdown and JSON trading reports.
- `data/runtime/learning/`: nightly learning recommendation artifacts.

Do not delete these folders during an active paper session. They are part of
restart recovery and post-session review.

## Stop The Runtime

Use `Ctrl+C` in the terminal running the process.

After stopping, verify:

- Runtime process exited cleanly.
- Latest state exists under `data/runtime/state/`.
- No unexpected paper orders were submitted.
- The next restart recovers persisted orders and fills.

## Dashboard Checks

Review these panels after startup:

- Runtime Health
- Incident Command
- Runtime Alerts
- Operator Controls
- Final Acceptance
- Paper Portfolio
- Risk State
- Daily Report
- Nightly Learning

The first question is always: “Is the runtime healthy enough to keep monitoring?”

## Health Meanings

- `healthy`: monitoring, broker sync, reconciliation, and evidence are clean.
- `watch`: intentional pause or early-cycle state; review but do not panic.
- `degraded`: runtime is alive but some condition blocks trust in new signals.
- `critical`: stop and review before allowing new paper orders.

## Stop Conditions

Pause the runtime or enable the paper kill switch if any of these occur:

- Broker reconciliation breaks.
- Latest prices are stale or missing.
- Broker sync fails.
- Runtime health is `critical`.
- Unexpected paper orders appear.
- Risk rejections spike unexpectedly.
- Dashboard is exposed on a non-local host.
- Credentials appear in logs, reports, or files.

## Emergency Stop Procedure

Use this path when the runtime may submit unsafe paper orders, reconciliation is
dirty, market data cannot be trusted, credentials may have leaked, or the
dashboard/control surface is behaving unexpectedly:

1. Enable **Paper Kill On** from the local dashboard if controls are reachable.
2. Select **Pause** from the local dashboard if controls are reachable.
3. Stop the runtime process with `Ctrl+C`.
4. Capture or load the latest Alpaca paper statement.
5. Run broker statement reconciliation before allowing any new paper orders.
6. Run post-run review and keep paper orders blocked until evidence is clean.

Do not resume scheduled paper trading until preflight, recovery, reconciliation,
secret scan, health, and completion evidence are clean.

## Control Guidance

- Use **Pause** when monitoring should continue but scheduled strategy evaluation should stop.
- Use **Paper Kill On** when no new paper orders should be submitted under any circumstance.
- Use **Reconcile** after broker state, order state, or fills look suspicious.
- Use **Report** after a supervised review or after a notable incident.

## Reconciliation Response

If reconciliation is not clean:

1. Enable the paper kill switch.
2. Force reconciliation.
3. Review broker cash, positions, open orders, and fills.
4. Compare broker state to the internal ledger.
5. Leave paper orders blocked until the mismatch is understood.
6. Record what happened in the daily report or a separate operator note.

## Restart Recovery

On restart:

1. Run preflight.
2. Run monitor-only dry run.
3. Run `python -m trading_app.runtime.recovery --output-dir data/runtime`.
4. Confirm recovered submissions, order statuses, and fills align with the latest
   runtime paper snapshot.
5. Confirm health is not `critical`.
6. Start the always-on runtime.

## Nightly Learning

Nightly learning is recommendation-only. It may compare candidates, but it must
not mutate the active paper model automatically. Treat it as valid only when it
runs after the daily report and every recommendation remains manual-review
gated.

If nightly learning fails:

- Keep the active paper model unchanged.
- Review the daily report and health incidents.
- Do not promote a model based on a failed or partial learning run.

## Live-Money Boundary

Live-money trading remains disabled. Any future move toward live-limited trading must go through the live readiness runbook and explicit human approval.
