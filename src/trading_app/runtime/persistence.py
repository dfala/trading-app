"""Local persistence for always-on paper runtime state."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from trading_app.broker import (
    BrokerReconciliationReport,
    BrokerStatementReconciliationReport,
)
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.learning import NightlyLearningRun, write_learning_markdown_report
from trading_app.market_data import LatestPriceSnapshot
from trading_app.paper import (
    PaperOrderStatus,
    PaperOrderSubmission,
    PaperTradingService,
)
from trading_app.reporting import DailyTradingReport
from trading_app.runtime.health import write_health_markdown_report
from trading_app.runtime.models import (
    FunctionalCompletionAuditReport,
    OperatorControlResult,
    OperatorControlState,
    RuntimeAlert,
    RuntimeArtifactIntegrityReport,
    RuntimeBrokerOrderHistoryReport,
    RuntimeCredentialedSessionReport,
    RuntimeCycleResult,
    RuntimeDashboardConsistencyReport,
    RuntimeDashboardVisualReport,
    RuntimeDataQualityAuditReport,
    RuntimeDryRunReport,
    RuntimeEvent,
    RuntimeEvidenceBundleReport,
    RuntimeEvidenceCoherenceReport,
    RuntimeFillSyncReport,
    RuntimeFinalAcceptanceReport,
    RuntimeHealthReport,
    RuntimeLifecycleDrillReport,
    RuntimeModelGovernanceReport,
    RuntimeOperationsReadinessReport,
    RuntimeOperatorSignoffReport,
    RuntimeOrderGuardrailReport,
    RuntimePostRunReviewReport,
    RuntimePreflightReport,
    RuntimeRecoveryAuditReport,
    RuntimeScheduleGuardrailReport,
    RuntimeSecretScanReport,
    RuntimeSnapshot,
    RuntimeSoakEvidenceReport,
    RuntimeValidationReport,
)
from trading_app.schemas import Fill


class RuntimeRecoveryState:
    """Recovered runtime records loaded from local persistence."""

    def __init__(
        self,
        *,
        latest_prices: LatestPriceSnapshot | None,
        last_cycle: RuntimeCycleResult | None,
        events: tuple[RuntimeEvent, ...],
        daily_report: DailyTradingReport | None,
        nightly_learning: NightlyLearningRun | None,
        daily_report_path: Path | None,
        learning_report_path: Path | None,
        submissions: tuple[PaperOrderSubmission, ...],
        order_statuses: tuple[PaperOrderStatus, ...],
        fills: tuple[Fill, ...],
        control_state: OperatorControlState | None,
        control_results: tuple[OperatorControlResult, ...],
        alerts: tuple[RuntimeAlert, ...],
        health_report: RuntimeHealthReport | None,
        health_report_path: Path | None,
        preflight_report: RuntimePreflightReport | None,
        dry_run_report: RuntimeDryRunReport | None,
        validation_report: RuntimeValidationReport | None,
        dashboard_snapshot: OperatorDashboardSnapshot | None,
        statement_reconciliation: BrokerStatementReconciliationReport | None,
        statement_reconciliation_path: Path | None,
    ) -> None:
        self.latest_prices = latest_prices
        self.last_cycle = last_cycle
        self.events = events
        self.daily_report = daily_report
        self.nightly_learning = nightly_learning
        self.daily_report_path = daily_report_path
        self.learning_report_path = learning_report_path
        self.submissions = submissions
        self.order_statuses = order_statuses
        self.fills = fills
        self.control_state = control_state
        self.control_results = control_results
        self.alerts = alerts
        self.health_report = health_report
        self.health_report_path = health_report_path
        self.preflight_report = preflight_report
        self.dry_run_report = dry_run_report
        self.validation_report = validation_report
        self.dashboard_snapshot = dashboard_snapshot
        self.statement_reconciliation = statement_reconciliation
        self.statement_reconciliation_path = statement_reconciliation_path


class RuntimePersistenceStore:
    """Persist runtime records as local JSON and JSONL files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.state_dir = self.root / "state"
        self.journal_dir = self.root / "journal"
        self.reports_dir = self.root / "reports"
        self.learning_dir = self.root / "learning"

    def ensure(self) -> None:
        for directory in (
            self.state_dir,
            self.journal_dir,
            self.reports_dir,
            self.learning_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def persist_latest_prices(self, snapshot: LatestPriceSnapshot | None) -> None:
        if snapshot is None:
            return
        self._write_model(self.state_dir / "latest-prices.json", snapshot)

    def persist_cycle(self, cycle: RuntimeCycleResult | None) -> None:
        if cycle is None:
            return
        self._write_model(self.state_dir / "last-cycle.json", cycle)
        self._append_model(self.journal_dir / "cycles.jsonl", cycle)

    def persist_events(self, events: tuple[RuntimeEvent, ...]) -> None:
        for event in events:
            self._append_model(self.journal_dir / "events.jsonl", event)

    def persist_control_state(self, state: OperatorControlState) -> None:
        self._write_model(self.state_dir / "operator-control-state.json", state)

    def persist_control_result(self, result: OperatorControlResult) -> None:
        self.persist_control_state(result.control_state)
        self._append_model(self.journal_dir / "control-actions.jsonl", result)

    def persist_alerts(self, alerts: tuple[RuntimeAlert, ...]) -> None:
        self._write_model_list(self.state_dir / "latest-alerts.json", alerts)
        for alert in alerts:
            self._append_model(self.journal_dir / "alerts.jsonl", alert)

    def persist_health_report(self, report: RuntimeHealthReport | None) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-health-report.json", report)
        self._append_model(self.journal_dir / "health.jsonl", report)
        markdown_path = write_health_markdown_report(report, self.reports_dir)
        self._write_json(
            self.state_dir / "latest-health-report-path.json",
            {"path": str(markdown_path)},
        )

    def persist_preflight_report(self, report: RuntimePreflightReport | None) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-preflight-report.json", report)
        self._append_model(self.journal_dir / "preflight.jsonl", report)

    def persist_dry_run_report(self, report: RuntimeDryRunReport | None) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-dry-run-report.json", report)
        self._append_model(self.journal_dir / "dry-runs.jsonl", report)

    def persist_validation_report(self, report: RuntimeValidationReport | None) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-validation-report.json", report)
        self._append_model(self.journal_dir / "validation.jsonl", report)

    def persist_soak_evidence_report(
        self, report: RuntimeSoakEvidenceReport | None
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-soak-evidence-report.json", report)
        self._append_model(self.journal_dir / "soak-evidence.jsonl", report)

    def persist_secret_scan_report(
        self, report: RuntimeSecretScanReport | None
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-secret-scan-report.json", report)
        self._append_model(self.journal_dir / "secret-scans.jsonl", report)

    def persist_completion_audit_report(
        self, report: FunctionalCompletionAuditReport | None
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-completion-audit-report.json", report
        )
        self._append_model(self.journal_dir / "completion-audits.jsonl", report)

    def read_completion_audit_report(
        self,
    ) -> FunctionalCompletionAuditReport | None:
        return self._read_model(
            self.state_dir / "latest-completion-audit-report.json",
            FunctionalCompletionAuditReport,
        )

    def persist_evidence_bundle_report(
        self,
        report: RuntimeEvidenceBundleReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-evidence-bundle-report.json", report)
        self._append_model(self.journal_dir / "evidence-bundles.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-evidence-bundle-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_evidence_bundle_report(self) -> RuntimeEvidenceBundleReport | None:
        return self._read_model(
            self.state_dir / "latest-evidence-bundle-report.json",
            RuntimeEvidenceBundleReport,
        )

    def read_evidence_bundle_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-evidence-bundle-report-path.json"
        )

    def persist_dashboard_consistency_report(
        self,
        report: RuntimeDashboardConsistencyReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-dashboard-consistency-report.json", report
        )
        self._append_model(self.journal_dir / "dashboard-consistency.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-dashboard-consistency-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_dashboard_consistency_report(
        self,
    ) -> RuntimeDashboardConsistencyReport | None:
        return self._read_model(
            self.state_dir / "latest-dashboard-consistency-report.json",
            RuntimeDashboardConsistencyReport,
        )

    def read_dashboard_consistency_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-dashboard-consistency-report-path.json"
        )

    def persist_dashboard_visual_report(
        self,
        report: RuntimeDashboardVisualReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-dashboard-visual-report.json", report
        )
        self._append_model(self.journal_dir / "dashboard-visual.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-dashboard-visual-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_dashboard_visual_report(
        self,
    ) -> RuntimeDashboardVisualReport | None:
        return self._read_model(
            self.state_dir / "latest-dashboard-visual-report.json",
            RuntimeDashboardVisualReport,
        )

    def read_dashboard_visual_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-dashboard-visual-report-path.json"
        )

    def persist_evidence_coherence_report(
        self,
        report: RuntimeEvidenceCoherenceReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-evidence-coherence-report.json", report
        )
        self._append_model(self.journal_dir / "evidence-coherence.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-evidence-coherence-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_evidence_coherence_report(
        self,
    ) -> RuntimeEvidenceCoherenceReport | None:
        return self._read_model(
            self.state_dir / "latest-evidence-coherence-report.json",
            RuntimeEvidenceCoherenceReport,
        )

    def read_evidence_coherence_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-evidence-coherence-report-path.json"
        )

    def persist_artifact_integrity_report(
        self,
        report: RuntimeArtifactIntegrityReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-artifact-integrity-report.json", report
        )
        self._append_model(self.journal_dir / "artifact-integrity.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-artifact-integrity-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_artifact_integrity_report(
        self,
    ) -> RuntimeArtifactIntegrityReport | None:
        return self._read_model(
            self.state_dir / "latest-artifact-integrity-report.json",
            RuntimeArtifactIntegrityReport,
        )

    def read_artifact_integrity_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-artifact-integrity-report-path.json"
        )

    def persist_operator_signoff_report(
        self,
        report: RuntimeOperatorSignoffReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-operator-signoff-report.json", report
        )
        self._append_model(self.journal_dir / "operator-signoffs.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-operator-signoff-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_operator_signoff_report(self) -> RuntimeOperatorSignoffReport | None:
        return self._read_model(
            self.state_dir / "latest-operator-signoff-report.json",
            RuntimeOperatorSignoffReport,
        )

    def read_operator_signoff_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-operator-signoff-report-path.json"
        )

    def persist_final_acceptance_report(
        self,
        report: RuntimeFinalAcceptanceReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-final-acceptance-report.json",
            report,
        )
        self._append_model(self.journal_dir / "final-acceptance.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-final-acceptance-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_final_acceptance_report(self) -> RuntimeFinalAcceptanceReport | None:
        return self._read_model(
            self.state_dir / "latest-final-acceptance-report.json",
            RuntimeFinalAcceptanceReport,
        )

    def read_final_acceptance_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-final-acceptance-report-path.json"
        )

    def persist_recovery_audit_report(
        self,
        report: RuntimeRecoveryAuditReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-recovery-audit-report.json", report)
        self._append_model(self.journal_dir / "recovery-audits.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-recovery-audit-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_recovery_audit_report(self) -> RuntimeRecoveryAuditReport | None:
        return self._read_model(
            self.state_dir / "latest-recovery-audit-report.json",
            RuntimeRecoveryAuditReport,
        )

    def read_recovery_audit_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-recovery-audit-report-path.json"
        )

    def persist_operations_readiness_report(
        self,
        report: RuntimeOperationsReadinessReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-operations-readiness-report.json", report
        )
        self._append_model(self.journal_dir / "operations-readiness.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-operations-readiness-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_operations_readiness_report(
        self,
    ) -> RuntimeOperationsReadinessReport | None:
        return self._read_model(
            self.state_dir / "latest-operations-readiness-report.json",
            RuntimeOperationsReadinessReport,
        )

    def read_operations_readiness_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-operations-readiness-report-path.json"
        )

    def persist_lifecycle_drill_report(
        self,
        report: RuntimeLifecycleDrillReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-lifecycle-drill-report.json", report)
        self._append_model(self.journal_dir / "lifecycle-drills.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-lifecycle-drill-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_lifecycle_drill_report(self) -> RuntimeLifecycleDrillReport | None:
        return self._read_model(
            self.state_dir / "latest-lifecycle-drill-report.json",
            RuntimeLifecycleDrillReport,
        )

    def read_lifecycle_drill_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-lifecycle-drill-report-path.json"
        )

    def persist_credentialed_session_report(
        self,
        report: RuntimeCredentialedSessionReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-credentialed-session-report.json",
            report,
        )
        self._append_model(self.journal_dir / "credentialed-sessions.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-credentialed-session-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_credentialed_session_report(
        self,
    ) -> RuntimeCredentialedSessionReport | None:
        return self._read_model(
            self.state_dir / "latest-credentialed-session-report.json",
            RuntimeCredentialedSessionReport,
        )

    def read_credentialed_session_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-credentialed-session-report-path.json"
        )

    def persist_model_governance_report(
        self,
        report: RuntimeModelGovernanceReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-model-governance-report.json", report
        )
        self._append_model(self.journal_dir / "model-governance.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-model-governance-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_model_governance_report(self) -> RuntimeModelGovernanceReport | None:
        return self._read_model(
            self.state_dir / "latest-model-governance-report.json",
            RuntimeModelGovernanceReport,
        )

    def read_model_governance_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-model-governance-report-path.json"
        )

    def persist_order_guardrail_report(
        self,
        report: RuntimeOrderGuardrailReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-order-guardrail-report.json", report)
        self._append_model(self.journal_dir / "order-guardrails.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-order-guardrail-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_order_guardrail_report(self) -> RuntimeOrderGuardrailReport | None:
        return self._read_model(
            self.state_dir / "latest-order-guardrail-report.json",
            RuntimeOrderGuardrailReport,
        )

    def read_order_guardrail_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-order-guardrail-report-path.json"
        )

    def persist_schedule_guardrail_report(
        self,
        report: RuntimeScheduleGuardrailReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-schedule-guardrail-report.json",
            report,
        )
        self._append_model(self.journal_dir / "schedule-guardrails.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-schedule-guardrail-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_schedule_guardrail_report(self) -> RuntimeScheduleGuardrailReport | None:
        return self._read_model(
            self.state_dir / "latest-schedule-guardrail-report.json",
            RuntimeScheduleGuardrailReport,
        )

    def read_schedule_guardrail_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-schedule-guardrail-report-path.json"
        )

    def persist_fill_sync_report(
        self,
        report: RuntimeFillSyncReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-fill-sync-report.json", report)
        self._append_model(self.journal_dir / "fill-sync.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-fill-sync-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_fill_sync_report(self) -> RuntimeFillSyncReport | None:
        return self._read_model(
            self.state_dir / "latest-fill-sync-report.json",
            RuntimeFillSyncReport,
        )

    def read_fill_sync_report_path(self) -> Path | None:
        return self._read_path(self.state_dir / "latest-fill-sync-report-path.json")

    def persist_data_quality_audit_report(
        self,
        report: RuntimeDataQualityAuditReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-data-quality-audit-report.json", report
        )
        self._append_model(self.journal_dir / "data-quality-audits.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-data-quality-audit-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_data_quality_audit_report(
        self,
    ) -> RuntimeDataQualityAuditReport | None:
        return self._read_model(
            self.state_dir / "latest-data-quality-audit-report.json",
            RuntimeDataQualityAuditReport,
        )

    def read_data_quality_audit_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-data-quality-audit-report-path.json"
        )

    def persist_broker_order_history_report(
        self,
        report: RuntimeBrokerOrderHistoryReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(
            self.state_dir / "latest-broker-order-history-report.json", report
        )
        self._append_model(self.journal_dir / "broker-order-history.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-broker-order-history-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_broker_order_history_report(
        self,
    ) -> RuntimeBrokerOrderHistoryReport | None:
        return self._read_model(
            self.state_dir / "latest-broker-order-history-report.json",
            RuntimeBrokerOrderHistoryReport,
        )

    def read_broker_order_history_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-broker-order-history-report-path.json"
        )

    def persist_post_run_review_report(
        self,
        report: RuntimePostRunReviewReport | None,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        if report is None:
            return
        self._write_model(self.state_dir / "latest-post-run-review-report.json", report)
        self._append_model(self.journal_dir / "post-run-reviews.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-post-run-review-report-path.json",
                {"path": str(markdown_path)},
            )

    def read_post_run_review_report(self) -> RuntimePostRunReviewReport | None:
        return self._read_model(
            self.state_dir / "latest-post-run-review-report.json",
            RuntimePostRunReviewReport,
        )

    def read_post_run_review_report_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-post-run-review-report-path.json"
        )

    def read_health_report_path(self) -> Path | None:
        return self._read_path(self.state_dir / "latest-health-report-path.json")

    def persist_submission(self, submission: PaperOrderSubmission) -> None:
        self._append_model(self.journal_dir / "submissions.jsonl", submission)

    def persist_order_status(self, status: PaperOrderStatus) -> None:
        self._append_model(self.journal_dir / "order-statuses.jsonl", status)

    def persist_fill(self, fill: Fill) -> None:
        self._append_model(self.journal_dir / "fills.jsonl", fill)

    def persist_reconciliation(self, report: BrokerReconciliationReport) -> None:
        self._write_model(self.state_dir / "latest-reconciliation.json", report)
        self._append_model(self.journal_dir / "reconciliation.jsonl", report)

    def persist_statement_reconciliation(
        self,
        report: BrokerStatementReconciliationReport,
        *,
        markdown_path: Path | None = None,
    ) -> None:
        self._write_model(
            self.state_dir / "latest-statement-reconciliation.json", report
        )
        self._append_model(self.journal_dir / "statement-reconciliation.jsonl", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-statement-reconciliation-path.json",
                {"path": str(markdown_path)},
            )

    def read_statement_reconciliation_path(self) -> Path | None:
        return self._read_path(
            self.state_dir / "latest-statement-reconciliation-path.json"
        )

    def read_statement_reconciliation_report(
        self,
    ) -> BrokerStatementReconciliationReport | None:
        return self._read_model(
            self.state_dir / "latest-statement-reconciliation.json",
            BrokerStatementReconciliationReport,
        )

    def read_soak_evidence_report(self) -> RuntimeSoakEvidenceReport | None:
        return self._read_model(
            self.state_dir / "latest-soak-evidence-report.json",
            RuntimeSoakEvidenceReport,
        )

    def read_secret_scan_report(self) -> RuntimeSecretScanReport | None:
        return self._read_model(
            self.state_dir / "latest-secret-scan-report.json",
            RuntimeSecretScanReport,
        )

    def persist_daily_report(
        self, report: DailyTradingReport | None, *, markdown_path: Path | None = None
    ) -> None:
        if report is None:
            return
        if markdown_path is not None and report.report_metadata is not None:
            report = report.model_copy(
                update={
                    "report_metadata": report.report_metadata.model_copy(
                        update={"markdown_path": str(markdown_path)}
                    )
                }
            )
        path = self.reports_dir / f"daily-report-{report.trading_day.isoformat()}.json"
        self._write_model(path, report)
        self._write_model(self.state_dir / "latest-daily-report.json", report)
        if markdown_path is not None:
            self._write_json(
                self.state_dir / "latest-daily-report-path.json",
                {"path": str(markdown_path)},
            )

    def persist_learning_run(self, run: NightlyLearningRun | None) -> None:
        if run is None:
            return
        path = self.learning_dir / f"{run.id}.json"
        self._write_model(path, run)
        self._write_model(self.state_dir / "latest-learning-run.json", run)
        markdown_path = write_learning_markdown_report(run, self.learning_dir)
        self._write_json(
            self.state_dir / "latest-learning-run-path.json",
            {"path": str(markdown_path)},
        )

    def read_learning_report_path(self) -> Path | None:
        return self._read_path(self.state_dir / "latest-learning-run-path.json")

    def persist_runtime_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        self._write_model(self.state_dir / "latest-runtime-snapshot.json", snapshot)

    def persist_dashboard_snapshot(
        self, snapshot: OperatorDashboardSnapshot | None
    ) -> None:
        if snapshot is None:
            return
        self._write_model(self.state_dir / "latest-dashboard-snapshot.json", snapshot)
        self._append_model(self.journal_dir / "dashboard-snapshots.jsonl", snapshot)

    def persist_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        self.persist_runtime_snapshot(snapshot)
        self.persist_latest_prices(snapshot.latest_prices)
        self.persist_cycle(snapshot.last_cycle)
        self.persist_daily_report(
            snapshot.daily_report,
            markdown_path=Path(snapshot.daily_report_path)
            if snapshot.daily_report_path
            else None,
        )
        self.persist_learning_run(snapshot.nightly_learning)
        if snapshot.control_state is not None:
            self.persist_control_state(snapshot.control_state)
        if snapshot.last_control_result is not None:
            self.persist_control_result(snapshot.last_control_result)
        self.persist_alerts(snapshot.alerts)
        self.persist_health_report(snapshot.health_report)

    def persist_service_state(self, service: PaperTradingService) -> None:
        existing_submission_ids = {
            submission.order.id
            for submission in self._read_jsonl(
                self.journal_dir / "submissions.jsonl", PaperOrderSubmission
            )
        }
        existing_fill_ids = {
            fill.id for fill in self._read_jsonl(self.journal_dir / "fills.jsonl", Fill)
        }
        for submission in service.submissions:
            if submission.order.id not in existing_submission_ids:
                self.persist_submission(submission)
                existing_submission_ids.add(submission.order.id)
        for status in service.order_statuses:
            self.persist_order_status(status)
        for fill in service.fills:
            if fill.id not in existing_fill_ids:
                self.persist_fill(fill)
                existing_fill_ids.add(fill.id)

    def recover(self) -> RuntimeRecoveryState:
        submissions = self._read_jsonl(
            self.journal_dir / "submissions.jsonl", PaperOrderSubmission
        )
        order_statuses = self._read_jsonl(
            self.journal_dir / "order-statuses.jsonl", PaperOrderStatus
        )
        fills = self._read_jsonl(self.journal_dir / "fills.jsonl", Fill)
        events = self._read_jsonl(self.journal_dir / "events.jsonl", RuntimeEvent)
        control_results = self._read_jsonl(
            self.journal_dir / "control-actions.jsonl", OperatorControlResult
        )
        daily_report_path = self._read_report_path()
        return RuntimeRecoveryState(
            latest_prices=self._read_model(
                self.state_dir / "latest-prices.json", LatestPriceSnapshot
            ),
            last_cycle=self._read_model(
                self.state_dir / "last-cycle.json", RuntimeCycleResult
            ),
            events=tuple(events),
            daily_report=self._read_model(
                self.state_dir / "latest-daily-report.json", DailyTradingReport
            ),
            nightly_learning=self._read_model(
                self.state_dir / "latest-learning-run.json", NightlyLearningRun
            ),
            daily_report_path=daily_report_path,
            learning_report_path=self.read_learning_report_path(),
            submissions=tuple(_dedupe_by_order_id(submissions)),
            order_statuses=tuple(_latest_order_statuses(order_statuses)),
            fills=tuple(_dedupe_by_fill_id(fills)),
            control_state=self._read_model(
                self.state_dir / "operator-control-state.json", OperatorControlState
            ),
            control_results=tuple(control_results),
            alerts=tuple(
                self._read_model_list(
                    self.state_dir / "latest-alerts.json", RuntimeAlert
                )
            ),
            health_report=self._read_model(
                self.state_dir / "latest-health-report.json", RuntimeHealthReport
            ),
            health_report_path=self.read_health_report_path(),
            preflight_report=self._read_model(
                self.state_dir / "latest-preflight-report.json",
                RuntimePreflightReport,
            ),
            dry_run_report=self._read_model(
                self.state_dir / "latest-dry-run-report.json",
                RuntimeDryRunReport,
            ),
            validation_report=self._read_model(
                self.state_dir / "latest-validation-report.json",
                RuntimeValidationReport,
            ),
            dashboard_snapshot=self._read_model(
                self.state_dir / "latest-dashboard-snapshot.json",
                OperatorDashboardSnapshot,
            ),
            statement_reconciliation=self.read_statement_reconciliation_report(),
            statement_reconciliation_path=self.read_statement_reconciliation_path(),
        )

    def restore_service(self, service: PaperTradingService) -> RuntimeRecoveryState:
        recovered = self.recover()
        service.restore_state(
            submissions=recovered.submissions,
            order_statuses=recovered.order_statuses,
            fills=recovered.fills,
        )
        return recovered

    def _write_model(self, path: Path, model: BaseModel) -> None:
        self._write_text(path, model.model_dump_json())

    def _append_model(self, path: Path, model: BaseModel) -> None:
        self.ensure()
        with path.open("a", encoding="utf-8") as file:
            file.write(model.model_dump_json())
            file.write("\n")

    def _write_json(self, path: Path, payload: dict) -> None:
        self._write_text(path, json.dumps(payload, sort_keys=True))

    def _write_model_list(self, path: Path, models: tuple[BaseModel, ...]) -> None:
        payload = [json.loads(model.model_dump_json()) for model in models]
        self._write_text(path, json.dumps(payload, sort_keys=True))

    def _write_text(self, path: Path, text: str) -> None:
        self.ensure()
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(text, encoding="utf-8")
        temporary_path.replace(path)

    def _read_model(self, path: Path, model_type):
        if not path.exists():
            return None
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def _read_jsonl(self, path: Path, model_type) -> list:
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(model_type.model_validate_json(line))
        return records

    def _read_model_list(self, path: Path, model_type) -> list:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [model_type.model_validate_json(json.dumps(item)) for item in payload]

    def _read_report_path(self) -> Path | None:
        return self._read_path(self.state_dir / "latest-daily-report-path.json")

    def _read_path(self, path: Path) -> Path | None:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("path")
        return Path(value) if value else None


def _dedupe_by_order_id(
    submissions: list[PaperOrderSubmission],
) -> list[PaperOrderSubmission]:
    by_order_id: dict[str, PaperOrderSubmission] = {}
    for submission in submissions:
        by_order_id[submission.order.id] = submission
    return sorted(by_order_id.values(), key=lambda item: item.submitted_at)


def _latest_order_statuses(
    statuses: list[PaperOrderStatus],
) -> list[PaperOrderStatus]:
    by_order_id: dict[str, PaperOrderStatus] = {}
    for status in statuses:
        current = by_order_id.get(status.order_id)
        if current is None or status.updated_at >= current.updated_at:
            by_order_id[status.order_id] = status
    return sorted(by_order_id.values(), key=lambda item: item.order_id)


def _dedupe_by_fill_id(fills: list[Fill]) -> list[Fill]:
    by_fill_id: dict[str, Fill] = {}
    for fill in fills:
        by_fill_id[fill.id] = fill
    return sorted(by_fill_id.values(), key=lambda item: item.filled_at)
