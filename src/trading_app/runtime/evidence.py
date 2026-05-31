"""Operator evidence bundle for paper-runtime review."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from trading_app.runtime.audit_coverage import (
    artifact_integrity_coverage_gap,
    broker_order_history_coverage_gap,
    credentialed_session_coverage_gap,
    dashboard_consistency_coverage_gap,
    dashboard_visual_coverage_gap,
    data_quality_coverage_gap,
    evidence_coherence_coverage_gap,
    fill_sync_coverage_gap,
    functional_completion_coverage_gap,
    lifecycle_coverage_gap,
    model_governance_coverage_gap,
    operations_coverage_gap,
    order_guardrail_coverage_gap,
    recovery_coverage_gap,
    schedule_guardrail_coverage_gap,
    validation_coverage_gap,
)
from trading_app.runtime.models import (
    RuntimeEvidenceBundleItem,
    RuntimeEvidenceBundleReport,
    RuntimeHealthStatus,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

MARKET_TZ = ZoneInfo("America/New_York")
REGULAR_CLOSE = dt_time(hour=16)
_REQUIRED_SECRET_NAMES = frozenset({"ALPACA_API_KEY", "ALPACA_SECRET_KEY"})


class RuntimeEvidenceBundleBuilder:
    """Build a single review dossier from persisted runtime artifacts."""

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

    def build(self, *, as_of: datetime | None = None) -> RuntimeEvidenceBundleReport:
        now = as_of or datetime.now(tz=UTC)
        recovered = self.store.recover()
        completion = self.store.read_completion_audit_report()
        soak = self.store.read_soak_evidence_report()
        secret_scan = self.store.read_secret_scan_report()
        statement = self.store.read_statement_reconciliation_report()
        artifact_integrity = self.store.read_artifact_integrity_report()
        artifact_integrity_path = self.store.read_artifact_integrity_report_path()
        dashboard_consistency = self.store.read_dashboard_consistency_report()
        dashboard_consistency_path = self.store.read_dashboard_consistency_report_path()
        dashboard_visual = self.store.read_dashboard_visual_report()
        dashboard_visual_path = self.store.read_dashboard_visual_report_path()
        evidence_coherence = self.store.read_evidence_coherence_report()
        evidence_coherence_path = self.store.read_evidence_coherence_report_path()
        data_quality_audit = self.store.read_data_quality_audit_report()
        data_quality_audit_path = self.store.read_data_quality_audit_report_path()
        broker_order_history = self.store.read_broker_order_history_report()
        broker_order_history_path = self.store.read_broker_order_history_report_path()
        recovery_audit = self.store.read_recovery_audit_report()
        recovery_audit_path = self.store.read_recovery_audit_report_path()
        operations_readiness = self.store.read_operations_readiness_report()
        operations_readiness_path = self.store.read_operations_readiness_report_path()
        lifecycle_drill = self.store.read_lifecycle_drill_report()
        lifecycle_drill_path = self.store.read_lifecycle_drill_report_path()
        credentialed_session = self.store.read_credentialed_session_report()
        credentialed_session_path = self.store.read_credentialed_session_report_path()
        model_governance = self.store.read_model_governance_report()
        model_governance_path = self.store.read_model_governance_report_path()
        order_guardrail = self.store.read_order_guardrail_report()
        order_guardrail_path = self.store.read_order_guardrail_report_path()
        schedule_guardrail = self.store.read_schedule_guardrail_report()
        schedule_guardrail_path = self.store.read_schedule_guardrail_report_path()
        fill_sync = self.store.read_fill_sync_report()
        fill_sync_path = self.store.read_fill_sync_report_path()
        items = _review_path_checked_items(
            self._preflight_item(recovered.preflight_report),
            self._operations_readiness_item(
                operations_readiness,
                operations_readiness_path,
            ),
            self._lifecycle_drill_item(lifecycle_drill, lifecycle_drill_path),
            self._dry_run_item(recovered.dry_run_report),
            self._validation_item(recovered.validation_report),
            self._soak_item(soak),
            self._runtime_snapshot_item(recovered),
            self._recovery_audit_item(recovery_audit, recovery_audit_path),
            self._dashboard_item(recovered.dashboard_snapshot),
            self._dashboard_consistency_item(
                dashboard_consistency,
                dashboard_consistency_path,
            ),
            self._dashboard_visual_item(dashboard_visual, dashboard_visual_path),
            self._data_quality_audit_item(
                data_quality_audit,
                data_quality_audit_path,
            ),
            self._broker_order_history_item(
                broker_order_history,
                broker_order_history_path,
            ),
            self._credentialed_session_item(
                credentialed_session,
                credentialed_session_path,
            ),
            self._evidence_coherence_item(
                evidence_coherence,
                evidence_coherence_path,
            ),
            self._artifact_integrity_item(
                artifact_integrity,
                artifact_integrity_path,
            ),
            self._health_item(recovered.health_report, recovered.health_report_path),
            self._daily_report_item(
                recovered.daily_report,
                recovered.daily_report_path,
            ),
            self._learning_item(
                recovered.nightly_learning,
                recovered.learning_report_path,
                recovered.daily_report,
            ),
            self._model_governance_item(model_governance, model_governance_path),
            self._schedule_guardrail_item(
                schedule_guardrail,
                schedule_guardrail_path,
            ),
            self._order_guardrail_item(order_guardrail, order_guardrail_path),
            self._fill_sync_item(fill_sync, fill_sync_path),
            self._secret_scan_item(secret_scan),
            self._statement_item(statement, recovered.statement_reconciliation_path),
            self._completion_item(completion),
        )
        required_count = sum(1 for item in items if item.required)
        passed_count = sum(
            1 for item in items if item.status == RuntimePreflightStatus.PASSED
        )
        warning_count = sum(
            1 for item in items if item.status == RuntimePreflightStatus.WARNING
        )
        failed_count = sum(
            1 for item in items if item.status == RuntimePreflightStatus.FAILED
        )
        missing_required_count = sum(
            1
            for item in items
            if item.required
            and item.status == RuntimePreflightStatus.FAILED
            and "missing" in item.summary.lower()
        )
        status = (
            RuntimePreflightStatus.FAILED
            if failed_count
            else RuntimePreflightStatus.WARNING
            if warning_count
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimeEvidenceBundleReport(
            as_of=now,
            status=status,
            ready_for_operator_review=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            items=items,
            required_count=required_count,
            passed_count=passed_count,
            warning_count=warning_count,
            failed_count=failed_count,
            missing_required_count=missing_required_count,
            summary=_summary(status, passed_count, len(items), failed_count),
        )
        if self.persist_report:
            markdown_path = write_evidence_bundle_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_evidence_bundle_report(
                report,
                markdown_path=markdown_path,
            )
        return report

    def _preflight_item(self, report) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "preflight",
                "Preflight",
                "Run python -m trading_app.runtime.preflight.",
            )
        passed = bool(report.can_start)
        return _item(
            "preflight",
            "Preflight",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(self.store.state_dir / "latest-preflight-report.json"),
            evidence=(
                f"status={report.status.value}",
                f"warnings={report.warnings}",
                f"failures={report.failures}",
            ),
            next_action="Resolve preflight failures before runtime startup."
            if not passed
            else "No action required.",
        )

    def _operations_readiness_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "operations_readiness",
                "Operations Readiness Audit",
                "Run python -m trading_app.runtime.ops --audit.",
            )
        coverage_gap = operations_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "operations_readiness",
            "Operations Readiness Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"dashboard_url={report.dashboard_url}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action="Fix operating posture and rerun operations readiness."
            if not passed
            else "No action required.",
        )

    def _lifecycle_drill_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "lifecycle_drill",
                "Lifecycle Drill",
                "Run python -m trading_app.runtime.lifecycle.",
            )
        coverage_gap = lifecycle_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "lifecycle_drill",
            "Lifecycle Drill",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"controls={report.operator_control_count}",
                f"emergency_stop={report.emergency_stop_confirmed}",
                f"shutdown_documented={report.shutdown_procedure_documented}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action=(
                "Exercise startup, shutdown, emergency-stop, and dashboard controls "
                "before operator signoff."
            )
            if not passed
            else "No action required.",
        )

    def _credentialed_session_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "credentialed_session",
                "Credentialed Session Proof",
                "Run python -m trading_app.runtime.session_proof.",
            )
        coverage_gap = credentialed_session_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "credentialed_session",
            "Credentialed Session Proof",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"validation={report.validation_id or 'missing'}",
                f"account={report.paper_account_id or 'missing'}",
                f"external_sources={report.external_source_count}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action="Fix credentialed session provenance before operator review."
            if not passed
            else "No action required.",
        )

    def _dry_run_item(self, report) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "monitor_dry_run",
                "Monitor-Only Dry Run",
                "Run python -m trading_app.runtime.dry_run.",
            )
        safe = (
            report.can_start_supervised_runtime
            and report.monitor_only
            and report.orders_submitted == 0
        )
        return _item(
            "monitor_dry_run",
            "Monitor-Only Dry Run",
            RuntimePreflightStatus.PASSED if safe else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(self.store.state_dir / "latest-dry-run-report.json"),
            evidence=(
                f"monitor_only={report.monitor_only}",
                f"orders_submitted={report.orders_submitted}",
            ),
            next_action="Run a monitor-only dry run with zero submitted orders."
            if not safe
            else "No action required.",
        )

    def _validation_item(self, report) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "validation_report",
                "Supervised Validation",
                "Run python -m trading_app.runtime.validation.",
            )
        coverage_gap = validation_coverage_gap(report)
        passed = report.status != RuntimePreflightStatus.FAILED and not coverage_gap
        return _item(
            "validation_report",
            "Supervised Validation",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=report.markdown_path,
            evidence=(
                f"latest_prices_refreshed={report.latest_prices_refreshed}",
                f"broker_synced={report.broker_synced}",
                f"orders_submitted={report.orders_submitted}",
                f"checklist_items={len(report.checklist)}",
                *coverage_gap,
            ),
            next_action="Resolve validation failures or missing checklist evidence."
            if not passed
            else "No action required.",
        )

    def _soak_item(self, report) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "soak_evidence",
                "Full-Day Plus Overnight Soak",
                "Run python -m trading_app.runtime.soak after a supervised soak.",
            )
        return _item(
            "soak_evidence",
            "Full-Day Plus Overnight Soak",
            report.status,
            f"Duration {report.duration_hours:.2f} hours; cycles {report.cycle_count}.",
            path=str(self.store.state_dir / "latest-soak-evidence-report.json"),
            evidence=(
                f"market_cycles={report.market_cycle_count}",
                f"overnight_cycles={report.overnight_cycle_count}",
                f"off_schedule_order_cycles={report.off_schedule_order_cycles}",
            ),
            next_action="Review warning-status soak evidence before operator signoff."
            if report.status == RuntimePreflightStatus.WARNING
            else "Complete a clean full-day plus overnight soak."
            if report.status == RuntimePreflightStatus.FAILED
            else "No action required.",
        )

    def _order_guardrail_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "order_guardrails",
                "Order Guardrail Audit",
                "Run python -m trading_app.runtime.guardrails.",
            )
        coverage_gap = order_guardrail_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "order_guardrails",
            "Order Guardrail Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"blocked={report.blocked_order_scenarios}",
                f"unexpected={report.unexpected_order_scenarios}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action=(
                "Fix incomplete or failed order guardrails before allowing "
                "paper orders."
            )
            if not passed
            else "No action required.",
        )

    def _schedule_guardrail_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "schedule_guardrails",
                "Schedule Guardrail Audit",
                "Run python -m trading_app.runtime.schedule.",
            )
        coverage_gap = schedule_guardrail_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "schedule_guardrails",
            "Schedule Guardrail Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"approved={report.approved_schedule_scenarios}",
                f"protected={report.protected_schedule_scenarios}",
                f"unexpected={report.unexpected_schedule_scenarios}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action=(
                "Fix incomplete or failed schedule guardrails before scheduled "
                "paper trading."
            )
            if not passed
            else "No action required.",
        )

    def _fill_sync_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "fill_sync",
                "Fill Sync Audit",
                "Run python -m trading_app.runtime.fills.",
            )
        coverage_gap = fill_sync_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "fill_sync",
            "Fill Sync Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"incremental={report.incremental_fill_scenarios}",
                f"duplicate={report.duplicate_fill_scenarios}",
                f"unexpected={report.unexpected_fill_scenarios}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action=(
                "Fix incomplete or failed fill-sync scenarios before trusting fills."
            )
            if not passed
            else "No action required.",
        )

    def _runtime_snapshot_item(self, recovered) -> RuntimeEvidenceBundleItem:
        snapshot = self._read_latest_runtime_snapshot()
        if snapshot is None:
            return _missing_item(
                "runtime_snapshot",
                "Runtime Snapshot",
                "Start the paper runtime until latest runtime state is persisted.",
            )
        mode = getattr(snapshot, "mode", None)
        paper_report_present = getattr(snapshot, "paper_report", None) is not None
        passed = mode == "Alpaca Paper" and paper_report_present
        return _item(
            "runtime_snapshot",
            "Runtime Snapshot",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            f"Runtime snapshot mode is {mode or 'unknown'}.",
            path=str(self.store.state_dir / "latest-runtime-snapshot.json"),
            evidence=(
                f"paper_report_present={paper_report_present}",
                f"events={len(getattr(snapshot, 'events', ()))}",
            ),
            next_action="Persist Alpaca Paper runtime snapshots with paper reports."
            if not passed
            else "No action required.",
        )

    def _recovery_audit_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "restart_recovery",
                "Restart Recovery Audit",
                "Run python -m trading_app.runtime.recovery.",
            )
        coverage_gap = recovery_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "restart_recovery",
            "Restart Recovery Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"raw_submissions={report.raw_submission_count}",
                f"recovered_submissions={report.recovered_submission_count}",
                f"raw_fills={report.raw_fill_count}",
                f"recovered_fills={report.recovered_fill_count}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action=(
                "Fix incomplete or failed recovery evidence and rerun the audit."
            )
            if not passed
            else "No action required.",
        )

    def _dashboard_item(self, snapshot) -> RuntimeEvidenceBundleItem:
        if snapshot is None:
            return _missing_item(
                "dashboard_snapshot",
                "Dashboard Snapshot",
                "Persist a dashboard snapshot from the Alpaca paper runtime.",
            )
        runtime_state = getattr(snapshot, "runtime_state", None)
        runtime_mode = _field(runtime_state, "mode") if runtime_state else None
        passed = snapshot.mode == "Alpaca Paper" and runtime_mode == "Alpaca Paper"
        return _item(
            "dashboard_snapshot",
            "Dashboard Snapshot",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            f"Dashboard mode is {snapshot.mode}.",
            path=str(self.store.state_dir / "latest-dashboard-snapshot.json"),
            evidence=(
                f"broker={snapshot.broker}",
                f"runtime_state_mode={runtime_mode or 'missing'}",
            ),
            next_action="Persist dashboard snapshots from the live runtime provider."
            if not passed
            else "No action required.",
        )

    def _dashboard_consistency_item(
        self,
        report,
        path: Path | None,
    ) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "dashboard_consistency",
                "Dashboard Consistency Audit",
                "Run python -m trading_app.runtime.dashboard_audit.",
            )
        coverage_gap = dashboard_consistency_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "dashboard_consistency",
            "Dashboard Consistency Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"checks={len(report.checks)}",
                f"status={report.status.value}",
                *coverage_gap,
            ),
            next_action=(
                "Regenerate dashboard state from the runtime provider and rerun "
                "the dashboard consistency audit."
            )
            if not passed
            else "No action required.",
        )

    def _dashboard_visual_item(
        self,
        report,
        path: Path | None,
    ) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "dashboard_visual",
                "Dashboard Visual Readiness Audit",
                "Run python -m trading_app.runtime.dashboard_visual.",
            )
        coverage_gap = dashboard_visual_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "dashboard_visual",
            "Dashboard Visual Readiness Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"critical_surfaces={report.critical_surface_count}",
                f"responsive_surfaces={report.responsive_surface_count}",
                f"failed_visual_scenarios={report.failed_visual_scenarios}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action=(
                "Fix rendered dashboard surface gaps and rerun the visual audit."
            )
            if not passed
            else "No action required.",
        )

    def _evidence_coherence_item(
        self,
        report,
        path: Path | None,
    ) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "evidence_coherence",
                "Evidence Coherence Audit",
                "Run python -m trading_app.runtime.coherence.",
            )
        coverage_gap = evidence_coherence_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "evidence_coherence",
            "Evidence Coherence Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"checks={len(report.checks)}",
                f"status={report.status.value}",
                *coverage_gap,
            ),
            next_action=(
                "Fix mixed or stale runtime evidence and rerun the coherence audit."
            )
            if not passed
            else "No action required.",
        )

    def _data_quality_audit_item(
        self,
        report,
        path: Path | None,
    ) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "data_quality_audit",
                "Data Quality Audit",
                "Run python -m trading_app.runtime.data_quality.",
            )
        coverage_gap = data_quality_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "data_quality_audit",
            "Data Quality Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary
            if passed
            else (
                "Data-quality audit failed or did not include required latest-price "
                "and daily-bar scenarios."
            ),
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"latest_price_scenarios={report.latest_price_scenarios}",
                f"daily_bar_scenarios={report.daily_bar_scenarios}",
                "symbol_universe_scenarios="
                f"{getattr(report, 'symbol_universe_scenarios', 0)}",
                f"failed={report.failed_quality_scenarios}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action="Fix failed data-quality scenarios before trusting data."
            if not passed
            else "No action required.",
        )

    def _broker_order_history_item(
        self,
        report,
        path: Path | None,
    ) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "broker_order_history",
                "Broker Order History Audit",
                "Run python -m trading_app.runtime.broker_history.",
            )
        coverage_gap = broker_order_history_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "broker_order_history",
            "Broker Order History Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"provider={report.provider}",
                f"local_orders={report.local_order_count}",
                f"broker_orders={report.broker_order_count}",
                f"matched={report.matched_order_count}",
                f"mismatches={report.mismatch_count}",
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action=(
                "Fix incomplete or failed broker order-history evidence before signoff."
            )
            if not passed
            else "No action required.",
        )

    def _artifact_integrity_item(
        self,
        report,
        path: Path | None,
    ) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "artifact_integrity",
                "Artifact Integrity Manifest",
                "Run python -m trading_app.runtime.integrity.",
            )
        coverage_gap = artifact_integrity_coverage_gap(
            report,
            require_evidence_bundle=False,
        )
        passed = report.passed and not coverage_gap
        return _item(
            "artifact_integrity",
            "Artifact Integrity Manifest",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"hashed={report.hashed_count}",
                f"missing_required={report.missing_required_count}",
                f"hash_mismatches={report.hash_mismatch_count}",
                f"required={report.required_count}",
                *coverage_gap,
            ),
            next_action=(
                "Regenerate missing evidence artifacts and rerun integrity manifest."
            )
            if not passed
            else "No action required.",
        )

    def _health_item(self, report, path: Path | None) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "health_report",
                "Runtime Health",
                "Run runtime health checks during or after the soak.",
            )
        status = report.status
        passed = status != RuntimeHealthStatus.CRITICAL
        return _item(
            "health_report",
            "Runtime Health",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else None,
            evidence=(
                f"health={status.value}",
                f"incidents={len(report.incidents)}",
            ),
            next_action="Resolve critical runtime health incidents."
            if not passed
            else "No action required.",
        )

    def _daily_report_item(
        self, report, path: Path | None
    ) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "daily_report",
                "Daily Report",
                "Run the runtime through the daily report window.",
            )
        if path is None:
            return _item(
                "daily_report",
                "Daily Report",
                RuntimePreflightStatus.FAILED,
                "Daily report exists without a persisted Markdown path.",
                evidence=(f"trading_day={report.trading_day.isoformat()}",),
                next_action="Persist the written daily report Markdown path.",
            )
        if not path.exists():
            return _item(
                "daily_report",
                "Daily Report",
                RuntimePreflightStatus.FAILED,
                "Daily report Markdown path does not exist.",
                path=str(path),
                evidence=(f"trading_day={report.trading_day.isoformat()}",),
                next_action="Regenerate the daily report Markdown artifact.",
            )
        if (
            report.report_metadata is None
            or report.report_metadata.markdown_path is None
        ):
            return _item(
                "daily_report",
                "Daily Report",
                RuntimePreflightStatus.FAILED,
                "Daily report metadata is missing the Markdown path.",
                path=str(path),
                evidence=(f"trading_day={report.trading_day.isoformat()}",),
                next_action="Persist report metadata with the Markdown path.",
            )
        if Path(report.report_metadata.markdown_path) != path:
            return _item(
                "daily_report",
                "Daily Report",
                RuntimePreflightStatus.FAILED,
                "Daily report metadata path does not match persisted path.",
                path=str(path),
                evidence=(
                    f"metadata_markdown_path={report.report_metadata.markdown_path}",
                ),
                next_action="Regenerate daily report metadata and path evidence.",
            )
        if not _generated_after_close(report.generated_at):
            return _item(
                "daily_report",
                "Daily Report",
                RuntimePreflightStatus.FAILED,
                "Daily report was generated before the regular market close.",
                path=str(path),
                evidence=(f"generated_at={report.generated_at.isoformat()}",),
                next_action="Generate the daily report after market close.",
            )
        return _item(
            "daily_report",
            "Daily Report",
            RuntimePreflightStatus.PASSED,
            f"Daily report exists for {report.trading_day.isoformat()}.",
            path=str(path),
            evidence=(
                f"generated_at={report.generated_at.isoformat()}",
                f"fills={len(report.fill_report)}",
                f"rejections={report.risk_report.rejection_count}",
            ),
            next_action="No action required.",
        )

    def _learning_item(
        self,
        learning,
        path: Path | None,
        daily_report,
    ) -> RuntimeEvidenceBundleItem:
        if learning is None:
            return _missing_item(
                "nightly_learning",
                "Nightly Learning",
                "Run nightly learning after the daily report.",
            )
        if daily_report is None:
            return _item(
                "nightly_learning",
                "Nightly Learning",
                RuntimePreflightStatus.FAILED,
                (
                    f"Nightly learning run {learning.id} is recorded without "
                    "a daily report."
                ),
                path=str(path) if path else None,
                evidence=(f"learning_as_of={learning.as_of.isoformat()}",),
                next_action=(
                    "Persist the daily report before reviewing nightly learning."
                ),
            )
        report_generated_at = _daily_report_generated_at(daily_report)
        if learning.as_of < report_generated_at:
            return _item(
                "nightly_learning",
                "Nightly Learning",
                RuntimePreflightStatus.FAILED,
                "Nightly learning ran before the daily report.",
                path=str(path) if path else None,
                evidence=(
                    f"daily_report_generated_at={report_generated_at.isoformat()}",
                    f"learning_as_of={learning.as_of.isoformat()}",
                ),
                next_action=(
                    "Run nightly learning only after the daily report is written."
                ),
            )
        missing_manual_review = tuple(
            recommendation.model.key
            for recommendation in learning.recommendations
            if not recommendation.manual_review_required
        )
        passed = bool(learning.active_model_unchanged) and not missing_manual_review
        return _item(
            "nightly_learning",
            "Nightly Learning",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            f"Nightly learning run {learning.id} is recorded.",
            path=str(path) if path else None,
            evidence=(
                f"daily_report_generated_at={report_generated_at.isoformat()}",
                f"learning_as_of={learning.as_of.isoformat()}",
                f"active_model_unchanged={learning.active_model_unchanged}",
                *(
                    tuple(
                        f"missing_manual_review={key}" for key in missing_manual_review
                    )
                    or ("all_recommendations_manual_review=true",)
                ),
            ),
            next_action=(
                "Investigate unexpected active-model mutation or ungated "
                "recommendations."
            )
            if not passed
            else "No action required.",
        )

    def _model_governance_item(self, report, path: Path | None):
        if report is None:
            return _missing_item(
                "model_governance",
                "Model Governance Audit",
                "Run python -m trading_app.runtime.governance.",
            )
        coverage_gap = model_governance_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "model_governance",
            "Model Governance Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=str(path) if path else report.markdown_path,
            evidence=(
                f"learning_run={report.learning_run_id or 'missing'}",
                f"recommendations={report.recommendation_count}",
                (f"authority_increases={len(report.unreviewed_authority_increases)}"),
                f"checks={len(report.checks)}",
                *coverage_gap,
            ),
            next_action="Fix model-governance failures before promotion review."
            if not passed
            else "No action required.",
        )

    def _secret_scan_item(self, report) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "secret_scan",
                "Post-Run Secret Scan",
                "Run python -m trading_app.runtime.security.",
            )
        missing_secret_names = _missing_secret_names(report)
        passed = report.passed and not missing_secret_names
        return _item(
            "secret_scan",
            "Post-Run Secret Scan",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary
            if passed
            else (
                "Secret scan failed or did not check configured Alpaca "
                "credential values."
            ),
            path=str(self.store.state_dir / "latest-secret-scan-report.json"),
            evidence=(
                f"files_scanned={report.files_scanned}",
                f"findings={len(report.findings)}",
                f"scan_roots={len(report.scan_roots)}",
                "missing_secret_names=" + ",".join(missing_secret_names),
            ),
            next_action="Remove leaked artifacts and rotate affected credentials."
            if not passed
            else "No action required.",
        )

    def _statement_item(self, report, path: Path | None) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "statement_reconciliation",
                "Broker Statement Reconciliation",
                "Run python -m trading_app.paper.reconcile_statement.",
            )
        return _item(
            "statement_reconciliation",
            "Broker Statement Reconciliation",
            RuntimePreflightStatus.PASSED
            if report.reconciled
            else RuntimePreflightStatus.FAILED,
            f"Statement {report.statement.statement_id} was compared to the ledger.",
            path=str(path) if path else None,
            evidence=(
                f"provider={report.statement.provider}",
                f"statement_path={report.statement_path or 'missing'}",
                f"issues={len(report.issues)}",
            ),
            next_action="Investigate statement mismatches before functional review."
            if not report.reconciled
            else "No action required.",
        )

    def _completion_item(self, report) -> RuntimeEvidenceBundleItem:
        if report is None:
            return _missing_item(
                "completion_audit",
                "Functional Completion Audit",
                "Run python -m trading_app.runtime.completion.",
            )
        coverage_gap = functional_completion_coverage_gap(report)
        passed = report.passed and not coverage_gap
        return _item(
            "completion_audit",
            "Functional Completion Audit",
            RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
            report.summary,
            path=report.markdown_path,
            evidence=(
                f"passed={report.passed}",
                f"proven={report.proven_count}",
                f"failed={report.failed_count}",
                f"external_required={report.external_required_count}",
                *coverage_gap,
            ),
            next_action="Resolve completion-audit gaps before functional review."
            if not passed
            else "No action required.",
        )

    def _read_latest_runtime_snapshot(self):
        path = self.store.state_dir / "latest-runtime-snapshot.json"
        if not path.exists():
            return None
        from trading_app.runtime.models import RuntimeSnapshot

        return RuntimeSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def render_evidence_bundle_text(report: RuntimeEvidenceBundleReport) -> str:
    """Render a compact evidence-bundle status."""

    lines = [
        f"Evidence bundle status: {report.status.value}",
        f"Ready for operator review: {_yes_no(report.ready_for_operator_review)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Evidence:",
    ]
    for item in report.items:
        lines.append(f"- {item.name}: {item.status.value} - {item.summary}")
    return "\n".join(lines)


def render_evidence_bundle_markdown(report: RuntimeEvidenceBundleReport) -> str:
    """Render a reviewable paper-runtime evidence dossier."""

    lines = [
        "# Paper Runtime Evidence Bundle",
        "",
        "> Paper trading only. This bundle does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Ready for operator review: `{_yes_no(report.ready_for_operator_review)}`",
        f"- Generated at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Required evidence: `{report.required_count}`",
        f"- Passed: `{report.passed_count}`",
        f"- Warnings: `{report.warning_count}`",
        f"- Failed: `{report.failed_count}`",
        f"- Missing required: `{report.missing_required_count}`",
        "",
        report.summary,
        "",
        "## Artifact Inventory",
        "",
        "| Artifact | Status | Required | Path | Evidence | Next Action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.items:
        evidence = "<br>".join(item.evidence) if item.evidence else "No evidence"
        lines.append(
            "| "
            f"{_escape_table(item.label)} | "
            f"{item.status.value} | "
            f"{_yes_no(item.required)} | "
            f"{_escape_table(item.path or 'not written')} | "
            f"{_escape_table(evidence)} | "
            f"{_escape_table(item.next_action)} |"
        )

    lines.extend(
        [
            "",
            "## Review Notes",
            "",
            "- Treat missing or failed required evidence as not functionally proven.",
            "- Review the completion audit before calling the paper app functional.",
            "- After review, record manual signoff with "
            "`python -m trading_app.runtime.signoff`.",
            "- Keep live-money trading disabled unless a separate live-readiness "
            "review is explicitly approved later.",
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence_bundle_markdown_report(
    report: RuntimeEvidenceBundleReport,
    reports_dir: Path | str,
) -> Path:
    """Write the evidence bundle Markdown dossier and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"evidence-bundle-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_evidence_bundle_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a paper-runtime operator evidence bundle."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeEvidenceBundleBuilder(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).build()
    print(
        report.model_dump_json() if args.json else render_evidence_bundle_text(report)
    )
    return 0 if report.ready_for_operator_review else 1


def _item(
    name: str,
    label: str,
    status: RuntimePreflightStatus,
    summary: str,
    *,
    path: str | None = None,
    evidence: tuple[str, ...] = (),
    next_action: str,
    required: bool = True,
) -> RuntimeEvidenceBundleItem:
    return RuntimeEvidenceBundleItem(
        name=name,
        label=label,
        status=status,
        required=required,
        summary=summary,
        path=path,
        evidence=evidence,
        next_action=next_action,
    )


def _review_path_checked_items(
    *items: RuntimeEvidenceBundleItem,
) -> tuple[RuntimeEvidenceBundleItem, ...]:
    return tuple(_review_path_checked_item(item) for item in items)


def _review_path_checked_item(
    item: RuntimeEvidenceBundleItem,
) -> RuntimeEvidenceBundleItem:
    if not item.required or item.status != RuntimePreflightStatus.PASSED:
        return item
    if not item.path:
        return item.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "summary": f"{item.summary} Review artifact path is missing.",
                "evidence": (*item.evidence, "review_path=missing"),
                "next_action": (
                    "Regenerate this evidence with a reviewable artifact path."
                ),
            }
        )
    path = Path(item.path)
    if path.exists():
        return item
    return item.model_copy(
        update={
            "status": RuntimePreflightStatus.FAILED,
            "summary": f"{item.summary} Review artifact path does not exist.",
            "evidence": (*item.evidence, f"review_path_missing={item.path}"),
            "next_action": "Regenerate this evidence artifact before operator review.",
        }
    )


def _missing_item(
    name: str,
    label: str,
    next_action: str,
    *,
    required: bool = True,
) -> RuntimeEvidenceBundleItem:
    return _item(
        name,
        label,
        RuntimePreflightStatus.FAILED,
        "Required evidence is missing.",
        next_action=next_action,
        required=required,
    )


def _summary(
    status: RuntimePreflightStatus,
    passed: int,
    total: int,
    failed: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return f"All {total} evidence artifacts are present and clean."
    return (
        f"{passed}/{total} evidence artifact(s) passed; {failed} failed or missing. "
        "Do not treat the paper app as functionally proven yet."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _daily_report_generated_at(report) -> datetime:
    metadata = getattr(report, "report_metadata", None)
    if metadata is not None and metadata.generated_at is not None:
        return metadata.generated_at
    return report.generated_at


def _generated_after_close(value: datetime) -> bool:
    return value.astimezone(MARKET_TZ).time() >= REGULAR_CLOSE


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _missing_secret_names(report) -> tuple[str, ...]:
    checked = set(report.secret_names_checked)
    return tuple(sorted(_REQUIRED_SECRET_NAMES - checked))


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


if __name__ == "__main__":
    raise SystemExit(main())
