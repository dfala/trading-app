from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.broker import BrokerPositionState, BrokerStatementSnapshot
from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.market_data import FixtureLatestPriceFetcher
from trading_app.paper import (
    reconcile_statement_snapshot,
    write_broker_statement_json,
    write_statement_reconciliation_markdown,
)
from trading_app.reporting import write_markdown_report
from trading_app.runtime import (
    OperatorControlAction,
    OperatorControlRequest,
    RuntimeArtifactIntegrityAuditor,
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
    RuntimeEvidenceBundleBuilder,
    RuntimeEvidenceCoherenceAuditor,
    RuntimeFillSyncAuditor,
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
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
    RuntimeSecretScanReport,
    RuntimeSnapshot,
    RuntimeSoakEvidenceReport,
    RuntimeStatus,
    RuntimeValidationChecklistItem,
    render_artifact_integrity_markdown,
    render_artifact_integrity_text,
    render_evidence_bundle_markdown,
    render_evidence_bundle_text,
    write_broker_order_history_json,
)
from trading_app.runtime.audit_coverage import (
    REQUIRED_VALIDATION_CHECKLIST_ITEMS,
    artifact_integrity_coverage_gap,
    evidence_bundle_coverage_gap,
)
from trading_app.runtime.evidence import main as evidence_main
from trading_app.runtime.integrity import main as integrity_main
from trading_app.schemas import DataFeed, OrderStatus

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_evidence_bundle_passes_with_complete_external_like_artifacts(
    tmp_path,
) -> None:
    _persist_complete_evidence(tmp_path)

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    text = render_evidence_bundle_text(report)
    markdown = render_evidence_bundle_markdown(report)

    assert report.ready_for_operator_review
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.failed_count == 0
    assert report.missing_required_count == 0
    assert evidence_bundle_coverage_gap(report) == ()
    assert all(
        item.path and Path(item.path).exists()
        for item in report.items
        if item.required and item.status == RuntimePreflightStatus.PASSED
    )
    assert {item.name for item in report.items} == {
        "preflight",
        "operations_readiness",
        "lifecycle_drill",
        "monitor_dry_run",
        "validation_report",
        "soak_evidence",
        "runtime_snapshot",
        "restart_recovery",
        "dashboard_snapshot",
        "dashboard_consistency",
        "dashboard_visual",
        "data_quality_audit",
        "broker_order_history",
        "credentialed_session",
        "evidence_coherence",
        "artifact_integrity",
        "health_report",
        "daily_report",
        "nightly_learning",
        "model_governance",
        "schedule_guardrails",
        "order_guardrails",
        "fill_sync",
        "secret_scan",
        "statement_reconciliation",
        "completion_audit",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Evidence bundle status" in text
    assert "Paper Runtime Evidence Bundle" in markdown
    assert "paper-secret-value-456" not in text
    assert "paper-secret-value-456" not in markdown
    assert (tmp_path / "state" / "latest-evidence-bundle-report.json").exists()
    assert (tmp_path / "journal" / "evidence-bundles.jsonl").exists()


def test_evidence_bundle_rejects_validation_without_checklist(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    validation = store.recover().validation_report
    assert validation is not None
    store.persist_validation_report(validation.model_copy(update={"checklist": ()}))

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["validation_report"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_checklist_items=" in item
        for item in by_name["validation_report"].evidence
    )


def test_evidence_bundle_fails_when_required_artifacts_are_missing(tmp_path) -> None:
    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)

    assert not report.ready_for_operator_review
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.missing_required_count == report.required_count
    assert all(item.status == RuntimePreflightStatus.FAILED for item in report.items)
    assert "Required evidence is missing" in render_evidence_bundle_text(report)


def test_evidence_bundle_requires_learning_after_daily_report(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    recovered = store.recover()
    assert recovered.daily_report is not None
    assert recovered.nightly_learning is not None
    early_learning = recovered.nightly_learning.model_copy(
        update={"as_of": recovered.daily_report.generated_at - timedelta(minutes=1)}
    )
    store.persist_learning_run(early_learning)

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["nightly_learning"].status == RuntimePreflightStatus.FAILED
    assert any(
        "learning_as_of" in item for item in by_name["nightly_learning"].evidence
    )


def test_evidence_bundle_requires_written_daily_report_artifact(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    daily_report_path = store.recover().daily_report_path
    assert daily_report_path is not None
    daily_report_path.unlink()

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["daily_report"].status == RuntimePreflightStatus.FAILED
    assert "Markdown path does not exist" in by_name["daily_report"].summary


def test_evidence_bundle_requires_reviewable_item_paths(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    validation = store.recover().validation_report
    assert validation is not None
    assert validation.markdown_path is not None
    Path(validation.markdown_path).unlink()

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["validation_report"].status == RuntimePreflightStatus.FAILED
    assert any(
        "review_path_missing=" in item for item in by_name["validation_report"].evidence
    )
    assert any(
        "nonpassing_items=validation_report" in item
        for item in evidence_bundle_coverage_gap(report)
    )


def test_evidence_bundle_coverage_rejects_self_referential_item_paths(
    tmp_path,
) -> None:
    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    item_path = tmp_path / "item-evidence.json"
    item_path.write_text("item evidence", encoding="utf-8")
    bundle_path = tmp_path / "evidence-bundle.md"
    bundle_path.write_text("bundle", encoding="utf-8")
    passed_report = report.model_copy(
        update={
            "status": RuntimePreflightStatus.PASSED,
            "ready_for_operator_review": True,
            "items": tuple(
                item.model_copy(
                    update={
                        "status": RuntimePreflightStatus.PASSED,
                        "path": str(item_path),
                    }
                )
                for item in report.items
            ),
            "required_count": len(report.items),
            "passed_count": len(report.items),
            "failed_count": 0,
            "missing_required_count": 0,
            "markdown_path": str(bundle_path),
        }
    )
    assert evidence_bundle_coverage_gap(passed_report) == ()

    self_referential = passed_report.model_copy(
        update={
            "items": tuple(
                item.model_copy(update={"path": str(bundle_path)})
                for item in passed_report.items
            )
        }
    )

    assert any(
        "self_referential_item_paths=" in item
        for item in evidence_bundle_coverage_gap(self_referential)
    )


def test_evidence_bundle_requires_credential_value_secret_scan(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    secret_scan = store.read_secret_scan_report()
    assert secret_scan is not None
    store.persist_secret_scan_report(
        secret_scan.model_copy(update={"secret_names_checked": ()})
    )

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["secret_scan"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_secret_names=ALPACA_API_KEY,ALPACA_SECRET_KEY" in item
        for item in by_name["secret_scan"].evidence
    )


def test_evidence_bundle_requires_full_data_quality_scenario_coverage(
    tmp_path,
) -> None:
    store = _persist_complete_evidence(tmp_path)
    audit = store.read_data_quality_audit_report()
    assert audit is not None
    store.persist_data_quality_audit_report(
        audit.model_copy(
            update={
                "latest_price_scenarios": 1,
                "daily_bar_scenarios": 0,
                "symbol_universe_scenarios": 0,
                "checks": (),
            }
        )
    )

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["data_quality_audit"].status == RuntimePreflightStatus.FAILED
    assert any(
        "latest_price_scenarios_missing=2" in item
        for item in by_name["data_quality_audit"].evidence
    )
    assert any(
        "daily_bar_scenarios_missing=3" in item
        for item in by_name["data_quality_audit"].evidence
    )
    assert any(
        "symbol_universe_scenarios_missing=1" in item
        for item in by_name["data_quality_audit"].evidence
    )


def test_evidence_bundle_requires_full_guardrail_and_fill_scenario_coverage(
    tmp_path,
) -> None:
    store = _persist_complete_evidence(tmp_path)
    order_guardrail = store.read_order_guardrail_report()
    schedule_guardrail = store.read_schedule_guardrail_report()
    fill_sync = store.read_fill_sync_report()
    assert order_guardrail is not None
    assert schedule_guardrail is not None
    assert fill_sync is not None
    store.persist_order_guardrail_report(
        order_guardrail.model_copy(
            update={
                "checks": order_guardrail.checks[:1],
                "blocked_order_scenarios": 1,
            }
        )
    )
    store.persist_schedule_guardrail_report(
        schedule_guardrail.model_copy(
            update={
                "checks": schedule_guardrail.checks[:1],
                "approved_schedule_scenarios": 0,
                "protected_schedule_scenarios": 1,
            }
        )
    )
    store.persist_fill_sync_report(
        fill_sync.model_copy(
            update={
                "checks": fill_sync.checks[:1],
                "incremental_fill_scenarios": 1,
                "duplicate_fill_scenarios": 0,
            }
        )
    )

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["order_guardrails"].status == RuntimePreflightStatus.FAILED
    assert by_name["schedule_guardrails"].status == RuntimePreflightStatus.FAILED
    assert by_name["fill_sync"].status == RuntimePreflightStatus.FAILED
    assert any(
        "blocked_order_scenarios_missing=5" in item
        for item in by_name["order_guardrails"].evidence
    )
    assert any(
        "protected_schedule_scenarios_missing=3" in item
        for item in by_name["schedule_guardrails"].evidence
    )
    assert any(
        "duplicate_fill_scenarios_missing=2" in item
        for item in by_name["fill_sync"].evidence
    )


def test_evidence_bundle_requires_full_broker_history_and_recovery_coverage(
    tmp_path,
) -> None:
    store = _persist_complete_evidence(tmp_path)
    recovery = store.read_recovery_audit_report()
    broker_history = store.read_broker_order_history_report()
    assert recovery is not None
    assert broker_history is not None
    store.persist_recovery_audit_report(
        recovery.model_copy(
            update={
                "checks": recovery.checks[:1],
            }
        )
    )
    store.persist_broker_order_history_report(
        broker_history.model_copy(
            update={
                "checks": broker_history.checks[:1],
                "matched_order_count": 0,
            }
        )
    )

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["restart_recovery"].status == RuntimePreflightStatus.FAILED
    assert by_name["broker_order_history"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_checks=" in item for item in by_name["restart_recovery"].evidence
    )
    assert any(
        "matched_order_count_missing=" in item
        for item in by_name["broker_order_history"].evidence
    )


def test_evidence_bundle_requires_startup_proof_coverage(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    operations = store.read_operations_readiness_report()
    lifecycle = store.read_lifecycle_drill_report()
    credentialed = store.read_credentialed_session_report()
    assert operations is not None
    assert lifecycle is not None
    assert credentialed is not None
    store.persist_operations_readiness_report(
        operations.model_copy(update={"checks": operations.checks[:1]})
    )
    store.persist_lifecycle_drill_report(
        lifecycle.model_copy(update={"checks": lifecycle.checks[:1]})
    )
    store.persist_credentialed_session_report(
        credentialed.model_copy(
            update={
                "checks": credentialed.checks[:1],
                "external_source_count": 0,
            }
        )
    )

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["operations_readiness"].status == RuntimePreflightStatus.FAILED
    assert by_name["lifecycle_drill"].status == RuntimePreflightStatus.FAILED
    assert by_name["credentialed_session"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_checks=" in item for item in by_name["operations_readiness"].evidence
    )
    assert any(
        "missing_checks=" in item for item in by_name["lifecycle_drill"].evidence
    )
    assert any(
        "external_source_count_missing=3" in item
        for item in by_name["credentialed_session"].evidence
    )


def test_evidence_bundle_requires_dashboard_and_governance_coverage(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    consistency = store.read_dashboard_consistency_report()
    visual = store.read_dashboard_visual_report()
    governance = store.read_model_governance_report()
    assert consistency is not None
    assert visual is not None
    assert governance is not None
    store.persist_dashboard_consistency_report(
        consistency.model_copy(update={"checks": consistency.checks[:1]})
    )
    store.persist_dashboard_visual_report(
        visual.model_copy(
            update={
                "checks": visual.checks[:1],
                "critical_surface_count": 1,
                "responsive_surface_count": 0,
            }
        )
    )
    store.persist_model_governance_report(
        governance.model_copy(
            update={
                "checks": governance.checks[:1],
                "recommendation_count": 0,
            }
        )
    )

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["dashboard_consistency"].status == RuntimePreflightStatus.FAILED
    assert by_name["dashboard_visual"].status == RuntimePreflightStatus.FAILED
    assert by_name["model_governance"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_checks=" in item for item in by_name["dashboard_consistency"].evidence
    )
    assert any(
        "critical_surface_count_missing=6" in item
        for item in by_name["dashboard_visual"].evidence
    )
    assert any(
        "recommendation_count_missing=1" in item
        for item in by_name["model_governance"].evidence
    )


def test_evidence_bundle_requires_final_review_packet_coverage(tmp_path) -> None:
    store = _persist_complete_evidence(tmp_path)
    coherence = store.read_evidence_coherence_report()
    integrity = store.read_artifact_integrity_report()
    completion = store.read_completion_audit_report()
    assert coherence is not None
    assert integrity is not None
    assert completion is not None
    store.persist_evidence_coherence_report(
        coherence.model_copy(update={"checks": coherence.checks[:1]})
    )
    store.persist_artifact_integrity_report(
        integrity.model_copy(
            update={
                "items": integrity.items[:1],
                "required_count": 1,
                "hashed_count": 1,
            }
        )
    )
    store.persist_completion_audit_report(
        completion.model_copy(
            update={
                "requirements": completion.requirements[:1],
                "proven_count": 1,
            }
        )
    )

    report = RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    by_name = {item.name: item for item in report.items}

    assert not report.ready_for_operator_review
    assert by_name["evidence_coherence"].status == RuntimePreflightStatus.FAILED
    assert by_name["artifact_integrity"].status == RuntimePreflightStatus.FAILED
    assert by_name["completion_audit"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_checks=" in item for item in by_name["evidence_coherence"].evidence
    )
    assert any(
        "missing_labels=" in item for item in by_name["artifact_integrity"].evidence
    )
    assert any(
        "missing_items=" in item for item in by_name["completion_audit"].evidence
    )


def test_evidence_bundle_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    complete_dir = tmp_path / "complete"
    missing_dir = tmp_path / "missing"
    _persist_complete_evidence(complete_dir)

    success = evidence_main(["--output-dir", str(complete_dir), "--json"])
    failure = evidence_main(["--output-dir", str(missing_dir), "--json"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"ready_for_operator_review":true' in output
    assert '"ready_for_operator_review":false' in output
    assert '"completion_audit"' in output


def test_artifact_integrity_manifest_hashes_review_artifacts(tmp_path) -> None:
    _persist_complete_evidence(tmp_path)
    RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)

    report = RuntimeArtifactIntegrityAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_artifact_integrity_text(report)
    markdown = render_artifact_integrity_markdown(report)
    by_label = {item.label: item for item in report.items}

    assert report.passed
    assert artifact_integrity_coverage_gap(report) == ()
    assert report.missing_required_count == 0
    assert report.hashed_count >= report.required_count
    assert by_label["evidence bundle state"].sha256 is not None
    assert by_label["evidence bundle markdown"].sha256 is not None
    assert by_label["broker statement source"].expected_sha256 is not None
    assert by_label["broker statement source"].hash_matches is True
    assert all(
        item.sha256 and len(item.sha256) == 64 for item in report.items if item.required
    )
    assert "Artifact integrity status" in text
    assert "Paper Runtime Artifact Integrity Manifest" in markdown
    assert (tmp_path / "state" / "latest-artifact-integrity-report.json").exists()
    assert (tmp_path / "journal" / "artifact-integrity.jsonl").exists()


def test_artifact_integrity_coverage_rejects_missing_current_artifact(
    tmp_path,
) -> None:
    _persist_complete_evidence(tmp_path)
    RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    report = RuntimeArtifactIntegrityAuditor(output_dir=tmp_path).audit(as_of=NOW)
    target = next(item for item in report.items if item.label == "preflight state")
    Path(target.path).unlink()

    gaps = artifact_integrity_coverage_gap(report)

    assert "current_file_missing_required=preflight state" in gaps


def test_artifact_integrity_coverage_rejects_changed_current_artifact(
    tmp_path,
) -> None:
    _persist_complete_evidence(tmp_path)
    RuntimeEvidenceBundleBuilder(output_dir=tmp_path).build(as_of=NOW)
    report = RuntimeArtifactIntegrityAuditor(output_dir=tmp_path).audit(as_of=NOW)
    target = next(item for item in report.items if item.label == "preflight state")
    Path(target.path).write_text("changed after integrity", encoding="utf-8")

    gaps = artifact_integrity_coverage_gap(report)

    assert "current_hash_mismatch_required=preflight state" in gaps


def test_artifact_integrity_rejects_mutated_broker_statement_source(
    tmp_path,
) -> None:
    store = _persist_complete_evidence(tmp_path)
    statement_report = store.read_statement_reconciliation_report()
    assert statement_report is not None
    assert statement_report.statement_path is not None
    Path(statement_report.statement_path).write_text(
        '{"changed": true}',
        encoding="utf-8",
    )

    report = RuntimeArtifactIntegrityAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_label = {item.label: item for item in report.items}
    gaps = artifact_integrity_coverage_gap(report)

    assert not report.passed
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.hash_mismatch_count == 1
    assert by_label["broker statement source"].hash_matches is False
    assert "hash_mismatch_count=1" in gaps
    assert "hash_mismatch_required=broker statement source" in gaps


def test_artifact_integrity_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    complete_dir = tmp_path / "complete"
    missing_dir = tmp_path / "missing"
    _persist_complete_evidence(complete_dir)

    success = integrity_main(["--output-dir", str(complete_dir), "--json"])
    failure = integrity_main(["--output-dir", str(missing_dir), "--json"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def _persist_complete_evidence(tmp_path: Path) -> RuntimePersistenceStore:
    store = RuntimePersistenceStore(tmp_path)
    demo = build_demo_dashboard_snapshot()
    paper_report = _alpaca_paper_report(demo.paper_report)
    daily_report, daily_report_path = _daily_report_artifact(
        demo.daily_report, tmp_path
    )
    nightly_learning = _external_like_model(demo.nightly_learning)
    control_state = _external_like_model(demo.control_state)
    alerts = _external_like_models(demo.alerts)
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
        health_report=_health_report(),
    )
    store.persist_preflight_report(_preflight_report())
    RuntimeOperationsReadinessAuditor(output_dir=tmp_path).audit(as_of=NOW)
    store.persist_dry_run_report(_dry_run_report())
    store.persist_validation_report(_validation_report(tmp_path))
    store.persist_soak_evidence_report(_soak_report(tmp_path))
    store.persist_secret_scan_report(_secret_scan_report(tmp_path))
    store.persist_runtime_snapshot(snapshot)
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
    store.persist_health_report(_health_report())
    store.persist_daily_report(daily_report, markdown_path=daily_report_path)
    store.persist_learning_run(nightly_learning)
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
    raw_statement_path = write_broker_statement_json(
        _matching_statement(demo),
        tmp_path / "statements",
    )
    statement_report = reconcile_statement_snapshot(
        paper_report.ledger_snapshot,
        _matching_statement(demo),
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
    RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    RuntimeArtifactIntegrityAuditor(output_dir=tmp_path).audit(as_of=NOW)
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


def _preflight_report() -> RuntimePreflightReport:
    return RuntimePreflightReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        can_start=True,
        summary="Preflight passed.",
        checks=(
            _preflight_check("credentials", "Alpaca credential variables are present."),
            _preflight_check("paper_boundary", "Runtime is configured for paper mode."),
            _preflight_check("runtime_schedule", "Daily-close schedule is configured."),
        ),
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


def _dry_run_report() -> RuntimeDryRunReport:
    return RuntimeDryRunReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        can_start_supervised_runtime=True,
        monitor_only=True,
        summary="Monitor-only dry run passed.",
        preflight_report=_preflight_report(),
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


def _validation_report(tmp_path: Path):
    from trading_app.runtime import RuntimeValidationReport

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = reports_dir / "validation.md"
    markdown_path.write_text("validation evidence", encoding="utf-8")
    return RuntimeValidationReport(
        id="validation-20260529T210000",
        started_at=NOW - timedelta(hours=26),
        completed_at=NOW - timedelta(hours=25, minutes=30),
        status=RuntimePreflightStatus.PASSED,
        can_start_full_day_soak=True,
        summary="Validation passed.",
        preflight_report=_preflight_report(),
        monitor_dry_run_report=_dry_run_report(),
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
        markdown_path=str(markdown_path),
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


def _soak_report(tmp_path: Path) -> RuntimeSoakEvidenceReport:
    return RuntimeSoakEvidenceReport(
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


def _secret_scan_report(tmp_path: Path) -> RuntimeSecretScanReport:
    return RuntimeSecretScanReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        passed=True,
        output_dir=str(tmp_path),
        files_scanned=4,
        files_skipped=0,
        secret_names_checked=("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
        summary="No configured secret values were found.",
    )


def _health_report() -> RuntimeHealthReport:
    return RuntimeHealthReport(
        as_of=NOW,
        status=RuntimeHealthStatus.HEALTHY,
        summary="Runtime health is clean.",
        next_action="Continue monitoring.",
        checks=(
            RuntimeHealthCheck(
                name="runtime_loop",
                status=RuntimeHealthStatus.HEALTHY,
                message="Runtime heartbeat is fresh.",
                checked_at=NOW,
            ),
        ),
    )


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
