from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.broker import BrokerPositionState, BrokerStatementSnapshot
from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.learning import ModelRegistryState
from trading_app.market_data import FixtureLatestPriceFetcher
from trading_app.paper import (
    reconcile_statement_snapshot,
    write_broker_statement_json,
    write_statement_reconciliation_markdown,
)
from trading_app.reporting import write_markdown_report
from trading_app.runtime import (
    FunctionalRequirementStatus,
    OperatorControlAction,
    OperatorControlRequest,
    RuntimeBrokerOrderHistoryAuditor,
    RuntimeCompletionAuditor,
    RuntimeControlCenter,
    RuntimeCredentialedSessionAuditor,
    RuntimeCycleResult,
    RuntimeDashboardConsistencyAuditor,
    RuntimeDashboardVisualAuditor,
    RuntimeDataQualityAuditor,
    RuntimeDryRunReport,
    RuntimeDryRunStep,
    RuntimeEvidenceCoherenceAuditor,
    RuntimeFillSyncAuditor,
    RuntimeLifecycleDrillAuditor,
    RuntimeModelGovernanceAuditor,
    RuntimeOperationsReadinessAuditor,
    RuntimeOrderGuardrailAuditor,
    RuntimePersistenceStore,
    RuntimePreflightCheck,
    RuntimePreflightReport,
    RuntimePreflightStatus,
    RuntimeRecoveryAuditor,
    RuntimeScheduleGuardrailAuditor,
    RuntimeSecretScanFinding,
    RuntimeSecretScanReport,
    RuntimeSnapshot,
    RuntimeSoakEvidenceReport,
    RuntimeStatus,
    RuntimeValidationChecklistItem,
    RuntimeValidationReport,
    render_completion_audit_markdown,
    render_completion_audit_text,
    render_evidence_coherence_markdown,
    render_evidence_coherence_text,
    write_broker_order_history_json,
)
from trading_app.runtime.audit_coverage import (
    REQUIRED_VALIDATION_CHECKLIST_ITEMS,
    functional_completion_coverage_gap,
)
from trading_app.runtime.coherence import main as coherence_main
from trading_app.runtime.completion import main as completion_main
from trading_app.schemas import DataFeed, OrderStatus

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_completion_audit_reports_external_requirements_when_artifacts_missing(
    tmp_path,
) -> None:
    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    statuses = {item.status for item in report.requirements}
    text = render_completion_audit_text(report)

    assert not report.passed
    assert report.status == RuntimePreflightStatus.WARNING
    assert report.external_required_count > 0
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert FunctionalRequirementStatus.EXTERNAL_REQUIRED in statuses
    assert FunctionalRequirementStatus.MISSING in statuses
    assert "Completion audit status" in text
    assert (tmp_path / "state" / "latest-completion-audit-report.json").exists()
    assert (tmp_path / "journal" / "completion-audits.jsonl").exists()


def test_completion_audit_passes_with_complete_external_like_artifacts(
    tmp_path,
) -> None:
    _persist_complete_evidence(tmp_path)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.proven_count == 18
    assert report.failed_count == 0
    assert report.missing_count == 0
    assert report.external_required_count == 0
    assert report.markdown_path is not None
    markdown = Path(report.markdown_path).read_text(encoding="utf-8")
    assert "Functional Paper App Completion Audit" in markdown
    assert "FR-18" in markdown
    assert "Paper trading only" in markdown
    assert {item.status for item in report.requirements} == {
        FunctionalRequirementStatus.PROVEN
    }


def test_functional_completion_coverage_requires_markdown_artifact(tmp_path) -> None:
    _persist_complete_evidence(tmp_path)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    assert not functional_completion_coverage_gap(report)
    assert report.markdown_path is not None

    Path(report.markdown_path).unlink()

    assert "markdown_path_file=missing" in functional_completion_coverage_gap(report)


def test_completion_audit_fails_duplicate_fills_and_secret_scan_failure(
    tmp_path,
) -> None:
    store = _persist_complete_evidence(tmp_path)
    duplicate_fill = build_demo_dashboard_snapshot().recent_fills[0]
    store.persist_fill(duplicate_fill)
    store.persist_secret_scan_report(
        RuntimeSecretScanReport(
            as_of=NOW,
            status=RuntimePreflightStatus.FAILED,
            passed=False,
            output_dir=str(tmp_path),
            files_scanned=1,
            files_skipped=0,
            secret_names_checked=("ALPACA_API_KEY",),
            findings=(
                RuntimeSecretScanFinding(
                    path="reports/daily.md",
                    line_number=4,
                    secret_name="ALPACA_API_KEY",
                    message="Configured secret value was found in runtime artifacts.",
                ),
            ),
            summary="Secret scan failed.",
        )
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    failed_ids = {
        item.id
        for item in report.requirements
        if item.status == FunctionalRequirementStatus.FAILED
    }

    assert not report.passed
    assert report.status == RuntimePreflightStatus.FAILED
    assert {"FR-10", "FR-11", "FR-17"}.issubset(failed_ids)


def test_completion_audit_requires_clean_credential_secret_scan(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-secret-scan-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-17"].status == FunctionalRequirementStatus.MISSING

    secret_scan = weak_store.read_secret_scan_report()
    assert secret_scan is not None
    weak_store.persist_secret_scan_report(
        secret_scan.model_copy(update={"secret_names_checked": ()})
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-17"].status == FunctionalRequirementStatus.MISSING


def test_completion_audit_requires_clean_statement_reconciliation(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    demo = build_demo_dashboard_snapshot()
    mismatched_statement = _matching_statement(demo).model_copy(
        update={"cash": demo.paper_report.ledger_snapshot.cash + Decimal("1")}
    )
    statement_report = reconcile_statement_snapshot(
        demo.paper_report.ledger_snapshot,
        mismatched_statement,
        as_of=NOW,
        statement_path=write_broker_statement_json(
            mismatched_statement,
            tmp_path / "statements",
        ),
    )
    markdown_path = write_statement_reconciliation_markdown(
        statement_report,
        tmp_path / "reports",
    )
    store.persist_statement_reconciliation(
        statement_report,
        markdown_path=markdown_path,
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-18"].status == FunctionalRequirementStatus.FAILED
    assert any("CASH_MISMATCH" in item for item in by_id["FR-18"].evidence)


def test_completion_audit_requires_unchanged_statement_source(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    statement_report = store.read_statement_reconciliation_report()
    assert statement_report is not None
    assert statement_report.statement_path is not None
    Path(statement_report.statement_path).write_text(
        '{"changed": true}',
        encoding="utf-8",
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-18"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert any("statement_sha256_mismatch" in item for item in by_id["FR-18"].evidence)


def test_completion_audit_requires_dashboard_consistency_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-dashboard-consistency-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-05"].status == FunctionalRequirementStatus.MISSING

    consistency = failed_store.read_dashboard_consistency_report()
    assert consistency is not None
    failed_store.persist_dashboard_consistency_report(
        consistency.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "summary": "Dashboard consistency failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-05"].status == FunctionalRequirementStatus.FAILED

    weak_consistency = weak_store.read_dashboard_consistency_report()
    assert weak_consistency is not None
    weak_store.persist_dashboard_consistency_report(
        weak_consistency.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_consistency.checks[:1],
                "summary": "Dashboard consistency passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-05"].status == FunctionalRequirementStatus.FAILED
    assert any("missing_checks=" in item for item in weak_by_id["FR-05"].evidence)


def test_completion_audit_requires_dashboard_visual_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-dashboard-visual-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-05"].status == FunctionalRequirementStatus.MISSING
    assert missing_by_id["FR-15"].status == FunctionalRequirementStatus.MISSING

    visual = failed_store.read_dashboard_visual_report()
    assert visual is not None
    failed_store.persist_dashboard_visual_report(
        visual.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "failed_visual_scenarios": 1,
                "summary": "Dashboard visual audit failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-05"].status == FunctionalRequirementStatus.FAILED

    weak_visual = weak_store.read_dashboard_visual_report()
    assert weak_visual is not None
    weak_store.persist_dashboard_visual_report(
        weak_visual.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_visual.checks[:1],
                "critical_surface_count": 1,
                "responsive_surface_count": 0,
                "failed_visual_scenarios": 0,
                "summary": "Dashboard visual audit passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-05"].status == FunctionalRequirementStatus.FAILED
    assert weak_by_id["FR-15"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "critical_surface_count_missing=6" in item
        for item in weak_by_id["FR-05"].evidence
    )
    assert any("missing_checks=" in item for item in weak_by_id["FR-15"].evidence)


def test_completion_audit_requires_dashboard_operator_state_to_match_runtime(
    tmp_path,
) -> None:
    store = _persist_complete_evidence(tmp_path)
    dashboard = _read_dashboard_snapshot(tmp_path)
    assert dashboard.control_state is not None
    stale_control = {
        **dashboard.control_state,
        "paused": True,
    }
    store.persist_dashboard_snapshot(
        dashboard.model_copy(
            update={
                "control_state": stale_control,
                "alerts": (),
            }
        )
    )
    RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-15"].status == FunctionalRequirementStatus.FAILED
    assert any("dashboard_alerts" in item for item in by_id["FR-15"].evidence)


def test_completion_audit_rejects_dashboard_demo_provenance(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    snapshot = _read_runtime_snapshot(tmp_path)
    demo = build_demo_dashboard_snapshot()
    store.persist_dashboard_snapshot(
        demo.model_copy(
            update={
                "generated_at": NOW,
                "mode": "Alpaca Paper",
                "broker": "alpaca-paper",
                "runtime_state": snapshot,
                "paper_report": snapshot.paper_report,
                "daily_report": snapshot.daily_report,
                "control_state": snapshot.control_state,
                "alerts": snapshot.alerts,
                "health_report": snapshot.health_report,
                "statement_reconciliation": None,
                "statement_reconciliation_path": None,
                "completion_audit": None,
            }
        )
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-05"].status == FunctionalRequirementStatus.FAILED
    assert any("demo_provenance=" in item for item in by_id["FR-05"].evidence)


def test_completion_audit_requires_operations_readiness_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-operations-readiness-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-01"].status == FunctionalRequirementStatus.MISSING
    assert missing_by_id["FR-17"].status == FunctionalRequirementStatus.MISSING

    failed_ops = RuntimeOperationsReadinessAuditor(
        output_dir=failed_dir,
        profile_output_dir=failed_dir,
    ).audit(as_of=NOW)
    assert not failed_ops.passed
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-01"].status == FunctionalRequirementStatus.FAILED
    assert failed_by_id["FR-17"].status == FunctionalRequirementStatus.FAILED

    weak_ops = weak_store.read_operations_readiness_report()
    assert weak_ops is not None
    weak_store.persist_operations_readiness_report(
        weak_ops.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_ops.checks[:1],
                "summary": "Operations readiness passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-01"].status == FunctionalRequirementStatus.FAILED
    assert weak_by_id["FR-17"].status == FunctionalRequirementStatus.FAILED
    assert any("missing_checks=" in item for item in weak_by_id["FR-01"].evidence)
    assert any("missing_checks=" in item for item in weak_by_id["FR-17"].evidence)


def test_completion_audit_requires_lifecycle_drill(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-lifecycle-drill-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-01"].status == FunctionalRequirementStatus.MISSING
    assert missing_by_id["FR-15"].status == FunctionalRequirementStatus.MISSING

    lifecycle = failed_store.read_lifecycle_drill_report()
    assert lifecycle is not None
    failed_store.persist_lifecycle_drill_report(
        lifecycle.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "operator_control_count": 1,
                "emergency_stop_confirmed": False,
                "summary": "Lifecycle drill failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-01"].status == FunctionalRequirementStatus.FAILED
    assert failed_by_id["FR-15"].status == FunctionalRequirementStatus.FAILED

    weak_lifecycle = weak_store.read_lifecycle_drill_report()
    assert weak_lifecycle is not None
    weak_store.persist_lifecycle_drill_report(
        weak_lifecycle.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_lifecycle.checks[:1],
                "summary": "Lifecycle drill passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-01"].status == FunctionalRequirementStatus.FAILED
    assert weak_by_id["FR-15"].status == FunctionalRequirementStatus.FAILED
    assert any("missing_checks=" in item for item in weak_by_id["FR-01"].evidence)
    assert any("missing_checks=" in item for item in weak_by_id["FR-15"].evidence)


def test_completion_audit_requires_credentialed_session_proof(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-credentialed-session-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-01"].status == FunctionalRequirementStatus.MISSING

    proof = failed_store.read_credentialed_session_report()
    assert proof is not None
    failed_store.persist_credentialed_session_report(
        proof.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "paper_account_id": None,
                "summary": "Credentialed session proof failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-01"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "credentialed_session_status=failed" in item
        for item in failed_by_id["FR-01"].evidence
    )

    weak_proof = weak_store.read_credentialed_session_report()
    assert weak_proof is not None
    weak_store.persist_credentialed_session_report(
        weak_proof.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_proof.checks[:1],
                "external_source_count": 0,
                "summary": "Credentialed session proof passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-01"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "external_source_count_missing=3" in item
        for item in weak_by_id["FR-01"].evidence
    )
    assert any("missing_checks=" in item for item in weak_by_id["FR-01"].evidence)


def test_completion_audit_requires_restart_recovery_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    stale_dir = tmp_path / "stale"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    stale_store = _persist_complete_evidence(stale_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-recovery-audit-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-11"].status == FunctionalRequirementStatus.MISSING

    stale_store.persist_fill(build_demo_dashboard_snapshot().recent_fills[0])
    stale_report = RuntimeCompletionAuditor(output_dir=stale_dir).audit(as_of=NOW)
    stale_by_id = {item.id: item for item in stale_report.requirements}

    assert not stale_report.passed
    assert stale_by_id["FR-11"].status == FunctionalRequirementStatus.FAILED
    assert any("current_fill_count=2" in item for item in stale_by_id["FR-11"].evidence)

    weak_recovery = weak_store.read_recovery_audit_report()
    assert weak_recovery is not None
    weak_store.persist_recovery_audit_report(
        weak_recovery.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_recovery.checks[:1],
                "summary": "Restart recovery audit passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-11"].status == FunctionalRequirementStatus.FAILED
    assert any("missing_checks=" in item for item in weak_by_id["FR-11"].evidence)


def test_completion_audit_requires_model_governance_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-model-governance-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-14"].status == FunctionalRequirementStatus.MISSING

    learning = _read_runtime_snapshot(failed_dir).nightly_learning
    assert learning is not None
    promoted_record = learning.registry_after.records[1].model_copy(
        update={"state": ModelRegistryState.SHADOW}
    )
    failed_learning = learning.model_copy(
        update={
            "registry_after": learning.registry_after.model_copy(
                update={
                    "records": (
                        learning.registry_after.records[0],
                        promoted_record,
                    )
                }
            )
        }
    )
    failed_store.persist_learning_run(failed_learning)
    failed_store.persist_runtime_snapshot(
        _read_runtime_snapshot(failed_dir).model_copy(
            update={"nightly_learning": failed_learning}
        )
    )
    RuntimeModelGovernanceAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-14"].status == FunctionalRequirementStatus.FAILED
    assert any("authority increase" in item for item in failed_by_id["FR-14"].evidence)

    weak_governance = weak_store.read_model_governance_report()
    assert weak_governance is not None
    weak_store.persist_model_governance_report(
        weak_governance.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_governance.checks[:1],
                "recommendation_count": 0,
                "summary": "Model governance passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-13"].status == FunctionalRequirementStatus.FAILED
    assert weak_by_id["FR-14"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "recommendation_count_missing=1" in item
        for item in weak_by_id["FR-14"].evidence
    )
    assert any("missing_checks=" in item for item in weak_by_id["FR-13"].evidence)


def test_completion_audit_requires_learning_after_daily_report(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    snapshot = _read_runtime_snapshot(tmp_path)
    assert snapshot.daily_report is not None
    assert snapshot.nightly_learning is not None
    early_learning = snapshot.nightly_learning.model_copy(
        update={"as_of": snapshot.daily_report.generated_at - timedelta(minutes=1)}
    )
    store.persist_learning_run(early_learning)
    store.persist_runtime_snapshot(
        snapshot.model_copy(update={"nightly_learning": early_learning})
    )
    RuntimeModelGovernanceAuditor(output_dir=tmp_path).audit(as_of=NOW)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-13"].status == FunctionalRequirementStatus.FAILED
    assert any("learning_as_of" in item for item in by_id["FR-13"].evidence)


def test_completion_audit_requires_recommendation_only_learning(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    snapshot = _read_runtime_snapshot(tmp_path)
    assert snapshot.nightly_learning is not None
    recommendation = snapshot.nightly_learning.recommendations[0].model_copy(
        update={"manual_review_required": False}
    )
    ungated_learning = snapshot.nightly_learning.model_copy(
        update={"recommendations": (recommendation,)}
    )
    store.persist_learning_run(ungated_learning)
    store.persist_runtime_snapshot(
        snapshot.model_copy(update={"nightly_learning": ungated_learning})
    )
    RuntimeModelGovernanceAuditor(output_dir=tmp_path).audit(as_of=NOW)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-13"].status == FunctionalRequirementStatus.FAILED
    assert by_id["FR-14"].status == FunctionalRequirementStatus.FAILED
    assert any("missing_manual_review" in item for item in by_id["FR-13"].evidence)


def test_completion_audit_requires_order_guardrail_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-order-guardrail-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-09"].status == FunctionalRequirementStatus.MISSING

    guardrail = failed_store.read_order_guardrail_report()
    assert guardrail is not None
    failed_store.persist_order_guardrail_report(
        guardrail.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "unexpected_order_scenarios": 1,
                "summary": "Order guardrail audit failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-09"].status == FunctionalRequirementStatus.FAILED
    assert any("unexpected=1" in item for item in failed_by_id["FR-09"].evidence)

    weak_guardrail = weak_store.read_order_guardrail_report()
    assert weak_guardrail is not None
    weak_store.persist_order_guardrail_report(
        weak_guardrail.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_guardrail.checks[:1],
                "blocked_order_scenarios": 1,
                "unexpected_order_scenarios": 0,
                "summary": "Order guardrail audit passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-09"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "blocked_order_scenarios_missing=5" in item
        for item in weak_by_id["FR-09"].evidence
    )
    assert any("missing_checks=" in item for item in weak_by_id["FR-09"].evidence)


def test_completion_audit_requires_schedule_guardrail_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-schedule-guardrail-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-08"].status == FunctionalRequirementStatus.MISSING

    guardrail = failed_store.read_schedule_guardrail_report()
    assert guardrail is not None
    failed_store.persist_schedule_guardrail_report(
        guardrail.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "unexpected_schedule_scenarios": 1,
                "summary": "Schedule guardrail audit failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-08"].status == FunctionalRequirementStatus.FAILED
    assert any("unexpected=1" in item for item in failed_by_id["FR-08"].evidence)

    weak_guardrail = weak_store.read_schedule_guardrail_report()
    assert weak_guardrail is not None
    weak_store.persist_schedule_guardrail_report(
        weak_guardrail.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_guardrail.checks[:1],
                "approved_schedule_scenarios": 0,
                "protected_schedule_scenarios": 1,
                "unexpected_schedule_scenarios": 0,
                "summary": "Schedule guardrail audit passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-08"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "approved_schedule_scenarios_missing=1" in item
        for item in weak_by_id["FR-08"].evidence
    )
    assert any(
        "protected_schedule_scenarios_missing=3" in item
        for item in weak_by_id["FR-08"].evidence
    )
    assert any("missing_checks=" in item for item in weak_by_id["FR-08"].evidence)


def test_completion_audit_requires_fill_sync_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-fill-sync-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-10"].status == FunctionalRequirementStatus.MISSING

    fill_sync = failed_store.read_fill_sync_report()
    assert fill_sync is not None
    failed_store.persist_fill_sync_report(
        fill_sync.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "unexpected_fill_scenarios": 1,
                "summary": "Fill-sync audit failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-10"].status == FunctionalRequirementStatus.FAILED
    assert any("unexpected=1" in item for item in failed_by_id["FR-10"].evidence)

    weak_fill_sync = weak_store.read_fill_sync_report()
    assert weak_fill_sync is not None
    weak_store.persist_fill_sync_report(
        weak_fill_sync.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_fill_sync.checks[:1],
                "incremental_fill_scenarios": 1,
                "duplicate_fill_scenarios": 0,
                "unexpected_fill_scenarios": 0,
                "summary": "Fill-sync audit passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-10"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "incremental_fill_scenarios_missing=1" in item
        for item in weak_by_id["FR-10"].evidence
    )
    assert any(
        "duplicate_fill_scenarios_missing=2" in item
        for item in weak_by_id["FR-10"].evidence
    )
    assert any("missing_checks=" in item for item in weak_by_id["FR-10"].evidence)


def test_completion_audit_requires_data_quality_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-data-quality-audit-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-06"].status == FunctionalRequirementStatus.MISSING
    assert missing_by_id["FR-16"].status == FunctionalRequirementStatus.MISSING

    audit = failed_store.read_data_quality_audit_report()
    assert audit is not None
    failed_store.persist_data_quality_audit_report(
        audit.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "failed_quality_scenarios": 1,
                "summary": "Data-quality audit failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-06"].status == FunctionalRequirementStatus.FAILED
    assert failed_by_id["FR-16"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "failed_quality_scenarios=1" in item for item in failed_by_id["FR-06"].evidence
    )

    weak_audit = weak_store.read_data_quality_audit_report()
    assert weak_audit is not None
    weak_store.persist_data_quality_audit_report(
        weak_audit.model_copy(
            update={
                "latest_price_scenarios": 1,
                "daily_bar_scenarios": 0,
                "symbol_universe_scenarios": 0,
                "checks": (),
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-06"].status == FunctionalRequirementStatus.FAILED
    assert weak_by_id["FR-16"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "latest_price_scenarios_missing=2" in item
        for item in weak_by_id["FR-06"].evidence
    )
    assert any(
        "daily_bar_scenarios_missing=3" in item for item in weak_by_id["FR-06"].evidence
    )
    assert any(
        "symbol_universe_scenarios_missing=1" in item
        for item in weak_by_id["FR-06"].evidence
    )


def test_completion_audit_requires_broker_order_history_audit(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    failed_dir = tmp_path / "failed"
    weak_dir = tmp_path / "weak"
    missing_store = _persist_complete_evidence(missing_dir)
    failed_store = _persist_complete_evidence(failed_dir)
    weak_store = _persist_complete_evidence(weak_dir)

    (missing_store.state_dir / "latest-broker-order-history-report.json").unlink()
    missing_report = RuntimeCompletionAuditor(output_dir=missing_dir).audit(as_of=NOW)
    missing_by_id = {item.id: item for item in missing_report.requirements}

    assert not missing_report.passed
    assert missing_by_id["FR-07"].status == FunctionalRequirementStatus.MISSING

    history = failed_store.read_broker_order_history_report()
    assert history is not None
    failed_store.persist_broker_order_history_report(
        history.model_copy(
            update={
                "status": RuntimePreflightStatus.FAILED,
                "passed": False,
                "mismatch_count": 1,
                "summary": "Broker order-history audit failed.",
            }
        )
    )
    failed_report = RuntimeCompletionAuditor(output_dir=failed_dir).audit(as_of=NOW)
    failed_by_id = {item.id: item for item in failed_report.requirements}

    assert not failed_report.passed
    assert failed_by_id["FR-07"].status == FunctionalRequirementStatus.FAILED
    assert any("mismatches=1" in item for item in failed_by_id["FR-07"].evidence)

    weak_history = weak_store.read_broker_order_history_report()
    assert weak_history is not None
    weak_store.persist_broker_order_history_report(
        weak_history.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_history.checks[:1],
                "matched_order_count": 0,
                "mismatch_count": 0,
                "summary": "Broker order-history audit passed.",
            }
        )
    )
    weak_report = RuntimeCompletionAuditor(output_dir=weak_dir).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_report.requirements}

    assert not weak_report.passed
    assert weak_by_id["FR-07"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "matched_order_count_missing=" in item for item in weak_by_id["FR-07"].evidence
    )
    assert any("missing_checks=" in item for item in weak_by_id["FR-07"].evidence)


def test_completion_audit_rejects_test_only_provenance_markers(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    preflight = _preflight_report()
    fixture_validation = _validation_report(preflight).model_copy(
        update={"id": "validation-fixture"}
    )
    store.persist_validation_report(fixture_validation)
    broker_history = store.read_broker_order_history_report()
    assert broker_history is not None
    store.persist_broker_order_history_report(
        broker_history.model_copy(update={"source": "provided"})
    )
    demo = build_demo_dashboard_snapshot()
    fixture_statement = _matching_statement(demo).model_copy(
        update={"source": "fixture-statement"}
    )
    fixture_statement_report = reconcile_statement_snapshot(
        _alpaca_paper_report(demo.paper_report).ledger_snapshot,
        fixture_statement,
        as_of=NOW,
    )
    statement_path = write_statement_reconciliation_markdown(
        fixture_statement_report,
        tmp_path / "reports",
    )
    store.persist_statement_reconciliation(
        fixture_statement_report,
        markdown_path=statement_path,
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-01"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert by_id["FR-07"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert by_id["FR-18"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED


def test_completion_audit_requires_soak_price_refresh_and_broker_sync(
    tmp_path,
) -> None:
    store = _persist_complete_evidence(tmp_path)
    soak = store.read_soak_evidence_report()
    assert soak is not None
    store.persist_soak_evidence_report(
        soak.model_copy(
            update={
                "prices_refreshed_cycle_count": soak.cycle_count - 1,
                "broker_synced_cycle_count": soak.cycle_count - 1,
                "missed_price_refresh_cycles": 1,
                "missed_broker_sync_cycles": 1,
            }
        )
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-04"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "missed_price_refresh_cycles=1" in item for item in by_id["FR-04"].evidence
    )
    assert any(
        "missed_broker_sync_cycles=1" in item for item in by_id["FR-04"].evidence
    )


def test_completion_audit_requires_clean_soak_runtime_events(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    soak = store.read_soak_evidence_report()
    assert soak is not None
    store.persist_soak_evidence_report(
        soak.model_copy(
            update={
                "runtime_event_count": 2,
                "runtime_warning_event_count": 1,
                "runtime_error_event_count": 1,
            }
        )
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-04"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "runtime_error_event_count=1" in item for item in by_id["FR-04"].evidence
    )


def test_completion_audit_requires_alpaca_paper_broker_provider(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    snapshot = _read_runtime_snapshot(tmp_path)
    demo_report = build_demo_dashboard_snapshot().paper_report
    store.persist_runtime_snapshot(
        snapshot.model_copy(update={"paper_report": demo_report})
    )
    dashboard = store.recover().dashboard_snapshot
    assert dashboard is not None
    store.persist_dashboard_snapshot(
        dashboard.model_copy(
            update={"broker": "memory-paper", "paper_report": demo_report}
        )
    )
    RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-07"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert "broker_provider=memory-paper" in by_id["FR-07"].evidence


def test_evidence_coherence_audit_passes_with_complete_artifacts(tmp_path) -> None:
    _persist_complete_evidence(tmp_path)

    report = RuntimeEvidenceCoherenceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_evidence_coherence_text(report)
    markdown = render_evidence_coherence_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert {check.name for check in report.checks}.issuperset(
        {
            "validation_before_soak",
            "snapshot_within_review_window",
            "alpaca_provider_alignment",
            "broker_order_history_after_runtime_snapshot",
            "broker_order_history_provider_alignment",
            "broker_order_history_order_alignment",
            "alpaca_price_source_alignment",
            "soak_evidence_clean",
        }
    )
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Evidence coherence status" in text
    assert "Paper Runtime Evidence Coherence Audit" in markdown


def test_evidence_coherence_failure_blocks_full_day_completion(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    preflight = _preflight_report()
    mixed_validation = _validation_report(preflight).model_copy(
        update={
            "started_at": NOW + timedelta(minutes=1),
            "completed_at": NOW + timedelta(minutes=2),
        }
    )
    store.persist_validation_report(mixed_validation)

    coherence = RuntimeEvidenceCoherenceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    completion = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in completion.requirements}

    assert not coherence.passed
    assert not completion.passed
    assert by_id["FR-04"].status == FunctionalRequirementStatus.FAILED
    assert any("evidence coherence" in item for item in by_id["FR-04"].evidence)

    RuntimeEvidenceCoherenceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    weak_coherence = store.read_evidence_coherence_report()
    assert weak_coherence is not None
    store.persist_evidence_coherence_report(
        weak_coherence.model_copy(
            update={
                "status": RuntimePreflightStatus.PASSED,
                "passed": True,
                "checks": weak_coherence.checks[:1],
                "summary": "Evidence coherence passed.",
            }
        )
    )
    weak_completion = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    weak_by_id = {item.id: item for item in weak_completion.requirements}

    assert not weak_completion.passed
    assert weak_by_id["FR-04"].status == FunctionalRequirementStatus.FAILED
    assert any("missing_checks=" in item for item in weak_by_id["FR-04"].evidence)


def test_evidence_coherence_requires_broker_order_history(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    (store.state_dir / "latest-broker-order-history-report.json").unlink()

    coherence = RuntimeEvidenceCoherenceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    completion = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    coherence_by_name = {check.name: check for check in coherence.checks}
    completion_by_id = {item.id: item for item in completion.requirements}

    assert not coherence.passed
    assert coherence_by_name["broker_order_history_present"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert not completion.passed
    assert completion_by_id["FR-04"].status == FunctionalRequirementStatus.FAILED
    assert completion_by_id["FR-07"].status == FunctionalRequirementStatus.MISSING


def test_evidence_coherence_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    complete_dir = tmp_path / "complete"
    missing_dir = tmp_path / "missing"
    _persist_complete_evidence(complete_dir)

    success = coherence_main(["--output-dir", str(complete_dir), "--json"])
    failure = coherence_main(["--output-dir", str(missing_dir), "--json"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def test_completion_audit_requires_alpaca_validation_and_price_source(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    preflight = _preflight_report()
    bad_dry_run = _dry_run_report(preflight).model_copy(
        update={
            "broker_provider": "memory-paper",
            "latest_price_source": "latest-fixture",
        }
    )
    bad_validation = _validation_report(preflight).model_copy(
        update={
            "monitor_dry_run_report": bad_dry_run,
            "broker_providers": ("memory-paper",),
            "latest_price_sources": ("latest-fixture",),
        }
    )
    store.persist_dry_run_report(bad_dry_run)
    store.persist_validation_report(bad_validation)
    snapshot = _read_runtime_snapshot(tmp_path)
    latest_prices = FixtureLatestPriceFetcher(
        {"SPY": Decimal("500")},
        observed_at=NOW,
        source="latest-fixture",
    ).fetch_latest_prices(("SPY",), as_of=NOW, feed=DataFeed.IEX)
    store.persist_runtime_snapshot(
        snapshot.model_copy(update={"latest_prices": latest_prices})
    )

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-01"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert by_id["FR-03"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert by_id["FR-06"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert any("memory-paper" in item for item in by_id["FR-01"].evidence)
    assert any("latest-fixture" in item for item in by_id["FR-06"].evidence)


def test_completion_audit_requires_validation_checklist(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    validation = store.recover().validation_report
    assert validation is not None
    store.persist_validation_report(validation.model_copy(update={"checklist": ()}))

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert not report.passed
    assert by_id["FR-01"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert any(
        "validation_broker_providers=alpaca-paper" in item
        for item in by_id["FR-01"].evidence
    )


def test_completion_audit_requires_written_daily_report_artifact(tmp_path) -> None:
    missing_path_dir = tmp_path / "missing-path"
    missing_file_dir = tmp_path / "missing-file"
    early_dir = tmp_path / "early"
    missing_path_store = _persist_complete_evidence(missing_path_dir)
    missing_file_store = _persist_complete_evidence(missing_file_dir)
    early_store = _persist_complete_evidence(early_dir)

    (missing_path_store.state_dir / "latest-daily-report-path.json").unlink()
    missing_path_report = RuntimeCompletionAuditor(output_dir=missing_path_dir).audit(
        as_of=NOW
    )
    missing_path_by_id = {item.id: item for item in missing_path_report.requirements}

    assert not missing_path_report.passed
    assert missing_path_by_id["FR-12"].status == FunctionalRequirementStatus.MISSING

    daily_report_path = missing_file_store.recover().daily_report_path
    assert daily_report_path is not None
    daily_report_path.unlink()
    missing_file_report = RuntimeCompletionAuditor(output_dir=missing_file_dir).audit(
        as_of=NOW
    )
    missing_file_by_id = {item.id: item for item in missing_file_report.requirements}

    assert not missing_file_report.passed
    assert missing_file_by_id["FR-12"].status == FunctionalRequirementStatus.FAILED
    assert any(
        "path_exists=false" in item for item in missing_file_by_id["FR-12"].evidence
    )

    recovered = early_store.recover()
    assert recovered.daily_report is not None
    assert recovered.daily_report_path is not None
    early_generated_at = NOW - timedelta(hours=6)
    early_metadata = recovered.daily_report.report_metadata.model_copy(
        update={"generated_at": early_generated_at}
    )
    early_report = recovered.daily_report.model_copy(
        update={"generated_at": early_generated_at, "report_metadata": early_metadata}
    )
    early_store.persist_daily_report(
        early_report,
        markdown_path=recovered.daily_report_path,
    )
    early_audit = RuntimeCompletionAuditor(output_dir=early_dir).audit(as_of=NOW)
    early_by_id = {item.id: item for item in early_audit.requirements}

    assert not early_audit.passed
    assert early_by_id["FR-12"].status == FunctionalRequirementStatus.FAILED
    assert any("generated_at" in item for item in early_by_id["FR-12"].evidence)


def test_completion_audit_requires_quality_and_active_model_evidence(
    tmp_path,
) -> None:
    missing_quality_dir = tmp_path / "missing-quality"
    missing_active_dir = tmp_path / "missing-active"
    quality_store = _persist_complete_evidence(missing_quality_dir)
    active_store = _persist_complete_evidence(missing_active_dir)

    quality_snapshot = _read_runtime_snapshot(missing_quality_dir)
    quality_report = quality_snapshot.daily_report.model_copy(
        update={"data_quality_report": None}
    )
    _replace_daily_report(quality_store, quality_report)
    quality_store.persist_runtime_snapshot(
        quality_snapshot.model_copy(update={"daily_report": quality_report})
    )
    quality_dashboard = quality_store.recover().dashboard_snapshot
    assert quality_dashboard is not None
    quality_store.persist_dashboard_snapshot(
        quality_dashboard.model_copy(update={"daily_report": quality_report})
    )

    quality_audit = RuntimeCompletionAuditor(output_dir=missing_quality_dir).audit(
        as_of=NOW
    )
    quality_by_id = {item.id: item for item in quality_audit.requirements}

    assert not quality_audit.passed
    assert quality_by_id["FR-05"].status == FunctionalRequirementStatus.MISSING
    assert quality_by_id["FR-06"].status == FunctionalRequirementStatus.MISSING
    assert quality_by_id["FR-12"].status == FunctionalRequirementStatus.MISSING

    active_snapshot = _read_runtime_snapshot(missing_active_dir)
    active_report = active_snapshot.daily_report.model_copy(
        update={"active_strategy_definition": None}
    )
    _replace_daily_report(active_store, active_report)
    active_store.persist_runtime_snapshot(
        active_snapshot.model_copy(update={"daily_report": active_report})
    )
    active_dashboard = active_store.recover().dashboard_snapshot
    assert active_dashboard is not None
    active_store.persist_dashboard_snapshot(
        active_dashboard.model_copy(
            update={
                "daily_report": active_report,
                "active_strategy_definition": None,
            }
        )
    )

    active_audit = RuntimeCompletionAuditor(output_dir=missing_active_dir).audit(
        as_of=NOW
    )
    active_by_id = {item.id: item for item in active_audit.requirements}

    assert not active_audit.passed
    assert active_by_id["FR-05"].status == FunctionalRequirementStatus.MISSING
    assert active_by_id["FR-12"].status == FunctionalRequirementStatus.MISSING
    assert "active-model dossier" in active_by_id["FR-12"].remediation


def test_completion_audit_uses_validation_embedded_dry_run_evidence(
    tmp_path,
) -> None:
    store = RuntimePersistenceStore(tmp_path)
    preflight = _preflight_report()
    validation = RuntimeValidationReport(
        id="validation-embedded-proof",
        started_at=NOW,
        completed_at=NOW,
        status=RuntimePreflightStatus.WARNING,
        can_start_full_day_soak=True,
        summary="Validation completed with external soak still required.",
        preflight_report=preflight,
        monitor_dry_run_report=_dry_run_report(preflight),
        steps=(),
        checklist=_validation_checklist(),
        warnings=1,
        failures=0,
        latest_prices_refreshed=True,
        latest_prices_fresh=True,
        broker_synced=True,
        dashboard_snapshot_serialized=True,
        orders_submitted=0,
        broker_providers=("alpaca-paper",),
        latest_price_sources=("alpaca",),
        latest_price_feeds=(DataFeed.IEX.value,),
    )
    store.persist_preflight_report(preflight)
    store.persist_validation_report(validation)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_id = {item.id: item for item in report.requirements}

    assert by_id["FR-03"].status == FunctionalRequirementStatus.PROVEN
    assert any("validation-monitor-dry-run" in item for item in by_id["FR-03"].evidence)
    assert by_id["FR-06"].status == FunctionalRequirementStatus.PROVEN
    assert by_id["FR-09"].status == FunctionalRequirementStatus.MISSING
    assert by_id["FR-04"].status == FunctionalRequirementStatus.EXTERNAL_REQUIRED
    assert by_id["FR-05"].status == FunctionalRequirementStatus.MISSING
    assert by_id["FR-10"].status == FunctionalRequirementStatus.MISSING


def test_completion_audit_text_and_markdown_do_not_leak_secret_values(
    tmp_path,
) -> None:
    _persist_complete_evidence(tmp_path)

    report = RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_completion_audit_text(report)
    markdown = render_completion_audit_markdown(report)

    assert "Functional Paper App Completion Audit" in markdown
    assert "paper-secret-value-456" not in text
    assert "paper-secret-value-456" not in markdown


def test_completion_audit_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    empty_dir = tmp_path / "empty"
    complete_dir = tmp_path / "complete"
    _persist_complete_evidence(complete_dir)

    failure = completion_main(
        ["--output-dir", str(empty_dir), "--json", "--no-persist"]
    )
    success = completion_main(["--output-dir", str(complete_dir), "--json"])
    output = capsys.readouterr().out

    assert failure == 1
    assert success == 0
    assert '"passed":false' in output
    assert '"passed":true' in output
    assert "completion-audit" in output


def _persist_complete_evidence(tmp_path) -> RuntimePersistenceStore:
    store = RuntimePersistenceStore(tmp_path)
    preflight = _preflight_report()
    demo = build_demo_dashboard_snapshot()
    paper_report = _alpaca_paper_report(demo.paper_report)
    daily_report, daily_report_path = _daily_report_artifact(
        demo.daily_report, tmp_path
    )
    nightly_learning = _external_like_model(demo.nightly_learning)
    control_state = _external_like_model(demo.control_state)
    alerts = _external_like_models(demo.alerts)
    health_report = _external_like_model(demo.health_report)
    latest_prices = FixtureLatestPriceFetcher(
        {"SPY": Decimal("500")},
        observed_at=NOW,
        source="alpaca",
    ).fetch_latest_prices(("SPY",), as_of=NOW, feed=DataFeed.IEX)
    snapshot = RuntimeSnapshot(
        as_of=NOW,
        status=RuntimeStatus.RUNNING,
        mode="Alpaca Paper",
        latest_prices=latest_prices,
        paper_report=paper_report,
        daily_report=daily_report,
        nightly_learning=nightly_learning,
        active_model_key="monthly_sector_momentum:1.0.0",
        daily_report_path=str(daily_report_path),
        control_state=control_state,
        alerts=alerts,
        health_report=health_report,
    )

    store.persist_preflight_report(preflight)
    RuntimeOperationsReadinessAuditor(output_dir=tmp_path).audit(as_of=NOW)
    store.persist_dry_run_report(_dry_run_report(preflight))
    store.persist_validation_report(_validation_report(preflight))
    store.persist_soak_evidence_report(
        RuntimeSoakEvidenceReport(
            as_of=NOW,
            status=RuntimePreflightStatus.PASSED,
            passed=True,
            output_dir=str(tmp_path),
            started_at=NOW - timedelta(hours=25),
            completed_at=NOW,
            duration_hours=25,
            cycle_count=26,
            market_cycle_count=8,
            off_hours_cycle_count=18,
            overnight_cycle_count=10,
            prices_refreshed_cycle_count=26,
            broker_synced_cycle_count=26,
            missed_price_refresh_cycles=0,
            missed_broker_sync_cycles=0,
            order_cycles=1,
            off_schedule_order_cycles=0,
            report_written=True,
            nightly_learning_ran=True,
            dashboard_snapshot_available=True,
            final_health_status="healthy",
            runtime_event_count=0,
            runtime_warning_event_count=0,
            runtime_error_event_count=0,
            checks=(),
        )
    )
    store.persist_secret_scan_report(
        RuntimeSecretScanReport(
            as_of=NOW,
            status=RuntimePreflightStatus.PASSED,
            passed=True,
            output_dir=str(tmp_path),
            files_scanned=4,
            files_skipped=0,
            secret_names_checked=("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
            summary="No configured secret values were found.",
        )
    )
    store.persist_daily_report(daily_report, markdown_path=daily_report_path)
    store.persist_runtime_snapshot(snapshot)
    store.persist_learning_run(nightly_learning)
    store.persist_dashboard_snapshot(
        _external_like_dashboard_snapshot(
            demo,
            update={
                "generated_at": NOW,
                "mode": "Alpaca Paper",
                "broker": "alpaca-paper",
                "runtime_state": snapshot,
                "paper_report": paper_report,
                "daily_report": daily_report,
                "nightly_learning": nightly_learning,
                "control_state": snapshot.control_state,
                "alerts": snapshot.alerts,
                "health_report": snapshot.health_report,
                "statement_reconciliation": None,
                "statement_reconciliation_path": None,
                "completion_audit": None,
            },
        )
    )
    for submission in paper_report.submissions:
        store.persist_submission(submission)
    for status in paper_report.order_statuses:
        store.persist_order_status(status)
    for fill in demo.recent_fills:
        store.persist_fill(fill)
    store.persist_reconciliation(paper_report.reconciliation)
    _persist_lifecycle_drill(store, tmp_path)
    RuntimeRecoveryAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeModelGovernanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeOrderGuardrailAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeScheduleGuardrailAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeFillSyncAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeDataQualityAuditor(output_dir=tmp_path).audit(as_of=NOW)
    broker_history_path = write_broker_order_history_json(
        _broker_history_orders(paper_report),
        tmp_path / "broker-history",
        as_of=NOW,
    )
    RuntimeBrokerOrderHistoryAuditor(
        output_dir=tmp_path,
        order_history_path=broker_history_path,
    ).audit(as_of=NOW)
    RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeDashboardVisualAuditor(output_dir=tmp_path).audit(as_of=NOW)
    statement = _matching_statement(demo)
    raw_statement_path = write_broker_statement_json(statement, tmp_path / "statements")
    statement_report = reconcile_statement_snapshot(
        paper_report.ledger_snapshot,
        statement,
        as_of=NOW,
        statement_path=raw_statement_path,
    )
    statement_path = write_statement_reconciliation_markdown(
        statement_report,
        tmp_path / "reports",
    )
    store.persist_statement_reconciliation(
        statement_report,
        markdown_path=statement_path,
    )
    RuntimeCredentialedSessionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeEvidenceCoherenceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    return store


def _persist_lifecycle_drill(store: RuntimePersistenceStore, tmp_path: Path) -> None:
    center = RuntimeControlCenter()
    for index, action in enumerate(
        (
            OperatorControlAction.PAUSE_RUNTIME,
            OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
            OperatorControlAction.FORCE_RECONCILIATION,
            OperatorControlAction.GENERATE_REPORT,
            OperatorControlAction.RESUME_RUNTIME,
            OperatorControlAction.DISABLE_PAPER_KILL_SWITCH,
        )
    ):
        store.persist_control_result(
            center.apply(
                OperatorControlRequest(
                    action=action,
                    requested_at=NOW + timedelta(seconds=index),
                    requested_by="test-operator",
                    reason="lifecycle drill",
                )
            )
        )
    RuntimeLifecycleDrillAuditor(output_dir=tmp_path).audit(as_of=NOW)


def _external_like_dashboard_snapshot(
    snapshot: OperatorDashboardSnapshot,
    *,
    update: dict,
) -> OperatorDashboardSnapshot:
    payload = json.loads(snapshot.model_dump_json())
    payload = _replace_demo_provenance(payload)
    payload["session_state"] = None
    return OperatorDashboardSnapshot.model_validate_json(
        json.dumps(payload)
    ).model_copy(update=update)


def _external_like_model(model):
    payload = json.loads(model.model_dump_json())
    payload = _replace_demo_provenance(payload)
    return model.__class__.model_validate_json(json.dumps(payload))


def _external_like_models(values):
    return tuple(_external_like_model(value) for value in values)


def _replace_demo_provenance(value):
    if isinstance(value, dict):
        return {key: _replace_demo_provenance(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_replace_demo_provenance(child) for child in value]
    if isinstance(value, str):
        return (
            value.replace("demo", "paper")
            .replace("Demo", "Paper")
            .replace("fixture", "market")
        )
    return value


def _alpaca_paper_report(report):
    broker_portfolio = report.broker_portfolio.model_copy(
        update={"provider": "alpaca-paper"}
    )
    reconciliation = report.reconciliation.model_copy(
        update={"broker_portfolio": broker_portfolio}
    )
    submissions = tuple(
        submission.model_copy(
            update={
                "broker_order": submission.broker_order.model_copy(
                    update={"provider": "alpaca-paper"}
                )
            }
        )
        if submission.broker_order is not None
        else submission
        for submission in report.submissions
    )
    return report.model_copy(
        update={
            "broker_portfolio": broker_portfolio,
            "reconciliation": reconciliation,
            "submissions": submissions,
        }
    )


def _broker_history_orders(paper_report):
    filled_by_order = {
        fill.order_id: sum(
            item.quantity
            for item in paper_report.fills
            if item.order_id == fill.order_id
        )
        for fill in paper_report.fills
    }
    orders = []
    for submission in paper_report.submissions:
        broker_order = submission.broker_order
        if broker_order is None:
            continue
        filled = filled_by_order.get(submission.order.id, Decimal("0"))
        orders.append(
            broker_order.model_copy(
                update={
                    "provider": "alpaca-paper",
                    "filled_quantity": filled,
                    "status": OrderStatus.FILLED if filled else broker_order.status,
                    "average_fill_price": Decimal("500") if filled else None,
                    "provider_status": "filled"
                    if filled
                    else broker_order.provider_status,
                }
            )
        )
    return tuple(orders)


def _daily_report_artifact(report, tmp_path: Path):
    report = _external_like_model(report)
    reports_dir = tmp_path / "reports"
    markdown_path = reports_dir / f"daily-report-{report.trading_day.isoformat()}.md"
    metadata = report.report_metadata.model_copy(
        update={
            "generated_at": NOW,
            "markdown_path": str(markdown_path),
        }
    )
    updated = report.model_copy(
        update={
            "generated_at": NOW,
            "report_metadata": metadata,
        }
    )
    written_path = write_markdown_report(updated, reports_dir)
    return updated, written_path


def _replace_daily_report(store: RuntimePersistenceStore, report) -> None:
    daily_report_path = store.recover().daily_report_path
    assert daily_report_path is not None
    if report.report_metadata is not None:
        report = report.model_copy(
            update={
                "report_metadata": report.report_metadata.model_copy(
                    update={"markdown_path": str(daily_report_path)}
                )
            }
        )
    write_markdown_report(report, daily_report_path.parent)
    store.persist_daily_report(report, markdown_path=daily_report_path)


def _matching_statement(demo) -> BrokerStatementSnapshot:
    positions = tuple(
        BrokerPositionState(
            symbol=position.symbol,
            quantity=position.quantity,
            average_entry_price=position.average_cost,
        )
        for position in demo.paper_report.ledger_snapshot.positions
    )
    return BrokerStatementSnapshot(
        statement_id="statement-2026-05-29",
        as_of=NOW,
        provider="alpaca-paper",
        account_id="paper-account-1",
        cash=demo.paper_report.ledger_snapshot.cash,
        positions=positions,
        source="alpaca-paper:paper-portfolio-capture",
    )


def _read_runtime_snapshot(tmp_path) -> RuntimeSnapshot:
    return RuntimeSnapshot.model_validate_json(
        (tmp_path / "state" / "latest-runtime-snapshot.json").read_text(
            encoding="utf-8"
        )
    )


def _read_dashboard_snapshot(tmp_path) -> OperatorDashboardSnapshot:
    return OperatorDashboardSnapshot.model_validate_json(
        (tmp_path / "state" / "latest-dashboard-snapshot.json").read_text(
            encoding="utf-8"
        )
    )


def _preflight_report() -> RuntimePreflightReport:
    checks = (
        _preflight_check("credentials", "Alpaca credential variables are present."),
        _preflight_check("paper_boundary", "Runtime is configured for paper mode."),
        _preflight_check("runtime_schedule", "Daily-close schedule is configured."),
    )
    return RuntimePreflightReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        can_start=True,
        summary="Preflight passed.",
        checks=checks,
        warnings=0,
        failures=0,
    )


def _preflight_check(name: str, message: str) -> RuntimePreflightCheck:
    return RuntimePreflightCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED,
        message=message,
        remediation="No action required.",
        checked_at=NOW,
    )


def _dry_run_report(preflight: RuntimePreflightReport) -> RuntimeDryRunReport:
    return RuntimeDryRunReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        can_start_supervised_runtime=True,
        monitor_only=True,
        summary="Monitor-only dry run passed.",
        preflight_report=preflight,
        cycle_result=RuntimeCycleResult(
            as_of=NOW,
            status=RuntimeStatus.RUNNING,
            prices_refreshed=True,
            broker_synced=True,
            orders_submitted=0,
        ),
        steps=(
            RuntimeDryRunStep(
                name="paper_order_safety",
                status=RuntimePreflightStatus.PASSED,
                message="Monitor-only dry run submitted no orders.",
                checked_at=NOW,
            ),
        ),
        warnings=0,
        failures=0,
        orders_before=0,
        orders_after=0,
        orders_submitted=0,
        runtime_mode="Alpaca Paper",
        broker_provider="alpaca-paper",
        latest_price_source="alpaca",
        latest_price_feed=DataFeed.IEX.value,
    )


def _validation_report(preflight: RuntimePreflightReport) -> RuntimeValidationReport:
    return RuntimeValidationReport(
        id="validation-20260529T210000",
        started_at=NOW - timedelta(hours=26),
        completed_at=NOW - timedelta(hours=25, minutes=30),
        status=RuntimePreflightStatus.PASSED,
        can_start_full_day_soak=True,
        summary="Validation passed.",
        preflight_report=preflight,
        monitor_dry_run_report=_dry_run_report(preflight),
        steps=(),
        checklist=_validation_checklist(),
        warnings=0,
        failures=0,
        latest_prices_refreshed=True,
        latest_prices_fresh=True,
        broker_synced=True,
        dashboard_snapshot_serialized=True,
        report_written=True,
        nightly_learning_ran=True,
        orders_submitted=0,
        broker_providers=("alpaca-paper",),
        latest_price_sources=("alpaca",),
        latest_price_feeds=(DataFeed.IEX.value,),
    )


def _validation_checklist() -> tuple[RuntimeValidationChecklistItem, ...]:
    return tuple(
        RuntimeValidationChecklistItem(
            name=name,
            status=RuntimePreflightStatus.PASSED,
            message="Validation checklist item passed.",
            evidence=("passed=true",),
        )
        for name in sorted(REQUIRED_VALIDATION_CHECKLIST_ITEMS)
    )
