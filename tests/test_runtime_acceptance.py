from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_app.runtime import (
    FunctionalCompletionAuditReport,
    FunctionalRequirementEvidence,
    FunctionalRequirementStatus,
    RuntimeArtifactIntegrityItem,
    RuntimeArtifactIntegrityReport,
    RuntimeCredentialedSessionCheck,
    RuntimeCredentialedSessionReport,
    RuntimeEvidenceBundleItem,
    RuntimeEvidenceBundleReport,
    RuntimeFinalAcceptanceAuditor,
    RuntimeOperatorSignoffCheck,
    RuntimeOperatorSignoffReport,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_artifact_integrity_markdown,
    render_completion_audit_markdown,
    render_credentialed_session_markdown,
    render_evidence_bundle_markdown,
    render_final_acceptance_markdown,
    render_final_acceptance_text,
    render_operator_signoff_markdown,
)
from trading_app.runtime.acceptance import main as acceptance_main
from trading_app.runtime.audit_coverage import (
    REQUIRED_ARTIFACT_LABELS,
    REQUIRED_CREDENTIAL_SESSION_CHECKS,
    REQUIRED_EVIDENCE_BUNDLE_ITEMS,
    REQUIRED_FUNCTIONAL_REQUIREMENTS,
    REQUIRED_OPERATOR_SIGNOFF_CHECKS,
    final_acceptance_coverage_gap,
)

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)
CONFIRMATION_CHECKS = (
    "confirmation_evidence_reviewed",
    "confirmation_alpaca_paper_account_history",
    "confirmation_no_unintended_orders",
    "confirmation_fills_and_reconciliation_reviewed",
    "confirmation_dashboard_reviewed",
    "confirmation_paper_only_boundary",
    "confirmation_limitations_acknowledged",
)


def test_final_acceptance_passes_after_clean_operator_signoff(tmp_path) -> None:
    _persist_signed_packet(tmp_path)

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_final_acceptance_text(report)
    markdown = render_final_acceptance_markdown(report)

    assert report.accepted_for_functional_paper_app
    assert report.status == RuntimePreflightStatus.PASSED
    assert {check.status for check in report.checks} == {RuntimePreflightStatus.PASSED}
    assert final_acceptance_coverage_gap(report) == ()
    assert report.signoff_path is not None
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Final acceptance status" in text
    assert "Functional Paper App Final Acceptance" in markdown
    assert "does not authorize live-money trading" in markdown
    assert (tmp_path / "state" / "latest-final-acceptance-report.json").exists()
    assert (tmp_path / "journal" / "final-acceptance.jsonl").exists()


def test_final_acceptance_fails_without_signoff(tmp_path) -> None:
    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert report.status == RuntimePreflightStatus.FAILED
    assert by_name["operator_signoff_accepted"].status == RuntimePreflightStatus.FAILED
    assert by_name["review_artifact_paths"].status == RuntimePreflightStatus.FAILED


def test_final_acceptance_rejects_stale_signoff_ordering(tmp_path) -> None:
    store = _persist_signed_packet(tmp_path)
    signoff = store.read_operator_signoff_report()
    assert signoff is not None
    store.persist_operator_signoff_report(
        signoff.model_copy(update={"as_of": NOW - timedelta(minutes=3)})
    )

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["final_packet_ordering"].status == RuntimePreflightStatus.FAILED


def test_final_acceptance_rejects_timestamp_before_signoff(tmp_path) -> None:
    _persist_signed_packet(tmp_path)

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(
        as_of=NOW - timedelta(seconds=1)
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["final_packet_ordering"].status == RuntimePreflightStatus.FAILED
    assert any(
        "acceptance_as_of=" in item
        for item in by_name["final_packet_ordering"].evidence
    )


def test_final_acceptance_rejects_completion_audit_after_signoff(tmp_path) -> None:
    store = _persist_signed_packet(tmp_path)
    completion = store.read_completion_audit_report()
    assert completion is not None
    store.persist_completion_audit_report(
        completion.model_copy(update={"as_of": NOW + timedelta(minutes=1)})
    )

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(
        as_of=NOW + timedelta(minutes=2)
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["final_packet_ordering"].status == RuntimePreflightStatus.FAILED
    assert any(
        "completion_as_of=" in item
        for item in by_name["final_packet_ordering"].evidence
    )


def test_final_acceptance_rejects_credentialed_session_after_signoff(tmp_path) -> None:
    store = _persist_signed_packet(tmp_path)
    credentialed = store.read_credentialed_session_report()
    assert credentialed is not None
    store.persist_credentialed_session_report(
        credentialed.model_copy(update={"as_of": NOW + timedelta(minutes=1)})
    )

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(
        as_of=NOW + timedelta(minutes=2)
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["final_packet_ordering"].status == RuntimePreflightStatus.FAILED
    assert any(
        "credentialed_session_as_of=" in item
        for item in by_name["final_packet_ordering"].evidence
    )


def test_final_acceptance_rejects_changed_reviewed_artifact(tmp_path) -> None:
    store = _persist_signed_packet(tmp_path)
    integrity = store.read_artifact_integrity_report()
    assert integrity is not None
    target = next(
        item for item in integrity.items if item.label == "evidence bundle markdown"
    )
    Path(target.path).write_text("changed after signoff", encoding="utf-8")

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["reviewed_artifact_hashes_current"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert any(
        "hash_mismatch=evidence bundle markdown" in item
        for item in by_name["reviewed_artifact_hashes_current"].evidence
    )


def test_final_acceptance_rejects_signed_path_that_is_not_latest(
    tmp_path,
) -> None:
    store = _persist_signed_packet(tmp_path)
    signoff = store.read_operator_signoff_report()
    assert signoff is not None
    old_bundle_path = tmp_path / "reports" / "old-evidence-bundle.md"
    old_bundle_path.write_text("old signed packet", encoding="utf-8")
    store.persist_operator_signoff_report(
        signoff.model_copy(update={"evidence_bundle_path": str(old_bundle_path)}),
        markdown_path=Path(signoff.markdown_path),
    )

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["signed_paths_match_latest"].status == RuntimePreflightStatus.FAILED
    assert any(
        "path_mismatch=evidence_bundle" in item
        for item in by_name["signed_paths_match_latest"].evidence
    )


def test_final_acceptance_rejects_partial_operator_signoff_checks(tmp_path) -> None:
    store = _persist_signed_packet(tmp_path)
    signoff = store.read_operator_signoff_report()
    assert signoff is not None
    assert signoff.markdown_path is not None
    store.persist_operator_signoff_report(
        signoff.model_copy(update={"checks": signoff.checks[:1]}),
        markdown_path=Path(signoff.markdown_path),
    )

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["operator_signoff_final"].status == RuntimePreflightStatus.FAILED
    assert any(
        "missing_checks=" in item for item in by_name["operator_signoff_final"].evidence
    )


def test_final_acceptance_rejects_changed_signoff_markdown(tmp_path) -> None:
    store = _persist_signed_packet(tmp_path)
    signoff = store.read_operator_signoff_report()
    assert signoff is not None
    assert signoff.markdown_path is not None
    Path(signoff.markdown_path).write_text("changed after signoff", encoding="utf-8")

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["operator_signoff_artifacts_current"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert any(
        "mismatch=operator_signoff_markdown" in item
        for item in by_name["operator_signoff_artifacts_current"].evidence
    )


def test_final_acceptance_coverage_rejects_missing_signed_paths(tmp_path) -> None:
    _persist_signed_packet(tmp_path)
    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    assert final_acceptance_coverage_gap(report) == ()
    assert report.signoff_path is not None
    Path(report.signoff_path).unlink()

    gaps = final_acceptance_coverage_gap(report)

    assert "signoff_path_file=missing" in gaps


def test_final_acceptance_rejects_changed_signed_completion_markdown(
    tmp_path,
) -> None:
    store = _persist_signed_packet(tmp_path)
    completion = store.read_completion_audit_report()
    assert completion is not None
    assert completion.markdown_path is not None
    Path(completion.markdown_path).write_text("changed completion", encoding="utf-8")

    report = RuntimeFinalAcceptanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_functional_paper_app
    assert by_name["signed_review_artifacts_current"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert any(
        "mismatch=completion_audit_markdown" in item
        for item in by_name["signed_review_artifacts_current"].evidence
    )


def test_final_acceptance_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    _persist_signed_packet(success_dir)

    success = acceptance_main(["--output-dir", str(success_dir), "--json"])
    failure = acceptance_main(
        ["--output-dir", str(failure_dir), "--json", "--no-persist"]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"accepted_for_functional_paper_app":true' in output
    assert '"accepted_for_functional_paper_app":false' in output


def _persist_signed_packet(tmp_path: Path) -> RuntimePersistenceStore:
    store = RuntimePersistenceStore(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = reports_dir / "evidence-bundle.md"
    credentialed_path = reports_dir / "credentialed-session.md"
    completion_path = reports_dir / "completion-audit.md"
    integrity_path = reports_dir / "artifact-integrity.md"
    signoff_path = reports_dir / "operator-signoff.md"
    for path in (
        bundle_path,
        credentialed_path,
        completion_path,
        integrity_path,
        signoff_path,
    ):
        path.write_text("signed paper evidence", encoding="utf-8")
    artifact_dir = reports_dir / "signed-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    bundle_item_path = artifact_dir / "evidence-bundle-item.json"
    bundle_item_path.write_text("signed evidence item", encoding="utf-8")

    bundle = RuntimeEvidenceBundleReport(
        as_of=NOW - timedelta(minutes=2),
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
                path=str(bundle_item_path),
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
        markdown_path=str(bundle_path),
    )
    bundle_path.write_text(render_evidence_bundle_markdown(bundle), encoding="utf-8")
    store.persist_evidence_bundle_report(bundle, markdown_path=bundle_path)
    completion = FunctionalCompletionAuditReport(
        as_of=NOW - timedelta(minutes=4),
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
        markdown_path=str(completion_path),
    )
    completion_path.write_text(
        render_completion_audit_markdown(completion),
        encoding="utf-8",
    )
    store.persist_completion_audit_report(completion)
    integrity = RuntimeArtifactIntegrityReport(
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
        markdown_path=str(integrity_path),
    )
    integrity_path.write_text(
        render_artifact_integrity_markdown(integrity),
        encoding="utf-8",
    )
    store.persist_artifact_integrity_report(integrity, markdown_path=integrity_path)
    credentialed = RuntimeCredentialedSessionReport(
        as_of=NOW - timedelta(minutes=5),
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
        markdown_path=str(credentialed_path),
    )
    credentialed_path.write_text(
        render_credentialed_session_markdown(credentialed),
        encoding="utf-8",
    )
    store.persist_credentialed_session_report(
        credentialed,
        markdown_path=credentialed_path,
    )
    signoff = RuntimeOperatorSignoffReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        accepted_for_paper_review=True,
        output_dir=str(tmp_path),
        reviewer="Dana",
        paper_account_id="paper-account-1",
        checks=tuple(
            RuntimeOperatorSignoffCheck(
                name=name,
                status=RuntimePreflightStatus.PASSED,
                message="Operator signoff check passed.",
                evidence=("confirmed=true",),
            )
            for name in sorted(REQUIRED_OPERATOR_SIGNOFF_CHECKS)
        ),
        confirmation_count=len(CONFIRMATION_CHECKS),
        missing_confirmation_count=0,
        evidence_bundle_path=str(bundle_path),
        credentialed_session_path=str(credentialed_path),
        completion_audit_path=str(completion_path),
        artifact_integrity_path=str(integrity_path),
        notes="Paper evidence reviewed.",
        summary="Operator signoff accepted.",
        markdown_path=str(signoff_path),
    )
    signoff_path.write_text(render_operator_signoff_markdown(signoff), encoding="utf-8")
    store.persist_operator_signoff_report(signoff, markdown_path=signoff_path)
    return store


def _integrity_item(label: str, artifact_dir: Path) -> RuntimeArtifactIntegrityItem:
    path = artifact_dir / f"{label.replace(' ', '-')}.txt"
    path.write_text(f"signed paper evidence: {label}", encoding="utf-8")
    data = path.read_bytes()
    return RuntimeArtifactIntegrityItem(
        label=label,
        path=str(path),
        required=True,
        exists=True,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
