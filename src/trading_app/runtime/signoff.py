"""Manual operator signoff for reviewed Alpaca paper evidence."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from trading_app.runtime.audit_coverage import (
    artifact_integrity_coverage_gap,
    credentialed_session_coverage_gap,
    evidence_bundle_coverage_gap,
    functional_completion_coverage_gap,
)
from trading_app.runtime.completion import render_completion_audit_markdown
from trading_app.runtime.evidence import render_evidence_bundle_markdown
from trading_app.runtime.integrity import render_artifact_integrity_markdown
from trading_app.runtime.models import (
    RuntimeOperatorSignoffCheck,
    RuntimeOperatorSignoffReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.runtime.session_proof import render_credentialed_session_markdown

_CONFIRMATIONS = (
    (
        "evidence_reviewed",
        (
            "Operator reviewed the evidence bundle, completion audit, and "
            "integrity manifest."
        ),
    ),
    (
        "alpaca_paper_account_history",
        "Operator compared Alpaca paper account history with local runtime evidence.",
    ),
    (
        "no_unintended_orders",
        "Operator found no unintended paper orders in the reviewed session.",
    ),
    (
        "fills_and_reconciliation_reviewed",
        "Operator reviewed fills, restart recovery, and statement reconciliation.",
    ),
    (
        "dashboard_reviewed",
        "Operator reviewed the dashboard during or after the paper runtime session.",
    ),
    (
        "paper_only_boundary",
        (
            "Operator confirmed paper-only mode, no margin, no shorts, and no "
            "live-money path."
        ),
    ),
    (
        "limitations_acknowledged",
        "Operator acknowledged IEX/free-data and tax-estimate limitations.",
    ),
)


class RuntimeOperatorSignoff:
    """Create a persisted manual signoff after evidence review."""

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

    def signoff(
        self,
        *,
        reviewer: str,
        paper_account_id: str,
        confirmations: set[str],
        notes: str = "",
        as_of: datetime | None = None,
    ) -> RuntimeOperatorSignoffReport:
        now = as_of or datetime.now(tz=UTC)
        reviewer_value = reviewer.strip()
        paper_account_value = paper_account_id.strip()
        evidence_bundle = self.store.read_evidence_bundle_report()
        evidence_bundle_path = self.store.read_evidence_bundle_report_path()
        bundle_ready = bool(
            evidence_bundle is not None and evidence_bundle.ready_for_operator_review
        )
        credentialed_session = self.store.read_credentialed_session_report()
        credentialed_session_path = self.store.read_credentialed_session_report_path()
        completion = self.store.read_completion_audit_report()
        artifact_integrity = self.store.read_artifact_integrity_report()
        artifact_integrity_path = self.store.read_artifact_integrity_report_path()
        completion_path = (
            Path(completion.markdown_path)
            if completion and completion.markdown_path
            else None
        )
        evidence_bundle_gap = (
            evidence_bundle_coverage_gap(evidence_bundle)
            if evidence_bundle is not None
            else ("evidence_bundle=missing",)
        )
        completion_gap = (
            functional_completion_coverage_gap(completion)
            if completion is not None
            else ("completion_audit=missing",)
        )
        artifact_integrity_gap = (
            artifact_integrity_coverage_gap(artifact_integrity)
            if artifact_integrity is not None
            else ("artifact_integrity=missing",)
        )
        artifact_integrity_fresh = _artifact_integrity_covers_evidence_bundle(
            artifact_integrity,
            evidence_bundle,
        )
        (
            artifact_hashes_current,
            artifact_hash_evidence,
        ) = _artifact_integrity_hashes_current(artifact_integrity)
        artifact_integrity_as_of = (
            artifact_integrity.as_of.isoformat()
            if artifact_integrity is not None
            else "missing"
        )
        evidence_bundle_as_of = (
            evidence_bundle.as_of.isoformat()
            if evidence_bundle is not None
            else "missing"
        )
        completion_as_of = completion.as_of.isoformat() if completion else "missing"
        credentialed_session_gap = (
            credentialed_session_coverage_gap(credentialed_session)
            if credentialed_session is not None
            else ("credentialed_session=missing",)
        )
        credentialed_session_as_of = (
            credentialed_session.as_of.isoformat()
            if credentialed_session is not None
            else "missing"
        )
        (
            reviewed_markdown_current,
            reviewed_markdown_evidence,
        ) = _reviewed_markdown_artifacts_current(
            evidence_bundle=evidence_bundle,
            evidence_bundle_path=evidence_bundle_path,
            completion=completion,
            completion_path=completion_path,
            artifact_integrity=artifact_integrity,
            artifact_integrity_path=artifact_integrity_path,
            credentialed_session=credentialed_session,
            credentialed_session_path=credentialed_session_path,
        )

        checks = (
            _report_check(
                "evidence_bundle_ready",
                bundle_ready and not evidence_bundle_gap,
                "Evidence bundle is ready for operator review.",
                "Evidence bundle is missing or not ready for operator review.",
                (
                    f"ready={bundle_ready}",
                    f"path={evidence_bundle_path or 'missing'}",
                    *evidence_bundle_gap,
                ),
            ),
            _report_check(
                "completion_audit_passed",
                completion is not None and completion.passed and not completion_gap,
                "Completion audit passed before operator signoff.",
                "Completion audit is missing or not passed.",
                (
                    f"passed={getattr(completion, 'passed', False)}",
                    f"path={completion_path or 'missing'}",
                    *completion_gap,
                ),
            ),
            _report_check(
                "artifact_integrity_passed",
                artifact_integrity is not None
                and artifact_integrity.passed
                and artifact_integrity_fresh
                and artifact_hashes_current
                and not artifact_integrity_gap,
                "Artifact integrity manifest passed before operator signoff.",
                "Artifact integrity manifest is missing or not passed.",
                (
                    f"passed={getattr(artifact_integrity, 'passed', False)}",
                    f"path={artifact_integrity_path or 'missing'}",
                    f"artifact_integrity_as_of={artifact_integrity_as_of}",
                    f"evidence_bundle_as_of={evidence_bundle_as_of}",
                    f"covers_evidence_bundle={artifact_integrity_fresh}",
                    f"artifact_hashes_current={artifact_hashes_current}",
                    *artifact_integrity_gap,
                    *artifact_hash_evidence,
                ),
            ),
            _report_check(
                "reviewer_recorded",
                bool(reviewer_value),
                "Reviewer identity was recorded.",
                "Reviewer identity is missing.",
                (f"reviewer={'present' if reviewer_value else 'missing'}",),
            ),
            _report_check(
                "paper_account_recorded",
                bool(paper_account_value),
                "Paper account identifier was recorded.",
                "Paper account identifier is missing.",
                (f"paper_account_id={paper_account_value or 'missing'}",),
            ),
            _report_check(
                "credentialed_session_passed",
                credentialed_session is not None
                and credentialed_session.passed
                and not credentialed_session_gap,
                "Credentialed session proof passed before operator signoff.",
                "Credentialed session proof is missing or not passed.",
                (
                    f"passed={getattr(credentialed_session, 'passed', False)}",
                    f"path={credentialed_session_path or 'missing'}",
                    *credentialed_session_gap,
                ),
            ),
            _report_check(
                "paper_account_matches_credentialed_session",
                _account_matches_credentialed_session(
                    paper_account_value,
                    credentialed_session,
                ),
                "Signoff paper account matches credentialed-session proof.",
                "Signoff paper account does not match credentialed-session proof.",
                (
                    f"paper_account_id={paper_account_value or 'missing'}",
                    (
                        "credentialed_session_account="
                        f"{_credentialed_account_id(credentialed_session) or 'missing'}"
                    ),
                ),
            ),
            _report_check(
                "signoff_packet_ordering",
                _signoff_packet_ordered(
                    now,
                    evidence_bundle,
                    completion,
                    artifact_integrity,
                    credentialed_session,
                ),
                "Operator signoff happened after the reviewed evidence packet.",
                "Operator signoff timestamp is before reviewed evidence.",
                (
                    f"signoff_as_of={now.isoformat()}",
                    f"evidence_bundle_as_of={evidence_bundle_as_of}",
                    f"completion_as_of={completion_as_of}",
                    f"artifact_integrity_as_of={artifact_integrity_as_of}",
                    f"credentialed_session_as_of={credentialed_session_as_of}",
                ),
            ),
            _report_check(
                "reviewed_markdown_artifacts_current",
                reviewed_markdown_current,
                "Reviewed Markdown artifacts match persisted review state.",
                "Reviewed Markdown artifacts are missing or stale.",
                reviewed_markdown_evidence,
            ),
            *_confirmation_checks(confirmations),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        missing_confirmations = sum(
            1 for name, _message in _CONFIRMATIONS if name not in confirmations
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeOperatorSignoffReport(
            as_of=now,
            status=status,
            accepted_for_paper_review=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            reviewer=reviewer_value or "missing",
            paper_account_id=paper_account_value or "missing",
            checks=checks,
            confirmation_count=len(_CONFIRMATIONS) - missing_confirmations,
            missing_confirmation_count=missing_confirmations,
            evidence_bundle_path=str(evidence_bundle_path)
            if evidence_bundle_path
            else None,
            credentialed_session_path=str(credentialed_session_path)
            if credentialed_session_path
            else None,
            completion_audit_path=str(completion_path) if completion_path else None,
            artifact_integrity_path=str(artifact_integrity_path)
            if artifact_integrity_path
            else None,
            notes=notes,
            summary=_summary(status, failures, missing_confirmations),
        )
        if self.persist_report:
            markdown_path = write_operator_signoff_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_operator_signoff_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_operator_signoff_text(report: RuntimeOperatorSignoffReport) -> str:
    """Render compact operator signoff status."""

    lines = [
        f"Operator signoff status: {report.status.value}",
        f"Accepted for paper review: {_yes_no(report.accepted_for_paper_review)}",
        f"Reviewer: {report.reviewer}",
        f"Paper account: {report.paper_account_id}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    if report.notes:
        lines.extend(("", "Notes:", report.notes))
    return "\n".join(lines)


def render_operator_signoff_markdown(report: RuntimeOperatorSignoffReport) -> str:
    """Render operator signoff Markdown."""

    lines = [
        "# Alpaca Paper Operator Signoff",
        "",
        "> Paper trading only. This signoff does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Accepted for paper review: `{_yes_no(report.accepted_for_paper_review)}`",
        f"- Reviewer: `{_escape_table(report.reviewer)}`",
        f"- Paper account: `{_escape_table(report.paper_account_id)}`",
        f"- Signed at: `{report.as_of.isoformat()}`",
        f"- Evidence bundle: `{report.evidence_bundle_path or 'missing'}`",
        (
            "- Credentialed session proof: "
            f"`{report.credentialed_session_path or 'missing'}`"
        ),
        f"- Completion audit: `{report.completion_audit_path or 'missing'}`",
        f"- Artifact integrity: `{report.artifact_integrity_path or 'missing'}`",
        f"- Confirmations: `{report.confirmation_count}`",
        f"- Missing confirmations: `{report.missing_confirmation_count}`",
        "",
        report.summary,
        "",
        "## Checks",
        "",
        "| Check | Status | Message | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        evidence = "<br>".join(check.evidence) if check.evidence else "No evidence"
        lines.append(
            "| "
            f"{_escape_table(check.name)} | "
            f"{check.status.value} | "
            f"{_escape_table(check.message)} | "
            f"{_escape_table(evidence)} |"
        )
    if report.notes:
        lines.extend(("", "## Operator Notes", "", report.notes, ""))
    else:
        lines.append("")
    return "\n".join(lines)


def write_operator_signoff_markdown_report(
    report: RuntimeOperatorSignoffReport,
    reports_dir: Path | str,
) -> Path:
    """Write operator signoff Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"operator-signoff-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_operator_signoff_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record manual Alpaca paper operator signoff."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--paper-account-id", required=True)
    parser.add_argument("--notes", default="")
    for name, message in _CONFIRMATIONS:
        parser.add_argument(
            f"--confirm-{name.replace('_', '-')}",
            action="store_true",
            help=message,
        )
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    confirmations = {
        name for name, _message in _CONFIRMATIONS if getattr(args, f"confirm_{name}")
    }
    report = RuntimeOperatorSignoff(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).signoff(
        reviewer=args.reviewer,
        paper_account_id=args.paper_account_id,
        confirmations=confirmations,
        notes=args.notes,
    )
    print(
        report.model_dump_json() if args.json else render_operator_signoff_text(report)
    )
    return 0 if report.accepted_for_paper_review else 1


def _confirmation_checks(
    confirmations: set[str],
) -> tuple[RuntimeOperatorSignoffCheck, ...]:
    return tuple(
        _report_check(
            f"confirmation_{name}",
            name in confirmations,
            message,
            f"Missing operator confirmation: {message}",
            (f"confirmed={name in confirmations}",),
        )
        for name, message in _CONFIRMATIONS
    )


def _report_check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeOperatorSignoffCheck:
    return RuntimeOperatorSignoffCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _account_matches_credentialed_session(
    paper_account_id: str,
    credentialed_session,
) -> bool:
    return bool(
        paper_account_id.strip()
        and credentialed_session is not None
        and credentialed_session.paper_account_id == paper_account_id.strip()
    )


def _credentialed_account_id(credentialed_session) -> str | None:
    return (
        credentialed_session.paper_account_id
        if credentialed_session is not None
        else None
    )


def _artifact_integrity_covers_evidence_bundle(
    artifact_integrity,
    evidence_bundle,
) -> bool:
    if artifact_integrity is None or evidence_bundle is None:
        return False
    required = {"evidence bundle state", "evidence bundle markdown"}
    labels = {
        item.label
        for item in artifact_integrity.items
        if item.required and item.exists and item.sha256
    }
    return (
        required.issubset(labels) and artifact_integrity.as_of >= evidence_bundle.as_of
    )


def _artifact_integrity_hashes_current(
    artifact_integrity,
) -> tuple[bool, tuple[str, ...]]:
    if artifact_integrity is None:
        return False, ("artifact_integrity=missing",)

    missing_files: list[str] = []
    missing_hashes: list[str] = []
    mismatched_hashes: list[str] = []
    checked = 0
    for item in artifact_integrity.items:
        if not item.required and not item.exists:
            continue
        path = Path(item.path)
        if not path.exists():
            missing_files.append(item.label)
            continue
        if not item.sha256:
            missing_hashes.append(item.label)
            continue
        checked += 1
        current_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if current_sha256 != item.sha256:
            mismatched_hashes.append(item.label)

    passed = not missing_files and not missing_hashes and not mismatched_hashes
    return passed, (
        f"checked={checked}",
        f"missing_files={len(missing_files)}",
        f"missing_hashes={len(missing_hashes)}",
        f"hash_mismatches={len(mismatched_hashes)}",
        *_label_evidence("missing_file", missing_files),
        *_label_evidence("missing_hash", missing_hashes),
        *_label_evidence("hash_mismatch", mismatched_hashes),
    )


def _signoff_packet_ordered(
    signoff_as_of: datetime,
    evidence_bundle,
    completion,
    artifact_integrity,
    credentialed_session,
) -> bool:
    return bool(
        evidence_bundle is not None
        and completion is not None
        and artifact_integrity is not None
        and credentialed_session is not None
        and signoff_as_of >= evidence_bundle.as_of
        and signoff_as_of >= completion.as_of
        and signoff_as_of >= artifact_integrity.as_of
        and signoff_as_of >= credentialed_session.as_of
        and artifact_integrity.as_of >= evidence_bundle.as_of
    )


def _reviewed_markdown_artifacts_current(
    *,
    evidence_bundle,
    evidence_bundle_path: Path | None,
    completion,
    completion_path: Path | None,
    artifact_integrity,
    artifact_integrity_path: Path | None,
    credentialed_session,
    credentialed_session_path: Path | None,
) -> tuple[bool, tuple[str, ...]]:
    artifacts = (
        (
            "evidence_bundle",
            evidence_bundle,
            evidence_bundle_path,
            render_evidence_bundle_markdown,
        ),
        (
            "completion_audit",
            completion,
            completion_path,
            render_completion_audit_markdown,
        ),
        (
            "artifact_integrity",
            artifact_integrity,
            artifact_integrity_path,
            render_artifact_integrity_markdown,
        ),
        (
            "credentialed_session",
            credentialed_session,
            credentialed_session_path,
            render_credentialed_session_markdown,
        ),
    )
    missing: list[str] = []
    mismatches: list[str] = []
    checked: list[str] = []
    for label, report, path, renderer in artifacts:
        if report is None:
            missing.append(f"{label}_report")
            continue
        expected_path = getattr(report, "markdown_path", None)
        if not expected_path:
            missing.append(f"{label}_markdown_path")
        if path is None:
            missing.append(f"{label}_path")
            continue
        if expected_path and str(path) != expected_path:
            mismatches.append(f"{label}_path")
        if not path.exists():
            missing.append(f"{label}_markdown")
            continue
        checked.append(label)
        if path.read_text(encoding="utf-8") != renderer(report):
            mismatches.append(f"{label}_markdown")

    return not missing and not mismatches, (
        f"checked={len(checked)}",
        *tuple(f"checked_artifact={label}" for label in sorted(checked)),
        *tuple(f"missing={item}" for item in sorted(missing)),
        *tuple(f"mismatch={item}" for item in sorted(mismatches)),
    )


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    missing_confirmations: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return (
            "Operator signoff accepted for the reviewed Alpaca paper evidence. "
            "Live-money trading remains disabled."
        )
    return (
        f"Operator signoff is incomplete: {failures} failed check(s), "
        f"{missing_confirmations} missing confirmation(s)."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _label_evidence(prefix: str, labels: list[str]) -> tuple[str, ...]:
    return tuple(f"{prefix}={label}" for label in sorted(labels)[:10])


if __name__ == "__main__":
    raise SystemExit(main())
