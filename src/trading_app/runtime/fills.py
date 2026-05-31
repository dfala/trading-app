"""Deterministic fill-sync audit for paper runtime accounting."""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime, timedelta
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
    RuntimeFillSyncCheck,
    RuntimeFillSyncReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.paper import AlwaysOnPaperRuntime, AlwaysOnPaperRuntimeConfig
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, Fill, Order, OrderSide, OrderStatus, OrderType
from trading_app.strategies import MonthlySectorMomentumStrategy

SYNC_TIME = datetime(2026, 5, 29, 19, 0, tzinfo=UTC)
SYMBOLS = ("AAA", "SPY")
ORDER_ID = "fill-sync-paper-order"


class RuntimeFillSyncAuditor:
    """Prove broker fill sync applies internal ledger fills exactly once."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeFillSyncReport:
        now = as_of or datetime.now(tz=UTC)
        scenario_dir = self.output_dir / "fill-sync-scenarios" / "incremental"
        if scenario_dir.exists():
            shutil.rmtree(scenario_dir)

        runtime = _runtime(scenario_dir)
        order = _submit_manual_order(runtime)
        runtime.service.broker.fill_order(
            order.id,
            price=Decimal("100"),
            quantity=Decimal("1"),
            filled_at=SYNC_TIME,
        )

        first_cycle = runtime.run_once(as_of=SYNC_TIME)
        checks = [
            _partial_fill_applied_once_check(runtime, scenario_dir, first_cycle),
        ]

        repeat_cycle = runtime.run_once(as_of=SYNC_TIME + timedelta(minutes=1))
        checks.append(
            _repeat_sync_does_not_duplicate_fill_check(
                runtime,
                scenario_dir,
                repeat_cycle,
            )
        )

        runtime.service.broker.fill_order(
            order.id,
            price=Decimal("100"),
            quantity=Decimal("1"),
            filled_at=SYNC_TIME + timedelta(minutes=2),
        )
        second_fill_cycle = runtime.run_once(as_of=SYNC_TIME + timedelta(minutes=2))
        checks.append(
            _second_incremental_fill_applied_once_check(
                runtime,
                scenario_dir,
                second_fill_cycle,
            )
        )

        restarted = _runtime(
            scenario_dir,
            broker=runtime.service.broker,
            persistence_store=RuntimePersistenceStore(scenario_dir),
        )
        restart_cycle = restarted.run_once(as_of=SYNC_TIME + timedelta(minutes=3))
        checks.append(
            _restart_sync_does_not_duplicate_fill_check(
                restarted,
                scenario_dir,
                restart_cycle,
            )
        )

        failed = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        report = RuntimeFillSyncReport(
            as_of=now,
            status=RuntimePreflightStatus.FAILED
            if failed
            else RuntimePreflightStatus.PASSED,
            passed=failed == 0,
            output_dir=str(self.output_dir),
            checks=tuple(checks),
            incremental_fill_scenarios=sum(
                1
                for check in checks
                if check.status == RuntimePreflightStatus.PASSED
                and "incremental" in check.name
            ),
            duplicate_fill_scenarios=sum(
                1
                for check in checks
                if check.status == RuntimePreflightStatus.PASSED
                and "duplicate" in check.name
            ),
            unexpected_fill_scenarios=failed,
            summary=_summary(failed, len(checks)),
        )
        if self.persist_report:
            markdown_path = write_fill_sync_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_fill_sync_report(report, markdown_path=markdown_path)
        return report


def render_fill_sync_text(report: RuntimeFillSyncReport) -> str:
    """Render compact fill-sync audit status."""

    lines = [
        f"Fill sync status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        f"Incremental fill scenarios: {report.incremental_fill_scenarios}",
        f"Duplicate fill scenarios: {report.duplicate_fill_scenarios}",
        f"Unexpected fill scenarios: {report.unexpected_fill_scenarios}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_fill_sync_markdown(report: RuntimeFillSyncReport) -> str:
    """Render fill-sync audit Markdown."""

    lines = [
        "# Paper Runtime Fill Sync Audit",
        "",
        "> Paper trading only. This audit proves broker fill deltas update the "
        "internal ledger exactly once.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Incremental fill scenarios: `{report.incremental_fill_scenarios}`",
        f"- Duplicate fill scenarios: `{report.duplicate_fill_scenarios}`",
        f"- Unexpected fill scenarios: `{report.unexpected_fill_scenarios}`",
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


def write_fill_sync_markdown_report(
    report: RuntimeFillSyncReport,
    reports_dir: Path | str,
) -> Path:
    """Write fill-sync Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"fill-sync-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_fill_sync_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run deterministic paper fill-sync audit."""

    parser = argparse.ArgumentParser(description="Audit paper runtime fill sync.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeFillSyncAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(report.model_dump_json() if args.json else render_fill_sync_text(report))
    return 0 if report.passed else 1


def _runtime(
    output_dir: Path,
    *,
    broker: InMemoryPaperBrokerAdapter | None = None,
    persistence_store: RuntimePersistenceStore | None = None,
) -> AlwaysOnPaperRuntime:
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(SYMBOLS),
            tradable_symbols=frozenset(SYMBOLS),
        )
    )
    service = PaperTradingService(
        broker=broker or InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000")),
        starting_cash=Decimal("10000"),
        risk_engine=risk_engine,
    )
    return AlwaysOnPaperRuntime(
        service=service,
        latest_price_fetcher=FixtureLatestPriceFetcher(
            {"AAA": Decimal("100"), "SPY": Decimal("500")},
            observed_at=SYNC_TIME,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="fill-sync-audit"),
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
        persistence_store=persistence_store or RuntimePersistenceStore(output_dir),
    )


def _submit_manual_order(runtime: AlwaysOnPaperRuntime) -> Order:
    order = Order(
        id=ORDER_ID,
        symbol="AAA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("2"),
        created_at=SYNC_TIME,
    )
    runtime.service.submit_order(
        order,
        strategy_id="fill-sync-audit",
        estimated_price=Decimal("100"),
        latest_prices={"AAA": Decimal("100")},
        as_of=SYNC_TIME,
    )
    return order


def _partial_fill_applied_once_check(
    runtime: AlwaysOnPaperRuntime,
    output_dir: Path,
    cycle,
) -> RuntimeFillSyncCheck:
    fills = _raw_fills(output_dir)
    position = runtime.service.ledger.get_position("AAA")
    passed = (
        cycle.fills_applied == 1
        and runtime.service.ledger.filled_quantity(ORDER_ID) == Decimal("1")
        and len(runtime.service.fills) == 1
        and len(fills) == 1
        and len({fill.id for fill in fills}) == 1
        and position is not None
        and position.quantity == Decimal("1")
    )
    return _fill_check(
        "first_incremental_fill_applies_once",
        passed,
        "First broker fill delta updated the ledger once.",
        "First broker fill delta was missing or duplicated.",
        (
            f"fills_applied={cycle.fills_applied}",
            f"ledger_filled={runtime.service.ledger.filled_quantity(ORDER_ID)}",
            f"service_fills={len(runtime.service.fills)}",
            f"journal_fills={len(fills)}",
            f"position_quantity={position.quantity if position else 'missing'}",
        ),
    )


def _repeat_sync_does_not_duplicate_fill_check(
    runtime: AlwaysOnPaperRuntime,
    output_dir: Path,
    cycle,
) -> RuntimeFillSyncCheck:
    fills = _raw_fills(output_dir)
    passed = (
        cycle.fills_applied == 0
        and runtime.service.ledger.filled_quantity(ORDER_ID) == Decimal("1")
        and len(runtime.service.fills) == 1
        and len(fills) == 1
        and len({fill.id for fill in fills}) == 1
    )
    return _fill_check(
        "repeat_sync_does_not_duplicate_fill",
        passed,
        "Repeat broker sync created no duplicate fill.",
        "Repeat broker sync duplicated a fill.",
        (
            f"fills_applied={cycle.fills_applied}",
            f"ledger_filled={runtime.service.ledger.filled_quantity(ORDER_ID)}",
            f"service_fills={len(runtime.service.fills)}",
            f"journal_fills={len(fills)}",
        ),
    )


def _second_incremental_fill_applied_once_check(
    runtime: AlwaysOnPaperRuntime,
    output_dir: Path,
    cycle,
) -> RuntimeFillSyncCheck:
    fills = _raw_fills(output_dir)
    position = runtime.service.ledger.get_position("AAA")
    order = runtime.service.ledger.get_order(ORDER_ID)
    passed = (
        cycle.fills_applied == 1
        and runtime.service.ledger.filled_quantity(ORDER_ID) == Decimal("2")
        and len(runtime.service.fills) == 2
        and len(fills) == 2
        and len({fill.id for fill in fills}) == 2
        and position is not None
        and position.quantity == Decimal("2")
        and order is not None
        and order.status == OrderStatus.FILLED
    )
    return _fill_check(
        "second_incremental_fill_applies_once",
        passed,
        "Second broker fill delta updated only the remaining quantity.",
        "Second broker fill delta was missing or duplicated.",
        (
            f"fills_applied={cycle.fills_applied}",
            f"ledger_filled={runtime.service.ledger.filled_quantity(ORDER_ID)}",
            f"service_fills={len(runtime.service.fills)}",
            f"journal_fills={len(fills)}",
            f"position_quantity={position.quantity if position else 'missing'}",
            f"order_status={order.status.value if order else 'missing'}",
        ),
    )


def _restart_sync_does_not_duplicate_fill_check(
    runtime: AlwaysOnPaperRuntime,
    output_dir: Path,
    cycle,
) -> RuntimeFillSyncCheck:
    fills = _raw_fills(output_dir)
    passed = (
        cycle.fills_applied == 0
        and runtime.service.ledger.filled_quantity(ORDER_ID) == Decimal("2")
        and len(runtime.service.fills) == 2
        and len(fills) == 2
        and len({fill.id for fill in fills}) == 2
    )
    return _fill_check(
        "restart_sync_does_not_duplicate_fill",
        passed,
        "Restarted runtime recovered filled quantity and created no duplicate fill.",
        "Restarted runtime duplicated recovered fills.",
        (
            f"fills_applied={cycle.fills_applied}",
            f"ledger_filled={runtime.service.ledger.filled_quantity(ORDER_ID)}",
            f"service_fills={len(runtime.service.fills)}",
            f"journal_fills={len(fills)}",
        ),
    )


def _raw_fills(output_dir: Path) -> tuple[Fill, ...]:
    path = output_dir / "journal" / "fills.jsonl"
    if not path.exists():
        return ()
    return tuple(
        Fill.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _fill_check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...],
) -> RuntimeFillSyncCheck:
    return RuntimeFillSyncCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _summary(failures: int, total: int) -> str:
    if failures:
        return (
            f"Fill-sync audit failed {failures}/{total} scenario(s); do not trust "
            "broker fill ingestion until fixed."
        )
    return f"All {total} fill-sync scenarios preserved exactly-once ledger updates."


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
