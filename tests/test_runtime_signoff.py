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
    RuntimeOperatorSignoff,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_artifact_integrity_markdown,
    render_completion_audit_markdown,
    render_credentialed_session_markdown,
    render_evidence_bundle_markdown,
    render_operator_signoff_markdown,
    render_operator_signoff_text,
)
from trading_app.runtime.audit_coverage import (
    REQUIRED_ARTIFACT_LABELS,
    REQUIRED_CREDENTIAL_SESSION_CHECKS,
    REQUIRED_EVIDENCE_BUNDLE_ITEMS,
    REQUIRED_FUNCTIONAL_REQUIREMENTS,
    operator_signoff_coverage_gap,
)
from trading_app.runtime.signoff import main as signoff_main

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)
CONFIRMATION_FLAGS = [
    "--confirm-evidence-reviewed",
    "--confirm-alpaca-paper-account-history",
    "--confirm-no-unintended-orders",
    "--confirm-fills-and-reconciliation-reviewed",
    "--confirm-dashboard-reviewed",
    "--confirm-paper-only-boundary",
    "--confirm-limitations-acknowledged",
]
CONFIRMATION_FLAG_NAMES = {
    "evidence_reviewed",
    "alpaca_paper_account_history",
    "no_unintended_orders",
    "fills_and_reconciliation_reviewed",
    "dashboard_reviewed",
    "paper_only_boundary",
    "limitations_acknowledged",
}


def test_operator_signoff_passes_after_clean_evidence_review(tmp_path) -> None:
    _persist_clean_review_evidence(tmp_path)

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations={
            "evidence_reviewed",
            "alpaca_paper_account_history",
            "no_unintended_orders",
            "fills_and_reconciliation_reviewed",
            "dashboard_reviewed",
            "paper_only_boundary",
            "limitations_acknowledged",
        },
        notes="Alpaca paper account history matched the reviewed local artifacts.",
        as_of=NOW,
    )
    text = render_operator_signoff_text(report)
    markdown = render_operator_signoff_markdown(report)

    assert report.accepted_for_paper_review
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.confirmation_count == 7
    assert report.missing_confirmation_count == 0
    assert operator_signoff_coverage_gap(report) == ()
    assert report.credentialed_session_path is not None
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Operator signoff status" in text
    assert "Alpaca Paper Operator Signoff" in markdown
    assert "does not authorize live-money trading" in markdown
    assert (tmp_path / "state" / "latest-operator-signoff-report.json").exists()
    assert (tmp_path / "journal" / "operator-signoffs.jsonl").exists()


def test_operator_signoff_fails_without_ready_evidence_or_confirmations(
    tmp_path,
) -> None:
    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations={"evidence_reviewed"},
        as_of=NOW,
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_paper_review
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.missing_confirmation_count == 6
    assert by_name["evidence_bundle_ready"].status == RuntimePreflightStatus.FAILED
    assert (
        by_name["credentialed_session_passed"].status == RuntimePreflightStatus.FAILED
    )
    assert by_name["paper_account_matches_credentialed_session"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert by_name["completion_audit_passed"].status == RuntimePreflightStatus.FAILED
    assert by_name["artifact_integrity_passed"].status == RuntimePreflightStatus.FAILED
    assert (
        by_name["confirmation_evidence_reviewed"].status
        == RuntimePreflightStatus.PASSED
    )
    assert (
        by_name["confirmation_no_unintended_orders"].status
        == RuntimePreflightStatus.FAILED
    )


def test_operator_signoff_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    _persist_clean_review_evidence(success_dir)

    success = signoff_main(
        [
            "--output-dir",
            str(success_dir),
            "--reviewer",
            "Dana",
            "--paper-account-id",
            "paper-account-1",
            "--json",
            *CONFIRMATION_FLAGS,
        ]
    )
    failure = signoff_main(
        [
            "--output-dir",
            str(failure_dir),
            "--reviewer",
            "Dana",
            "--paper-account-id",
            "paper-account-1",
            "--json",
            "--no-persist",
        ]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"accepted_for_paper_review":true' in output
    assert '"accepted_for_paper_review":false' in output
    assert "paper-account-1" in output


def test_operator_signoff_rejects_account_mismatch(tmp_path) -> None:
    _persist_clean_review_evidence(tmp_path)

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-2",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW,
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_paper_review
    assert by_name["credentialed_session_passed"].status == (
        RuntimePreflightStatus.PASSED
    )
    assert by_name["paper_account_matches_credentialed_session"].status == (
        RuntimePreflightStatus.FAILED
    )


def test_operator_signoff_rejects_missing_reviewer_and_account(tmp_path) -> None:
    _persist_clean_review_evidence(tmp_path)

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="   ",
        paper_account_id="  ",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW,
    )
    by_name = {check.name: check for check in report.checks}
    gaps = operator_signoff_coverage_gap(report)

    assert not report.accepted_for_paper_review
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.reviewer == "missing"
    assert report.paper_account_id == "missing"
    assert by_name["reviewer_recorded"].status == RuntimePreflightStatus.FAILED
    assert by_name["paper_account_recorded"].status == RuntimePreflightStatus.FAILED
    assert by_name["paper_account_matches_credentialed_session"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert "reviewer=missing" in gaps
    assert "paper_account_id=missing" in gaps


def test_operator_signoff_coverage_rejects_missing_review_paths(tmp_path) -> None:
    _persist_clean_review_evidence(tmp_path)

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW,
    )
    assert operator_signoff_coverage_gap(report) == ()
    assert report.evidence_bundle_path is not None
    Path(report.evidence_bundle_path).unlink()

    gaps = operator_signoff_coverage_gap(report)

    assert "missing_path_files=evidence_bundle_path" in gaps


def test_operator_signoff_rejects_integrity_manifest_before_bundle(tmp_path) -> None:
    store = _persist_clean_review_evidence(tmp_path)
    integrity = store.read_artifact_integrity_report()
    assert integrity is not None
    store.persist_artifact_integrity_report(
        integrity.model_copy(update={"as_of": NOW - timedelta(seconds=1)})
    )

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW,
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_paper_review
    assert by_name["artifact_integrity_passed"].status == RuntimePreflightStatus.FAILED
    assert any(
        "covers_evidence_bundle=False" in item
        for item in by_name["artifact_integrity_passed"].evidence
    )


def test_operator_signoff_rejects_changed_reviewed_artifact(tmp_path) -> None:
    store = _persist_clean_review_evidence(tmp_path)
    integrity = store.read_artifact_integrity_report()
    assert integrity is not None
    target = next(
        item for item in integrity.items if item.label == "evidence bundle markdown"
    )
    Path(target.path).write_text("changed before signoff", encoding="utf-8")

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW,
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_paper_review
    assert by_name["artifact_integrity_passed"].status == RuntimePreflightStatus.FAILED
    assert any(
        "hash_mismatch=evidence bundle markdown" in item
        for item in by_name["artifact_integrity_passed"].evidence
    )


def test_operator_signoff_rejects_changed_reviewed_markdown(tmp_path) -> None:
    store = _persist_clean_review_evidence(tmp_path)
    completion = store.read_completion_audit_report()
    assert completion is not None
    assert completion.markdown_path is not None
    Path(completion.markdown_path).write_text(
        "changed before signoff",
        encoding="utf-8",
    )

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW,
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_paper_review
    assert by_name["reviewed_markdown_artifacts_current"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert any(
        "mismatch=completion_audit_markdown" in item
        for item in by_name["reviewed_markdown_artifacts_current"].evidence
    )


def test_operator_signoff_rejects_timestamp_before_reviewed_packet(tmp_path) -> None:
    _persist_clean_review_evidence(tmp_path)

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW - timedelta(seconds=1),
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_paper_review
    assert by_name["signoff_packet_ordering"].status == RuntimePreflightStatus.FAILED
    assert any(
        "signoff_as_of=" in item for item in by_name["signoff_packet_ordering"].evidence
    )


def test_operator_signoff_rejects_partial_passed_review_packets(tmp_path) -> None:
    store = _persist_clean_review_evidence(tmp_path)
    bundle = store.read_evidence_bundle_report()
    completion = store.read_completion_audit_report()
    integrity = store.read_artifact_integrity_report()
    credentialed = store.read_credentialed_session_report()
    assert bundle is not None
    assert completion is not None
    assert integrity is not None
    assert credentialed is not None
    store.persist_evidence_bundle_report(
        bundle.model_copy(
            update={
                "items": bundle.items[:1],
                "required_count": 1,
                "passed_count": 1,
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
    store.persist_artifact_integrity_report(
        integrity.model_copy(
            update={
                "items": integrity.items[:1],
                "required_count": 1,
                "hashed_count": 1,
            }
        )
    )
    store.persist_credentialed_session_report(
        credentialed.model_copy(
            update={
                "checks": credentialed.checks[:1],
                "reviewed_artifact_count": 1,
                "external_source_count": 1,
            }
        )
    )

    report = RuntimeOperatorSignoff(output_dir=tmp_path).signoff(
        reviewer="Dana",
        paper_account_id="paper-account-1",
        confirmations=set(CONFIRMATION_FLAG_NAMES),
        as_of=NOW,
    )
    by_name = {check.name: check for check in report.checks}

    assert not report.accepted_for_paper_review
    assert by_name["evidence_bundle_ready"].status == RuntimePreflightStatus.FAILED
    assert by_name["completion_audit_passed"].status == RuntimePreflightStatus.FAILED
    assert by_name["artifact_integrity_passed"].status == RuntimePreflightStatus.FAILED
    assert (
        by_name["credentialed_session_passed"].status == RuntimePreflightStatus.FAILED
    )
    assert any(
        "missing_items=" in item for item in by_name["evidence_bundle_ready"].evidence
    )
    assert any(
        "missing_items=" in item for item in by_name["completion_audit_passed"].evidence
    )
    assert any(
        "missing_labels=" in item
        for item in by_name["artifact_integrity_passed"].evidence
    )
    assert any(
        "external_source_count_missing=2" in item
        for item in by_name["credentialed_session_passed"].evidence
    )


def _persist_clean_review_evidence(tmp_path: Path) -> RuntimePersistenceStore:
    store = RuntimePersistenceStore(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = reports_dir / "evidence-bundle.md"
    credentialed_session_path = reports_dir / "credentialed-session.md"
    completion_path = reports_dir / "completion-audit.md"
    integrity_path = reports_dir / "artifact-integrity.md"
    artifact_dir = reports_dir / "signed-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    bundle_item_path = artifact_dir / "evidence-bundle-item.json"
    bundle_item_path.write_text("signed evidence item", encoding="utf-8")

    bundle = RuntimeEvidenceBundleReport(
        as_of=NOW,
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

    credentialed = RuntimeCredentialedSessionReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        passed=True,
        output_dir=str(tmp_path),
        validation_id="validation-20260529T210000",
        session_started_at=NOW,
        session_completed_at=NOW,
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
        markdown_path=str(credentialed_session_path),
    )
    credentialed_session_path.write_text(
        render_credentialed_session_markdown(credentialed),
        encoding="utf-8",
    )
    store.persist_credentialed_session_report(
        credentialed,
        markdown_path=credentialed_session_path,
    )

    completion = FunctionalCompletionAuditReport(
        as_of=NOW,
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
        as_of=NOW,
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
    store.persist_artifact_integrity_report(
        integrity,
        markdown_path=integrity_path,
    )
    return store


def _integrity_item(label: str, artifact_dir: Path) -> RuntimeArtifactIntegrityItem:
    path = artifact_dir / f"{label.replace(' ', '-')}.txt"
    path.write_text(f"paper review evidence: {label}", encoding="utf-8")
    data = path.read_bytes()
    return RuntimeArtifactIntegrityItem(
        label=label,
        path=str(path),
        required=True,
        exists=True,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
