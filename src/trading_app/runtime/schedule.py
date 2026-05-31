"""Deterministic schedule-authority audit for the paper runtime."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime.models import (
    RuntimePreflightStatus,
    RuntimeScheduleGuardrailCheck,
    RuntimeScheduleGuardrailReport,
)
from trading_app.runtime.paper import AlwaysOnPaperRuntime, AlwaysOnPaperRuntimeConfig
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed
from trading_app.strategies import MonthlySectorMomentumStrategy

PRE_CLOSE = datetime(2026, 5, 29, 19, 55, tzinfo=UTC)
PRE_TRADE_WINDOW = datetime(2026, 5, 29, 20, 4, tzinfo=UTC)
TRADE_WINDOW = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
SAME_DAY_LATER = datetime(2026, 5, 29, 21, 0, tzinfo=UTC)
WEEKEND_WINDOW = datetime(2026, 5, 30, 20, 10, tzinfo=UTC)
SYMBOLS = ("AAA", "SPY")


class RuntimeScheduleGuardrailAuditor:
    """Prove strategy authority is constrained to the approved schedule."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeScheduleGuardrailReport:
        now = as_of or datetime.now(tz=UTC)
        checks = (
            _regular_hours_monitor_only_check(self.output_dir),
            _pre_trade_window_monitor_only_check(self.output_dir),
            _daily_close_evaluates_check(self.output_dir),
            _same_day_repeat_blocks_check(self.output_dir),
            _weekend_blocks_check(self.output_dir),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        approved = sum(1 for check in checks if check.name == "daily_close_evaluates")
        protected = len(checks) - approved - failures
        report = RuntimeScheduleGuardrailReport(
            as_of=now,
            status=RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.PASSED,
            passed=failures == 0,
            output_dir=str(self.output_dir),
            checks=checks,
            approved_schedule_scenarios=approved if failures == 0 else 0,
            protected_schedule_scenarios=protected,
            unexpected_schedule_scenarios=failures,
            summary=_summary(failures, len(checks)),
        )
        if self.persist_report:
            markdown_path = write_schedule_guardrail_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_schedule_guardrail_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_schedule_guardrail_text(report: RuntimeScheduleGuardrailReport) -> str:
    """Render compact schedule-guardrail status."""

    lines = [
        f"Schedule guardrail status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        f"Approved schedule scenarios: {report.approved_schedule_scenarios}",
        f"Protected schedule scenarios: {report.protected_schedule_scenarios}",
        f"Unexpected schedule scenarios: {report.unexpected_schedule_scenarios}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_schedule_guardrail_markdown(
    report: RuntimeScheduleGuardrailReport,
) -> str:
    """Render schedule-guardrail audit Markdown."""

    lines = [
        "# Paper Runtime Schedule Guardrail Audit",
        "",
        (
            "> Paper trading only. This audit proves strategy authority remains "
            "daily-close only."
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Approved schedule scenarios: `{report.approved_schedule_scenarios}`",
        f"- Protected schedule scenarios: `{report.protected_schedule_scenarios}`",
        f"- Unexpected schedule scenarios: `{report.unexpected_schedule_scenarios}`",
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


def write_schedule_guardrail_markdown_report(
    report: RuntimeScheduleGuardrailReport,
    reports_dir: Path | str,
) -> Path:
    """Write schedule-guardrail Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"schedule-guardrails-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_schedule_guardrail_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run deterministic paper runtime schedule-guardrail audit."""

    parser = argparse.ArgumentParser(description="Audit paper runtime schedule gates.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeScheduleGuardrailAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    output = (
        report.model_dump_json()
        if args.json
        else render_schedule_guardrail_text(report)
    )
    print(output)
    return 0 if report.passed else 1


def _regular_hours_monitor_only_check(
    output_dir: Path,
) -> RuntimeScheduleGuardrailCheck:
    runtime = _runtime(output_dir / "schedule-scenarios" / "regular-hours")
    cycle = runtime.run_once(as_of=PRE_CLOSE)
    return _schedule_check(
        "regular_hours_monitor_only",
        (
            cycle.prices_refreshed
            and cycle.broker_synced
            and not cycle.strategy_evaluated
            and cycle.orders_submitted == 0
        ),
        "Regular-hours cycle monitored without strategy authority.",
        "Regular-hours cycle evaluated strategy or submitted orders.",
        _cycle_evidence(cycle, PRE_CLOSE),
    )


def _pre_trade_window_monitor_only_check(
    output_dir: Path,
) -> RuntimeScheduleGuardrailCheck:
    runtime = _runtime(output_dir / "schedule-scenarios" / "pre-trade-window")
    cycle = runtime.run_once(as_of=PRE_TRADE_WINDOW)
    return _schedule_check(
        "pre_trade_window_monitor_only",
        (
            cycle.prices_refreshed
            and cycle.broker_synced
            and not cycle.strategy_evaluated
            and cycle.orders_submitted == 0
        ),
        "Pre-trade daily-close window monitored without strategy authority.",
        "Pre-trade daily-close window evaluated strategy or submitted orders.",
        _cycle_evidence(cycle, PRE_TRADE_WINDOW),
    )


def _daily_close_evaluates_check(output_dir: Path) -> RuntimeScheduleGuardrailCheck:
    runtime = _runtime(output_dir / "schedule-scenarios" / "daily-close")
    cycle = runtime.run_once(as_of=TRADE_WINDOW)
    return _schedule_check(
        "daily_close_evaluates",
        cycle.strategy_evaluated and cycle.orders_submitted == 1,
        "Daily-close window evaluated strategy exactly once.",
        "Daily-close window did not evaluate strategy exactly once.",
        _cycle_evidence(cycle, TRADE_WINDOW),
    )


def _same_day_repeat_blocks_check(output_dir: Path) -> RuntimeScheduleGuardrailCheck:
    runtime = _runtime(output_dir / "schedule-scenarios" / "same-day-repeat")
    first = runtime.run_once(as_of=TRADE_WINDOW)
    second = runtime.run_once(as_of=SAME_DAY_LATER)
    return _schedule_check(
        "same_day_repeat_blocks",
        (
            first.strategy_evaluated
            and first.orders_submitted == 1
            and not second.strategy_evaluated
            and second.orders_submitted == 0
        ),
        "Second same-day cycle did not receive strategy authority.",
        "Second same-day cycle evaluated strategy or submitted orders.",
        (
            *_cycle_evidence(first, TRADE_WINDOW, prefix="first"),
            *_cycle_evidence(second, SAME_DAY_LATER, prefix="second"),
        ),
    )


def _weekend_blocks_check(output_dir: Path) -> RuntimeScheduleGuardrailCheck:
    runtime = _runtime(output_dir / "schedule-scenarios" / "weekend")
    cycle = runtime.run_once(as_of=WEEKEND_WINDOW)
    return _schedule_check(
        "weekend_blocks_strategy",
        (
            cycle.prices_refreshed
            and cycle.broker_synced
            and not cycle.strategy_evaluated
            and cycle.orders_submitted == 0
        ),
        "Weekend cycle monitored without strategy authority.",
        "Weekend cycle evaluated strategy or submitted orders.",
        _cycle_evidence(cycle, WEEKEND_WINDOW),
    )


def _runtime(output_dir: Path) -> AlwaysOnPaperRuntime:
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(SYMBOLS),
            tradable_symbols=frozenset(SYMBOLS),
        )
    )
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(
        broker=broker,
        starting_cash=Decimal("10000"),
        risk_engine=risk_engine,
    )
    return AlwaysOnPaperRuntime(
        service=service,
        latest_price_fetcher=FixtureLatestPriceFetcher(
            {"AAA": Decimal("100"), "SPY": Decimal("500")},
            observed_at=TRADE_WINDOW,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="schedule-audit"),
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA",),
            lookback_days=5,
            top_n=1,
        ),
        risk_engine=risk_engine,
        config=AlwaysOnPaperRuntimeConfig(
            symbols=SYMBOLS,
            starting_cash=Decimal("10000"),
            feed=DataFeed.IEX,
            output_dir=output_dir,
        ),
    )


def _schedule_check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...],
) -> RuntimeScheduleGuardrailCheck:
    return RuntimeScheduleGuardrailCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _cycle_evidence(
    cycle,
    as_of: datetime,
    *,
    prefix: str = "cycle",
) -> tuple[str, ...]:
    return (
        f"{prefix}_as_of={as_of.isoformat()}",
        f"{prefix}_prices_refreshed={cycle.prices_refreshed}",
        f"{prefix}_broker_synced={cycle.broker_synced}",
        f"{prefix}_strategy_evaluated={cycle.strategy_evaluated}",
        f"{prefix}_orders_submitted={cycle.orders_submitted}",
        f"{prefix}_status={cycle.status.value}",
    )


def _summary(failures: int, total: int) -> str:
    if failures:
        return (
            f"Schedule guardrail audit failed {failures}/{total} scenario(s); "
            "do not trust daily-close strategy authority until fixed."
        )
    return f"All {total} schedule guardrail scenarios behaved as expected."


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
