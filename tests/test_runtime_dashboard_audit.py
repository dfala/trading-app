from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.market_data import FixtureLatestPriceFetcher
from trading_app.runtime import (
    FunctionalCompletionAuditReport,
    FunctionalRequirementEvidence,
    FunctionalRequirementStatus,
    RuntimeArtifactIntegrityItem,
    RuntimeArtifactIntegrityReport,
    RuntimeCredentialedSessionCheck,
    RuntimeCredentialedSessionReport,
    RuntimeDashboardConsistencyAuditor,
    RuntimeEvidenceBundleItem,
    RuntimeEvidenceBundleReport,
    RuntimeFinalAcceptanceCheck,
    RuntimeFinalAcceptanceReport,
    RuntimeHealthStatus,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    RuntimeSnapshot,
    RuntimeStatus,
    render_artifact_integrity_markdown,
    render_completion_audit_markdown,
    render_credentialed_session_markdown,
    render_dashboard_consistency_markdown,
    render_dashboard_consistency_text,
    render_evidence_bundle_markdown,
    render_final_acceptance_markdown,
)
from trading_app.runtime.audit_coverage import (
    REQUIRED_ARTIFACT_LABELS,
    REQUIRED_CREDENTIAL_SESSION_CHECKS,
    REQUIRED_EVIDENCE_BUNDLE_ITEMS,
    REQUIRED_FINAL_ACCEPTANCE_CHECKS,
    REQUIRED_FUNCTIONAL_REQUIREMENTS,
)
from trading_app.runtime.dashboard_audit import main as dashboard_audit_main
from trading_app.schemas import DataFeed

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_dashboard_consistency_audit_passes_for_matching_snapshots(tmp_path) -> None:
    _persist_matching_snapshots(tmp_path)

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_dashboard_consistency_text(report)
    markdown = render_dashboard_consistency_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert {check.name for check in report.checks}.issuperset(
        {
            "runtime_snapshot_present",
            "dashboard_snapshot_present",
            "snapshot_freshness",
            "snapshot_timestamp",
            "cash",
            "positions",
            "data_quality",
            "operator_controls",
            "runtime_alerts",
            "runtime_health",
            "final_acceptance",
        }
    )
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Dashboard consistency status" in text
    assert "Dashboard Consistency Audit" in markdown
    assert (tmp_path / "state" / "latest-dashboard-consistency-report.json").exists()
    assert (tmp_path / "journal" / "dashboard-consistency.jsonl").exists()


def test_dashboard_consistency_audit_fails_when_dashboard_is_missing(tmp_path) -> None:
    store, _, _ = _persist_matching_snapshots(tmp_path, dashboard=False)

    report = RuntimeDashboardConsistencyAuditor(
        output_dir=tmp_path,
        persistence_store=store,
    ).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert report.status == RuntimePreflightStatus.FAILED
    assert by_name["runtime_snapshot_present"].status == RuntimePreflightStatus.PASSED
    assert by_name["dashboard_snapshot_present"].status == RuntimePreflightStatus.FAILED


def test_dashboard_consistency_audit_fails_for_stale_cash_or_mode(tmp_path) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    store.persist_dashboard_snapshot(
        dashboard.model_copy(
            update={
                "mode": "Demo",
                "cash": dashboard.cash + Decimal("100"),
            }
        )
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["paper_mode"].status == RuntimePreflightStatus.FAILED
    assert by_name["cash"].status == RuntimePreflightStatus.FAILED


def test_dashboard_consistency_audit_fails_for_broker_provider_mismatch(
    tmp_path,
) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    store.persist_dashboard_snapshot(
        dashboard.model_copy(update={"broker": "alpaca-paper"})
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["broker_provider"].status == RuntimePreflightStatus.FAILED


def test_dashboard_consistency_audit_fails_for_stale_operator_state(tmp_path) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    assert dashboard.control_state is not None
    assert dashboard.health_report is not None
    stale_control = dashboard.control_state.model_copy(update={"paused": True})
    stale_health = dashboard.health_report.model_copy(
        update={"status": RuntimeHealthStatus.CRITICAL}
    )
    store.persist_dashboard_snapshot(
        dashboard.model_copy(
            update={
                "control_state": stale_control,
                "alerts": (),
                "health_report": stale_health,
            }
        )
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["operator_controls"].status == RuntimePreflightStatus.FAILED
    assert by_name["runtime_alerts"].status == RuntimePreflightStatus.FAILED
    assert by_name["runtime_health"].status == RuntimePreflightStatus.FAILED


def test_dashboard_consistency_audit_rejects_missing_completion_markdown(
    tmp_path,
) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    completion = _complete_completion_audit_report(tmp_path, write_markdown=False)
    assert completion.markdown_path is not None
    store.persist_completion_audit_report(completion)
    store.persist_dashboard_snapshot(
        dashboard.model_copy(update={"completion_audit": completion})
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["completion_audit"].status == RuntimePreflightStatus.FAILED
    assert any(
        "markdown_path_file=missing" in item
        for item in by_name["completion_audit"].evidence
    )


def test_dashboard_consistency_audit_rejects_changed_completion_markdown(
    tmp_path,
) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    completion = _complete_completion_audit_report(tmp_path)
    assert completion.markdown_path is not None
    store.persist_completion_audit_report(completion)
    Path(completion.markdown_path).write_text(
        "changed completion audit",
        encoding="utf-8",
    )
    store.persist_dashboard_snapshot(
        dashboard.model_copy(update={"completion_audit": completion})
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["completion_audit"].status == RuntimePreflightStatus.FAILED
    assert any(
        "mismatch=completion_audit_markdown" in item
        for item in by_name["completion_audit"].evidence
    )


def test_dashboard_consistency_audit_rejects_partial_completion_audit(
    tmp_path,
) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    completion = _complete_completion_audit_report(tmp_path)
    assert completion.markdown_path is not None
    partial = completion.model_copy(
        update={"requirements": completion.requirements[:1]}
    )
    Path(partial.markdown_path).write_text(
        render_completion_audit_markdown(partial),
        encoding="utf-8",
    )
    store.persist_completion_audit_report(partial)
    store.persist_dashboard_snapshot(
        dashboard.model_copy(update={"completion_audit": partial})
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["completion_audit"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_items=" in item for item in by_name["completion_audit"].evidence
    )


def test_dashboard_consistency_audit_rejects_missing_evidence_bundle_markdown(
    tmp_path,
) -> None:
    store, _, _ = _persist_matching_snapshots(tmp_path)
    bundle = _complete_evidence_bundle_report(tmp_path, write_markdown=False)
    assert bundle.markdown_path is not None
    store.persist_evidence_bundle_report(
        bundle,
        markdown_path=Path(bundle.markdown_path),
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["evidence_bundle"].status == RuntimePreflightStatus.FAILED
    assert any(
        "markdown_path_file=missing" in item
        for item in by_name["evidence_bundle"].evidence
    )


def test_dashboard_consistency_audit_rejects_changed_evidence_bundle_markdown(
    tmp_path,
) -> None:
    store, _, _ = _persist_matching_snapshots(tmp_path)
    bundle = _complete_evidence_bundle_report(tmp_path)
    assert bundle.markdown_path is not None
    store.persist_evidence_bundle_report(
        bundle,
        markdown_path=Path(bundle.markdown_path),
    )
    Path(bundle.markdown_path).write_text("changed evidence bundle", encoding="utf-8")

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["evidence_bundle"].status == RuntimePreflightStatus.FAILED
    assert any(
        "mismatch=evidence_bundle_markdown" in item
        for item in by_name["evidence_bundle"].evidence
    )


def test_dashboard_consistency_audit_rejects_self_referential_bundle_paths(
    tmp_path,
) -> None:
    store, _, _ = _persist_matching_snapshots(tmp_path)
    bundle = _complete_evidence_bundle_report(tmp_path)
    assert bundle.markdown_path is not None
    self_referential = bundle.model_copy(
        update={
            "items": tuple(
                item.model_copy(update={"path": bundle.markdown_path})
                for item in bundle.items
            )
        }
    )
    Path(self_referential.markdown_path).write_text(
        render_evidence_bundle_markdown(self_referential),
        encoding="utf-8",
    )
    store.persist_evidence_bundle_report(
        self_referential,
        markdown_path=Path(self_referential.markdown_path),
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["evidence_bundle"].status == RuntimePreflightStatus.FAILED
    assert any(
        "self_referential_item_paths=" in item
        for item in by_name["evidence_bundle"].evidence
    )


def test_dashboard_consistency_audit_rejects_changed_artifact_integrity_markdown(
    tmp_path,
) -> None:
    store, _, _ = _persist_matching_snapshots(tmp_path)
    integrity = _complete_artifact_integrity_report(tmp_path)
    assert integrity.markdown_path is not None
    store.persist_artifact_integrity_report(
        integrity,
        markdown_path=Path(integrity.markdown_path),
    )
    Path(integrity.markdown_path).write_text("changed integrity", encoding="utf-8")

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["artifact_integrity"].status == RuntimePreflightStatus.FAILED
    assert any(
        "mismatch=artifact_integrity_markdown" in item
        for item in by_name["artifact_integrity"].evidence
    )


def test_dashboard_consistency_audit_rejects_changed_credentialed_session_markdown(
    tmp_path,
) -> None:
    store, _, _ = _persist_matching_snapshots(tmp_path)
    credentialed = _complete_credentialed_session_report(tmp_path)
    assert credentialed.markdown_path is not None
    store.persist_credentialed_session_report(
        credentialed,
        markdown_path=Path(credentialed.markdown_path),
    )
    Path(credentialed.markdown_path).write_text(
        "changed credentialed session",
        encoding="utf-8",
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["credentialed_session"].status == RuntimePreflightStatus.FAILED
    assert any(
        "mismatch=credentialed_session_markdown" in item
        for item in by_name["credentialed_session"].evidence
    )


def test_dashboard_consistency_audit_fails_for_stale_final_acceptance(
    tmp_path,
) -> None:
    store, _, _ = _persist_matching_snapshots(tmp_path)
    store.persist_final_acceptance_report(_final_acceptance_report())

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["final_acceptance"].status == RuntimePreflightStatus.FAILED


def test_dashboard_consistency_audit_rejects_partial_final_acceptance(
    tmp_path,
) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    partial = _final_acceptance_report()
    store.persist_final_acceptance_report(partial)
    store.persist_dashboard_snapshot(
        dashboard.model_copy(update={"final_acceptance": partial})
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["final_acceptance"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_checks=" in item for item in by_name["final_acceptance"].evidence
    )


def test_dashboard_consistency_audit_rejects_missing_final_acceptance_markdown(
    tmp_path,
) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    final = _complete_final_acceptance_report(tmp_path, write_markdown=False)
    assert final.markdown_path is not None
    store.persist_final_acceptance_report(
        final,
        markdown_path=Path(final.markdown_path),
    )
    store.persist_dashboard_snapshot(
        dashboard.model_copy(update={"final_acceptance": final})
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["final_acceptance"].status == RuntimePreflightStatus.FAILED
    assert any(
        "markdown_path_file=missing" in item
        for item in by_name["final_acceptance"].evidence
    )


def test_dashboard_consistency_audit_rejects_changed_final_acceptance_markdown(
    tmp_path,
) -> None:
    store, _, dashboard = _persist_matching_snapshots(tmp_path)
    final = _complete_final_acceptance_report(tmp_path)
    assert final.markdown_path is not None
    store.persist_final_acceptance_report(
        final,
        markdown_path=Path(final.markdown_path),
    )
    Path(final.markdown_path).write_text("changed final acceptance", encoding="utf-8")
    store.persist_dashboard_snapshot(
        dashboard.model_copy(update={"final_acceptance": final})
    )

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["final_acceptance"].status == RuntimePreflightStatus.FAILED
    assert any(
        "mismatch=final_acceptance_markdown" in item
        for item in by_name["final_acceptance"].evidence
    )


def test_dashboard_consistency_audit_fails_for_stale_snapshot(tmp_path) -> None:
    _persist_matching_snapshots(tmp_path)

    report = RuntimeDashboardConsistencyAuditor(output_dir=tmp_path).audit(
        as_of=NOW + timedelta(minutes=16)
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["snapshot_freshness"].status == RuntimePreflightStatus.FAILED
    assert any(
        "allowed_seconds=900.00" in item
        for item in by_name["snapshot_freshness"].evidence
    )


def test_dashboard_consistency_cli_outputs_json_and_exit_codes(
    tmp_path, capsys
) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    _persist_matching_snapshots(success_dir)

    success = dashboard_audit_main(
        [
            "--output-dir",
            str(success_dir),
            "--max-snapshot-age-seconds",
            "315360000",
            "--json",
        ]
    )
    failure = dashboard_audit_main(["--output-dir", str(failure_dir), "--json"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def _persist_matching_snapshots(
    tmp_path: Path,
    *,
    dashboard: bool = True,
) -> tuple[RuntimePersistenceStore, RuntimeSnapshot, object]:
    store = RuntimePersistenceStore(tmp_path)
    demo = build_demo_dashboard_snapshot()
    latest_prices = FixtureLatestPriceFetcher(
        {"SPY": Decimal("500")},
        observed_at=NOW,
    ).fetch_latest_prices(("SPY",), as_of=NOW, feed=DataFeed.IEX)
    snapshot = RuntimeSnapshot(
        as_of=NOW,
        status=RuntimeStatus.RUNNING,
        mode="Alpaca Paper",
        latest_prices=latest_prices,
        paper_report=demo.paper_report,
        daily_report=demo.daily_report,
        nightly_learning=demo.nightly_learning,
        active_model_key="monthly_sector_momentum:1.0.0",
        control_state=demo.control_state,
        alerts=demo.alerts,
        health_report=demo.health_report,
    )
    dashboard_snapshot = demo.model_copy(
        update={
            "generated_at": NOW,
            "mode": "Alpaca Paper",
            "broker": demo.broker,
            "runtime_state": snapshot,
            "statement_reconciliation": None,
            "statement_reconciliation_path": None,
            "completion_audit": None,
            "final_acceptance": None,
        }
    )
    store.persist_runtime_snapshot(snapshot)
    if dashboard:
        store.persist_dashboard_snapshot(dashboard_snapshot)
    return store, snapshot, dashboard_snapshot


def _final_acceptance_report() -> RuntimeFinalAcceptanceReport:
    return RuntimeFinalAcceptanceReport(
        as_of=NOW - timedelta(minutes=1),
        status=RuntimePreflightStatus.PASSED,
        accepted_for_functional_paper_app=True,
        output_dir="data/runtime",
        checks=(
            RuntimeFinalAcceptanceCheck(
                name="operator_signoff_accepted",
                status=RuntimePreflightStatus.PASSED,
                message="Operator signoff accepted the reviewed paper evidence.",
                evidence=("accepted=true",),
            ),
        ),
        signoff_path="data/runtime/reports/operator-signoff.md",
        summary="Final paper-app acceptance passed for the signed evidence packet.",
        markdown_path="data/runtime/reports/final-acceptance.md",
    )


def _complete_completion_audit_report(
    tmp_path: Path,
    *,
    write_markdown: bool = True,
) -> FunctionalCompletionAuditReport:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = reports_dir / "completion-audit.md"
    report = FunctionalCompletionAuditReport(
        as_of=NOW - timedelta(minutes=1),
        status=RuntimePreflightStatus.PASSED,
        passed=True,
        output_dir=str(tmp_path),
        proven_count=len(REQUIRED_FUNCTIONAL_REQUIREMENTS),
        missing_count=0,
        failed_count=0,
        external_required_count=0,
        requirements=tuple(
            FunctionalRequirementEvidence(
                id=requirement_id,
                requirement=f"{requirement_id} paper evidence reviewed.",
                status=FunctionalRequirementStatus.PROVEN,
                evidence=("reviewed=true",),
                remediation="No action required.",
            )
            for requirement_id in sorted(REQUIRED_FUNCTIONAL_REQUIREMENTS)
        ),
        summary="Completion audit passed.",
        markdown_path=str(markdown_path),
    )
    if write_markdown:
        markdown_path.write_text(
            render_completion_audit_markdown(report),
            encoding="utf-8",
        )
    return report


def _complete_evidence_bundle_report(
    tmp_path: Path,
    *,
    write_markdown: bool = True,
) -> RuntimeEvidenceBundleReport:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    item_path = reports_dir / "review-item-evidence.json"
    item_path.write_text("review item evidence", encoding="utf-8")
    markdown_path = reports_dir / "evidence-bundle.md"
    report = RuntimeEvidenceBundleReport(
        as_of=NOW - timedelta(minutes=1),
        status=RuntimePreflightStatus.PASSED,
        ready_for_operator_review=True,
        output_dir=str(tmp_path),
        items=tuple(
            RuntimeEvidenceBundleItem(
                name=name,
                label=name.replace("_", " ").title(),
                status=RuntimePreflightStatus.PASSED,
                required=True,
                summary="Evidence item passed.",
                path=str(item_path),
                evidence=("passed=true",),
                next_action="No action required.",
            )
            for name in sorted(REQUIRED_EVIDENCE_BUNDLE_ITEMS)
        ),
        required_count=len(REQUIRED_EVIDENCE_BUNDLE_ITEMS),
        passed_count=len(REQUIRED_EVIDENCE_BUNDLE_ITEMS),
        warning_count=0,
        failed_count=0,
        missing_required_count=0,
        summary="Evidence bundle is ready.",
        markdown_path=str(markdown_path),
    )
    if write_markdown:
        markdown_path.write_text(
            render_evidence_bundle_markdown(report),
            encoding="utf-8",
        )
    return report


def _complete_artifact_integrity_report(
    tmp_path: Path,
    *,
    write_markdown: bool = True,
) -> RuntimeArtifactIntegrityReport:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = reports_dir / "dashboard-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = reports_dir / "artifact-integrity.md"
    report = RuntimeArtifactIntegrityReport(
        as_of=NOW - timedelta(minutes=1),
        status=RuntimePreflightStatus.PASSED,
        passed=True,
        output_dir=str(tmp_path),
        items=tuple(
            _integrity_item(label, artifact_dir)
            for label in sorted(REQUIRED_ARTIFACT_LABELS)
        ),
        required_count=len(REQUIRED_ARTIFACT_LABELS),
        hashed_count=len(REQUIRED_ARTIFACT_LABELS),
        missing_required_count=0,
        summary="Artifact integrity passed.",
        markdown_path=str(markdown_path),
    )
    if write_markdown:
        markdown_path.write_text(
            render_artifact_integrity_markdown(report),
            encoding="utf-8",
        )
    return report


def _complete_credentialed_session_report(
    tmp_path: Path,
    *,
    write_markdown: bool = True,
) -> RuntimeCredentialedSessionReport:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = reports_dir / "credentialed-session.md"
    report = RuntimeCredentialedSessionReport(
        as_of=NOW - timedelta(minutes=1),
        status=RuntimePreflightStatus.PASSED,
        passed=True,
        output_dir=str(tmp_path),
        validation_id="validation-20260529T210000",
        session_started_at=NOW - timedelta(hours=26),
        session_completed_at=NOW - timedelta(minutes=10),
        paper_account_id="paper-account-1",
        broker_providers=("alpaca-paper",),
        latest_price_sources=("alpaca", "alpaca-sip"),
        feed="IEX",
        checks=tuple(
            RuntimeCredentialedSessionCheck(
                name=name,
                status=RuntimePreflightStatus.PASSED,
                message="Credentialed session check passed.",
                evidence=("paper_account_id=paper-account-1",),
            )
            for name in sorted(REQUIRED_CREDENTIAL_SESSION_CHECKS)
        ),
        reviewed_artifact_count=len(REQUIRED_CREDENTIAL_SESSION_CHECKS),
        external_source_count=3,
        summary="Credentialed session proof passed.",
        markdown_path=str(markdown_path),
    )
    if write_markdown:
        markdown_path.write_text(
            render_credentialed_session_markdown(report),
            encoding="utf-8",
        )
    return report


def _integrity_item(label: str, artifact_dir: Path) -> RuntimeArtifactIntegrityItem:
    path = artifact_dir / f"{label.replace(' ', '-')}.txt"
    path.write_text(f"dashboard review evidence: {label}", encoding="utf-8")
    data = path.read_bytes()
    return RuntimeArtifactIntegrityItem(
        label=label,
        path=str(path),
        required=True,
        exists=True,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _complete_final_acceptance_report(
    tmp_path: Path,
    *,
    write_markdown: bool = True,
) -> RuntimeFinalAcceptanceReport:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    signoff_path = reports_dir / "operator-signoff.md"
    signoff_path.write_text("operator signoff", encoding="utf-8")
    markdown_path = reports_dir / "final-acceptance.md"
    report = RuntimeFinalAcceptanceReport(
        as_of=NOW - timedelta(minutes=1),
        status=RuntimePreflightStatus.PASSED,
        accepted_for_functional_paper_app=True,
        output_dir=str(tmp_path),
        checks=tuple(
            RuntimeFinalAcceptanceCheck(
                name=name,
                status=RuntimePreflightStatus.PASSED,
                message="Final acceptance check passed.",
                evidence=("passed=true",),
            )
            for name in sorted(REQUIRED_FINAL_ACCEPTANCE_CHECKS)
        ),
        signoff_path=str(signoff_path),
        summary="Final paper-app acceptance passed for the signed evidence packet.",
        markdown_path=str(markdown_path),
    )
    if write_markdown:
        markdown_path.write_text(
            render_final_acceptance_markdown(report),
            encoding="utf-8",
        )
    return report
