"""Credentialed Alpaca paper session provenance audit."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trading_app.runtime.models import (
    RuntimeCredentialedSessionCheck,
    RuntimeCredentialedSessionReport,
    RuntimePreflightReport,
    RuntimePreflightStatus,
    RuntimeSnapshot,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

_FORBIDDEN_PROVENANCE_MARKERS = (
    "fixture",
    "demo",
    "memory",
)
_FORBIDDEN_EXACT_SOURCES = {"provided", "missing"}
_REQUIRED_SECRET_NAMES = frozenset({"ALPACA_API_KEY", "ALPACA_SECRET_KEY"})


class RuntimeCredentialedSessionAuditor:
    """Audit that persisted artifacts look like one Alpaca paper session."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        persistence_store: RuntimePersistenceStore | None = None,
        expected_paper_account_id: str | None = None,
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.expected_paper_account_id = expected_paper_account_id
        self.persist_report = persist_report

    def audit(
        self, *, as_of: datetime | None = None
    ) -> RuntimeCredentialedSessionReport:
        now = as_of or datetime.now(tz=UTC)
        recovered = self.store.recover()
        preflight = recovered.preflight_report
        validation = recovered.validation_report
        soak = self.store.read_soak_evidence_report()
        secret_scan = self.store.read_secret_scan_report()
        snapshot = _read_runtime_snapshot(self.store)
        dashboard = recovered.dashboard_snapshot
        statement = self.store.read_statement_reconciliation_report()
        broker_history = self.store.read_broker_order_history_report()
        account_id = _paper_account_id(snapshot, dashboard, statement)
        latest = snapshot.latest_prices if snapshot else None
        checks = (
            _check(
                "preflight_credentials",
                _preflight_credentials_passed(preflight),
                "Preflight passed with Alpaca paper credentials required.",
                "Preflight credential evidence is missing or failed.",
                (
                    f"preflight={preflight.status.value}"
                    if preflight is not None
                    else "preflight=missing",
                    f"can_start={preflight.can_start}"
                    if preflight is not None
                    else "can_start=false",
                ),
            ),
            _check(
                "credentialed_validation",
                _validation_is_credentialed(validation),
                "Validation uses required credentials and Alpaca paper broker proof.",
                "Validation is missing, failed, or not credentialed Alpaca paper.",
                _validation_evidence(validation),
            ),
            _check(
                "runtime_snapshot_alpaca_paper",
                _snapshot_is_alpaca_paper(snapshot),
                "Runtime snapshot is Alpaca Paper with Alpaca paper portfolio.",
                "Runtime snapshot is missing or not Alpaca paper.",
                (
                    f"mode={snapshot.mode}" if snapshot else "mode=missing",
                    (
                        "broker_provider="
                        f"{snapshot.paper_report.broker_portfolio.provider}"
                    )
                    if snapshot and snapshot.paper_report
                    else "broker_provider=missing",
                ),
            ),
            _check(
                "dashboard_snapshot_alpaca_paper",
                _dashboard_is_alpaca_paper(dashboard),
                "Dashboard snapshot is sourced from Alpaca Paper runtime state.",
                "Dashboard snapshot is missing or not Alpaca paper.",
                (
                    f"mode={getattr(dashboard, 'mode', 'missing')}",
                    f"broker={getattr(dashboard, 'broker', 'missing')}",
                    (
                        "runtime_state_mode="
                        f"{_field(dashboard.runtime_state, 'mode', 'missing')}"
                    )
                    if dashboard is not None
                    else "runtime_state_mode=missing",
                ),
            ),
            _check(
                "latest_price_provenance",
                _latest_prices_are_external(latest, validation),
                "Latest-price provenance points to Alpaca market data.",
                "Latest-price provenance is missing or fixture-like.",
                _latest_price_evidence(latest, validation),
            ),
            _check(
                "soak_session_window",
                soak is not None
                and soak.passed
                and _ordered(soak.started_at, soak.completed_at),
                "Full-day plus overnight soak has an ordered completed window.",
                "Soak evidence is missing, failed, or has no completed window.",
                (
                    f"soak_status={soak.status.value}"
                    if soak is not None
                    else "soak_status=missing",
                    f"duration_hours={soak.duration_hours if soak else 0}",
                    f"cycles={soak.cycle_count if soak else 0}",
                ),
            ),
            _check(
                "statement_provenance",
                _statement_is_alpaca_paper(statement)
                and _account_matches(account_id, self.expected_paper_account_id),
                "Broker statement reconciliation is clean Alpaca paper evidence.",
                "Broker statement reconciliation is missing, failed, or untrusted.",
                _statement_evidence(
                    statement, account_id, self.expected_paper_account_id
                ),
            ),
            _check(
                "broker_order_history_provenance",
                _broker_history_is_alpaca_paper(broker_history),
                "Broker order-history audit is clean Alpaca paper evidence.",
                "Broker order-history audit is missing, failed, or untrusted.",
                (
                    f"provider={broker_history.provider}"
                    if broker_history is not None
                    else "provider=missing",
                    f"source={broker_history.source}"
                    if broker_history is not None
                    else "source=missing",
                    f"matched={broker_history.matched_order_count}"
                    if broker_history is not None
                    else "matched=0",
                    f"mismatches={broker_history.mismatch_count}"
                    if broker_history is not None
                    else "mismatches=0",
                ),
            ),
            _check(
                "secret_scan_clean",
                _secret_scan_is_credential_value_scan(secret_scan),
                "Secret scan found no configured credential values in artifacts.",
                (
                    "Secret scan is missing, found leaked credential values, or "
                    "did not check both Alpaca credential values."
                ),
                (
                    f"secret_scan={secret_scan.status.value}"
                    if secret_scan is not None
                    else "secret_scan=missing",
                    f"findings={len(secret_scan.findings) if secret_scan else 0}",
                    (
                        "secret_names_checked="
                        f"{','.join(secret_scan.secret_names_checked)}"
                    )
                    if secret_scan is not None
                    else "secret_names_checked=missing",
                ),
            ),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeCredentialedSessionReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            validation_id=validation.id if validation else None,
            session_started_at=_session_started_at(validation, soak),
            session_completed_at=_session_completed_at(validation, soak),
            paper_account_id=account_id,
            broker_providers=_broker_providers(
                validation, snapshot, statement, broker_history
            ),
            latest_price_sources=_latest_price_sources(latest, validation),
            feed=_feed(latest, validation),
            checks=checks,
            reviewed_artifact_count=len(checks),
            external_source_count=_external_source_count(
                latest, validation, statement, broker_history
            ),
            summary=_summary(status, failures, account_id),
        )
        if self.persist_report:
            markdown_path = write_credentialed_session_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_credentialed_session_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_credentialed_session_text(
    report: RuntimeCredentialedSessionReport,
) -> str:
    """Render compact credentialed session proof status."""

    lines = [
        f"Credentialed session status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Validation: {report.validation_id or 'missing'}",
        f"Paper account: {report.paper_account_id or 'missing'}",
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
    return "\n".join(lines)


def render_credentialed_session_markdown(
    report: RuntimeCredentialedSessionReport,
) -> str:
    """Render credentialed session proof Markdown."""

    lines = [
        "# Credentialed Alpaca Paper Session Proof",
        "",
        "> Paper trading only. This proof records provenance without storing "
        "credential values.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Validation ID: `{report.validation_id or 'missing'}`",
        f"- Session started: `{_datetime_text(report.session_started_at)}`",
        f"- Session completed: `{_datetime_text(report.session_completed_at)}`",
        f"- Paper account: `{report.paper_account_id or 'missing'}`",
        f"- Broker providers: `{_join(report.broker_providers)}`",
        f"- Latest-price sources: `{_join(report.latest_price_sources)}`",
        f"- Feed: `{report.feed or 'missing'}`",
        f"- External sources counted: `{report.external_source_count}`",
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


def write_credentialed_session_markdown_report(
    report: RuntimeCredentialedSessionReport,
    reports_dir: Path | str,
) -> Path:
    """Write credentialed session proof Markdown and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"credentialed-session-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_credentialed_session_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit credentialed Alpaca paper session provenance."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--expected-paper-account-id", default=None)
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeCredentialedSessionAuditor(
        output_dir=args.output_dir,
        expected_paper_account_id=args.expected_paper_account_id,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json()
        if args.json
        else render_credentialed_session_text(report)
    )
    return 0 if report.passed else 1


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeCredentialedSessionCheck:
    return RuntimeCredentialedSessionCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _read_runtime_snapshot(store: RuntimePersistenceStore) -> RuntimeSnapshot | None:
    path = store.state_dir / "latest-runtime-snapshot.json"
    if not path.exists():
        return None
    return RuntimeSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _preflight_credentials_passed(report: RuntimePreflightReport | None) -> bool:
    if report is None or not report.can_start:
        return False
    credential_check = next(
        (check for check in report.checks if check.name == "credentials"),
        None,
    )
    return (
        credential_check is not None
        and credential_check.status == RuntimePreflightStatus.PASSED
    )


def _secret_scan_is_credential_value_scan(secret_scan) -> bool:
    if secret_scan is None or not secret_scan.passed:
        return False
    return _REQUIRED_SECRET_NAMES.issubset(set(secret_scan.secret_names_checked))


def _validation_is_credentialed(validation) -> bool:
    return bool(
        validation is not None
        and validation.status == RuntimePreflightStatus.PASSED
        and validation.can_start_full_day_soak
        and validation.credential_required
        and _ordered(validation.started_at, validation.completed_at)
        and "alpaca-paper" in validation.broker_providers
        and not _has_forbidden_marker(validation.id)
    )


def _snapshot_is_alpaca_paper(snapshot: RuntimeSnapshot | None) -> bool:
    return bool(
        snapshot is not None
        and snapshot.mode == "Alpaca Paper"
        and snapshot.paper_report is not None
        and snapshot.paper_report.broker_portfolio.provider == "alpaca-paper"
    )


def _dashboard_is_alpaca_paper(dashboard) -> bool:
    return bool(
        dashboard is not None
        and dashboard.mode == "Alpaca Paper"
        and dashboard.broker == "alpaca-paper"
        and _field(dashboard.runtime_state, "mode") == "Alpaca Paper"
    )


def _latest_prices_are_external(latest, validation) -> bool:
    validation_sources = getattr(validation, "latest_price_sources", ()) or ()
    return bool(
        latest is not None
        and latest.all_fresh
        and _trusted_alpaca_source(latest.source)
        and all(_trusted_alpaca_source(record.source) for record in latest.prices)
        and (
            not validation_sources
            or any(_trusted_alpaca_source(source) for source in validation_sources)
        )
    )


def _statement_is_alpaca_paper(report) -> bool:
    return bool(
        report is not None
        and report.reconciled
        and report.statement.provider == "alpaca-paper"
        and report.statement.account_id
        and _trusted_source(report.statement.source)
    )


def _broker_history_is_alpaca_paper(report) -> bool:
    return bool(
        report is not None
        and report.passed
        and report.provider == "alpaca-paper"
        and _trusted_source(report.source)
    )


def _account_matches(account_id: str | None, expected: str | None) -> bool:
    return bool(account_id and (expected is None or account_id == expected))


def _ordered(started_at: datetime | None, completed_at: datetime | None) -> bool:
    return bool(
        started_at is not None
        and completed_at is not None
        and started_at <= completed_at
    )


def _paper_account_id(snapshot, dashboard, statement) -> str | None:
    if statement is not None and statement.statement.account_id:
        return statement.statement.account_id
    if snapshot is not None and snapshot.paper_report is not None:
        account_id = snapshot.paper_report.broker_portfolio.account_id
        if account_id:
            return account_id
    if dashboard is not None and dashboard.paper_report is not None:
        return dashboard.paper_report.broker_portfolio.account_id
    return None


def _validation_evidence(validation) -> tuple[str, ...]:
    if validation is None:
        return ("validation=missing",)
    return (
        f"validation_id={validation.id}",
        f"status={validation.status.value}",
        f"credential_required={validation.credential_required}",
        f"can_start_full_day_soak={validation.can_start_full_day_soak}",
        f"broker_providers={_join(validation.broker_providers)}",
    )


def _latest_price_evidence(latest, validation) -> tuple[str, ...]:
    validation_sources = getattr(validation, "latest_price_sources", ()) or ()
    validation_feeds = getattr(validation, "latest_price_feeds", ()) or ()
    if latest is None:
        return (
            "latest_snapshot=missing",
            f"validation_sources={_join(validation_sources)}",
            f"validation_feeds={_join(validation_feeds)}",
        )
    return (
        f"latest_source={latest.source}",
        f"latest_feed={latest.feed.value}",
        f"latest_status={latest.status.value}",
        f"missing_symbols={_join(latest.missing_symbols)}",
        f"validation_sources={_join(validation_sources)}",
    )


def _statement_evidence(
    report,
    account_id: str | None,
    expected_account_id: str | None,
) -> tuple[str, ...]:
    if report is None:
        return ("statement=missing",)
    return (
        f"statement={report.statement.statement_id}",
        f"provider={report.statement.provider}",
        f"source={report.statement.source}",
        f"statement_path={report.statement_path or 'missing'}",
        f"account_id={account_id or 'missing'}",
        f"expected_account_id={expected_account_id or 'not-specified'}",
        f"reconciled={report.reconciled}",
        f"issues={len(report.issues)}",
    )


def _session_started_at(validation, soak) -> datetime | None:
    if soak is not None and soak.started_at is not None:
        return soak.started_at
    return validation.started_at if validation is not None else None


def _session_completed_at(validation, soak) -> datetime | None:
    if soak is not None and soak.completed_at is not None:
        return soak.completed_at
    return validation.completed_at if validation is not None else None


def _broker_providers(
    validation, snapshot, statement, broker_history
) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(getattr(validation, "broker_providers", ()) or ())
    if snapshot is not None and snapshot.paper_report is not None:
        values.append(snapshot.paper_report.broker_portfolio.provider)
    if statement is not None:
        values.append(statement.statement.provider)
    if broker_history is not None:
        values.append(broker_history.provider)
    return tuple(sorted(set(values)))


def _latest_price_sources(latest, validation) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(getattr(validation, "latest_price_sources", ()) or ())
    if latest is not None:
        values.append(latest.source)
        values.extend(record.source for record in latest.prices)
    return tuple(sorted(set(values)))


def _feed(latest, validation) -> str | None:
    if latest is not None:
        return latest.feed.value
    feeds = getattr(validation, "latest_price_feeds", ()) or ()
    return feeds[0] if feeds else None


def _external_source_count(latest, validation, statement, broker_history) -> int:
    sources = list(_latest_price_sources(latest, validation))
    if statement is not None:
        sources.append(statement.statement.source)
    if broker_history is not None:
        sources.append(broker_history.source)
    return sum(1 for source in sources if _trusted_source(source))


def _trusted_alpaca_source(source: str | None) -> bool:
    return _trusted_source(source) and "alpaca" in source.casefold()


def _trusted_source(source: str | None) -> bool:
    return bool(source) and not _has_forbidden_marker(source)


def _has_forbidden_marker(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.casefold()
    return normalized in _FORBIDDEN_EXACT_SOURCES or any(
        marker in normalized for marker in _FORBIDDEN_PROVENANCE_MARKERS
    )


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    account_id: str | None,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return (
            "Credentialed session proof passed; persisted artifacts consistently "
            f"point to Alpaca paper account {account_id} without storing secrets."
        )
    return (
        f"Credentialed session proof found {failures} failed check(s). Produce a "
        "real Alpaca paper run with clean provenance, statement reconciliation, "
        "broker order history, and secret scan evidence."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _datetime_text(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "missing"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _join(values) -> str:
    values = tuple(values)
    return ", ".join(str(value) for value in values) if values else "none"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
