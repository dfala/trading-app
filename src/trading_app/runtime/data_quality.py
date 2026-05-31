"""Deterministic market-data quality audit for paper runtime evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.market_data import (
    DataQualityIssueCode,
    DataQualityStatus,
    FixtureLatestPriceFetcher,
    MarketDataQualityChecker,
)
from trading_app.runtime.models import (
    RuntimeDataQualityAuditCheck,
    RuntimeDataQualityAuditReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DailyBar, DataFeed

AUDIT_TIME = datetime(2026, 5, 29, 20, tzinfo=UTC)


class RuntimeDataQualityAuditor:
    """Prove data-quality checks catch stale, missing, and weak data."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeDataQualityAuditReport:
        now = as_of or datetime.now(tz=UTC)
        checks = (
            _fresh_sip_latest_prices_check(),
            _iex_latest_prices_warn_check(),
            _stale_missing_latest_prices_fail_check(),
            _clean_sip_daily_bars_check(),
            _iex_missing_daily_bars_warn_check(),
            _duplicate_mixed_lookahead_daily_bars_fail_check(),
            _invalid_symbol_universe_fail_check(),
        )
        failed = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        report = RuntimeDataQualityAuditReport(
            as_of=now,
            status=RuntimePreflightStatus.FAILED
            if failed
            else RuntimePreflightStatus.PASSED,
            passed=failed == 0,
            output_dir=str(self.output_dir),
            checks=checks,
            latest_price_scenarios=3,
            daily_bar_scenarios=3,
            symbol_universe_scenarios=1,
            failed_quality_scenarios=failed,
            summary=_summary(failed, len(checks)),
        )
        if self.persist_report:
            markdown_path = write_data_quality_audit_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_data_quality_audit_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_data_quality_audit_text(report: RuntimeDataQualityAuditReport) -> str:
    """Render compact data-quality audit status."""

    lines = [
        f"Data quality audit status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        f"Latest-price scenarios: {report.latest_price_scenarios}",
        f"Daily-bar scenarios: {report.daily_bar_scenarios}",
        f"Symbol-universe scenarios: {report.symbol_universe_scenarios}",
        f"Failed quality scenarios: {report.failed_quality_scenarios}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_data_quality_audit_markdown(
    report: RuntimeDataQualityAuditReport,
) -> str:
    """Render data-quality audit Markdown."""

    lines = [
        "# Paper Runtime Data Quality Audit",
        "",
        "> Paper trading only. This audit proves market-data quality guardrails "
        "catch stale, missing, weak, and timestamp-unsafe data.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Latest-price scenarios: `{report.latest_price_scenarios}`",
        f"- Daily-bar scenarios: `{report.daily_bar_scenarios}`",
        f"- Symbol-universe scenarios: `{report.symbol_universe_scenarios}`",
        f"- Failed quality scenarios: `{report.failed_quality_scenarios}`",
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


def write_data_quality_audit_markdown_report(
    report: RuntimeDataQualityAuditReport,
    reports_dir: Path | str,
) -> Path:
    """Write data-quality audit Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"data-quality-audit-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_data_quality_audit_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run deterministic paper market-data quality audit."""

    parser = argparse.ArgumentParser(description="Audit paper runtime data quality.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeDataQualityAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json()
        if args.json
        else render_data_quality_audit_text(report)
    )
    return 0 if report.passed else 1


def _fresh_sip_latest_prices_check() -> RuntimeDataQualityAuditCheck:
    snapshot = FixtureLatestPriceFetcher(
        {"AAA": Decimal("100"), "BBB": Decimal("120")},
        observed_at=AUDIT_TIME,
        source="alpaca",
    ).fetch_latest_prices(
        ("AAA", "BBB"),
        as_of=AUDIT_TIME,
        feed=DataFeed.SIP,
        max_age=timedelta(minutes=15),
    )
    report = MarketDataQualityChecker().assess_latest_prices(
        snapshot,
        symbols=("AAA", "BBB"),
        generated_at=AUDIT_TIME,
    )
    return _quality_check(
        "fresh_sip_latest_prices_pass",
        report.status == DataQualityStatus.PASSED and report.can_use_for_trading,
        "Fresh SIP latest prices passed for trading use.",
        "Fresh SIP latest prices did not pass for trading use.",
        report,
    )


def _iex_latest_prices_warn_check() -> RuntimeDataQualityAuditCheck:
    snapshot = FixtureLatestPriceFetcher(
        {"AAA": Decimal("100")},
        observed_at=AUDIT_TIME,
        source="alpaca",
    ).fetch_latest_prices(
        ("AAA",),
        as_of=AUDIT_TIME,
        feed=DataFeed.IEX,
        max_age=timedelta(minutes=15),
    )
    report = MarketDataQualityChecker().assess_latest_prices(
        snapshot,
        symbols=("AAA",),
        generated_at=AUDIT_TIME,
    )
    codes = _codes(report)
    return _quality_check(
        "iex_latest_prices_warn_development_grade",
        report.status == DataQualityStatus.WARNING
        and report.can_use_for_research
        and not report.can_use_for_trading
        and DataQualityIssueCode.IEX_DEVELOPMENT_GRADE.value in codes,
        "IEX latest prices were labeled development-grade.",
        "IEX latest prices were not labeled development-grade.",
        report,
    )


def _stale_missing_latest_prices_fail_check() -> RuntimeDataQualityAuditCheck:
    snapshot = FixtureLatestPriceFetcher(
        {"AAA": Decimal("100")},
        observed_at=AUDIT_TIME - timedelta(hours=1),
        source="alpaca",
        missing_symbols=("BBB",),
    ).fetch_latest_prices(
        ("AAA", "BBB"),
        as_of=AUDIT_TIME,
        feed=DataFeed.IEX,
        max_age=timedelta(minutes=15),
    )
    report = MarketDataQualityChecker().assess_latest_prices(
        snapshot,
        symbols=("AAA", "BBB"),
        generated_at=AUDIT_TIME,
    )
    codes = _codes(report)
    return _quality_check(
        "stale_missing_latest_prices_fail",
        report.status == DataQualityStatus.FAILED
        and not report.can_use_for_trading
        and DataQualityIssueCode.STALE_LATEST_PRICE.value in codes
        and DataQualityIssueCode.MISSING_LATEST_PRICE.value in codes,
        "Stale and missing latest prices failed quality checks.",
        "Stale or missing latest prices did not fail quality checks.",
        report,
    )


def _clean_sip_daily_bars_check() -> RuntimeDataQualityAuditCheck:
    bars = (
        _bar("AAA", date(2026, 5, 28), feed=DataFeed.SIP),
        _bar("AAA", date(2026, 5, 29), feed=DataFeed.SIP),
    )
    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 28),
        end=date(2026, 5, 29),
        generated_at=AUDIT_TIME,
        expected_feed=DataFeed.SIP,
        as_of_date=date(2026, 5, 29),
    )
    return _quality_check(
        "clean_sip_daily_bars_pass",
        report.status == DataQualityStatus.PASSED and report.can_use_for_trading,
        "Clean SIP daily bars passed for trading use.",
        "Clean SIP daily bars did not pass for trading use.",
        report,
    )


def _iex_missing_daily_bars_warn_check() -> RuntimeDataQualityAuditCheck:
    bars = (_bar("AAA", date(2026, 5, 28), feed=DataFeed.IEX),)
    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 28),
        end=date(2026, 5, 29),
        generated_at=AUDIT_TIME,
        expected_feed=DataFeed.IEX,
        as_of_date=date(2026, 5, 29),
    )
    codes = _codes(report)
    return _quality_check(
        "iex_missing_daily_bars_warn",
        report.status == DataQualityStatus.WARNING
        and report.can_use_for_research
        and not report.can_use_for_trading
        and DataQualityIssueCode.IEX_DEVELOPMENT_GRADE.value in codes
        and DataQualityIssueCode.MISSING_BAR.value in codes,
        "IEX and missing daily bars produced warning quality evidence.",
        "IEX or missing daily bars were not flagged as warnings.",
        report,
    )


def _duplicate_mixed_lookahead_daily_bars_fail_check() -> RuntimeDataQualityAuditCheck:
    bars = (
        _bar("AAA", date(2026, 5, 29), feed=DataFeed.SIP),
        _bar("AAA", date(2026, 5, 29), feed=DataFeed.IEX),
        _bar("AAA", date(2026, 6, 1), feed=DataFeed.SIP),
    )
    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 29),
        end=date(2026, 6, 1),
        generated_at=AUDIT_TIME,
        expected_feed=DataFeed.SIP,
        as_of_date=date(2026, 5, 29),
    )
    codes = _codes(report)
    return _quality_check(
        "duplicate_mixed_lookahead_daily_bars_fail",
        report.status == DataQualityStatus.FAILED
        and not report.can_use_for_research
        and DataQualityIssueCode.DUPLICATE_BAR.value in codes
        and DataQualityIssueCode.MIXED_FEEDS.value in codes
        and DataQualityIssueCode.LOOKAHEAD_BAR.value in codes,
        "Duplicate, mixed-feed, and lookahead daily bars failed quality checks.",
        "Broken daily bars did not fail quality checks.",
        report,
    )


def _invalid_symbol_universe_fail_check() -> RuntimeDataQualityAuditCheck:
    snapshot = FixtureLatestPriceFetcher(
        {"AAA": Decimal("100")},
        observed_at=AUDIT_TIME,
        source="alpaca",
    ).fetch_latest_prices(
        ("AAA",),
        as_of=AUDIT_TIME,
        feed=DataFeed.SIP,
        max_age=timedelta(minutes=15),
    )
    report = MarketDataQualityChecker().assess_latest_prices(
        snapshot,
        symbols=("spy",),
        generated_at=AUDIT_TIME,
    )
    codes = _codes(report)
    return _quality_check(
        "invalid_symbol_universe_fail",
        report.status == DataQualityStatus.FAILED
        and not report.can_use_for_research
        and not report.can_use_for_trading
        and DataQualityIssueCode.INVALID_SYMBOL.value in codes,
        "Invalid lowercase symbol universe failed quality checks.",
        "Invalid symbol universe did not fail quality checks.",
        report,
    )


def _bar(symbol: str, trading_date: date, *, feed: DataFeed) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            21,
            tzinfo=UTC,
        ),
        ingested_at=AUDIT_TIME,
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100"),
        volume=Decimal("1000000"),
        source="data-quality-audit",
        data_feed=feed,
    )


def _quality_check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    report,
) -> RuntimeDataQualityAuditCheck:
    return RuntimeDataQualityAuditCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=(
            f"quality_status={report.status.value}",
            f"research_usable={report.can_use_for_research}",
            f"trading_usable={report.can_use_for_trading}",
            f"warnings={report.warnings}",
            f"failures={report.failures}",
            f"codes={','.join(_codes(report)) or '-'}",
        ),
    )


def _codes(report) -> tuple[str, ...]:
    return tuple(sorted({issue.code.value for issue in report.issues}))


def _summary(failures: int, total: int) -> str:
    if failures:
        return (
            f"Data-quality audit failed {failures}/{total} scenario(s); do not "
            "trust market data until the guardrails are fixed."
        )
    return f"All {total} market-data quality scenarios behaved as expected."


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
