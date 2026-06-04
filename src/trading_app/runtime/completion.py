"""Functional completion evidence audit for the paper trading app."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from trading_app.broker import BrokerStatementReconciliationReport
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.paper import PaperOrderSubmission
from trading_app.runtime.audit_coverage import (
    broker_order_history_coverage_gap,
    credentialed_session_coverage_gap,
    dashboard_consistency_coverage_gap,
    dashboard_visual_coverage_gap,
    data_quality_coverage_gap,
    evidence_coherence_coverage_gap,
    fill_sync_coverage_gap,
    lifecycle_coverage_gap,
    model_governance_coverage_gap,
    operations_coverage_gap,
    order_guardrail_coverage_gap,
    recovery_coverage_gap,
    schedule_guardrail_coverage_gap,
    validation_coverage_gap,
)
from trading_app.runtime.models import (
    FunctionalCompletionAuditReport,
    FunctionalRequirementEvidence,
    FunctionalRequirementStatus,
    RuntimeBrokerOrderHistoryReport,
    RuntimeCredentialedSessionReport,
    RuntimeDashboardConsistencyReport,
    RuntimeDashboardVisualReport,
    RuntimeDataQualityAuditReport,
    RuntimeDryRunReport,
    RuntimeEvidenceCoherenceReport,
    RuntimeFillSyncReport,
    RuntimeLifecycleDrillReport,
    RuntimeModelGovernanceReport,
    RuntimeOperationsReadinessReport,
    RuntimeOrderGuardrailReport,
    RuntimePreflightReport,
    RuntimePreflightStatus,
    RuntimeRecoveryAuditReport,
    RuntimeScheduleGuardrailReport,
    RuntimeSecretScanReport,
    RuntimeSnapshot,
    RuntimeSoakEvidenceReport,
    RuntimeValidationReport,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, Fill

MARKET_TZ = ZoneInfo("America/New_York")
REGULAR_CLOSE = dt_time(hour=16)

_REQ_BROKER_VISIBILITY = (
    "Broker connection, cash, positions, orders, fills, and reconciliation are visible."
)
_REQ_ORDER_GUARDS = (
    "Paper orders block on stale data, risk rejection, dirty reconciliation, or "
    "controls."
)
_REQ_RESTART_RECOVERY = (
    "Restart recovery rebuilds internal state without duplicate orders or fills."
)
_REQUIRED_SECRET_NAMES = frozenset({"ALPACA_API_KEY", "ALPACA_SECRET_KEY"})


class RuntimeCompletionAuditor:
    """Audit runtime artifacts against the functional paper-app definition."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        persistence_store: RuntimePersistenceStore | None = None,
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.persist_report = persist_report

    def audit(
        self, *, as_of: datetime | None = None
    ) -> FunctionalCompletionAuditReport:
        now = as_of or datetime.now(tz=UTC)
        artifacts = _Artifacts.load(self.store)
        requirements = (
            _credentialed_start(artifacts),
            _offline_preflight(artifacts),
            _monitor_only_dry_run(artifacts),
            _full_day_soak(artifacts),
            _dashboard_runtime_state(artifacts),
            _latest_price_refresh(artifacts),
            _broker_portfolio_visibility(artifacts),
            _daily_close_schedule(artifacts),
            _order_blocking_guards(artifacts),
            _fill_integrity(artifacts),
            _restart_recovery_integrity(artifacts),
            _daily_report_written(artifacts),
            _nightly_learning_after_report(artifacts),
            _active_model_locked(artifacts),
            _operator_controls_alerts(artifacts),
            _iex_labeling(artifacts),
            _paper_only_boundary(artifacts),
            _broker_statement_review(artifacts),
        )
        proven = sum(
            1
            for requirement in requirements
            if requirement.status == FunctionalRequirementStatus.PROVEN
        )
        missing = sum(
            1
            for requirement in requirements
            if requirement.status == FunctionalRequirementStatus.MISSING
        )
        failed = sum(
            1
            for requirement in requirements
            if requirement.status == FunctionalRequirementStatus.FAILED
        )
        external = sum(
            1
            for requirement in requirements
            if requirement.status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
        )
        passed = proven == len(requirements)
        status = (
            RuntimePreflightStatus.FAILED
            if failed
            else RuntimePreflightStatus.WARNING
            if missing or external
            else RuntimePreflightStatus.PASSED
        )
        report = FunctionalCompletionAuditReport(
            as_of=now,
            status=status,
            passed=passed,
            output_dir=str(self.output_dir),
            proven_count=proven,
            missing_count=missing,
            failed_count=failed,
            external_required_count=external,
            requirements=requirements,
            summary=_summary(
                passed=passed,
                proven=proven,
                total=len(requirements),
                missing=missing,
                failed=failed,
                external=external,
            ),
        )
        if self.persist_report:
            markdown_path = write_completion_audit_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_completion_audit_report(report)
        return report


def render_completion_audit_text(report: FunctionalCompletionAuditReport) -> str:
    """Render an operator-facing completion audit."""

    lines = [
        f"Completion audit status: {report.status.value}",
        f"Passed: {'yes' if report.passed else 'no'}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Counts:",
        f"- proven: {report.proven_count}",
        f"- missing: {report.missing_count}",
        f"- failed: {report.failed_count}",
        f"- external required: {report.external_required_count}",
        "",
        "Requirements:",
    ]
    for item in report.requirements:
        evidence = "; ".join(item.evidence) if item.evidence else "no evidence"
        lines.append(f"- {item.id}: {item.status.value} - {item.requirement}")
        lines.append(f"  Evidence: {evidence}")
        lines.append(f"  Next: {item.remediation}")
    return "\n".join(lines)


def render_completion_audit_markdown(
    report: FunctionalCompletionAuditReport,
) -> str:
    """Render a reviewable completion-audit dossier."""

    lines = [
        "# Functional Paper App Completion Audit",
        "",
        "> Paper trading only. This dossier does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Proven: `{report.proven_count}`",
        f"- Missing: `{report.missing_count}`",
        f"- Failed: `{report.failed_count}`",
        f"- External evidence required: `{report.external_required_count}`",
        "",
        report.summary,
        "",
        "## Paper Boundary",
        "",
        "- This audit covers the paper-trading phase only.",
        "- Live-money trading, margin, shorts, options, futures, forex, crypto, "
        "and non-U.S. markets remain out of scope.",
        "- AI recommendations remain advisory and cannot promote or execute models "
        "without explicit approval.",
        "",
        "## Requirement Evidence",
        "",
        "| ID | Status | Requirement | Evidence | Next Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.requirements:
        evidence = "<br>".join(item.evidence) if item.evidence else "No evidence"
        lines.append(
            "| "
            f"{_escape_table(item.id)} | "
            f"{_escape_table(item.status.value)} | "
            f"{_escape_table(item.requirement)} | "
            f"{_escape_table(evidence)} | "
            f"{_escape_table(item.remediation)} |"
        )

    lines.extend(
        (
            "",
            "## Next Action",
            "",
            _completion_next_action(report),
            "",
        )
    )
    return "\n".join(lines)


def write_completion_audit_markdown_report(
    report: FunctionalCompletionAuditReport,
    reports_dir: Path | str,
) -> Path:
    """Write the completion audit dossier and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"completion-audit-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_completion_audit_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Audit local artifacts against the functional completion definition."""

    parser = argparse.ArgumentParser(description="Audit functional app completion.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeCompletionAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json() if args.json else render_completion_audit_text(report)
    )
    return 0 if report.passed else 1


class _Artifacts:
    def __init__(
        self,
        *,
        preflight: RuntimePreflightReport | None,
        dry_run: RuntimeDryRunReport | None,
        validation: RuntimeValidationReport | None,
        soak: RuntimeSoakEvidenceReport | None,
        secret_scan: RuntimeSecretScanReport | None,
        snapshot: RuntimeSnapshot | None,
        dashboard_snapshot: OperatorDashboardSnapshot | None,
        dashboard_consistency: RuntimeDashboardConsistencyReport | None,
        dashboard_visual: RuntimeDashboardVisualReport | None,
        evidence_coherence: RuntimeEvidenceCoherenceReport | None,
        data_quality_audit: RuntimeDataQualityAuditReport | None,
        broker_order_history: RuntimeBrokerOrderHistoryReport | None,
        credentialed_session: RuntimeCredentialedSessionReport | None,
        model_governance: RuntimeModelGovernanceReport | None,
        order_guardrail: RuntimeOrderGuardrailReport | None,
        schedule_guardrail: RuntimeScheduleGuardrailReport | None,
        fill_sync: RuntimeFillSyncReport | None,
        daily_report,
        daily_report_path: Path | None,
        operations_readiness: RuntimeOperationsReadinessReport | None,
        lifecycle_drill: RuntimeLifecycleDrillReport | None,
        recovery_audit: RuntimeRecoveryAuditReport | None,
        submissions: tuple[PaperOrderSubmission, ...],
        fills: tuple[Fill, ...],
        statement_reconciliation: BrokerStatementReconciliationReport | None,
    ) -> None:
        self.preflight = preflight
        self.dry_run = dry_run
        self.validation = validation
        self.soak = soak
        self.secret_scan = secret_scan
        self.snapshot = snapshot
        self.dashboard_snapshot = dashboard_snapshot
        self.dashboard_consistency = dashboard_consistency
        self.dashboard_visual = dashboard_visual
        self.evidence_coherence = evidence_coherence
        self.data_quality_audit = data_quality_audit
        self.broker_order_history = broker_order_history
        self.credentialed_session = credentialed_session
        self.model_governance = model_governance
        self.order_guardrail = order_guardrail
        self.schedule_guardrail = schedule_guardrail
        self.fill_sync = fill_sync
        self.daily_report = daily_report
        self.daily_report_path = daily_report_path
        self.operations_readiness = operations_readiness
        self.lifecycle_drill = lifecycle_drill
        self.recovery_audit = recovery_audit
        self.submissions = submissions
        self.fills = fills
        self.statement_reconciliation = statement_reconciliation

    @classmethod
    def load(cls, store: RuntimePersistenceStore) -> _Artifacts:
        recovered = store.recover()
        return cls(
            preflight=recovered.preflight_report,
            dry_run=recovered.dry_run_report,
            validation=recovered.validation_report,
            soak=_read_model(
                store.state_dir / "latest-soak-evidence-report.json",
                RuntimeSoakEvidenceReport,
            ),
            secret_scan=_read_model(
                store.state_dir / "latest-secret-scan-report.json",
                RuntimeSecretScanReport,
            ),
            snapshot=_read_model(
                store.state_dir / "latest-runtime-snapshot.json",
                RuntimeSnapshot,
            ),
            dashboard_snapshot=_read_model(
                store.state_dir / "latest-dashboard-snapshot.json",
                OperatorDashboardSnapshot,
            ),
            dashboard_consistency=store.read_dashboard_consistency_report(),
            dashboard_visual=store.read_dashboard_visual_report(),
            evidence_coherence=store.read_evidence_coherence_report(),
            data_quality_audit=store.read_data_quality_audit_report(),
            broker_order_history=store.read_broker_order_history_report(),
            credentialed_session=store.read_credentialed_session_report(),
            model_governance=store.read_model_governance_report(),
            order_guardrail=store.read_order_guardrail_report(),
            schedule_guardrail=store.read_schedule_guardrail_report(),
            fill_sync=store.read_fill_sync_report(),
            daily_report=recovered.daily_report,
            daily_report_path=recovered.daily_report_path,
            operations_readiness=store.read_operations_readiness_report(),
            lifecycle_drill=store.read_lifecycle_drill_report(),
            recovery_audit=store.read_recovery_audit_report(),
            submissions=tuple(
                _read_jsonl(
                    store.journal_dir / "submissions.jsonl", PaperOrderSubmission
                )
            ),
            fills=tuple(_read_jsonl(store.journal_dir / "fills.jsonl", Fill)),
            statement_reconciliation=_read_model(
                store.state_dir / "latest-statement-reconciliation.json",
                BrokerStatementReconciliationReport,
            ),
        )


def _credentialed_start(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    preflight = artifacts.preflight
    if preflight is None:
        return _external("FR-01", "Operator can start with Alpaca paper credentials.")
    credential_check = _check_by_name(preflight, "credentials")
    if preflight.can_start and _check_passed(credential_check):
        validation = artifacts.validation
        if not _validation_has_alpaca_broker_proof(validation):
            evidence = ["preflight can_start=true", "credentials=present"]
            if validation is None:
                evidence.append("validation=missing")
            else:
                evidence.append(
                    "validation_broker_providers="
                    f"{','.join(validation.broker_providers) or 'missing'}"
                )
            return _external(
                "FR-01",
                "Operator can start with Alpaca paper credentials.",
                evidence=tuple(evidence),
            )
        operations = artifacts.operations_readiness
        if operations is None:
            return _missing(
                "FR-01",
                "Operator can start with Alpaca paper credentials.",
                "Run python -m trading_app.runtime.ops --audit.",
            )
        operations_gap = operations_coverage_gap(operations)
        if not operations.passed or operations_gap:
            return _failed(
                "FR-01",
                "Operator can start with Alpaca paper credentials.",
                (
                    f"operations readiness status={operations.status.value}",
                    f"checks={len(operations.checks)}",
                    *operations_gap,
                ),
                (
                    "Fix incomplete or failed operations-readiness evidence before "
                    "supervised startup."
                ),
            )
        lifecycle = artifacts.lifecycle_drill
        if lifecycle is None:
            return _missing(
                "FR-01",
                "Operator can start with Alpaca paper credentials.",
                "Run python -m trading_app.runtime.lifecycle after a supervised drill.",
            )
        lifecycle_gap = lifecycle_coverage_gap(lifecycle)
        if not lifecycle.passed or lifecycle_gap:
            return _failed(
                "FR-01",
                "Operator can start with Alpaca paper credentials.",
                (
                    f"lifecycle_drill_status={lifecycle.status.value}",
                    f"controls={lifecycle.operator_control_count}",
                    *lifecycle_gap,
                ),
                (
                    "Exercise the complete documented startup, shutdown, and "
                    "control drill."
                ),
            )
        credentialed_session = artifacts.credentialed_session
        if credentialed_session is None:
            return _missing(
                "FR-01",
                "Operator can start with Alpaca paper credentials.",
                "Run python -m trading_app.runtime.session_proof.",
            )
        credentialed_session_gap = credentialed_session_coverage_gap(
            credentialed_session
        )
        if not credentialed_session.passed or credentialed_session_gap:
            return _failed(
                "FR-01",
                "Operator can start with Alpaca paper credentials.",
                (
                    f"credentialed_session_status={credentialed_session.status.value}",
                    f"validation_id={credentialed_session.validation_id or 'missing'}",
                    f"account_id={credentialed_session.paper_account_id or 'missing'}",
                    *credentialed_session_gap,
                ),
                (
                    "Fix incomplete or failed credentialed-session evidence "
                    "before completion."
                ),
            )
        evidence = [
            "preflight can_start=true",
            "credentials=present",
            "validation broker_provider=alpaca-paper",
            "operations_readiness=passed",
            "lifecycle_drill=passed",
            "credentialed_session=passed",
        ]
        if artifacts.secret_scan and artifacts.secret_scan.passed:
            evidence.append("secret scan passed")
        return _proven(
            "FR-01", "Operator can start with Alpaca paper credentials.", evidence
        )
    return _failed(
        "FR-01",
        "Operator can start with Alpaca paper credentials.",
        ("preflight credentials check failed",),
        "Run preflight with valid Alpaca paper credentials.",
    )


def _offline_preflight(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    if artifacts.preflight is None:
        return _missing(
            "FR-02",
            "App performs offline preflight before runtime startup.",
            "Run python -m trading_app.runtime.preflight.",
        )
    if artifacts.preflight.can_start:
        return _proven(
            "FR-02",
            "App performs offline preflight before runtime startup.",
            (f"preflight status={artifacts.preflight.status.value}",),
        )
    return _failed(
        "FR-02",
        "App performs offline preflight before runtime startup.",
        (f"preflight status={artifacts.preflight.status.value}",),
        "Fix preflight failures before runtime startup.",
    )


def _monitor_only_dry_run(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    dry_run = _monitor_only_dry_run_report(artifacts)
    if dry_run is None:
        return _external(
            "FR-03",
            "Credentialed dry run runs without placing paper orders by default.",
        )
    if (
        dry_run.can_start_supervised_runtime
        and dry_run.monitor_only
        and dry_run.orders_submitted == 0
    ):
        if not _dry_run_has_alpaca_broker_proof(dry_run, artifacts.validation):
            return _external(
                "FR-03",
                "Credentialed dry run runs without placing paper orders by default.",
                evidence=(
                    "monitor_only=true",
                    "orders_submitted=0",
                    (f"broker_provider={dry_run.broker_provider or 'missing'}"),
                ),
            )
        return _proven(
            "FR-03",
            "Credentialed dry run runs without placing paper orders by default.",
            (
                "monitor_only=true",
                "orders_submitted=0",
                f"source={_dry_run_source(artifacts, dry_run)}",
                f"broker_provider={dry_run.broker_provider or 'alpaca-paper'}",
            ),
        )
    return _failed(
        "FR-03",
        "Credentialed dry run runs without placing paper orders by default.",
        (f"orders_submitted={dry_run.orders_submitted}",),
        "Run monitor-only dry run and confirm zero submitted paper orders.",
    )


def _full_day_soak(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    soak = artifacts.soak
    if soak is None:
        return _external(
            "FR-04",
            "App can run continuously for one full market day and overnight.",
        )
    if soak.passed:
        missed_cycle_evidence = []
        if soak.prices_refreshed_cycle_count != soak.cycle_count:
            missed_cycle_evidence.append(
                "prices_refreshed_cycle_count="
                f"{soak.prices_refreshed_cycle_count} cycle_count={soak.cycle_count}"
            )
        if soak.broker_synced_cycle_count != soak.cycle_count:
            missed_cycle_evidence.append(
                f"broker_synced_cycle_count={soak.broker_synced_cycle_count} "
                f"cycle_count={soak.cycle_count}"
            )
        if soak.missed_price_refresh_cycles:
            missed_cycle_evidence.append(
                f"missed_price_refresh_cycles={soak.missed_price_refresh_cycles}"
            )
        if soak.missed_broker_sync_cycles:
            missed_cycle_evidence.append(
                f"missed_broker_sync_cycles={soak.missed_broker_sync_cycles}"
            )
        if missed_cycle_evidence:
            return _failed(
                "FR-04",
                "App can run continuously for one full market day and overnight.",
                tuple(missed_cycle_evidence),
                (
                    "Rerun soak evidence after every runtime cycle proves latest "
                    "price refresh and broker sync."
                ),
            )
        if soak.runtime_error_event_count:
            return _failed(
                "FR-04",
                "App can run continuously for one full market day and overnight.",
                (
                    f"runtime_error_event_count={soak.runtime_error_event_count}",
                    f"runtime_event_count={soak.runtime_event_count}",
                ),
                (
                    "Review runtime error events and rerun a clean full-day plus "
                    "overnight soak before completion."
                ),
            )
        coherence = artifacts.evidence_coherence
        if coherence is None:
            return _missing(
                "FR-04",
                "App can run continuously for one full market day and overnight.",
                "Run python -m trading_app.runtime.coherence.",
            )
        coherence_gap = evidence_coherence_coverage_gap(coherence)
        if not coherence.passed or coherence_gap:
            return _failed(
                "FR-04",
                "App can run continuously for one full market day and overnight.",
                (
                    f"evidence coherence status={coherence.status.value}",
                    f"checks={len(coherence.checks)}",
                    *coherence_gap,
                ),
                "Fix mixed or stale runtime evidence and rerun coherence audit.",
            )
        return _proven(
            "FR-04",
            "App can run continuously for one full market day and overnight.",
            (
                f"duration_hours={soak.duration_hours}",
                f"market_cycles={soak.market_cycle_count}",
                f"overnight_cycles={soak.overnight_cycle_count}",
                f"price_refresh_cycles={soak.prices_refreshed_cycle_count}",
                f"broker_sync_cycles={soak.broker_synced_cycle_count}",
                f"runtime_warning_events={soak.runtime_warning_event_count}",
                f"runtime_error_events={soak.runtime_error_event_count}",
                "evidence_coherence=passed",
            ),
        )
    return _failed(
        "FR-04",
        "App can run continuously for one full market day and overnight.",
        (f"soak status={soak.status.value}",),
        "Complete a clean full-day plus overnight soak and rerun soak evidence.",
    )


def _dashboard_runtime_state(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    dashboard_snapshot = artifacts.dashboard_snapshot
    snapshot = artifacts.snapshot
    if dashboard_snapshot is not None:
        runtime_state = dashboard_snapshot.runtime_state
        runtime_mode = _field(runtime_state, "mode")
        if dashboard_snapshot.mode == "Alpaca Paper" and runtime_mode == "Alpaca Paper":
            missing = []
            if dashboard_snapshot.active_strategy_definition is None:
                missing.append("active strategy definition missing")
            if dashboard_snapshot.daily_report.data_quality_report is None:
                missing.append("data quality report missing")
            if missing:
                return _missing(
                    "FR-05",
                    "Dashboard shows real runtime state, not static demo state.",
                    (
                        "Persist dashboard snapshots with active-model and "
                        "data-quality evidence."
                    ),
                )
            demo_markers = _dashboard_demo_provenance_markers(dashboard_snapshot)
            if demo_markers:
                return _failed(
                    "FR-05",
                    "Dashboard shows real runtime state, not static demo state.",
                    demo_markers,
                    (
                        "Regenerate dashboard state from the Alpaca paper runtime "
                        "provider; demo or fixture provenance cannot prove "
                        "functional readiness."
                    ),
                )
            strategy = dashboard_snapshot.active_strategy_definition
            quality = dashboard_snapshot.daily_report.data_quality_report
            consistency = artifacts.dashboard_consistency
            if consistency is None:
                return _missing(
                    "FR-05",
                    "Dashboard shows real runtime state, not static demo state.",
                    (
                        "Run python -m trading_app.runtime.dashboard_audit "
                        "--output-dir data/runtime."
                    ),
                )
            consistency_gap = dashboard_consistency_coverage_gap(consistency)
            if not consistency.passed or consistency_gap:
                return _failed(
                    "FR-05",
                    "Dashboard shows real runtime state, not static demo state.",
                    (
                        f"dashboard consistency status={consistency.status.value}",
                        f"checks={len(consistency.checks)}",
                        *consistency_gap,
                    ),
                    (
                        "Fix dashboard/runtime mismatches and rerun the dashboard "
                        "consistency audit."
                    ),
                )
            visual = artifacts.dashboard_visual
            if visual is None:
                return _missing(
                    "FR-05",
                    "Dashboard shows real runtime state, not static demo state.",
                    (
                        "Run python -m trading_app.runtime.dashboard_visual "
                        "--output-dir data/runtime."
                    ),
                )
            visual_gap = dashboard_visual_coverage_gap(visual)
            if not visual.passed or visual_gap:
                failed_checks = tuple(
                    check.name
                    for check in visual.checks
                    if check.status == RuntimePreflightStatus.FAILED
                )
                return _failed(
                    "FR-05",
                    "Dashboard shows real runtime state, not static demo state.",
                    (
                        f"dashboard visual status={visual.status.value}",
                        f"failed_visual_scenarios={visual.failed_visual_scenarios}",
                        *tuple(
                            f"dashboard_visual_failed={name}" for name in failed_checks
                        ),
                        *visual_gap,
                    ),
                    (
                        "Fix Next dashboard readiness gaps and rerun the "
                        "dashboard visual audit."
                    ),
                )
            return _proven(
                "FR-05",
                "Dashboard shows real runtime state, not static demo state.",
                (
                    f"dashboard mode={dashboard_snapshot.mode}",
                    f"runtime_state mode={runtime_mode}",
                    f"broker={dashboard_snapshot.broker}",
                    f"active_model={strategy.strategy_id}:{strategy.version}",
                    f"data_quality={quality.status.value}",
                    "dashboard_consistency=passed",
                    "dashboard_visual=passed",
                ),
            )
        return _failed(
            "FR-05",
            "Dashboard shows real runtime state, not static demo state.",
            (
                f"dashboard mode={dashboard_snapshot.mode}",
                f"runtime_state mode={runtime_mode or 'missing'}",
            ),
            "Persist dashboard snapshots from the Alpaca paper runtime provider.",
        )
    if snapshot is None:
        return _missing(
            "FR-05",
            "Dashboard shows real runtime state, not static demo state.",
            "Persist a dashboard snapshot from the Alpaca paper runtime.",
        )
    if snapshot.mode == "Alpaca Paper":
        return _missing(
            "FR-05",
            "Dashboard shows real runtime state, not static demo state.",
            "Persist dashboard-shaped snapshot evidence, not only runtime state.",
        )
    return _failed(
        "FR-05",
        "Dashboard shows real runtime state, not static demo state.",
        (f"snapshot mode={snapshot.mode}",),
        "Use the Alpaca paper runtime snapshot provider for the dashboard.",
    )


def _latest_price_refresh(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    snapshot = artifacts.snapshot
    latest = snapshot.latest_prices if snapshot else None
    if latest is not None and latest.all_fresh:
        if latest.source != "alpaca":
            return _external(
                "FR-06",
                "Latest prices refresh on schedule and show freshness.",
                evidence=(
                    f"latest price status={latest.status.value}",
                    f"feed={latest.feed.value}",
                    f"source={latest.source}",
                ),
            )
        audit_gap = _data_quality_audit_requirement(
            "FR-06",
            "Latest prices refresh on schedule and show freshness.",
            artifacts,
        )
        if audit_gap is not None:
            return audit_gap
        quality = _market_data_quality_report(artifacts)
        if quality is None:
            return _missing(
                "FR-06",
                "Latest prices refresh on schedule and show freshness.",
                (
                    "Persist a daily report or dashboard snapshot with "
                    "market-data quality evidence."
                ),
            )
        if quality.failures:
            return _failed(
                "FR-06",
                "Latest prices refresh on schedule and show freshness.",
                (
                    f"latest price status={latest.status.value}",
                    f"data quality failures={quality.failures}",
                    f"data quality status={quality.status.value}",
                ),
                (
                    "Resolve market-data quality failures before treating prices "
                    "as usable."
                ),
            )
        return _proven(
            "FR-06",
            "Latest prices refresh on schedule and show freshness.",
            (
                f"latest price status={latest.status.value}",
                f"feed={latest.feed.value}",
                f"source={latest.source}",
                f"data_quality={quality.status.value}",
                f"research_usable={quality.can_use_for_research}",
                f"trading_usable={quality.can_use_for_trading}",
                "data_quality_audit=passed",
            ),
        )
    if latest is None:
        validation = artifacts.validation
        if validation and validation.latest_prices_refreshed:
            validation_gap = validation_coverage_gap(validation)
            if validation_gap:
                return _failed(
                    "FR-06",
                    "Latest prices refresh on schedule and show freshness.",
                    (
                        "validation latest_prices_refreshed=true",
                        *validation_gap,
                    ),
                    (
                        "Rerun supervised validation so latest-price proof is "
                        "backed by the credentialed paper checklist."
                    ),
                )
            if "alpaca" not in validation.latest_price_sources:
                return _external(
                    "FR-06",
                    "Latest prices refresh on schedule and show freshness.",
                    evidence=(
                        "validation latest_prices_refreshed=true",
                        (
                            "validation latest_price_sources="
                            f"{','.join(validation.latest_price_sources) or 'missing'}"
                        ),
                    ),
                )
            if validation.latest_prices_fresh:
                return _proven(
                    "FR-06",
                    "Latest prices refresh on schedule and show freshness.",
                    (
                        "validation latest_prices_refreshed=true",
                        "validation latest_prices_fresh=true",
                        "validation latest_price_source=alpaca",
                    ),
                )
            return _failed(
                "FR-06",
                "Latest prices refresh on schedule and show freshness.",
                (
                    "validation latest_prices_refreshed=true",
                    "validation latest_prices_fresh=false",
                ),
                (
                    "Resolve stale or missing latest prices before paper orders "
                    "are allowed."
                ),
            )
        return _missing(
            "FR-06",
            "Latest prices refresh on schedule and show freshness.",
            "Run the paper runtime until latest-price state is persisted.",
        )
    return _failed(
        "FR-06",
        "Latest prices refresh on schedule and show freshness.",
        (
            f"latest price status={latest.status.value}",
            f"missing={','.join(latest.missing_symbols) or '-'}",
        ),
        "Resolve stale or missing latest prices before paper orders are allowed.",
    )


def _broker_portfolio_visibility(
    artifacts: _Artifacts,
) -> FunctionalRequirementEvidence:
    snapshot = artifacts.snapshot
    if (
        snapshot is None
        or snapshot.paper_report is None
        or snapshot.daily_report is None
    ):
        return _missing(
            "FR-07",
            _REQ_BROKER_VISIBILITY,
            "Persist a runtime snapshot with paper portfolio and daily report state.",
        )
    paper = snapshot.paper_report
    provider = paper.broker_portfolio.provider
    if provider != "alpaca-paper":
        return _external(
            "FR-07",
            _REQ_BROKER_VISIBILITY,
            evidence=(f"broker_provider={provider}",),
        )
    broker_history = artifacts.broker_order_history
    if broker_history is None:
        return _missing(
            "FR-07",
            _REQ_BROKER_VISIBILITY,
            "Run python -m trading_app.runtime.broker_history.",
        )
    coverage_gap = broker_order_history_coverage_gap(broker_history)
    if not broker_history.passed or coverage_gap:
        failed_checks = tuple(
            f"{check.name}={check.status.value}"
            for check in broker_history.checks
            if check.status == RuntimePreflightStatus.FAILED
        )
        return _failed(
            "FR-07",
            _REQ_BROKER_VISIBILITY,
            (
                f"broker_history_status={broker_history.status.value}",
                f"broker_history_provider={broker_history.provider}",
                f"mismatches={broker_history.mismatch_count}",
                *failed_checks,
                *coverage_gap,
            ),
            (
                "Fix incomplete or failed broker order-history evidence before "
                "completion."
            ),
        )
    if broker_history.source == "provided":
        return _external(
            "FR-07",
            _REQ_BROKER_VISIBILITY,
            evidence=(
                f"broker_history_provider={broker_history.provider}",
                f"broker_history_source={broker_history.source}",
            ),
        )
    return _proven(
        "FR-07",
        _REQ_BROKER_VISIBILITY,
        (
            f"broker_provider={provider}",
            f"cash={paper.ledger_snapshot.cash}",
            f"positions={len(paper.ledger_snapshot.positions)}",
            f"orders={len(paper.order_statuses)}",
            f"fills={len(paper.fills)}",
            f"reconciled={paper.reconciliation.reconciled}",
            "broker_order_history=passed",
        ),
    )


def _daily_close_schedule(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    preflight = artifacts.preflight
    soak = artifacts.soak
    guardrail = artifacts.schedule_guardrail
    schedule_check = (
        _check_by_name(preflight, "runtime_schedule") if preflight else None
    )
    if soak and soak.off_schedule_order_cycles:
        return _failed(
            "FR-08",
            "Strategy evaluation occurs only on approved daily-close schedule.",
            (f"off_schedule_order_cycles={soak.off_schedule_order_cycles}",),
            "Investigate off-schedule order cycles before continuing.",
        )
    if schedule_check is None:
        return _missing(
            "FR-08",
            "Strategy evaluation occurs only on approved daily-close schedule.",
            "Run preflight and schedule guardrail audit for schedule proof.",
        )
    if schedule_check.status == RuntimePreflightStatus.FAILED:
        return _failed(
            "FR-08",
            "Strategy evaluation occurs only on approved daily-close schedule.",
            (
                f"runtime_schedule={schedule_check.status.value}",
                *schedule_check.evidence,
            ),
            "Fix runtime schedule preflight failures before continuing.",
        )
    if guardrail is None:
        return _missing(
            "FR-08",
            "Strategy evaluation occurs only on approved daily-close schedule.",
            "Run python -m trading_app.runtime.schedule.",
        )
    coverage_gap = schedule_guardrail_coverage_gap(guardrail)
    if not guardrail.passed or coverage_gap:
        failed_checks = tuple(
            f"{check.name}={check.status.value}"
            for check in guardrail.checks
            if check.status == RuntimePreflightStatus.FAILED
        )
        return _failed(
            "FR-08",
            "Strategy evaluation occurs only on approved daily-close schedule.",
            (
                f"schedule_guardrail_status={guardrail.status.value}",
                f"unexpected={guardrail.unexpected_schedule_scenarios}",
                *failed_checks,
                *coverage_gap,
            ),
            (
                "Fix incomplete or failed schedule guardrails before scheduled "
                "paper orders resume."
            ),
        )
    evidence = [
        "runtime schedule preflight passed",
        "schedule_guardrail_audit=passed",
        f"approved_schedule_scenarios={guardrail.approved_schedule_scenarios}",
        f"protected_schedule_scenarios={guardrail.protected_schedule_scenarios}",
    ]
    if soak:
        evidence.append(f"off_schedule_order_cycles={soak.off_schedule_order_cycles}")
    return _proven(
        "FR-08",
        "Strategy evaluation occurs only on approved daily-close schedule.",
        tuple(evidence),
    )


def _order_blocking_guards(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    dry_run = _monitor_only_dry_run_report(artifacts)
    validation = artifacts.validation
    guardrail = artifacts.order_guardrail
    if dry_run is None:
        return _external(
            "FR-09",
            _REQ_ORDER_GUARDS,
        )
    if dry_run.monitor_only and dry_run.orders_submitted == 0:
        if guardrail is None:
            return _missing(
                "FR-09",
                _REQ_ORDER_GUARDS,
                "Run python -m trading_app.runtime.guardrails.",
            )
        coverage_gap = order_guardrail_coverage_gap(guardrail)
        if not guardrail.passed or coverage_gap:
            failed_checks = tuple(
                f"{check.name}={check.status.value}"
                for check in guardrail.checks
                if check.status == RuntimePreflightStatus.FAILED
            )
            return _failed(
                "FR-09",
                _REQ_ORDER_GUARDS,
                (
                    f"order_guardrail_status={guardrail.status.value}",
                    f"unexpected={guardrail.unexpected_order_scenarios}",
                    *failed_checks,
                    *coverage_gap,
                ),
                (
                    "Fix incomplete or failed order guardrails before scheduled "
                    "paper orders resume."
                ),
            )
        evidence = [
            "monitor-only dry run blocked orders",
            "order_guardrail_audit=passed",
            f"blocked_guardrail_scenarios={guardrail.blocked_order_scenarios}",
            f"source={_dry_run_source(artifacts, dry_run)}",
        ]
        if validation:
            evidence.append(
                f"validation orders_submitted={validation.orders_submitted}"
            )
        return _proven(
            "FR-09",
            _REQ_ORDER_GUARDS,
            tuple(evidence),
        )
    return _failed(
        "FR-09",
        _REQ_ORDER_GUARDS,
        (f"dry_run orders_submitted={dry_run.orders_submitted}",),
        "Re-run guardrail validation and verify monitor-only order blocking.",
    )


def _fill_integrity(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    fills = artifacts.fills
    fill_sync = artifacts.fill_sync
    if fill_sync is None:
        return _missing(
            "FR-10",
            "Fills update the internal ledger exactly once.",
            "Run python -m trading_app.runtime.fills.",
        )
    coverage_gap = fill_sync_coverage_gap(fill_sync)
    if not fill_sync.passed or coverage_gap:
        failed_checks = tuple(
            f"{check.name}={check.status.value}"
            for check in fill_sync.checks
            if check.status == RuntimePreflightStatus.FAILED
        )
        return _failed(
            "FR-10",
            "Fills update the internal ledger exactly once.",
            (
                f"fill_sync_status={fill_sync.status.value}",
                f"unexpected={fill_sync.unexpected_fill_scenarios}",
                *failed_checks,
                *coverage_gap,
            ),
            (
                "Fix incomplete or failed fill-sync scenarios before trusting "
                "broker fill ingestion."
            ),
        )
    if not fills:
        return _external(
            "FR-10",
            "Fills update the internal ledger exactly once.",
            evidence=(
                "fill_sync_audit=passed",
                f"incremental_fill_scenarios={fill_sync.incremental_fill_scenarios}",
                f"duplicate_fill_scenarios={fill_sync.duplicate_fill_scenarios}",
                "persisted_fill_count=0",
            ),
        )
    duplicate_ids = _duplicates(fill.id for fill in fills)
    if duplicate_ids:
        return _failed(
            "FR-10",
            "Fills update the internal ledger exactly once.",
            tuple(f"duplicate fill id={fill_id}" for fill_id in duplicate_ids),
            "Investigate duplicate fill journal entries and broker sync state.",
        )
    return _proven(
        "FR-10",
        "Fills update the internal ledger exactly once.",
        (
            "fill_sync_audit=passed",
            f"incremental_fill_scenarios={fill_sync.incremental_fill_scenarios}",
            f"duplicate_fill_scenarios={fill_sync.duplicate_fill_scenarios}",
            f"unique_fill_count={len(fills)}",
        ),
    )


def _restart_recovery_integrity(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    submissions = artifacts.submissions
    fills = artifacts.fills
    recovery = artifacts.recovery_audit
    if not submissions and not fills and recovery is None:
        return _external(
            "FR-11",
            _REQ_RESTART_RECOVERY,
        )
    if recovery is None:
        return _missing(
            "FR-11",
            _REQ_RESTART_RECOVERY,
            "Run python -m trading_app.runtime.recovery.",
        )
    stale_evidence = []
    if recovery.raw_submission_count != len(submissions):
        stale_evidence.append(
            "recovery raw_submission_count="
            f"{recovery.raw_submission_count} "
            f"current_submission_count={len(submissions)}"
        )
    if recovery.raw_fill_count != len(fills):
        stale_evidence.append(
            f"recovery raw_fill_count={recovery.raw_fill_count} "
            f"current_fill_count={len(fills)}"
        )
    if stale_evidence:
        return _failed(
            "FR-11",
            _REQ_RESTART_RECOVERY,
            tuple(stale_evidence),
            "Rerun the restart recovery audit after the latest order/fill sync.",
        )
    coverage_gap = recovery_coverage_gap(recovery)
    if not recovery.passed or coverage_gap:
        failed_checks = tuple(
            f"{check.name}={check.status.value}"
            for check in recovery.checks
            if check.status == RuntimePreflightStatus.FAILED
        )
        duplicate_evidence = (
            tuple(
                f"duplicate order id={value}" for value in recovery.duplicate_order_ids
            )
            + tuple(
                f"duplicate broker order id={value}"
                for value in recovery.duplicate_broker_order_ids
            )
            + tuple(
                f"duplicate fill id={value}" for value in recovery.duplicate_fill_ids
            )
        )
        return _failed(
            "FR-11",
            _REQ_RESTART_RECOVERY,
            (
                f"recovery audit status={recovery.status.value}",
                *failed_checks,
                *duplicate_evidence,
                *coverage_gap,
            ),
            (
                "Fix incomplete or failed restart recovery evidence before "
                "recovery is trusted."
            ),
        )
    duplicate_order_ids = _duplicates(submission.order.id for submission in submissions)
    duplicate_broker_ids = _duplicates(
        submission.broker_order.broker_order_id
        for submission in submissions
        if submission.broker_order is not None
    )
    duplicate_fills = _duplicates(fill.id for fill in fills)
    duplicate_evidence = (
        tuple(f"duplicate order id={order_id}" for order_id in duplicate_order_ids)
        + tuple(
            f"duplicate broker order id={broker_id}"
            for broker_id in duplicate_broker_ids
        )
        + tuple(f"duplicate fill id={fill_id}" for fill_id in duplicate_fills)
    )
    if duplicate_evidence:
        return _failed(
            "FR-11",
            _REQ_RESTART_RECOVERY,
            duplicate_evidence,
            (
                "Clean duplicate persisted order or fill evidence before recovery "
                "is trusted."
            ),
        )
    return _proven(
        "FR-11",
        _REQ_RESTART_RECOVERY,
        (
            "recovery_audit=passed",
            f"raw_submission_count={recovery.raw_submission_count}",
            f"recovered_submission_count={recovery.recovered_submission_count}",
            f"raw_fill_count={recovery.raw_fill_count}",
            f"recovered_fill_count={recovery.recovered_fill_count}",
        ),
    )


def _daily_report_written(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    report = artifacts.daily_report
    if report is not None:
        path = artifacts.daily_report_path
        if report.report_metadata is None:
            return _missing(
                "FR-12",
                "Daily report is written after market close.",
                "Persist daily reports with report metadata and artifact path.",
            )
        if path is None:
            return _missing(
                "FR-12",
                "Daily report is written after market close.",
                "Persist the written daily report Markdown path.",
            )
        if not path.exists():
            return _failed(
                "FR-12",
                "Daily report is written after market close.",
                (f"daily_report_path={path}", "path_exists=false"),
                "Regenerate the daily Markdown report and persist its path.",
            )
        metadata_path = report.report_metadata.markdown_path
        if metadata_path is None:
            return _missing(
                "FR-12",
                "Daily report is written after market close.",
                "Persist report metadata with the Markdown path.",
            )
        if Path(metadata_path) != path:
            return _failed(
                "FR-12",
                "Daily report is written after market close.",
                (
                    f"daily_report_path={path}",
                    f"metadata_markdown_path={metadata_path}",
                ),
                "Regenerate daily report metadata so the persisted path matches.",
            )
        if not _generated_after_close(report.generated_at):
            return _failed(
                "FR-12",
                "Daily report is written after market close.",
                (f"generated_at={report.generated_at.isoformat()}",),
                "Generate the daily report only after the regular market close.",
            )
        if _local_report_date(report.generated_at) != report.trading_day:
            return _failed(
                "FR-12",
                "Daily report is written after market close.",
                (
                    f"generated_local_date={_local_report_date(report.generated_at)}",
                    f"trading_day={report.trading_day.isoformat()}",
                ),
                "Generate the report for the matching U.S. trading day.",
            )
        if report.data_quality_report is None:
            return _missing(
                "FR-12",
                "Daily report is written after market close.",
                "Persist daily reports with market-data quality evidence.",
            )
        if report.data_quality_report.failures:
            return _failed(
                "FR-12",
                "Daily report is written after market close.",
                (
                    f"data_quality={report.data_quality_report.status.value}",
                    f"failures={report.data_quality_report.failures}",
                ),
                "Resolve market-data quality failures before using the report.",
            )
        if report.active_strategy_definition is None:
            return _missing(
                "FR-12",
                "Daily report is written after market close.",
                "Persist daily reports with the active-model dossier.",
            )
        return _proven(
            "FR-12",
            "Daily report is written after market close.",
            (
                f"trading_day={report.trading_day.isoformat()}",
                f"generated_at={report.generated_at.isoformat()}",
                f"markdown_path={path}",
                f"data_quality={report.data_quality_report.status.value}",
                (
                    "active_model="
                    f"{report.active_strategy_definition.strategy_id}:"
                    f"{report.active_strategy_definition.version}"
                ),
            ),
        )
    snapshot = artifacts.snapshot
    if snapshot and snapshot.daily_report is not None:
        return _missing(
            "FR-12",
            "Daily report is written after market close.",
            (
                "Persist the generated daily report and Markdown path, not only "
                "snapshot state."
            ),
        )
    validation = artifacts.validation
    if validation and validation.report_written:
        return _missing(
            "FR-12",
            "Daily report is written after market close.",
            (
                "Persist the written daily report artifact with data-quality "
                "evidence and active-model dossier."
            ),
        )
    return _external(
        "FR-12",
        "Daily report is written after market close.",
    )


def _nightly_learning_after_report(
    artifacts: _Artifacts,
) -> FunctionalRequirementEvidence:
    snapshot = artifacts.snapshot
    if (
        snapshot
        and artifacts.daily_report is not None
        and snapshot.nightly_learning is not None
    ):
        report_generated_at = _daily_report_generated_at(artifacts.daily_report)
        learning = snapshot.nightly_learning
        if learning.as_of < report_generated_at:
            return _failed(
                "FR-13",
                "Nightly learning runs after reporting in recommendation-only mode.",
                (
                    f"daily_report_generated_at={report_generated_at.isoformat()}",
                    f"learning_as_of={learning.as_of.isoformat()}",
                ),
                "Run nightly learning only after the daily report is written.",
            )
        if not learning.active_model_unchanged:
            return _failed(
                "FR-13",
                "Nightly learning runs after reporting in recommendation-only mode.",
                (
                    f"learning_id={learning.id}",
                    "active_model_unchanged=false",
                ),
                "Keep nightly learning advisory and rerun model-governance review.",
            )
        missing_manual_review = tuple(
            recommendation.model.key
            for recommendation in learning.recommendations
            if not recommendation.manual_review_required
        )
        if missing_manual_review:
            return _failed(
                "FR-13",
                "Nightly learning runs after reporting in recommendation-only mode.",
                tuple(f"missing_manual_review={key}" for key in missing_manual_review),
                "Require manual review for every nightly learning recommendation.",
            )
        governance = artifacts.model_governance
        if governance is None:
            return _missing(
                "FR-13",
                "Nightly learning runs after reporting in recommendation-only mode.",
                "Run python -m trading_app.runtime.governance.",
            )
        governance_gap = model_governance_coverage_gap(governance)
        if not governance.passed or governance_gap:
            failed_checks = tuple(
                f"{check.name}={check.status.value}"
                for check in governance.checks
                if check.status == RuntimePreflightStatus.FAILED
            )
            return _failed(
                "FR-13",
                "Nightly learning runs after reporting in recommendation-only mode.",
                (
                    f"model_governance_status={governance.status.value}",
                    *failed_checks,
                    *governance_gap,
                ),
                "Fix model-governance failures before nightly learning is trusted.",
            )
        return _proven(
            "FR-13",
            "Nightly learning runs after reporting in recommendation-only mode.",
            (
                f"learning_id={learning.id}",
                f"daily_report_generated_at={report_generated_at.isoformat()}",
                f"learning_as_of={learning.as_of.isoformat()}",
                "recommendation_only=true",
                "all_recommendations_manual_review=true",
                "model_governance=passed",
            ),
        )
    validation = artifacts.validation
    if validation and validation.report_written and validation.nightly_learning_ran:
        return _missing(
            "FR-13",
            "Nightly learning runs after reporting in recommendation-only mode.",
            (
                "Persist runtime snapshot evidence with daily report, nightly "
                "learning, and model-governance audit."
            ),
        )
    return _external(
        "FR-13",
        "Nightly learning runs after reporting in recommendation-only mode.",
    )


def _active_model_locked(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    snapshot = artifacts.snapshot
    learning = snapshot.nightly_learning if snapshot else None
    if learning is None:
        return _missing(
            "FR-14",
            "Active model does not change without explicit approval.",
            "Run nightly learning or validation with learning proof.",
        )
    governance = artifacts.model_governance
    if governance is None:
        return _missing(
            "FR-14",
            "Active model does not change without explicit approval.",
            "Run python -m trading_app.runtime.governance.",
        )
    governance_gap = model_governance_coverage_gap(governance)
    if not governance.passed or governance_gap:
        failed_checks = tuple(
            f"{check.name}={check.status.value}"
            for check in governance.checks
            if check.status == RuntimePreflightStatus.FAILED
        )
        return _failed(
            "FR-14",
            "Active model does not change without explicit approval.",
            (
                f"model governance status={governance.status.value}",
                *failed_checks,
                *(
                    f"authority increase={item}"
                    for item in governance.unreviewed_authority_increases
                ),
                *governance_gap,
            ),
            "Fix model-governance failures before promotion review.",
        )
    if learning.active_model_unchanged:
        return _proven(
            "FR-14",
            "Active model does not change without explicit approval.",
            (
                "active_model_unchanged=true",
                "model_governance=passed",
                f"recommendations={governance.recommendation_count}",
            ),
        )
    return _failed(
        "FR-14",
        "Active model does not change without explicit approval.",
        ("active_model_unchanged=false",),
        "Review model registry mutation and promotion controls.",
    )


def _operator_controls_alerts(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    snapshot = artifacts.snapshot
    if snapshot is None or snapshot.control_state is None:
        return _missing(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            "Persist runtime snapshot with operator control state.",
        )
    dashboard_snapshot = artifacts.dashboard_snapshot
    if dashboard_snapshot is None:
        return _missing(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            "Persist a dashboard snapshot with operator controls and alerts.",
        )
    if not _control_state_matches(
        dashboard_snapshot.control_state,
        snapshot.control_state,
    ) or not _alert_ids_match(dashboard_snapshot.alerts, snapshot.alerts):
        return _failed(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            (
                f"dashboard_alerts={len(dashboard_snapshot.alerts)}",
                f"runtime_alerts={len(snapshot.alerts)}",
                (
                    "dashboard_paused="
                    f"{_field(dashboard_snapshot.control_state, 'paused', 'missing')}"
                ),
                f"runtime_paused={snapshot.control_state.paused}",
            ),
            "Regenerate dashboard state from the runtime snapshot provider.",
        )
    consistency = artifacts.dashboard_consistency
    if consistency is None:
        return _missing(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            "Run python -m trading_app.runtime.dashboard_audit.",
        )
    consistency_gap = dashboard_consistency_coverage_gap(consistency)
    failed_checks = tuple(
        check.name
        for check in consistency.checks
        if check.name in {"operator_controls", "runtime_alerts", "runtime_health"}
        and check.status == RuntimePreflightStatus.FAILED
    )
    if failed_checks or consistency_gap:
        return _failed(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            (
                *tuple(
                    f"dashboard_consistency_failed={name}" for name in failed_checks
                ),
                *consistency_gap,
            ),
            "Fix dashboard operator-state mismatches and rerun dashboard audit.",
        )
    visual = artifacts.dashboard_visual
    if visual is None:
        return _missing(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            "Run python -m trading_app.runtime.dashboard_visual.",
        )
    visual_gap = dashboard_visual_coverage_gap(visual)
    failed_visual_checks = tuple(
        check.name
        for check in visual.checks
        if check.name
        in {"operator_controls_present", "alerts_and_degraded_states_visible"}
        and check.status == RuntimePreflightStatus.FAILED
    )
    if failed_visual_checks or visual_gap:
        return _failed(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            (
                *tuple(
                    f"dashboard_visual_failed={name}" for name in failed_visual_checks
                ),
                *visual_gap,
            ),
            "Fix rendered operator controls and alert surfaces, then rerun the audit.",
        )
    lifecycle = artifacts.lifecycle_drill
    if lifecycle is None:
        return _missing(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            "Run python -m trading_app.runtime.lifecycle.",
        )
    lifecycle_gap = lifecycle_coverage_gap(lifecycle)
    if not lifecycle.passed or lifecycle_gap:
        return _failed(
            "FR-15",
            "Alerts and operator controls are visible and actionable.",
            (
                f"lifecycle_drill_status={lifecycle.status.value}",
                f"controls={lifecycle.operator_control_count}",
                f"emergency_stop={lifecycle.emergency_stop_confirmed}",
                *lifecycle_gap,
            ),
            "Exercise dashboard/operator controls and rerun lifecycle drill.",
        )
    return _proven(
        "FR-15",
        "Alerts and operator controls are visible and actionable.",
        (
            f"paused={snapshot.control_state.paused}",
            f"paper_kill_switch={snapshot.control_state.paper_kill_switch_enabled}",
            f"alerts={len(snapshot.alerts)}",
            "dashboard_controls_match_runtime=true",
            "dashboard_alerts_match_runtime=true",
            "dashboard_visual_controls=passed",
            "lifecycle_drill=passed",
        ),
    )


def _iex_labeling(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    snapshot = artifacts.snapshot
    latest = snapshot.latest_prices if snapshot else None
    if latest is None:
        return _missing(
            "FR-16",
            "IEX/free data is clearly labeled development-grade.",
            "Persist latest-price state with feed provenance.",
        )
    if latest.feed != DataFeed.IEX:
        return _proven(
            "FR-16",
            "IEX/free data is clearly labeled development-grade.",
            (f"feed={latest.feed.value}",),
        )
    if latest.warning and "development-grade" in latest.warning:
        audit_gap = _data_quality_audit_requirement(
            "FR-16",
            "IEX/free data is clearly labeled development-grade.",
            artifacts,
        )
        if audit_gap is not None:
            return audit_gap
        return _proven(
            "FR-16",
            "IEX/free data is clearly labeled development-grade.",
            (
                latest.warning,
                "data_quality_audit=passed",
                (
                    "latest_price_scenarios="
                    f"{artifacts.data_quality_audit.latest_price_scenarios}"
                ),
            ),
        )
    return _failed(
        "FR-16",
        "IEX/free data is clearly labeled development-grade.",
        ("feed=IEX without development-grade warning",),
        "Attach IEX development-grade warning to latest-price state and reports.",
    )


def _paper_only_boundary(artifacts: _Artifacts) -> FunctionalRequirementEvidence:
    preflight = artifacts.preflight
    snapshot = artifacts.snapshot
    secret_scan = artifacts.secret_scan
    boundary_check = _check_by_name(preflight, "paper_boundary") if preflight else None
    if secret_scan is None:
        return _missing(
            "FR-17",
            "App never creates a real-money trading path during paper phase.",
            "Run python -m trading_app.runtime.security with Alpaca credentials set.",
        )
    if not secret_scan.passed:
        return _failed(
            "FR-17",
            "App never creates a real-money trading path during paper phase.",
            (
                "secret scan failed",
                f"findings={len(secret_scan.findings)}",
            ),
            "Remove leaked credential artifacts and rerun safety checks.",
        )
    missing_secret_names = _missing_secret_names(secret_scan)
    if missing_secret_names:
        return _missing(
            "FR-17",
            "App never creates a real-money trading path during paper phase.",
            (
                "Rerun python -m trading_app.runtime.security with "
                f"{', '.join(missing_secret_names)} available in the environment."
            ),
        )
    operations = artifacts.operations_readiness
    if operations is None:
        return _missing(
            "FR-17",
            "App never creates a real-money trading path during paper phase.",
            "Run python -m trading_app.runtime.ops --audit.",
        )
    operations_gap = operations_coverage_gap(operations)
    if not operations.passed or operations_gap:
        return _failed(
            "FR-17",
            "App never creates a real-money trading path during paper phase.",
            (
                f"operations readiness status={operations.status.value}",
                f"checks={len(operations.checks)}",
                *operations_gap,
            ),
            "Fix incomplete or failed operations-readiness evidence before continuing.",
        )
    if (
        _check_passed(boundary_check)
        and snapshot is not None
        and snapshot.mode == "Alpaca Paper"
    ):
        evidence = [
            "paper_boundary preflight passed",
            f"snapshot mode={snapshot.mode}",
            "operations_readiness=passed",
        ]
        evidence.append(f"secret_scan={secret_scan.status.value}")
        evidence.append(f"secret_scan_roots={len(secret_scan.scan_roots)}")
        evidence.append(
            "secret_names_checked=" + ",".join(secret_scan.secret_names_checked)
        )
        return _proven(
            "FR-17",
            "App never creates a real-money trading path during paper phase.",
            tuple(evidence),
        )
    return _missing(
        "FR-17",
        "App never creates a real-money trading path during paper phase.",
        "Run preflight and persist Alpaca Paper runtime snapshot.",
    )


def _broker_statement_review(
    artifacts: _Artifacts,
) -> FunctionalRequirementEvidence:
    report = artifacts.statement_reconciliation
    if report is None:
        return _external(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
        )
    if report.statement.provider != "alpaca-paper":
        return _external(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
            evidence=(f"statement_provider={report.statement.provider}",),
        )
    if _contains_fixture_marker(report.statement.source):
        return _external(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
            evidence=(f"statement_source={report.statement.source}",),
        )
    if not report.statement_path:
        return _external(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
            evidence=("statement_path=missing",),
        )
    if not Path(report.statement_path).exists():
        return _external(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
            evidence=(f"statement_path_missing={report.statement_path}",),
        )
    if not report.statement_sha256:
        return _external(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
            evidence=(f"statement_sha256=missing path={report.statement_path}",),
        )
    current_statement_sha256 = _sha256_path(Path(report.statement_path))
    if current_statement_sha256 != report.statement_sha256:
        return _external(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
            evidence=(
                f"statement_sha256_mismatch={report.statement_path}",
                f"expected={report.statement_sha256}",
                f"actual={current_statement_sha256}",
            ),
        )
    if report.reconciled:
        return _proven(
            "FR-18",
            "Post-run broker statement reconciliation is clean.",
            (
                f"statement={report.statement.statement_id}",
                f"provider={report.statement.provider}",
                f"statement_path={report.statement_path}",
                f"statement_sha256={report.statement_sha256}",
                f"issues={len(report.issues)}",
            ),
        )
    issue_types = sorted({issue.issue_type.value for issue in report.issues})
    return _failed(
        "FR-18",
        "Post-run broker statement reconciliation is clean.",
        (
            f"statement={report.statement.statement_id}",
            f"issues={len(report.issues)}",
            f"issue_types={','.join(issue_types)}",
        ),
        (
            "Investigate broker statement mismatches before calling the paper app "
            "functional."
        ),
    )


def _read_model(path: Path, model_type: type[BaseModel]):
    if not path.exists():
        return None
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path, model_type: type[BaseModel]) -> list:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(model_type.model_validate_json(line))
    return records


def _check_by_name(report: RuntimePreflightReport | None, name: str):
    if report is None:
        return None
    return next((check for check in report.checks if check.name == name), None)


def _check_passed(check) -> bool:
    return check is not None and check.status == RuntimePreflightStatus.PASSED


def _monitor_only_dry_run_report(
    artifacts: _Artifacts,
) -> RuntimeDryRunReport | None:
    if artifacts.dry_run is not None:
        return artifacts.dry_run
    validation = artifacts.validation
    if validation is None:
        return None
    return validation.monitor_dry_run_report


def _dry_run_source(artifacts: _Artifacts, dry_run: RuntimeDryRunReport) -> str:
    if artifacts.dry_run == dry_run:
        return "standalone-dry-run"
    return "validation-monitor-dry-run"


def _validation_has_alpaca_broker_proof(
    validation: RuntimeValidationReport | None,
) -> bool:
    return bool(
        validation
        and validation.status != RuntimePreflightStatus.FAILED
        and validation.credential_required
        and "alpaca-paper" in validation.broker_providers
        and not _contains_fixture_marker(validation.id)
        and not validation_coverage_gap(validation)
    )


def _dry_run_has_alpaca_broker_proof(
    dry_run: RuntimeDryRunReport,
    validation: RuntimeValidationReport | None,
) -> bool:
    return (
        dry_run.broker_provider == "alpaca-paper"
        or _validation_has_alpaca_broker_proof(validation)
    )


def _duplicates(values) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _market_data_quality_report(artifacts: _Artifacts):
    snapshot_report = (
        artifacts.snapshot.daily_report.data_quality_report
        if artifacts.snapshot is not None
        and artifacts.snapshot.daily_report is not None
        else None
    )
    if snapshot_report is not None:
        return snapshot_report
    dashboard_report = (
        artifacts.dashboard_snapshot.daily_report.data_quality_report
        if artifacts.dashboard_snapshot is not None
        else None
    )
    return dashboard_report


def _data_quality_audit_requirement(
    id: str,  # noqa: A002
    requirement: str,
    artifacts: _Artifacts,
) -> FunctionalRequirementEvidence | None:
    audit = artifacts.data_quality_audit
    if audit is None:
        return _missing(
            id,
            requirement,
            "Run python -m trading_app.runtime.data_quality.",
        )
    coverage_gap = data_quality_coverage_gap(audit)
    if coverage_gap:
        return _failed(
            id,
            requirement,
            (
                f"data_quality_audit_status={audit.status.value}",
                f"latest_price_scenarios={audit.latest_price_scenarios}",
                f"daily_bar_scenarios={audit.daily_bar_scenarios}",
                "symbol_universe_scenarios="
                f"{getattr(audit, 'symbol_universe_scenarios', 0)}",
                f"checks={len(audit.checks)}",
                *coverage_gap,
            ),
            (
                "Rerun the full market-data quality audit with latest-price and "
                "daily-bar coverage before completion."
            ),
        )
    if not audit.passed:
        failed_checks = tuple(
            f"{check.name}={check.status.value}"
            for check in audit.checks
            if check.status == RuntimePreflightStatus.FAILED
        )
        return _failed(
            id,
            requirement,
            (
                f"data_quality_audit_status={audit.status.value}",
                f"failed_quality_scenarios={audit.failed_quality_scenarios}",
                *failed_checks,
            ),
            "Fix failed market-data quality audit scenarios.",
        )
    return None


def _daily_report_generated_at(report) -> datetime:
    metadata = getattr(report, "report_metadata", None)
    if metadata is not None and metadata.generated_at is not None:
        return metadata.generated_at
    return report.generated_at


def _generated_after_close(value: datetime) -> bool:
    return value.astimezone(MARKET_TZ).time() >= REGULAR_CLOSE


def _local_report_date(value: datetime):
    return value.astimezone(MARKET_TZ).date()


def _control_state_matches(dashboard_state, runtime_state) -> bool:
    if dashboard_state is None or runtime_state is None:
        return False
    return (
        _field(dashboard_state, "paused") == _field(runtime_state, "paused")
        and _field(dashboard_state, "paper_kill_switch_enabled")
        == _field(runtime_state, "paper_kill_switch_enabled")
        and _same_timestamp_value(
            _field(dashboard_state, "updated_at"),
            _field(runtime_state, "updated_at"),
        )
        and _field(dashboard_state, "updated_by") == _field(runtime_state, "updated_by")
        and _field(dashboard_state, "reason") == _field(runtime_state, "reason")
    )


def _same_timestamp_value(left, right) -> bool:
    left_dt = _coerce_datetime(left)
    right_dt = _coerce_datetime(right)
    if left_dt is None or right_dt is None:
        return left == right
    return left_dt == right_dt


def _coerce_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _alert_ids_match(dashboard_alerts, runtime_alerts) -> bool:
    return tuple(_field(alert, "id", "missing") for alert in dashboard_alerts) == tuple(
        _field(alert, "id", "missing") for alert in runtime_alerts
    )


def _proven(
    id: str,  # noqa: A002
    requirement: str,
    evidence: tuple[str, ...] | list[str],
) -> FunctionalRequirementEvidence:
    return FunctionalRequirementEvidence(
        id=id,
        requirement=requirement,
        status=FunctionalRequirementStatus.PROVEN,
        evidence=tuple(evidence),
        remediation="No action required for this requirement.",
    )


def _missing(
    id: str,  # noqa: A002
    requirement: str,
    remediation: str,
) -> FunctionalRequirementEvidence:
    return FunctionalRequirementEvidence(
        id=id,
        requirement=requirement,
        status=FunctionalRequirementStatus.MISSING,
        remediation=remediation,
    )


def _external(
    id: str,  # noqa: A002
    requirement: str,
    evidence: tuple[str, ...] = (),
) -> FunctionalRequirementEvidence:
    return FunctionalRequirementEvidence(
        id=id,
        requirement=requirement,
        status=FunctionalRequirementStatus.EXTERNAL_REQUIRED,
        evidence=evidence,
        remediation=(
            "Run a real Alpaca paper validation or full-day soak and persist "
            "the resulting evidence."
        ),
    )


def _failed(
    id: str,  # noqa: A002
    requirement: str,
    evidence: tuple[str, ...],
    remediation: str,
) -> FunctionalRequirementEvidence:
    return FunctionalRequirementEvidence(
        id=id,
        requirement=requirement,
        status=FunctionalRequirementStatus.FAILED,
        evidence=evidence,
        remediation=remediation,
    )


def _summary(
    *,
    passed: bool,
    proven: int,
    total: int,
    missing: int,
    failed: int,
    external: int,
) -> str:
    if passed:
        return f"All {total} functional paper-app requirements are proven."
    return (
        f"{proven}/{total} requirement(s) proven; {missing} missing, "
        f"{failed} failed, and {external} require external runtime evidence."
    )


def _completion_next_action(report: FunctionalCompletionAuditReport) -> str:
    if report.failed_count:
        return (
            "Do not treat the paper app as functional. Fix failed requirements, "
            "rerun validation, and rerun the completion audit."
        )
    if report.missing_count or report.external_required_count:
        return (
            "Do not treat the paper app as fully proven yet. Produce the missing "
            "runtime artifacts or complete the required real Alpaca paper evidence."
        )
    return (
        "All functional paper-app requirements are proven by local evidence. "
        "Keep live-money trading disabled unless a separate live-readiness review "
        "is explicitly approved later."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _contains_fixture_marker(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.casefold()
    return "fixture" in normalized or normalized.startswith("demo-")


def _missing_secret_names(secret_scan: RuntimeSecretScanReport) -> tuple[str, ...]:
    checked = set(secret_scan.secret_names_checked)
    return tuple(sorted(_REQUIRED_SECRET_NAMES - checked))


def _dashboard_demo_provenance_markers(
    snapshot: OperatorDashboardSnapshot,
) -> tuple[str, ...]:
    markers = tuple(_collect_demo_markers(snapshot))
    return markers[:8]


def _collect_demo_markers(value, path: str = "dashboard") -> list[str]:
    if _is_dashboard_audit_artifact_path(path):
        return []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        markers: list[str] = []
        for key, child in value.items():
            markers.extend(_collect_demo_markers(child, f"{path}.{key}"))
        return markers
    if isinstance(value, (list, tuple)):
        markers = []
        for index, child in enumerate(value):
            markers.extend(_collect_demo_markers(child, f"{path}[{index}]"))
        return markers
    if isinstance(value, str) and _contains_demo_provenance(value):
        return [f"demo_provenance={path}"]
    return []


def _contains_demo_provenance(value: str) -> bool:
    normalized = value.casefold()
    return "demo" in normalized or "fixture" in normalized or "mock" in normalized


def _is_dashboard_audit_artifact_path(path: str) -> bool:
    """Ignore embedded audit reports when scanning dashboard runtime provenance."""
    return path.startswith(("dashboard.completion_audit", "dashboard.final_acceptance"))


if __name__ == "__main__":
    raise SystemExit(main())
