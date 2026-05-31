"""Restart recovery audit for persisted paper-runtime journals."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from trading_app.paper import PaperOrderStatus, PaperOrderSubmission
from trading_app.runtime.models import (
    RuntimePreflightStatus,
    RuntimeRecoveryAuditCheck,
    RuntimeRecoveryAuditReport,
    RuntimeSnapshot,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import Fill


class RuntimeRecoveryAuditor:
    """Prove persisted journals can be safely rehydrated after restart."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeRecoveryAuditReport:
        now = as_of or datetime.now(tz=UTC)
        raw_submissions = _read_raw_jsonl(
            self.store.journal_dir / "submissions.jsonl",
            PaperOrderSubmission,
        )
        raw_order_statuses = _read_raw_jsonl(
            self.store.journal_dir / "order-statuses.jsonl",
            PaperOrderStatus,
        )
        raw_fills = _read_raw_jsonl(self.store.journal_dir / "fills.jsonl", Fill)
        journal_errors = (
            raw_submissions.errors + raw_order_statuses.errors + raw_fills.errors
        )

        recovered = None
        recovery_error = None
        try:
            recovered = self.store.recover()
        except Exception as error:  # pragma: no cover - exact pydantic text varies
            recovery_error = _safe_error(error)

        snapshot, snapshot_error = _read_runtime_snapshot(self.store)

        duplicate_order_ids = _duplicates(
            submission.order.id for submission in raw_submissions.records
        )
        duplicate_broker_order_ids = _duplicates(
            submission.broker_order.broker_order_id
            for submission in raw_submissions.records
            if submission.broker_order is not None
        )
        duplicate_fill_ids = _duplicates(fill.id for fill in raw_fills.records)

        checks = (
            _journals_readable_check(
                journal_errors,
                raw_submission_count=len(raw_submissions.records),
                raw_order_status_count=len(raw_order_statuses.records),
                raw_fill_count=len(raw_fills.records),
            ),
            _state_recovered_check(recovered is not None, recovery_error),
            _duplicate_check(
                "duplicate_order_ids",
                duplicate_order_ids,
                "No duplicate client order IDs were found.",
                "Duplicate client order IDs were found.",
            ),
            _duplicate_check(
                "duplicate_broker_order_ids",
                duplicate_broker_order_ids,
                "No duplicate broker order IDs were found.",
                "Duplicate broker order IDs were found.",
            ),
            _duplicate_check(
                "duplicate_fill_ids",
                duplicate_fill_ids,
                "No duplicate fill IDs were found.",
                "Duplicate fill IDs were found.",
            ),
            _dedupe_consistency_check(
                recovered,
                raw_submissions.records,
                raw_order_statuses.records,
                raw_fills.records,
            ),
            _runtime_snapshot_alignment_check(
                snapshot,
                snapshot_error,
                recovered_submission_count=len(recovered.submissions)
                if recovered is not None
                else 0,
                recovered_order_status_count=len(recovered.order_statuses)
                if recovered is not None
                else 0,
                recovered_fill_count=len(recovered.fills)
                if recovered is not None
                else 0,
            ),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeRecoveryAuditReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            checks=checks,
            raw_submission_count=len(raw_submissions.records),
            recovered_submission_count=len(recovered.submissions)
            if recovered is not None
            else 0,
            raw_order_status_count=len(raw_order_statuses.records),
            recovered_order_status_count=len(recovered.order_statuses)
            if recovered is not None
            else 0,
            raw_fill_count=len(raw_fills.records),
            recovered_fill_count=len(recovered.fills) if recovered is not None else 0,
            duplicate_order_ids=tuple(duplicate_order_ids),
            duplicate_broker_order_ids=tuple(duplicate_broker_order_ids),
            duplicate_fill_ids=tuple(duplicate_fill_ids),
            summary=_summary(status, failures),
        )
        if self.persist_report:
            markdown_path = write_recovery_audit_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_recovery_audit_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_recovery_audit_text(report: RuntimeRecoveryAuditReport) -> str:
    """Render compact restart-recovery audit status."""

    lines = [
        f"Recovery audit status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Counts:",
        f"- raw submissions: {report.raw_submission_count}",
        f"- recovered submissions: {report.recovered_submission_count}",
        f"- raw order statuses: {report.raw_order_status_count}",
        f"- recovered order statuses: {report.recovered_order_status_count}",
        f"- raw fills: {report.raw_fill_count}",
        f"- recovered fills: {report.recovered_fill_count}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_recovery_audit_markdown(report: RuntimeRecoveryAuditReport) -> str:
    """Render restart-recovery audit Markdown for operator review."""

    lines = [
        "# Paper Runtime Restart Recovery Audit",
        "",
        "> Paper trading only. This audit verifies local journal rehydration.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Raw submissions: `{report.raw_submission_count}`",
        f"- Recovered submissions: `{report.recovered_submission_count}`",
        f"- Raw order statuses: `{report.raw_order_status_count}`",
        f"- Recovered order statuses: `{report.recovered_order_status_count}`",
        f"- Raw fills: `{report.raw_fill_count}`",
        f"- Recovered fills: `{report.recovered_fill_count}`",
        "",
        report.summary,
        "",
        "## Duplicate Keys",
        "",
        f"- Client order IDs: `{_join_or_none(report.duplicate_order_ids)}`",
        f"- Broker order IDs: `{_join_or_none(report.duplicate_broker_order_ids)}`",
        f"- Fill IDs: `{_join_or_none(report.duplicate_fill_ids)}`",
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
    lines.append("")
    return "\n".join(lines)


def write_recovery_audit_markdown_report(
    report: RuntimeRecoveryAuditReport,
    reports_dir: Path | str,
) -> Path:
    """Write restart-recovery audit Markdown and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"recovery-audit-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_recovery_audit_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit paper-runtime restart recovery from persisted journals."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeRecoveryAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(report.model_dump_json() if args.json else render_recovery_audit_text(report))
    return 0 if report.passed else 1


@dataclass(frozen=True)
class _JournalRead:
    records: tuple[BaseModel, ...]
    errors: tuple[str, ...]


def _read_raw_jsonl[ModelT: BaseModel](
    path: Path, model_type: type[ModelT]
) -> _JournalRead:
    if not path.exists():
        return _JournalRead(records=(), errors=())
    records: list[ModelT] = []
    errors: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            records.append(model_type.model_validate_json(line))
        except Exception as error:  # pragma: no cover - malformed fixtures are rare
            errors.append(f"{path}:{line_number}: {_safe_error(error)}")
    return _JournalRead(records=tuple(records), errors=tuple(errors))


def _read_runtime_snapshot(
    store: RuntimePersistenceStore,
) -> tuple[RuntimeSnapshot | None, str | None]:
    path = store.state_dir / "latest-runtime-snapshot.json"
    if not path.exists():
        return None, f"missing runtime snapshot: {path}"
    try:
        return (
            RuntimeSnapshot.model_validate_json(path.read_text(encoding="utf-8")),
            None,
        )
    except Exception as error:  # pragma: no cover - malformed fixtures are rare
        return None, _safe_error(error)


def _journals_readable_check(
    errors: tuple[str, ...],
    *,
    raw_submission_count: int,
    raw_order_status_count: int,
    raw_fill_count: int,
) -> RuntimeRecoveryAuditCheck:
    if errors:
        return _check(
            "journals_readable",
            RuntimePreflightStatus.FAILED,
            "One or more runtime journals could not be parsed.",
            errors,
        )
    return _check(
        "journals_readable",
        RuntimePreflightStatus.PASSED,
        "Runtime journals are readable.",
        (
            f"raw_submissions={raw_submission_count}",
            f"raw_order_statuses={raw_order_status_count}",
            f"raw_fills={raw_fill_count}",
        ),
    )


def _state_recovered_check(
    recovered: bool,
    recovery_error: str | None,
) -> RuntimeRecoveryAuditCheck:
    if not recovered:
        return _check(
            "state_recovered",
            RuntimePreflightStatus.FAILED,
            "Persisted state could not be recovered.",
            (recovery_error or "unknown recovery error",),
        )
    return _check(
        "state_recovered",
        RuntimePreflightStatus.PASSED,
        "Persisted state recovered successfully.",
    )


def _duplicate_check(
    name: str,
    duplicates: tuple[str, ...],
    passed_message: str,
    failed_message: str,
) -> RuntimeRecoveryAuditCheck:
    if duplicates:
        return _check(
            name,
            RuntimePreflightStatus.FAILED,
            failed_message,
            tuple(f"duplicate={value}" for value in duplicates),
        )
    return _check(name, RuntimePreflightStatus.PASSED, passed_message)


def _dedupe_consistency_check(
    recovered,
    submissions: tuple[BaseModel, ...],
    order_statuses: tuple[BaseModel, ...],
    fills: tuple[BaseModel, ...],
) -> RuntimeRecoveryAuditCheck:
    if recovered is None:
        return _check(
            "dedupe_consistency",
            RuntimePreflightStatus.FAILED,
            "Recovered counts are unavailable.",
        )
    expected_submissions = len({submission.order.id for submission in submissions})
    expected_statuses = len({status.order_id for status in order_statuses})
    expected_fills = len({fill.id for fill in fills})
    recovered_counts = (
        len(recovered.submissions),
        len(recovered.order_statuses),
        len(recovered.fills),
    )
    expected_counts = (expected_submissions, expected_statuses, expected_fills)
    if recovered_counts != expected_counts:
        return _check(
            "dedupe_consistency",
            RuntimePreflightStatus.FAILED,
            "Recovered counts do not match unique journal keys.",
            (
                f"expected_submissions={expected_submissions}",
                f"recovered_submissions={len(recovered.submissions)}",
                f"expected_order_statuses={expected_statuses}",
                f"recovered_order_statuses={len(recovered.order_statuses)}",
                f"expected_fills={expected_fills}",
                f"recovered_fills={len(recovered.fills)}",
            ),
        )
    return _check(
        "dedupe_consistency",
        RuntimePreflightStatus.PASSED,
        "Recovered state matches unique journal keys.",
        (
            f"submissions={expected_submissions}",
            f"order_statuses={expected_statuses}",
            f"fills={expected_fills}",
        ),
    )


def _runtime_snapshot_alignment_check(
    snapshot: RuntimeSnapshot | None,
    snapshot_error: str | None,
    *,
    recovered_submission_count: int,
    recovered_order_status_count: int,
    recovered_fill_count: int,
) -> RuntimeRecoveryAuditCheck:
    if snapshot is None:
        return _check(
            "runtime_snapshot_alignment",
            RuntimePreflightStatus.FAILED,
            "Runtime snapshot is unavailable for recovery alignment.",
            (snapshot_error or "missing runtime snapshot",),
        )
    if snapshot.paper_report is None:
        return _check(
            "runtime_snapshot_alignment",
            RuntimePreflightStatus.FAILED,
            "Runtime snapshot has no paper report.",
        )
    snapshot_submission_count = len(snapshot.paper_report.submissions)
    snapshot_order_status_count = len(snapshot.paper_report.order_statuses)
    snapshot_fill_count = len(snapshot.paper_report.fills)
    aligned = (
        snapshot_submission_count == recovered_submission_count
        and snapshot_order_status_count == recovered_order_status_count
        and snapshot_fill_count == recovered_fill_count
    )
    evidence = (
        f"snapshot_submissions={snapshot_submission_count}",
        f"recovered_submissions={recovered_submission_count}",
        f"snapshot_order_statuses={snapshot_order_status_count}",
        f"recovered_order_statuses={recovered_order_status_count}",
        f"snapshot_fills={snapshot_fill_count}",
        f"recovered_fills={recovered_fill_count}",
    )
    if not aligned:
        return _check(
            "runtime_snapshot_alignment",
            RuntimePreflightStatus.FAILED,
            "Recovered journals do not align with latest runtime snapshot.",
            evidence,
        )
    return _check(
        "runtime_snapshot_alignment",
        RuntimePreflightStatus.PASSED,
        "Recovered journals align with latest runtime snapshot.",
        evidence,
    )


def _check(
    name: str,
    status: RuntimePreflightStatus,
    message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeRecoveryAuditCheck:
    return RuntimeRecoveryAuditCheck(
        name=name,
        status=status,
        message=message,
        evidence=evidence,
    )


def _duplicates(values) -> tuple[str, ...]:
    counts = Counter(str(value) for value in values)
    return tuple(sorted(value for value, count in counts.items() if count > 1))


def _summary(status: RuntimePreflightStatus, failures: int) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Restart recovery audit passed; persisted journals rehydrate cleanly."
    return (
        f"Restart recovery audit found {failures} failed check(s). "
        "Do not trust restart recovery until the journals are cleaned up."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _safe_error(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _join_or_none(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
