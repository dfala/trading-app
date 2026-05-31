"""Evidence coherence audit for paper runtime artifacts."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trading_app.broker import BrokerStatementReconciliationReport
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.runtime.models import (
    RuntimeBrokerOrderHistoryReport,
    RuntimeCredentialedSessionReport,
    RuntimeDashboardConsistencyReport,
    RuntimeEvidenceCoherenceCheck,
    RuntimeEvidenceCoherenceReport,
    RuntimePreflightStatus,
    RuntimeSnapshot,
    RuntimeSoakEvidenceReport,
    RuntimeValidationReport,
)
from trading_app.runtime.persistence import RuntimePersistenceStore


class RuntimeEvidenceCoherenceAuditor:
    """Check that persisted evidence tells one coherent paper-session story."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeEvidenceCoherenceReport:
        now = as_of or datetime.now(tz=UTC)
        validation = _read_model(
            self.store.state_dir / "latest-validation-report.json",
            RuntimeValidationReport,
        )
        soak = self.store.read_soak_evidence_report()
        runtime = _read_model(
            self.store.state_dir / "latest-runtime-snapshot.json",
            RuntimeSnapshot,
        )
        dashboard = _read_model(
            self.store.state_dir / "latest-dashboard-snapshot.json",
            OperatorDashboardSnapshot,
        )
        dashboard_consistency = self.store.read_dashboard_consistency_report()
        statement = self.store.read_statement_reconciliation_report()
        broker_order_history = self.store.read_broker_order_history_report()
        credentialed_session = self.store.read_credentialed_session_report()
        checks = tuple(
            _checks(
                validation=validation,
                soak=soak,
                runtime=runtime,
                dashboard=dashboard,
                dashboard_consistency=dashboard_consistency,
                statement=statement,
                broker_order_history=broker_order_history,
                credentialed_session=credentialed_session,
                as_of=now,
            )
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        warnings = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.WARNING
        )
        status = (
            RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.WARNING
            if warnings
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimeEvidenceCoherenceReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            checks=checks,
            summary=_summary(status, failures, warnings),
        )
        if self.persist_report:
            markdown_path = write_evidence_coherence_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_evidence_coherence_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_evidence_coherence_text(report: RuntimeEvidenceCoherenceReport) -> str:
    """Render compact evidence-coherence status."""

    lines = [
        f"Evidence coherence status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
    return "\n".join(lines)


def render_evidence_coherence_markdown(report: RuntimeEvidenceCoherenceReport) -> str:
    """Render reviewable evidence-coherence Markdown."""

    lines = [
        "# Paper Runtime Evidence Coherence Audit",
        "",
        "> Paper trading only. This audit checks artifact timing and provenance.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
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
    lines.append("")
    return "\n".join(lines)


def write_evidence_coherence_markdown_report(
    report: RuntimeEvidenceCoherenceReport,
    reports_dir: Path | str,
) -> Path:
    """Write evidence-coherence Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"evidence-coherence-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_evidence_coherence_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit paper-runtime artifact timing and provenance."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeEvidenceCoherenceAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json()
        if args.json
        else render_evidence_coherence_text(report)
    )
    return 0 if report.passed else 1


def _checks(
    *,
    validation: RuntimeValidationReport | None,
    soak: RuntimeSoakEvidenceReport | None,
    runtime: RuntimeSnapshot | None,
    dashboard: OperatorDashboardSnapshot | None,
    dashboard_consistency: RuntimeDashboardConsistencyReport | None,
    statement: BrokerStatementReconciliationReport | None,
    broker_order_history: RuntimeBrokerOrderHistoryReport | None,
    credentialed_session: RuntimeCredentialedSessionReport | None,
    as_of: datetime,
) -> list[RuntimeEvidenceCoherenceCheck]:
    checks = [
        _check(
            "validation_present",
            validation is not None,
            "Validation report is present.",
            "Validation report is missing.",
        ),
        _check(
            "soak_present",
            soak is not None,
            "Soak evidence report is present.",
            "Soak evidence report is missing.",
        ),
        _check(
            "runtime_snapshot_present",
            runtime is not None,
            "Runtime snapshot is present.",
            "Runtime snapshot is missing.",
        ),
        _check(
            "dashboard_snapshot_present",
            dashboard is not None,
            "Dashboard snapshot is present.",
            "Dashboard snapshot is missing.",
        ),
        _check(
            "dashboard_consistency_present",
            dashboard_consistency is not None,
            "Dashboard consistency report is present.",
            "Dashboard consistency report is missing.",
        ),
        _check(
            "statement_reconciliation_present",
            statement is not None,
            "Statement reconciliation report is present.",
            "Statement reconciliation report is missing.",
        ),
        _check(
            "broker_order_history_present",
            broker_order_history is not None,
            "Broker order-history report is present.",
            "Broker order-history report is missing.",
        ),
        _check(
            "credentialed_session_present",
            credentialed_session is not None,
            "Credentialed session proof is present.",
            "Credentialed session proof is missing.",
        ),
    ]
    if (
        validation is None
        or soak is None
        or runtime is None
        or dashboard is None
        or dashboard_consistency is None
        or statement is None
        or broker_order_history is None
        or credentialed_session is None
    ):
        return checks

    paper_report = runtime.paper_report
    latest_prices = runtime.latest_prices
    checks.extend(
        (
            _check(
                "validation_window",
                validation.started_at <= validation.completed_at <= as_of,
                "Validation timestamps are ordered.",
                "Validation timestamps are not ordered.",
                (
                    f"started_at={validation.started_at.isoformat()}",
                    f"completed_at={validation.completed_at.isoformat()}",
                    f"as_of={as_of.isoformat()}",
                ),
            ),
            _check(
                "soak_window",
                soak.started_at is not None
                and soak.completed_at is not None
                and soak.started_at <= soak.completed_at <= as_of,
                "Soak timestamps are ordered.",
                "Soak timestamps are missing or not ordered.",
                (
                    f"started_at={_iso(soak.started_at)}",
                    f"completed_at={_iso(soak.completed_at)}",
                    f"as_of={as_of.isoformat()}",
                ),
            ),
            _check(
                "validation_before_soak",
                soak.started_at is not None
                and validation.started_at <= soak.started_at,
                "Validation started before the reviewed soak window.",
                "Validation appears to come from after the reviewed soak window.",
                (
                    f"validation_started={validation.started_at.isoformat()}",
                    f"soak_started={_iso(soak.started_at)}",
                ),
            ),
            _check(
                "snapshot_within_review_window",
                soak.started_at is not None
                and soak.started_at <= runtime.as_of <= as_of,
                "Runtime snapshot falls inside the reviewed evidence window.",
                "Runtime snapshot is outside the reviewed evidence window.",
                (
                    f"snapshot_as_of={runtime.as_of.isoformat()}",
                    f"soak_started={_iso(soak.started_at)}",
                    f"audit_as_of={as_of.isoformat()}",
                ),
            ),
            _check(
                "dashboard_consistency_passed",
                dashboard_consistency.passed,
                "Dashboard consistency passed.",
                "Dashboard consistency did not pass.",
                (f"status={dashboard_consistency.status.value}",),
            ),
            _check(
                "dashboard_matches_runtime_snapshot",
                dashboard.generated_at == runtime.as_of,
                "Dashboard snapshot timestamp matches runtime snapshot.",
                "Dashboard snapshot timestamp does not match runtime snapshot.",
                (
                    f"dashboard_generated_at={dashboard.generated_at.isoformat()}",
                    f"runtime_as_of={runtime.as_of.isoformat()}",
                ),
            ),
            _check(
                "statement_after_runtime_snapshot",
                statement.as_of >= runtime.as_of,
                "Statement reconciliation was generated after the runtime snapshot.",
                "Statement reconciliation predates the runtime snapshot.",
                (
                    f"statement_as_of={statement.as_of.isoformat()}",
                    f"runtime_as_of={runtime.as_of.isoformat()}",
                ),
            ),
            _check(
                "broker_order_history_after_runtime_snapshot",
                broker_order_history.as_of >= runtime.as_of
                and broker_order_history.as_of <= as_of,
                "Broker order-history audit falls inside the reviewed window.",
                "Broker order-history audit is outside the reviewed window.",
                (
                    f"broker_history_as_of={broker_order_history.as_of.isoformat()}",
                    f"runtime_as_of={runtime.as_of.isoformat()}",
                    f"audit_as_of={as_of.isoformat()}",
                ),
            ),
            _check(
                "alpaca_provider_alignment",
                _has_alpaca_validation(validation)
                and _runtime_provider(paper_report) == "alpaca-paper"
                and dashboard.broker == "alpaca-paper"
                and statement.statement.provider == "alpaca-paper",
                "Validation, runtime, dashboard, and statement all show Alpaca paper.",
                "Provider provenance is missing or inconsistent.",
                (
                    (
                        "validation_brokers="
                        f"{','.join(validation.broker_providers) or '-'}"
                    ),
                    f"runtime_broker={_runtime_provider(paper_report) or '-'}",
                    f"dashboard_broker={dashboard.broker}",
                    f"statement_provider={statement.statement.provider}",
                ),
            ),
            _check(
                "broker_order_history_provider_alignment",
                broker_order_history.provider == "alpaca-paper"
                and broker_order_history.passed,
                "Broker order-history evidence shows Alpaca paper and passed.",
                "Broker order-history evidence is not clean Alpaca paper evidence.",
                (
                    f"provider={broker_order_history.provider}",
                    f"passed={broker_order_history.passed}",
                    f"source={broker_order_history.source}",
                ),
            ),
            _check(
                "broker_order_history_order_alignment",
                broker_order_history.local_order_count
                == broker_order_history.matched_order_count
                and broker_order_history.broker_order_count
                == broker_order_history.matched_order_count
                and broker_order_history.mismatch_count == 0,
                "Broker order-history counts align with persisted local evidence.",
                "Broker order-history counts do not align with local evidence.",
                (
                    f"local={broker_order_history.local_order_count}",
                    f"broker={broker_order_history.broker_order_count}",
                    f"matched={broker_order_history.matched_order_count}",
                    f"mismatches={broker_order_history.mismatch_count}",
                ),
            ),
            _check(
                "alpaca_price_source_alignment",
                "alpaca" in validation.latest_price_sources
                and latest_prices is not None
                and latest_prices.source == "alpaca",
                "Validation and runtime latest prices use Alpaca source.",
                "Latest-price source provenance is missing or inconsistent.",
                (
                    "validation_price_sources="
                    f"{','.join(validation.latest_price_sources) or '-'}",
                    (
                        "runtime_latest_price_source="
                        f"{latest_prices.source if latest_prices else '-'}"
                    ),
                ),
            ),
            _check(
                "soak_evidence_clean",
                soak.passed
                and soak.duration_hours >= 24
                and soak.market_cycle_count > 0
                and soak.overnight_cycle_count > 0
                and soak.off_schedule_order_cycles == 0,
                "Soak evidence is clean for full-day plus overnight review.",
                "Soak evidence is incomplete or contains off-schedule orders.",
                (
                    f"duration_hours={soak.duration_hours}",
                    f"market_cycles={soak.market_cycle_count}",
                    f"overnight_cycles={soak.overnight_cycle_count}",
                    f"off_schedule_order_cycles={soak.off_schedule_order_cycles}",
                ),
            ),
            _check(
                "credentialed_session_passed",
                credentialed_session.passed,
                "Credentialed session proof passed.",
                "Credentialed session proof failed.",
                (
                    f"status={credentialed_session.status.value}",
                    f"validation={credentialed_session.validation_id or '-'}",
                    f"account={credentialed_session.paper_account_id or '-'}",
                ),
            ),
            _check(
                "credentialed_session_window_alignment",
                credentialed_session.session_started_at == soak.started_at
                and credentialed_session.session_completed_at == soak.completed_at,
                "Credentialed session proof matches the reviewed soak window.",
                "Credentialed session proof does not match the reviewed soak window.",
                (
                    f"session_started={_iso(credentialed_session.session_started_at)}",
                    f"soak_started={_iso(soak.started_at)}",
                    f"session_completed={_iso(credentialed_session.session_completed_at)}",
                    f"soak_completed={_iso(soak.completed_at)}",
                ),
            ),
            _check(
                "credentialed_session_validation_alignment",
                credentialed_session.validation_id == validation.id,
                "Credentialed session proof matches validation evidence.",
                "Credentialed session proof does not match validation evidence.",
                (
                    f"session_validation={credentialed_session.validation_id or '-'}",
                    f"validation_id={validation.id}",
                ),
            ),
            _check(
                "credentialed_session_account_alignment",
                credentialed_session.paper_account_id == statement.statement.account_id,
                "Credentialed session proof matches statement account.",
                "Credentialed session proof account does not match statement account.",
                (
                    f"session_account={credentialed_session.paper_account_id or '-'}",
                    f"statement_account={statement.statement.account_id or '-'}",
                ),
            ),
        )
    )
    return checks


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeEvidenceCoherenceCheck:
    return RuntimeEvidenceCoherenceCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _read_model(path: Path, model_type):
    if not path.exists():
        return None
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _has_alpaca_validation(validation: RuntimeValidationReport) -> bool:
    return (
        validation.credential_required and "alpaca-paper" in validation.broker_providers
    )


def _runtime_provider(paper_report) -> str | None:
    return paper_report.broker_portfolio.provider if paper_report is not None else None


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "missing"


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    warnings: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Runtime evidence is coherent across timing and provenance checks."
    return (
        f"Evidence coherence found {failures} failed check(s) and {warnings} "
        "warning check(s)."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
