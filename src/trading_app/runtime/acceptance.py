"""Final post-signoff acceptance gate for the paper trading app."""

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
    operator_signoff_coverage_gap,
)
from trading_app.runtime.completion import render_completion_audit_markdown
from trading_app.runtime.evidence import render_evidence_bundle_markdown
from trading_app.runtime.integrity import render_artifact_integrity_markdown
from trading_app.runtime.models import (
    RuntimeFinalAcceptanceCheck,
    RuntimeFinalAcceptanceReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.runtime.session_proof import render_credentialed_session_markdown
from trading_app.runtime.signoff import render_operator_signoff_markdown

_REQUIRED_CONFIRMATION_CHECKS = frozenset(
    {
        "confirmation_evidence_reviewed",
        "confirmation_alpaca_paper_account_history",
        "confirmation_no_unintended_orders",
        "confirmation_fills_and_reconciliation_reviewed",
        "confirmation_dashboard_reviewed",
        "confirmation_paper_only_boundary",
        "confirmation_limitations_acknowledged",
    }
)


class RuntimeFinalAcceptanceAuditor:
    """Verify that a signed paper-runtime evidence packet is complete."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeFinalAcceptanceReport:
        now = as_of or datetime.now(tz=UTC)
        signoff = self.store.read_operator_signoff_report()
        signoff_path = self.store.read_operator_signoff_report_path()
        bundle_path = self.store.read_evidence_bundle_report_path()
        integrity_path = self.store.read_artifact_integrity_report_path()
        credentialed_path = self.store.read_credentialed_session_report_path()
        bundle = self.store.read_evidence_bundle_report()
        completion = self.store.read_completion_audit_report()
        integrity = self.store.read_artifact_integrity_report()
        credentialed = self.store.read_credentialed_session_report()
        completion_path = (
            Path(completion.markdown_path)
            if completion and completion.markdown_path
            else None
        )
        signoff_account = signoff.paper_account_id if signoff else "missing"
        credentialed_account = (
            credentialed.paper_account_id if credentialed else "missing"
        )
        signoff_as_of = signoff.as_of.isoformat() if signoff else "missing"
        integrity_as_of = integrity.as_of.isoformat() if integrity else "missing"
        completion_as_of = completion.as_of.isoformat() if completion else "missing"
        credentialed_as_of = (
            credentialed.as_of.isoformat() if credentialed else "missing"
        )

        checks = (
            _check(
                "operator_signoff_accepted",
                bool(
                    signoff
                    and signoff.status == RuntimePreflightStatus.PASSED
                    and signoff.accepted_for_paper_review
                ),
                "Operator signoff accepted the reviewed paper evidence.",
                "Operator signoff is missing or not accepted.",
                (
                    f"status={signoff.status.value if signoff else 'missing'}",
                    (
                        "accepted="
                        f"{signoff.accepted_for_paper_review if signoff else False}"
                    ),
                    f"path={signoff_path or 'missing'}",
                ),
            ),
            _operator_signoff_coverage_check(signoff),
            _operator_signoff_artifact_check(signoff, signoff_path, self.store),
            _confirmation_check(signoff),
            _path_check(signoff),
            _signed_path_alignment_check(
                signoff,
                signoff_path=signoff_path,
                bundle_path=bundle_path,
                completion_path=completion_path,
                integrity_path=integrity_path,
                credentialed_path=credentialed_path,
            ),
            _signed_review_artifacts_current_check(
                bundle=bundle,
                bundle_path=bundle_path,
                completion=completion,
                completion_path=completion_path,
                integrity=integrity,
                integrity_path=integrity_path,
                credentialed=credentialed,
                credentialed_path=credentialed_path,
            ),
            _coverage_check(
                "completion_audit_final",
                completion,
                functional_completion_coverage_gap,
                "Completion audit remains fully proven.",
                "Completion audit is missing, failed, or incomplete.",
            ),
            _coverage_check(
                "evidence_bundle_final",
                bundle,
                evidence_bundle_coverage_gap,
                "Evidence bundle remains ready for operator review.",
                "Evidence bundle is missing, failed, or incomplete.",
            ),
            _coverage_check(
                "artifact_integrity_final",
                integrity,
                artifact_integrity_coverage_gap,
                "Artifact integrity manifest covers all required review artifacts.",
                "Artifact integrity manifest is missing, failed, or incomplete.",
            ),
            _integrity_manifest_current_check(integrity),
            _coverage_check(
                "credentialed_session_final",
                credentialed,
                credentialed_session_coverage_gap,
                "Credentialed-session proof remains complete.",
                "Credentialed-session proof is missing, failed, or incomplete.",
            ),
            _check(
                "paper_account_alignment",
                bool(
                    signoff
                    and credentialed
                    and signoff.paper_account_id == credentialed.paper_account_id
                ),
                "Signed paper account matches credentialed-session proof.",
                "Signed paper account does not match credentialed-session proof.",
                (
                    f"signoff_account={signoff_account}",
                    f"credentialed_account={credentialed_account}",
                ),
            ),
            _check(
                "final_packet_ordering",
                bool(
                    signoff
                    and integrity
                    and bundle
                    and completion
                    and credentialed
                    and now >= signoff.as_of
                    and signoff.as_of >= integrity.as_of >= bundle.as_of
                    and signoff.as_of >= completion.as_of
                    and signoff.as_of >= credentialed.as_of
                ),
                "Final acceptance happened after the signed evidence packet.",
                "Final packet ordering is stale or incomplete.",
                (
                    f"acceptance_as_of={now.isoformat()}",
                    f"signoff_as_of={signoff_as_of}",
                    f"artifact_integrity_as_of={integrity_as_of}",
                    f"completion_as_of={completion_as_of}",
                    f"credentialed_session_as_of={credentialed_as_of}",
                    f"bundle_as_of={bundle.as_of.isoformat() if bundle else 'missing'}",
                ),
            ),
            _check(
                "paper_only_acceptance_boundary",
                _passed_check(signoff, "confirmation_paper_only_boundary")
                and _passed_check(signoff, "confirmation_limitations_acknowledged"),
                "Paper-only boundary and limitations were explicitly accepted.",
                "Paper-only boundary or limitations acknowledgement is missing.",
                (
                    "live_money_authorized=false",
                    "paper_only_phase=true",
                ),
            ),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeFinalAcceptanceReport(
            as_of=now,
            status=status,
            accepted_for_functional_paper_app=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            checks=checks,
            signoff_path=str(signoff_path) if signoff_path else None,
            summary=_summary(status, failures),
        )
        if self.persist_report:
            markdown_path = write_final_acceptance_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_final_acceptance_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_final_acceptance_text(report: RuntimeFinalAcceptanceReport) -> str:
    """Render compact final acceptance status."""

    lines = [
        f"Final acceptance status: {report.status.value}",
        (
            "Accepted for functional paper app: "
            f"{_yes_no(report.accepted_for_functional_paper_app)}"
        ),
        f"Output dir: {report.output_dir}",
        f"Signoff: {report.signoff_path or 'missing'}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_final_acceptance_markdown(report: RuntimeFinalAcceptanceReport) -> str:
    """Render final post-signoff acceptance Markdown."""

    lines = [
        "# Functional Paper App Final Acceptance",
        "",
        "> Paper trading only. This report does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        (
            "- Accepted for functional paper app: "
            f"`{_yes_no(report.accepted_for_functional_paper_app)}`"
        ),
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Operator signoff: `{report.signoff_path or 'missing'}`",
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
    lines.extend(("", "## Boundary", "", "- Live-money trading remains disabled.", ""))
    return "\n".join(lines)


def write_final_acceptance_markdown_report(
    report: RuntimeFinalAcceptanceReport,
    reports_dir: Path | str,
) -> Path:
    """Write final acceptance Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"final-acceptance-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_final_acceptance_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit final post-signoff paper app acceptance."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeFinalAcceptanceAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json() if args.json else render_final_acceptance_text(report)
    )
    return 0 if report.accepted_for_functional_paper_app else 1


def _coverage_check(
    name: str,
    report,
    coverage,
    passed_message: str,
    failed_message: str,
) -> RuntimeFinalAcceptanceCheck:
    gaps = coverage(report) if report is not None else (f"{name}=missing",)
    passed = bool(report and getattr(report, "passed", False) and not gaps)
    if name == "evidence_bundle_final":
        passed = bool(
            report and getattr(report, "ready_for_operator_review", False) and not gaps
        )
    return _check(
        name,
        passed,
        passed_message,
        failed_message,
        (
            f"status={getattr(getattr(report, 'status', None), 'value', 'missing')}",
            f"passed={getattr(report, 'passed', False)}",
            *gaps,
        ),
    )


def _operator_signoff_coverage_check(signoff) -> RuntimeFinalAcceptanceCheck:
    gaps = (
        operator_signoff_coverage_gap(signoff)
        if signoff is not None
        else ("operator_signoff=missing",)
    )
    return _check(
        "operator_signoff_final",
        bool(
            signoff
            and signoff.status == RuntimePreflightStatus.PASSED
            and signoff.accepted_for_paper_review
            and not gaps
        ),
        "Operator signoff contains every required final-review check.",
        "Operator signoff is missing, failed, or incomplete.",
        (
            f"status={getattr(getattr(signoff, 'status', None), 'value', 'missing')}",
            f"accepted={getattr(signoff, 'accepted_for_paper_review', False)}",
            "missing_confirmations="
            f"{getattr(signoff, 'missing_confirmation_count', 'missing')}",
            *gaps,
        ),
    )


def _operator_signoff_artifact_check(
    signoff,
    signoff_path: Path | None,
    store: RuntimePersistenceStore,
) -> RuntimeFinalAcceptanceCheck:
    state_path = store.state_dir / "latest-operator-signoff-report.json"
    pointer_path = store.state_dir / "latest-operator-signoff-report-path.json"
    expected_markdown_path = (
        Path(signoff.markdown_path)
        if signoff is not None and signoff.markdown_path
        else None
    )
    missing: list[str] = []
    mismatches: list[str] = []
    state_sha256 = "missing"
    markdown_sha256 = "missing"

    if signoff is None:
        missing.append("operator_signoff_report")
    if not state_path.exists():
        missing.append("operator_signoff_state")
    else:
        state_sha256 = hashlib.sha256(state_path.read_bytes()).hexdigest()
    if not pointer_path.exists():
        missing.append("operator_signoff_path_pointer")
    if signoff_path is None:
        missing.append("operator_signoff_path")
    if expected_markdown_path is None:
        missing.append("operator_signoff_markdown_path")
    elif signoff_path is not None and str(signoff_path) != str(expected_markdown_path):
        mismatches.append("operator_signoff_markdown_path")

    if signoff_path is not None:
        if not signoff_path.exists():
            missing.append("operator_signoff_markdown")
        elif signoff is not None:
            markdown_bytes = signoff_path.read_bytes()
            markdown_sha256 = hashlib.sha256(markdown_bytes).hexdigest()
            expected_markdown = render_operator_signoff_markdown(signoff)
            if markdown_bytes.decode("utf-8") != expected_markdown:
                mismatches.append("operator_signoff_markdown")

    return _check(
        "operator_signoff_artifacts_current",
        bool(signoff and not missing and not mismatches),
        "Operator signoff state and Markdown artifacts remain current.",
        "Operator signoff state or Markdown artifacts are missing or stale.",
        (
            f"state_path={state_path}",
            f"pointer_path={pointer_path}",
            f"markdown_path={signoff_path or 'missing'}",
            f"state_sha256={state_sha256}",
            f"markdown_sha256={markdown_sha256}",
            *tuple(f"missing={item}" for item in sorted(missing)),
            *tuple(f"mismatch={item}" for item in sorted(mismatches)),
        ),
    )


def _signed_review_artifacts_current_check(
    *,
    bundle,
    bundle_path: Path | None,
    completion,
    completion_path: Path | None,
    integrity,
    integrity_path: Path | None,
    credentialed,
    credentialed_path: Path | None,
) -> RuntimeFinalAcceptanceCheck:
    artifacts = (
        (
            "evidence_bundle",
            bundle,
            bundle_path,
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
            integrity,
            integrity_path,
            render_artifact_integrity_markdown,
        ),
        (
            "credentialed_session",
            credentialed,
            credentialed_path,
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

    return _check(
        "signed_review_artifacts_current",
        not missing and not mismatches,
        "Signed review Markdown artifacts match persisted review state.",
        "Signed review Markdown artifacts are missing or stale.",
        (
            f"checked={len(checked)}",
            *tuple(f"checked_artifact={label}" for label in sorted(checked)),
            *tuple(f"missing={item}" for item in sorted(missing)),
            *tuple(f"mismatch={item}" for item in sorted(mismatches)),
        ),
    )


def _integrity_manifest_current_check(integrity) -> RuntimeFinalAcceptanceCheck:
    if integrity is None:
        return _check(
            "reviewed_artifact_hashes_current",
            False,
            "Reviewed artifact hashes still match the integrity manifest.",
            "Artifact integrity manifest is missing.",
            ("artifact_integrity=missing",),
        )

    missing_files: list[str] = []
    missing_hashes: list[str] = []
    mismatched_hashes: list[str] = []
    checked = 0
    for item in integrity.items:
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
    return _check(
        "reviewed_artifact_hashes_current",
        passed,
        "Reviewed artifact hashes still match the integrity manifest.",
        "Reviewed artifacts changed after the integrity manifest was generated.",
        (
            f"checked={checked}",
            f"missing_files={len(missing_files)}",
            f"missing_hashes={len(missing_hashes)}",
            f"hash_mismatches={len(mismatched_hashes)}",
            *_label_evidence("missing_file", missing_files),
            *_label_evidence("missing_hash", missing_hashes),
            *_label_evidence("hash_mismatch", mismatched_hashes),
        ),
    )


def _confirmation_check(signoff) -> RuntimeFinalAcceptanceCheck:
    passed_names = {
        check.name
        for check in getattr(signoff, "checks", ())
        if check.status == RuntimePreflightStatus.PASSED
    }
    missing = tuple(sorted(_REQUIRED_CONFIRMATION_CHECKS - passed_names))
    missing_confirmation_count = getattr(
        signoff, "missing_confirmation_count", "missing"
    )
    return _check(
        "operator_confirmations",
        bool(signoff and signoff.missing_confirmation_count == 0 and not missing),
        "All required operator confirmations are present.",
        "Required operator confirmations are missing.",
        (
            f"missing_confirmations={missing_confirmation_count}",
            *tuple(f"missing_check={name}" for name in missing),
        ),
    )


def _path_check(signoff) -> RuntimeFinalAcceptanceCheck:
    paths = {
        "evidence_bundle": getattr(signoff, "evidence_bundle_path", None),
        "credentialed_session": getattr(signoff, "credentialed_session_path", None),
        "completion_audit": getattr(signoff, "completion_audit_path", None),
        "artifact_integrity": getattr(signoff, "artifact_integrity_path", None),
        "signoff": getattr(signoff, "markdown_path", None),
    }
    missing = tuple(sorted(name for name, path in paths.items() if not path))
    missing_files = tuple(
        sorted(
            name
            for name, path in paths.items()
            if path is not None and not Path(path).exists()
        )
    )
    return _check(
        "review_artifact_paths",
        bool(signoff and not missing and not missing_files),
        "Signed review artifact paths exist.",
        "Signed review artifact paths are missing or stale.",
        (
            *tuple(f"missing_path={name}" for name in missing),
            *tuple(f"missing_file={name}" for name in missing_files),
        )
        or ("paths=present",),
    )


def _signed_path_alignment_check(
    signoff,
    *,
    signoff_path: Path | None,
    bundle_path: Path | None,
    completion_path: Path | None,
    integrity_path: Path | None,
    credentialed_path: Path | None,
) -> RuntimeFinalAcceptanceCheck:
    expected = {
        "evidence_bundle": str(bundle_path) if bundle_path else None,
        "credentialed_session": str(credentialed_path) if credentialed_path else None,
        "completion_audit": str(completion_path) if completion_path else None,
        "artifact_integrity": str(integrity_path) if integrity_path else None,
        "signoff": str(signoff_path) if signoff_path else None,
    }
    actual = {
        "evidence_bundle": getattr(signoff, "evidence_bundle_path", None),
        "credentialed_session": getattr(signoff, "credentialed_session_path", None),
        "completion_audit": getattr(signoff, "completion_audit_path", None),
        "artifact_integrity": getattr(signoff, "artifact_integrity_path", None),
        "signoff": getattr(signoff, "markdown_path", None),
    }
    missing_latest = tuple(sorted(name for name, path in expected.items() if not path))
    mismatched = tuple(
        sorted(
            name
            for name, path in expected.items()
            if path is not None and actual[name] != path
        )
    )
    return _check(
        "signed_paths_match_latest",
        bool(signoff and not missing_latest and not mismatched),
        "Signed review paths match the latest persisted evidence paths.",
        "Signed review paths do not match the latest persisted evidence paths.",
        (
            *tuple(f"missing_latest_path={name}" for name in missing_latest),
            *tuple(
                f"path_mismatch={name}:signed={actual[name] or 'missing'}:"
                f"latest={expected[name]}"
                for name in mismatched
            ),
        )
        or ("signed_paths=current",),
    )


def _passed_check(signoff, name: str) -> bool:
    return any(
        check.name == name and check.status == RuntimePreflightStatus.PASSED
        for check in getattr(signoff, "checks", ())
    )


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeFinalAcceptanceCheck:
    return RuntimeFinalAcceptanceCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _summary(status: RuntimePreflightStatus, failures: int) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return (
            "Final paper-app acceptance passed for the signed evidence packet. "
            "Live-money trading remains disabled."
        )
    return f"Final paper-app acceptance failed with {failures} failed check(s)."


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
