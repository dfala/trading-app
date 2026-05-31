"""Artifact integrity manifest for reviewed paper-runtime evidence."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from trading_app.runtime.models import (
    RuntimeArtifactIntegrityItem,
    RuntimeArtifactIntegrityReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

_PathEntry = tuple[str, Path, bool] | tuple[str, Path, bool, str | None]


class RuntimeArtifactIntegrityAuditor:
    """Hash the runtime evidence artifacts used for operator review."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeArtifactIntegrityReport:
        now = as_of or datetime.now(tz=UTC)
        items = tuple(_integrity_items(self.store))
        required_count = sum(1 for item in items if item.required)
        hashed_count = sum(1 for item in items if item.exists and item.sha256)
        missing_required_count = sum(
            1 for item in items if item.required and not item.exists
        )
        hash_mismatch_count = sum(
            1 for item in items if item.required and item.hash_matches is False
        )
        status = (
            RuntimePreflightStatus.FAILED
            if missing_required_count or hash_mismatch_count
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimeArtifactIntegrityReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            items=items,
            required_count=required_count,
            hashed_count=hashed_count,
            missing_required_count=missing_required_count,
            hash_mismatch_count=hash_mismatch_count,
            summary=_summary(
                status,
                hashed_count,
                len(items),
                missing_required_count,
                hash_mismatch_count,
            ),
        )
        if self.persist_report:
            markdown_path = write_artifact_integrity_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_artifact_integrity_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_artifact_integrity_text(report: RuntimeArtifactIntegrityReport) -> str:
    """Render compact artifact integrity status."""

    lines = [
        f"Artifact integrity status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Artifacts:",
    ]
    for item in report.items:
        digest = item.sha256[:12] if item.sha256 else "missing"
        lines.append(f"- {item.label}: {digest} - {item.path}")
    return "\n".join(lines)


def render_artifact_integrity_markdown(
    report: RuntimeArtifactIntegrityReport,
) -> str:
    """Render reviewable artifact integrity Markdown."""

    lines = [
        "# Paper Runtime Artifact Integrity Manifest",
        "",
        "> Paper trading only. This manifest fingerprints reviewed local evidence.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Generated at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Required artifacts: `{report.required_count}`",
        f"- Hashed artifacts: `{report.hashed_count}`",
        f"- Missing required: `{report.missing_required_count}`",
        f"- Hash mismatches: `{report.hash_mismatch_count}`",
        "",
        report.summary,
        "",
        "## Artifacts",
        "",
        (
            "| Artifact | Required | Exists | Size | SHA-256 | Expected SHA-256 "
            "| Match | Path |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.items:
        lines.append(
            "| "
            f"{_escape_table(item.label)} | "
            f"{_yes_no(item.required)} | "
            f"{_yes_no(item.exists)} | "
            f"{item.size_bytes} | "
            f"{item.sha256 or 'missing'} | "
            f"{item.expected_sha256 or '-'} | "
            f"{_match_text(item.hash_matches)} | "
            f"{_escape_table(item.path)} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_artifact_integrity_markdown_report(
    report: RuntimeArtifactIntegrityReport,
    reports_dir: Path | str,
) -> Path:
    """Write artifact integrity Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"artifact-integrity-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_artifact_integrity_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a SHA-256 manifest for paper-runtime evidence artifacts."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeArtifactIntegrityAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json()
        if args.json
        else render_artifact_integrity_text(report)
    )
    return 0 if report.passed else 1


def _integrity_items(
    store: RuntimePersistenceStore,
) -> list[RuntimeArtifactIntegrityItem]:
    paths = list(_required_state_paths(store))
    paths.extend(_report_paths(store))
    deduped: dict[str, _PathEntry] = {}
    for entry in paths:
        if len(entry) == 3:
            label, path, required = entry
            expected_sha256 = None
        else:
            label, path, required, expected_sha256 = entry
        deduped[str(path)] = (label, path, required, expected_sha256)
    return [
        _integrity_item(
            label=label,
            path=path,
            required=required,
            expected_sha256=expected_sha256,
        )
        for label, path, required, expected_sha256 in sorted(
            deduped.values(),
            key=lambda item: item[0],
        )
    ]


def _required_state_paths(
    store: RuntimePersistenceStore,
) -> tuple[_PathEntry, ...]:
    state = store.state_dir
    return (
        ("preflight state", state / "latest-preflight-report.json", True, None),
        (
            "operations readiness state",
            state / "latest-operations-readiness-report.json",
            True,
            None,
        ),
        (
            "lifecycle drill state",
            state / "latest-lifecycle-drill-report.json",
            True,
            None,
        ),
        ("dry-run state", state / "latest-dry-run-report.json", True, None),
        ("validation state", state / "latest-validation-report.json", True, None),
        ("soak state", state / "latest-soak-evidence-report.json", True, None),
        ("runtime snapshot state", state / "latest-runtime-snapshot.json", True, None),
        (
            "dashboard snapshot state",
            state / "latest-dashboard-snapshot.json",
            True,
            None,
        ),
        ("daily report state", state / "latest-daily-report.json", True, None),
        (
            "daily report path state",
            state / "latest-daily-report-path.json",
            True,
            None,
        ),
        (
            "dashboard consistency state",
            state / "latest-dashboard-consistency-report.json",
            True,
            None,
        ),
        (
            "dashboard visual state",
            state / "latest-dashboard-visual-report.json",
            True,
            None,
        ),
        (
            "data quality audit state",
            state / "latest-data-quality-audit-report.json",
            True,
            None,
        ),
        (
            "broker order history state",
            state / "latest-broker-order-history-report.json",
            True,
            None,
        ),
        (
            "credentialed session state",
            state / "latest-credentialed-session-report.json",
            True,
            None,
        ),
        (
            "evidence coherence state",
            state / "latest-evidence-coherence-report.json",
            True,
            None,
        ),
        (
            "restart recovery state",
            state / "latest-recovery-audit-report.json",
            True,
            None,
        ),
        ("secret scan state", state / "latest-secret-scan-report.json", True, None),
        (
            "model governance state",
            state / "latest-model-governance-report.json",
            True,
            None,
        ),
        (
            "order guardrail state",
            state / "latest-order-guardrail-report.json",
            True,
            None,
        ),
        (
            "schedule guardrail state",
            state / "latest-schedule-guardrail-report.json",
            True,
            None,
        ),
        ("fill sync state", state / "latest-fill-sync-report.json", True, None),
        (
            "statement reconciliation state",
            state / "latest-statement-reconciliation.json",
            True,
            None,
        ),
        (
            "completion audit state",
            state / "latest-completion-audit-report.json",
            True,
            None,
        ),
    )


def _report_paths(
    store: RuntimePersistenceStore,
) -> list[_PathEntry]:
    recovered = store.recover()
    paths: list[_PathEntry] = []
    if recovered.validation_report and recovered.validation_report.markdown_path:
        paths.append(
            (
                "validation markdown",
                Path(recovered.validation_report.markdown_path),
                False,
            )
        )
    operations_path = store.read_operations_readiness_report_path()
    if operations_path:
        paths.append(("operations readiness markdown", operations_path, False))
    lifecycle_path = store.read_lifecycle_drill_report_path()
    if lifecycle_path:
        paths.append(("lifecycle drill markdown", lifecycle_path, False))
    if recovered.health_report_path:
        paths.append(("health markdown", recovered.health_report_path, False))
    if recovered.daily_report_path:
        paths.append(("daily report markdown", recovered.daily_report_path, False))
    if recovered.learning_report_path:
        paths.append(("learning markdown", recovered.learning_report_path, False))
    model_governance_path = store.read_model_governance_report_path()
    if model_governance_path:
        paths.append(("model governance markdown", model_governance_path, False))
    order_guardrail_path = store.read_order_guardrail_report_path()
    if order_guardrail_path:
        paths.append(("order guardrail markdown", order_guardrail_path, False))
    schedule_guardrail_path = store.read_schedule_guardrail_report_path()
    if schedule_guardrail_path:
        paths.append(("schedule guardrail markdown", schedule_guardrail_path, False))
    fill_sync_path = store.read_fill_sync_report_path()
    if fill_sync_path:
        paths.append(("fill sync markdown", fill_sync_path, False))
    dashboard_consistency_path = store.read_dashboard_consistency_report_path()
    if dashboard_consistency_path:
        paths.append(
            ("dashboard consistency markdown", dashboard_consistency_path, False)
        )
    dashboard_visual_path = store.read_dashboard_visual_report_path()
    if dashboard_visual_path:
        paths.append(("dashboard visual markdown", dashboard_visual_path, False))
    dashboard_visual_report = store.read_dashboard_visual_report()
    if dashboard_visual_report and dashboard_visual_report.rendered_html_path:
        paths.append(
            (
                "dashboard visual rendered html",
                Path(dashboard_visual_report.rendered_html_path),
                False,
            )
        )
    data_quality_path = store.read_data_quality_audit_report_path()
    if data_quality_path:
        paths.append(("data quality audit markdown", data_quality_path, False))
    broker_history_path = store.read_broker_order_history_report_path()
    if broker_history_path:
        paths.append(("broker order history markdown", broker_history_path, False))
    broker_history = store.read_broker_order_history_report()
    if broker_history and broker_history.order_history_path:
        paths.append(
            (
                "broker order history source",
                Path(broker_history.order_history_path),
                False,
            )
        )
    credentialed_session_path = store.read_credentialed_session_report_path()
    if credentialed_session_path:
        paths.append(
            ("credentialed session markdown", credentialed_session_path, False)
        )
    evidence_coherence_path = store.read_evidence_coherence_report_path()
    if evidence_coherence_path:
        paths.append(("evidence coherence markdown", evidence_coherence_path, False))
    recovery_path = store.read_recovery_audit_report_path()
    if recovery_path:
        paths.append(("restart recovery markdown", recovery_path, False))
    statement_path = store.read_statement_reconciliation_path()
    if statement_path:
        paths.append(("statement reconciliation markdown", statement_path, False))
    statement = store.read_statement_reconciliation_report()
    if statement and statement.statement_path:
        paths.append(
            (
                "broker statement source",
                Path(statement.statement_path),
                True,
                statement.statement_sha256,
            )
        )
    completion = store.read_completion_audit_report()
    if completion and completion.markdown_path:
        paths.append(
            ("completion audit markdown", Path(completion.markdown_path), False)
        )
    evidence_bundle = store.read_evidence_bundle_report()
    if evidence_bundle:
        paths.append(
            (
                "evidence bundle state",
                store.state_dir / "latest-evidence-bundle-report.json",
                True,
            )
        )
        evidence_bundle_path = store.read_evidence_bundle_report_path()
        if evidence_bundle_path:
            paths.append(("evidence bundle markdown", evidence_bundle_path, True))
    signoff = store.read_operator_signoff_report()
    if signoff:
        paths.append(
            (
                "operator signoff state",
                store.state_dir / "latest-operator-signoff-report.json",
                False,
            )
        )
        signoff_path = store.read_operator_signoff_report_path()
        if signoff_path:
            paths.append(("operator signoff markdown", signoff_path, False))
    return paths


def _integrity_item(
    *,
    label: str,
    path: Path,
    required: bool,
    expected_sha256: str | None = None,
) -> RuntimeArtifactIntegrityItem:
    exists = path.exists()
    if not exists:
        return RuntimeArtifactIntegrityItem(
            label=label,
            path=str(path),
            required=required,
            exists=False,
            expected_sha256=expected_sha256,
            hash_matches=False if expected_sha256 else None,
        )
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return RuntimeArtifactIntegrityItem(
        label=label,
        path=str(path),
        required=required,
        exists=True,
        size_bytes=len(data),
        sha256=digest,
        expected_sha256=expected_sha256,
        hash_matches=digest == expected_sha256 if expected_sha256 else None,
    )


def _summary(
    status: RuntimePreflightStatus,
    hashed: int,
    total: int,
    missing_required: int,
    hash_mismatches: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return f"All required artifacts exist; {hashed}/{total} artifact(s) hashed."
    return (
        f"{missing_required} required artifact(s) are missing; "
        f"{hash_mismatches} required artifact hash mismatch(es) were found; "
        f"{hashed}/{total} artifact(s) were hashed."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _match_text(value: bool | None) -> str:
    if value is None:
        return "-"
    return _yes_no(value)


if __name__ == "__main__":
    raise SystemExit(main())
