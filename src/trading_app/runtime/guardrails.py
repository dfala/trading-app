"""Deterministic order-guardrail audit for paper runtime safety."""

from __future__ import annotations

import argparse
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
    OperatorControlAction,
    RuntimeOrderGuardrailCheck,
    RuntimeOrderGuardrailReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.paper import AlwaysOnPaperRuntime, AlwaysOnPaperRuntimeConfig
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, Order, OrderSide, OrderType
from trading_app.strategies import MonthlySectorMomentumStrategy

SCENARIO_TIME = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
SYMBOLS = ("AAA", "SPY")


class RuntimeOrderGuardrailAuditor:
    """Prove paper order guardrails block unsafe order paths."""

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

    def audit(self, *, as_of: datetime | None = None) -> RuntimeOrderGuardrailReport:
        now = as_of or datetime.now(tz=UTC)
        checks = (
            _missing_latest_price_check(self.output_dir),
            _stale_latest_price_check(self.output_dir),
            _risk_rejection_check(self.output_dir),
            _dirty_reconciliation_check(self.output_dir),
            _paper_kill_switch_check(self.output_dir),
            _operator_pause_check(self.output_dir),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        report = RuntimeOrderGuardrailReport(
            as_of=now,
            status=RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.PASSED,
            passed=failures == 0,
            output_dir=str(self.output_dir),
            checks=checks,
            blocked_order_scenarios=len(checks) - failures,
            unexpected_order_scenarios=failures,
            summary=_summary(failures, len(checks)),
        )
        if self.persist_report:
            markdown_path = write_order_guardrail_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_order_guardrail_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_order_guardrail_text(report: RuntimeOrderGuardrailReport) -> str:
    """Render compact order-guardrail status."""

    lines = [
        f"Order guardrail status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        f"Blocked scenarios: {report.blocked_order_scenarios}",
        f"Unexpected order scenarios: {report.unexpected_order_scenarios}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_order_guardrail_markdown(report: RuntimeOrderGuardrailReport) -> str:
    """Render order-guardrail audit Markdown."""

    lines = [
        "# Paper Runtime Order Guardrail Audit",
        "",
        "> Paper trading only. This audit proves unsafe paper order paths block.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Blocked scenarios: `{report.blocked_order_scenarios}`",
        f"- Unexpected order scenarios: `{report.unexpected_order_scenarios}`",
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


def write_order_guardrail_markdown_report(
    report: RuntimeOrderGuardrailReport,
    reports_dir: Path | str,
) -> Path:
    """Write order-guardrail Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"order-guardrails-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_order_guardrail_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run deterministic paper order-guardrail audit."""

    parser = argparse.ArgumentParser(description="Audit paper order guardrails.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeOrderGuardrailAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json() if args.json else render_order_guardrail_text(report)
    )
    return 0 if report.passed else 1


def _missing_latest_price_check(output_dir: Path) -> RuntimeOrderGuardrailCheck:
    runtime = _runtime(
        output_dir / "guardrail-scenarios" / "missing-latest-price",
        missing_symbols=("AAA",),
    )
    cycle = runtime.run_once(as_of=SCENARIO_TIME)
    return _guardrail_check(
        "missing_latest_price_blocks_orders",
        cycle.orders_submitted == 0 and cycle.status.value in {"degraded", "blocked"},
        "Missing latest prices blocked scheduled paper orders.",
        "Missing latest prices did not block scheduled paper orders.",
        (
            f"orders_submitted={cycle.orders_submitted}",
            f"strategy_evaluated={cycle.strategy_evaluated}",
            f"status={cycle.status.value}",
        ),
    )


def _stale_latest_price_check(output_dir: Path) -> RuntimeOrderGuardrailCheck:
    runtime = _runtime(
        output_dir / "guardrail-scenarios" / "stale-latest-price",
        observed_at=SCENARIO_TIME - timedelta(hours=2),
    )
    cycle = runtime.run_once(as_of=SCENARIO_TIME)
    return _guardrail_check(
        "stale_latest_price_blocks_orders",
        cycle.orders_submitted == 0 and cycle.status.value in {"degraded", "blocked"},
        "Stale latest prices blocked scheduled paper orders.",
        "Stale latest prices did not block scheduled paper orders.",
        (
            f"orders_submitted={cycle.orders_submitted}",
            f"status={cycle.status.value}",
            f"events={len(cycle.events)}",
        ),
    )


def _risk_rejection_check(output_dir: Path) -> RuntimeOrderGuardrailCheck:
    runtime = _runtime(
        output_dir / "guardrail-scenarios" / "risk-rejection",
        risk_config=RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(SYMBOLS),
            tradable_symbols=frozenset(SYMBOLS),
            blocked_symbols=frozenset({"AAA"}),
        ),
    )
    cycle = runtime.run_once(as_of=SCENARIO_TIME)
    rejected = tuple(
        submission
        for submission in runtime.service.submissions
        if not submission.accepted
    )
    return _guardrail_check(
        "risk_rejection_blocks_orders",
        cycle.orders_submitted == 0 and bool(rejected),
        "Risk rejection blocked broker paper submission.",
        "Risk rejection did not block broker paper submission.",
        (
            f"orders_submitted={cycle.orders_submitted}",
            f"rejected_submissions={len(rejected)}",
            f"broker_submissions={len(runtime.service.broker.submitted_orders)}",
        ),
    )


def _dirty_reconciliation_check(output_dir: Path) -> RuntimeOrderGuardrailCheck:
    runtime = _runtime(output_dir / "guardrail-scenarios" / "dirty-reconciliation")
    external_order = Order(
        id="external-broker-order",
        symbol="AAA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=SCENARIO_TIME,
    )
    runtime.service.broker.submit_order(external_order)
    runtime.service.broker.fill_order(
        "external-broker-order",
        price=Decimal("100"),
        filled_at=SCENARIO_TIME,
    )
    cycle = runtime.run_once(as_of=SCENARIO_TIME)
    report = runtime.service.portfolio_report(as_of=SCENARIO_TIME)
    return _guardrail_check(
        "dirty_reconciliation_blocks_orders",
        cycle.orders_submitted == 0 and not report.reconciliation.reconciled,
        "Dirty reconciliation blocked scheduled paper orders.",
        "Dirty reconciliation did not block scheduled paper orders.",
        (
            f"orders_submitted={cycle.orders_submitted}",
            f"reconciled={report.reconciliation.reconciled}",
            f"issues={len(report.reconciliation.issues)}",
        ),
    )


def _paper_kill_switch_check(output_dir: Path) -> RuntimeOrderGuardrailCheck:
    runtime = _runtime(output_dir / "guardrail-scenarios" / "paper-kill-switch")
    runtime.apply_control(
        OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
        requested_at=SCENARIO_TIME,
        requested_by="guardrail-audit",
        reason="prove kill switch blocks paper orders",
    )
    cycle = runtime.run_once(as_of=SCENARIO_TIME)
    return _guardrail_check(
        "paper_kill_switch_blocks_orders",
        cycle.orders_submitted == 0,
        "Paper kill switch blocked scheduled paper orders.",
        "Paper kill switch did not block scheduled paper orders.",
        (
            f"orders_submitted={cycle.orders_submitted}",
            f"paper_kill_switch={runtime.control_center.state.paper_kill_switch_enabled}",
        ),
    )


def _operator_pause_check(output_dir: Path) -> RuntimeOrderGuardrailCheck:
    runtime = _runtime(output_dir / "guardrail-scenarios" / "operator-pause")
    runtime.apply_control(
        OperatorControlAction.PAUSE_RUNTIME,
        requested_at=SCENARIO_TIME,
        requested_by="guardrail-audit",
        reason="prove pause blocks scheduled paper orders",
    )
    cycle = runtime.run_once(as_of=SCENARIO_TIME)
    return _guardrail_check(
        "operator_pause_blocks_orders",
        cycle.orders_submitted == 0,
        "Operator pause blocked scheduled paper orders.",
        "Operator pause did not block scheduled paper orders.",
        (
            f"orders_submitted={cycle.orders_submitted}",
            f"paused={runtime.control_center.state.paused}",
        ),
    )


def _runtime(
    output_dir: Path,
    *,
    observed_at: datetime = SCENARIO_TIME,
    missing_symbols: tuple[str, ...] = (),
    risk_config: RiskConfig | None = None,
) -> AlwaysOnPaperRuntime:
    config = risk_config or RiskConfig(
        enforce_market_hours=False,
        us_tradable_universe=frozenset(SYMBOLS),
        tradable_symbols=frozenset(SYMBOLS),
    )
    risk_engine = RiskEngine(config)
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
            observed_at=observed_at,
            missing_symbols=missing_symbols,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="guardrail-audit"),
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


def _guardrail_check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...],
) -> RuntimeOrderGuardrailCheck:
    return RuntimeOrderGuardrailCheck(
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
            f"Order guardrail audit failed {failures}/{total} scenario(s); "
            "do not allow scheduled paper orders until fixed."
        )
    return f"All {total} paper order guardrail scenarios blocked as expected."


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
