"""One-command post-run evidence review for Alpaca paper sessions."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_app.alpaca_credentials import normalize_alpaca_env_value
from trading_app.broker import AlpacaPaperBrokerAdapter, PaperBrokerAdapter
from trading_app.paper.statement import (
    capture_broker_statement_snapshot,
    load_broker_statement,
    reconcile_statement_snapshot,
    write_broker_statement_json,
    write_statement_reconciliation_markdown,
)
from trading_app.runtime.broker_history import RuntimeBrokerOrderHistoryAuditor
from trading_app.runtime.coherence import RuntimeEvidenceCoherenceAuditor
from trading_app.runtime.completion import RuntimeCompletionAuditor
from trading_app.runtime.dashboard_audit import RuntimeDashboardConsistencyAuditor
from trading_app.runtime.dashboard_visual import RuntimeDashboardVisualAuditor
from trading_app.runtime.data_quality import RuntimeDataQualityAuditor
from trading_app.runtime.evidence import RuntimeEvidenceBundleBuilder
from trading_app.runtime.fills import RuntimeFillSyncAuditor
from trading_app.runtime.governance import RuntimeModelGovernanceAuditor
from trading_app.runtime.guardrails import RuntimeOrderGuardrailAuditor
from trading_app.runtime.integrity import RuntimeArtifactIntegrityAuditor
from trading_app.runtime.lifecycle import RuntimeLifecycleDrillAuditor
from trading_app.runtime.models import (
    RuntimePostRunReviewReport,
    RuntimePostRunReviewStep,
    RuntimePreflightStatus,
)
from trading_app.runtime.ops import RuntimeOperationsReadinessAuditor
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.runtime.recovery import RuntimeRecoveryAuditor
from trading_app.runtime.schedule import RuntimeScheduleGuardrailAuditor
from trading_app.runtime.security import RuntimeSecretScanner
from trading_app.runtime.session_proof import RuntimeCredentialedSessionAuditor
from trading_app.runtime.soak import (
    RuntimeSoakEvidenceAnalyzer,
    RuntimeSoakEvidenceConfig,
)

BrokerFactory = Callable[[], PaperBrokerAdapter]


class RuntimePostRunReviewer:
    """Run local post-run review steps in a safe, repeatable order."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        statement_path: Path | str | None = None,
        broker_order_history_path: Path | str | None = None,
        broker_factory: BrokerFactory | None = None,
        env: Mapping[str, str] | None = None,
        secret_scan_paths: tuple[Path | str, ...] = (),
        persist_report: bool = True,
        min_duration: timedelta = timedelta(hours=24),
        max_market_gap: timedelta = timedelta(seconds=180),
        max_off_hours_gap: timedelta = timedelta(minutes=30),
        max_dashboard_age: timedelta = timedelta(minutes=15),
    ) -> None:
        self.output_dir = Path(output_dir)
        self.statement_path = Path(statement_path) if statement_path else None
        self.broker_order_history_path = (
            Path(broker_order_history_path) if broker_order_history_path else None
        )
        self.broker_factory = broker_factory or AlpacaPaperBrokerAdapter
        self.env = env if env is not None else os.environ
        self.secret_scan_paths = tuple(Path(path) for path in secret_scan_paths)
        self.persist_report = persist_report
        self.min_duration = min_duration
        self.max_market_gap = max_market_gap
        self.max_off_hours_gap = max_off_hours_gap
        self.max_dashboard_age = max_dashboard_age
        self.store = RuntimePersistenceStore(self.output_dir)

    def review(self, *, as_of: datetime | None = None) -> RuntimePostRunReviewReport:
        now = as_of or datetime.now(tz=UTC)
        steps: list[RuntimePostRunReviewStep] = []

        operations_readiness_report = RuntimeOperationsReadinessAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "operations_readiness",
                RuntimePreflightStatus.PASSED
                if operations_readiness_report.passed
                else operations_readiness_report.status,
                operations_readiness_report.summary,
                evidence=(
                    f"dashboard_url={operations_readiness_report.dashboard_url}",
                    f"checks={len(operations_readiness_report.checks)}",
                ),
                path=operations_readiness_report.markdown_path,
            )
        )

        lifecycle_drill_report = RuntimeLifecycleDrillAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "lifecycle_drill",
                RuntimePreflightStatus.PASSED
                if lifecycle_drill_report.passed
                else lifecycle_drill_report.status,
                lifecycle_drill_report.summary,
                evidence=(
                    f"controls={lifecycle_drill_report.operator_control_count}",
                    (
                        "emergency_stop="
                        f"{lifecycle_drill_report.emergency_stop_confirmed}"
                    ),
                    (
                        "shutdown_documented="
                        f"{lifecycle_drill_report.shutdown_procedure_documented}"
                    ),
                ),
                path=lifecycle_drill_report.markdown_path,
            )
        )

        soak_report = RuntimeSoakEvidenceAnalyzer(
            RuntimeSoakEvidenceConfig(
                output_dir=self.output_dir,
                min_duration=self.min_duration,
                max_market_gap=self.max_market_gap,
                max_off_hours_gap=self.max_off_hours_gap,
            )
        ).analyze(as_of=now)
        steps.append(
            _step(
                "soak_evidence",
                soak_report.status,
                "Soak evidence passed."
                if soak_report.status == RuntimePreflightStatus.PASSED
                else "Soak evidence has warnings that require operator review."
                if soak_report.status == RuntimePreflightStatus.WARNING
                else "Soak evidence is missing or failed.",
                evidence=(
                    f"duration_hours={soak_report.duration_hours}",
                    f"cycles={soak_report.cycle_count}",
                    f"off_schedule_order_cycles={soak_report.off_schedule_order_cycles}",
                    f"runtime_warning_events={soak_report.runtime_warning_event_count}",
                    f"runtime_error_events={soak_report.runtime_error_event_count}",
                ),
            )
        )

        recovery_audit_report = RuntimeRecoveryAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "restart_recovery",
                RuntimePreflightStatus.PASSED
                if recovery_audit_report.passed
                else recovery_audit_report.status,
                recovery_audit_report.summary,
                evidence=(
                    f"raw_submissions={recovery_audit_report.raw_submission_count}",
                    (
                        "recovered_submissions="
                        f"{recovery_audit_report.recovered_submission_count}"
                    ),
                    f"raw_fills={recovery_audit_report.raw_fill_count}",
                    f"recovered_fills={recovery_audit_report.recovered_fill_count}",
                ),
                path=recovery_audit_report.markdown_path,
            )
        )

        dashboard_consistency_report = RuntimeDashboardConsistencyAuditor(
            output_dir=self.output_dir,
            max_snapshot_age=self.max_dashboard_age,
        ).audit(as_of=now)
        steps.append(
            _step(
                "dashboard_consistency",
                RuntimePreflightStatus.PASSED
                if dashboard_consistency_report.passed
                else dashboard_consistency_report.status,
                dashboard_consistency_report.summary,
                evidence=(
                    f"checks={len(dashboard_consistency_report.checks)}",
                    f"status={dashboard_consistency_report.status.value}",
                ),
                path=dashboard_consistency_report.markdown_path,
            )
        )

        dashboard_visual_report = RuntimeDashboardVisualAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "dashboard_visual",
                RuntimePreflightStatus.PASSED
                if dashboard_visual_report.passed
                else dashboard_visual_report.status,
                dashboard_visual_report.summary,
                evidence=(
                    f"critical_surfaces={dashboard_visual_report.critical_surface_count}",
                    f"responsive_surfaces={dashboard_visual_report.responsive_surface_count}",
                    (
                        "failed_visual_scenarios="
                        f"{dashboard_visual_report.failed_visual_scenarios}"
                    ),
                    f"checks={len(dashboard_visual_report.checks)}",
                ),
                path=dashboard_visual_report.markdown_path,
            )
        )

        statement_reconciliation_report = None
        statement_path = None
        try:
            statement_path = self._statement_path(now)
            runtime_snapshot = _read_runtime_snapshot(self.output_dir)
            if runtime_snapshot.paper_report is None:
                raise ValueError(
                    "latest runtime snapshot does not include a paper report"
                )
            statement = load_broker_statement(statement_path)
            statement_reconciliation_report = reconcile_statement_snapshot(
                runtime_snapshot.paper_report.ledger_snapshot,
                statement,
                as_of=now,
                statement_path=statement_path,
            )
            statement_markdown_path = write_statement_reconciliation_markdown(
                statement_reconciliation_report,
                self.output_dir / "reports",
            )
            self.store.persist_statement_reconciliation(
                statement_reconciliation_report,
                markdown_path=statement_markdown_path,
            )
            steps.append(
                _step(
                    "statement_reconciliation",
                    RuntimePreflightStatus.PASSED
                    if statement_reconciliation_report.reconciled
                    else RuntimePreflightStatus.FAILED,
                    "Broker statement reconciled."
                    if statement_reconciliation_report.reconciled
                    else "Broker statement reconciliation has mismatches.",
                    evidence=(
                        f"statement={statement.statement_id}",
                        f"statement_path={statement_path}",
                        f"issues={len(statement_reconciliation_report.issues)}",
                    ),
                    path=str(statement_markdown_path),
                )
            )
        except Exception as error:
            steps.append(
                _step(
                    "statement_reconciliation",
                    RuntimePreflightStatus.FAILED,
                    "Broker statement capture or reconciliation failed.",
                    evidence=(_safe_error(error, self.env),),
                    path=str(statement_path) if statement_path is not None else None,
                )
            )

        secret_scan_paths = self.secret_scan_paths
        if statement_path is not None:
            secret_scan_paths = (*secret_scan_paths, statement_path)
        secret_scan_report = RuntimeSecretScanner(
            output_dir=self.output_dir,
            env=self.env,
            scan_paths=secret_scan_paths,
        ).scan(as_of=now)
        steps.append(
            _step(
                "secret_scan",
                RuntimePreflightStatus.PASSED
                if secret_scan_report.passed
                else RuntimePreflightStatus.FAILED,
                secret_scan_report.summary,
                evidence=(
                    f"files_scanned={secret_scan_report.files_scanned}",
                    f"findings={len(secret_scan_report.findings)}",
                    f"scan_roots={len(secret_scan_report.scan_roots)}",
                ),
            )
        )

        model_governance_report = RuntimeModelGovernanceAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "model_governance",
                RuntimePreflightStatus.PASSED
                if model_governance_report.passed
                else model_governance_report.status,
                model_governance_report.summary,
                evidence=(
                    (
                        "learning_run="
                        f"{model_governance_report.learning_run_id or 'missing'}"
                    ),
                    f"recommendations={model_governance_report.recommendation_count}",
                    (
                        "authority_increases="
                        f"{len(model_governance_report.unreviewed_authority_increases)}"
                    ),
                ),
                path=model_governance_report.markdown_path,
            )
        )

        order_guardrail_report = RuntimeOrderGuardrailAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "order_guardrails",
                RuntimePreflightStatus.PASSED
                if order_guardrail_report.passed
                else order_guardrail_report.status,
                order_guardrail_report.summary,
                evidence=(
                    f"blocked={order_guardrail_report.blocked_order_scenarios}",
                    f"unexpected={order_guardrail_report.unexpected_order_scenarios}",
                    f"checks={len(order_guardrail_report.checks)}",
                ),
                path=order_guardrail_report.markdown_path,
            )
        )

        schedule_guardrail_report = RuntimeScheduleGuardrailAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "schedule_guardrails",
                RuntimePreflightStatus.PASSED
                if schedule_guardrail_report.passed
                else schedule_guardrail_report.status,
                schedule_guardrail_report.summary,
                evidence=(
                    f"approved={schedule_guardrail_report.approved_schedule_scenarios}",
                    f"protected={schedule_guardrail_report.protected_schedule_scenarios}",
                    f"unexpected={schedule_guardrail_report.unexpected_schedule_scenarios}",
                    f"checks={len(schedule_guardrail_report.checks)}",
                ),
                path=schedule_guardrail_report.markdown_path,
            )
        )

        fill_sync_report = RuntimeFillSyncAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "fill_sync",
                RuntimePreflightStatus.PASSED
                if fill_sync_report.passed
                else fill_sync_report.status,
                fill_sync_report.summary,
                evidence=(
                    f"incremental={fill_sync_report.incremental_fill_scenarios}",
                    f"duplicate={fill_sync_report.duplicate_fill_scenarios}",
                    f"unexpected={fill_sync_report.unexpected_fill_scenarios}",
                    f"checks={len(fill_sync_report.checks)}",
                ),
                path=fill_sync_report.markdown_path,
            )
        )

        data_quality_audit_report = RuntimeDataQualityAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "data_quality_audit",
                RuntimePreflightStatus.PASSED
                if data_quality_audit_report.passed
                else data_quality_audit_report.status,
                data_quality_audit_report.summary,
                evidence=(
                    (
                        "latest_price_scenarios="
                        f"{data_quality_audit_report.latest_price_scenarios}"
                    ),
                    (
                        "daily_bar_scenarios="
                        f"{data_quality_audit_report.daily_bar_scenarios}"
                    ),
                    (
                        "symbol_universe_scenarios="
                        f"{data_quality_audit_report.symbol_universe_scenarios}"
                    ),
                    f"failed={data_quality_audit_report.failed_quality_scenarios}",
                    f"checks={len(data_quality_audit_report.checks)}",
                ),
                path=data_quality_audit_report.markdown_path,
            )
        )

        broker_order_history_report = RuntimeBrokerOrderHistoryAuditor(
            output_dir=self.output_dir,
            order_history_path=self.broker_order_history_path,
            broker_factory=None
            if self.broker_order_history_path is not None
            else self.broker_factory,
            session_started_at=soak_report.started_at,
            session_completed_at=soak_report.completed_at,
        ).audit(as_of=now)
        steps.append(
            _step(
                "broker_order_history",
                RuntimePreflightStatus.PASSED
                if broker_order_history_report.passed
                else broker_order_history_report.status,
                broker_order_history_report.summary,
                evidence=(
                    f"provider={broker_order_history_report.provider}",
                    f"local_orders={broker_order_history_report.local_order_count}",
                    f"broker_orders={broker_order_history_report.broker_order_count}",
                    f"matched={broker_order_history_report.matched_order_count}",
                    f"mismatches={broker_order_history_report.mismatch_count}",
                ),
                path=broker_order_history_report.markdown_path,
            )
        )

        credentialed_session_report = RuntimeCredentialedSessionAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "credentialed_session",
                RuntimePreflightStatus.PASSED
                if credentialed_session_report.passed
                else credentialed_session_report.status,
                credentialed_session_report.summary,
                evidence=(
                    (
                        "validation="
                        f"{credentialed_session_report.validation_id or 'missing'}"
                    ),
                    (
                        "account="
                        f"{credentialed_session_report.paper_account_id or 'missing'}"
                    ),
                    (
                        "external_sources="
                        f"{credentialed_session_report.external_source_count}"
                    ),
                ),
                path=credentialed_session_report.markdown_path,
            )
        )

        evidence_coherence_report = RuntimeEvidenceCoherenceAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "evidence_coherence",
                RuntimePreflightStatus.PASSED
                if evidence_coherence_report.passed
                else evidence_coherence_report.status,
                evidence_coherence_report.summary,
                evidence=(
                    f"checks={len(evidence_coherence_report.checks)}",
                    f"status={evidence_coherence_report.status.value}",
                ),
                path=evidence_coherence_report.markdown_path,
            )
        )

        completion_audit_report = RuntimeCompletionAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "completion_audit",
                RuntimePreflightStatus.PASSED
                if completion_audit_report.passed
                else completion_audit_report.status,
                completion_audit_report.summary,
                evidence=(
                    f"proven={completion_audit_report.proven_count}",
                    f"failed={completion_audit_report.failed_count}",
                    f"external_required={completion_audit_report.external_required_count}",
                ),
                path=completion_audit_report.markdown_path,
            )
        )

        RuntimeArtifactIntegrityAuditor(output_dir=self.output_dir).audit(as_of=now)

        evidence_bundle_report = RuntimeEvidenceBundleBuilder(
            output_dir=self.output_dir,
        ).build(as_of=now)
        steps.append(
            _step(
                "evidence_bundle",
                RuntimePreflightStatus.PASSED
                if evidence_bundle_report.ready_for_operator_review
                else evidence_bundle_report.status,
                evidence_bundle_report.summary,
                evidence=(
                    f"passed={evidence_bundle_report.passed_count}",
                    f"failed={evidence_bundle_report.failed_count}",
                    f"missing_required={evidence_bundle_report.missing_required_count}",
                ),
                path=evidence_bundle_report.markdown_path,
            )
        )

        artifact_integrity_report = RuntimeArtifactIntegrityAuditor(
            output_dir=self.output_dir,
        ).audit(as_of=now)
        steps.append(
            _step(
                "artifact_integrity",
                RuntimePreflightStatus.PASSED
                if artifact_integrity_report.passed
                else artifact_integrity_report.status,
                artifact_integrity_report.summary,
                evidence=(
                    f"hashed={artifact_integrity_report.hashed_count}",
                    (
                        "missing_required="
                        f"{artifact_integrity_report.missing_required_count}"
                    ),
                    f"hash_mismatches={artifact_integrity_report.hash_mismatch_count}",
                ),
                path=artifact_integrity_report.markdown_path,
            )
        )

        failures = sum(
            1 for step in steps if step.status == RuntimePreflightStatus.FAILED
        )
        warnings = sum(
            1 for step in steps if step.status == RuntimePreflightStatus.WARNING
        )
        status = (
            RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.WARNING
            if warnings
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimePostRunReviewReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            steps=tuple(steps),
            soak_report=soak_report,
            secret_scan_report=secret_scan_report,
            statement_reconciliation_report=statement_reconciliation_report,
            completion_audit_report=completion_audit_report,
            evidence_bundle_report=evidence_bundle_report,
            dashboard_consistency_report=dashboard_consistency_report,
            dashboard_visual_report=dashboard_visual_report,
            evidence_coherence_report=evidence_coherence_report,
            artifact_integrity_report=artifact_integrity_report,
            lifecycle_drill_report=lifecycle_drill_report,
            credentialed_session_report=credentialed_session_report,
            model_governance_report=model_governance_report,
            order_guardrail_report=order_guardrail_report,
            schedule_guardrail_report=schedule_guardrail_report,
            fill_sync_report=fill_sync_report,
            data_quality_audit_report=data_quality_audit_report,
            broker_order_history_report=broker_order_history_report,
            operations_readiness_report=operations_readiness_report,
            recovery_audit_report=recovery_audit_report,
            summary=_summary(status, failures, warnings),
        )
        if self.persist_report:
            markdown_path = write_post_run_review_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_post_run_review_report(
                report,
                markdown_path=markdown_path,
            )
        return report

    def _statement_path(self, as_of: datetime) -> Path:
        if self.statement_path is not None:
            return self.statement_path
        broker = self.broker_factory()
        statement = capture_broker_statement_snapshot(broker, as_of=as_of)
        return write_broker_statement_json(
            statement,
            self.output_dir / "statements",
        )


def render_post_run_review_text(report: RuntimePostRunReviewReport) -> str:
    """Render compact post-run review status."""

    lines = [
        f"Post-run review status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Steps:",
    ]
    for step in report.steps:
        lines.append(f"- {step.name}: {step.status.value} - {step.message}")
    return "\n".join(lines)


def render_post_run_review_markdown(report: RuntimePostRunReviewReport) -> str:
    """Render a Markdown post-run review dossier."""

    lines = [
        "# Paper Runtime Post-Run Review",
        "",
        "> Paper trading only. This review does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Reviewed at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        "",
        report.summary,
        "",
        "## Steps",
        "",
        "| Step | Status | Message | Evidence | Path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for step in report.steps:
        evidence = "<br>".join(step.evidence) if step.evidence else "No evidence"
        lines.append(
            "| "
            f"{_escape_table(step.name)} | "
            f"{step.status.value} | "
            f"{_escape_table(step.message)} | "
            f"{_escape_table(evidence)} | "
            f"{_escape_table(step.path or 'not written')} |"
        )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            _next_action(report),
            "",
        ]
    )
    return "\n".join(lines)


def write_post_run_review_markdown_report(
    report: RuntimePostRunReviewReport,
    reports_dir: Path | str,
) -> Path:
    """Write the post-run review Markdown report."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"post-run-review-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_post_run_review_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run post-run review for an Alpaca paper session."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument(
        "--statement",
        default=None,
        help=(
            "Optional saved broker statement JSON or CSV. "
            "Defaults to Alpaca paper capture."
        ),
    )
    parser.add_argument(
        "--broker-order-history",
        default=None,
        help=(
            "Optional saved broker order-history JSON/JSONL. Defaults to Alpaca "
            "paper capture."
        ),
    )
    parser.add_argument("--min-duration-hours", type=float, default=24)
    parser.add_argument("--max-market-gap-seconds", type=float, default=180)
    parser.add_argument("--max-off-hours-gap-seconds", type=float, default=1800)
    parser.add_argument("--max-dashboard-age-seconds", type=float, default=900)
    parser.add_argument(
        "--include-secret-scan-path",
        action="append",
        default=[],
        help=(
            "Additional exported dashboard, log, or artifact path to include in "
            "the post-run secret scan."
        ),
    )
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimePostRunReviewer(
        output_dir=args.output_dir,
        statement_path=args.statement,
        broker_order_history_path=args.broker_order_history,
        secret_scan_paths=tuple(args.include_secret_scan_path),
        persist_report=not args.no_persist,
        min_duration=timedelta(hours=args.min_duration_hours),
        max_market_gap=timedelta(seconds=args.max_market_gap_seconds),
        max_off_hours_gap=timedelta(seconds=args.max_off_hours_gap_seconds),
        max_dashboard_age=timedelta(seconds=args.max_dashboard_age_seconds),
    ).review()
    print(
        report.model_dump_json() if args.json else render_post_run_review_text(report)
    )
    return 0 if report.passed else 1


def _read_runtime_snapshot(output_dir: Path):
    from trading_app.runtime.models import RuntimeSnapshot

    path = output_dir / "state" / "latest-runtime-snapshot.json"
    if not path.exists():
        raise ValueError(f"missing runtime snapshot: {path}")
    return RuntimeSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _step(
    name: str,
    status: RuntimePreflightStatus,
    message: str,
    *,
    evidence: tuple[str, ...] = (),
    path: str | None = None,
    required: bool = True,
) -> RuntimePostRunReviewStep:
    return RuntimePostRunReviewStep(
        name=name,
        status=status,
        required=required,
        message=message,
        evidence=evidence,
        path=path,
    )


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    warnings: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Post-run review passed; the evidence bundle is ready for review."
    return (
        f"Post-run review found {failures} failed step(s) and {warnings} warning "
        "step(s). Do not call the paper app functional yet."
    )


def _next_action(report: RuntimePostRunReviewReport) -> str:
    if report.passed:
        return (
            "Review the evidence bundle and completion audit before calling the "
            "paper app functional."
        )
    return (
        "Fix failed post-run review steps, rerun this command, and keep paper "
        "orders blocked until evidence is clean."
    )


def _safe_error(error: Exception, env: Mapping[str, str]) -> str:
    text = str(error)
    for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        value = normalize_alpaca_env_value(str(env.get(name, ""))) or ""
        if value and len(value) >= 4:
            text = text.replace(value, f"<redacted {name}>")
    return f"{type(error).__name__}: {text}"


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
