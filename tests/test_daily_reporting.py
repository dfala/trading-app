from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.market_data import MarketDataQualityChecker
from trading_app.paper import PaperTaxLotMethod, PaperTradingService
from trading_app.reporting import (
    DailyReportGenerator,
    ReportSeverity,
    render_markdown,
    write_markdown_report,
)
from trading_app.risk import RiskConfig, RiskEngine, RiskRule
from trading_app.schemas import (
    DailyBar,
    DataFeed,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading_app.strategies import StrategyAuthority
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

NOW = datetime(2026, 5, 29, 16, tzinfo=UTC)


def make_order(order_id: str, quantity: Decimal = Decimal("5")) -> Order:
    return Order(
        id=order_id,
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_at=NOW,
    )


def populated_service() -> PaperTradingService:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(
        broker=broker,
        starting_cash=Decimal("10000"),
        risk_engine=RiskEngine(
            RiskConfig(
                us_tradable_universe=frozenset({"SPY"}),
                tradable_symbols=frozenset({"SPY"}),
                max_orders_per_day=1,
            )
        ),
    )
    first_order = make_order("daily-order-1")
    service.submit_order(
        first_order,
        strategy_id="sector_momentum",
        estimated_price=Decimal("500"),
        latest_prices={"SPY": Decimal("500")},
        as_of=NOW,
    )
    service.ingest_fill_event(
        broker.fill_order(
            first_order.id,
            price=Decimal("500"),
            commission=Decimal("1"),
            filled_at=NOW,
        )
    )
    service.submit_order(
        make_order("daily-order-2", Decimal("1")),
        strategy_id="sector_momentum",
        estimated_price=Decimal("505"),
        latest_prices={"SPY": Decimal("505")},
        as_of=NOW,
    )
    return service


def active_strategy_definition():
    return MonthlySectorMomentumStrategy().definition(authority=StrategyAuthority.PAPER)


def test_daily_report_contains_model_pnl_risk_and_rejections() -> None:
    service = populated_service()
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
        markdown_path="/tmp/daily-report-2026-05-29.md",
        active_strategy_definition=active_strategy_definition(),
    )

    assert daily_report.report_metadata is not None
    assert daily_report.report_metadata.markdown_path == (
        "/tmp/daily-report-2026-05-29.md"
    )
    assert "broker_fills" in daily_report.report_metadata.evidence_sources
    assert "active_strategy_definition" in (
        daily_report.report_metadata.evidence_sources
    )
    assert daily_report.active_strategy_definition is not None
    assert daily_report.active_strategy_definition.strategy_id == (
        "monthly_sector_momentum"
    )
    assert daily_report.trading_day == NOW.date()
    assert daily_report.model_reports[0].strategy_id == "sector_momentum"
    assert daily_report.model_reports[0].submitted_orders == 2
    assert daily_report.model_reports[0].accepted_orders == 1
    assert daily_report.model_reports[0].rejected_orders == 1
    assert daily_report.model_reports[0].filled_orders == 1
    assert daily_report.pnl_report.ending_cash == Decimal("7499")
    assert daily_report.pnl_report.estimated_equity == Decimal("9999")
    assert daily_report.pnl_report.total_fees == Decimal("1")
    assert daily_report.risk_report.severity == ReportSeverity.ATTENTION
    assert daily_report.risk_report.rejection_rules == (RiskRule.MAX_ORDERS_PER_DAY,)
    assert daily_report.tax_report.active_lot_count == 1
    assert daily_report.tax_report.realized_lot_count == 0
    assert daily_report.tax_report.lot_method == PaperTaxLotMethod.FIFO
    assert daily_report.tax_report.total_realized_gains == Decimal("0")
    assert daily_report.fill_report[0].fill_id
    assert daily_report.fill_report[0].order_id == "daily-order-1"
    assert daily_report.benchmark_report is not None
    assert not daily_report.benchmark_report.comparison_available
    assert daily_report.rejected_signal_report.rejected_signals[0].order_id == (
        "daily-order-2"
    )
    assert daily_report.rejected_signal_report.rejected_signals[0].rule == (
        RiskRule.MAX_ORDERS_PER_DAY
    )
    assert "Active model is monthly_sector_momentum:1.0.0" in (
        daily_report.ai_summary.summary
    )
    assert "active_strategy_definition" in daily_report.ai_summary.evidence
    assert "active_model:monthly_sector_momentum:1.0.0" in (
        daily_report.ai_summary.evidence
    )


def test_trade_explanations_are_human_readable_and_grounded() -> None:
    service = populated_service()
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
    )

    first, second = daily_report.trade_explanations

    assert first.order_id == "daily-order-1"
    assert first.status == OrderStatus.FILLED
    assert first.accepted
    assert "Risk approved" in first.explanation
    assert "order:daily-order-1" in first.evidence
    assert first.fill_ids
    assert "ledger:fill_applied" in first.ledger_trace
    assert "strategy target sizing" in first.signal_rationale
    assert second.order_id == "daily-order-2"
    assert second.status == OrderStatus.REJECTED
    assert not second.accepted
    assert "MAX_ORDERS_PER_DAY" in second.explanation
    assert "order:daily-order-2" in second.evidence
    assert "ledger:not_recorded" in second.ledger_trace


def test_daily_report_records_operator_actions_runtime_events_and_learning() -> None:
    service = populated_service()
    operator_action = SimpleNamespace(
        request=SimpleNamespace(
            action=SimpleNamespace(value="pause_runtime"),
            requested_at=NOW,
            requested_by="operator",
            reason="review fills",
        ),
        status=SimpleNamespace(value="accepted"),
        message="Paper trading is paused; monitoring remains active.",
    )
    runtime_event = SimpleNamespace(
        timestamp=NOW,
        severity=SimpleNamespace(value="warning"),
        category="market_data",
        message="Latest prices are stale.",
        evidence=("SPY",),
    )
    learning = SimpleNamespace(
        active_model_unchanged=True,
        research_memo="Candidate needs more evidence.",
        recommendations=(
            SimpleNamespace(
                action=SimpleNamespace(value="watch"),
                model=SimpleNamespace(key="sector_momentum:1.1.0"),
                manual_review_required=True,
                rationale="Insufficient excess return.",
                evidence=("walk_forward",),
            ),
        ),
    )

    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
        operator_actions=(operator_action,),
        runtime_events=(runtime_event,),
        nightly_learning=learning,
    )

    assert daily_report.operator_actions[0].action == "pause_runtime"
    assert daily_report.runtime_events[0].category == "market_data"
    assert daily_report.learning_report is not None
    assert daily_report.learning_report.active_model_unchanged
    assert daily_report.learning_report.recommendations[0].model_key == (
        "sector_momentum:1.1.0"
    )
    assert "operator_actions" in daily_report.report_metadata.evidence_sources
    assert "runtime_events" in daily_report.report_metadata.evidence_sources
    assert "nightly_learning" in daily_report.report_metadata.evidence_sources
    assert "operator action" in daily_report.ai_summary.summary
    assert "learning_recommendation:sector_momentum:1.1.0:watch" in (
        daily_report.ai_summary.evidence
    )


def test_ai_governance_summary_uses_only_report_evidence() -> None:
    service = populated_service()
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
    )

    assert "2 paper order(s)" in daily_report.ai_summary.summary
    assert "1 accepted and 1 rejected" in daily_report.ai_summary.summary
    assert "1 broker fill(s)" in daily_report.ai_summary.summary
    assert "order:daily-order-1" in daily_report.ai_summary.evidence
    assert "order:daily-order-2" in daily_report.ai_summary.evidence
    assert any(item.startswith("fill:") for item in daily_report.ai_summary.evidence)
    assert not any("imaginary" in item for item in daily_report.ai_summary.evidence)
    assert daily_report.ai_summary.prohibited_actions == (
        "Do not invent trades that are absent from trade_explanations.",
        "Do not recommend live-money action from a paper daily report.",
        "Do not override risk decisions or reconciliation issues.",
        "Do not promote or mutate the active model from a daily report.",
    )


def test_markdown_report_is_reviewable() -> None:
    service = populated_service()
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
        active_strategy_definition=active_strategy_definition(),
    )

    markdown = render_markdown(daily_report)

    assert "# Daily Trading Report - 2026-05-29" in markdown
    assert "## Report Metadata" in markdown
    assert "## AI Governance Summary" in markdown
    assert "## Model Activity" in markdown
    assert "## Active Model Dossier" in markdown
    assert "- Model: Monthly Sector ETF Momentum" in markdown
    assert "- Authority: paper" in markdown
    assert "- Signal logic: Rank symbols by trailing adjusted" in markdown
    assert "- Known failure modes: Momentum reversals" in markdown
    assert "- AI role: Explain rank changes" in markdown
    assert "## P&L" in markdown
    assert "## Benchmark" in markdown
    assert "## Risk" in markdown
    assert "## Reconciliation Details" in markdown
    assert "No reconciliation issues were detected." in markdown
    assert "## Tax Estimate" in markdown
    assert "Lot method: FIFO" in markdown
    assert "Estimated tax: unavailable" in markdown
    assert "## Data Quality" in markdown
    assert "## Rejected Signals" in markdown
    assert "## Fills" in markdown
    assert "## Operator Actions" in markdown
    assert "## Runtime Events" in markdown
    assert "## Learning Recommendations" in markdown
    assert "daily-order-2 SPY: MAX_ORDERS_PER_DAY" in markdown
    assert "ledger:fill_applied" in markdown
    assert "Evidence: order:daily-order-1" in markdown


def test_markdown_report_lists_reconciliation_issue_details() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(broker=broker, starting_cash=Decimal("10000"))
    external_order = make_order("external-paper-order", Decimal("1"))
    broker.submit_order(external_order)
    broker.fill_order(
        external_order.id,
        price=Decimal("100"),
        filled_at=NOW,
    )
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
    )

    markdown = render_markdown(daily_report)

    assert not daily_report.reconciliation.reconciled
    assert "UNKNOWN_BROKER_ORDER" in markdown
    assert "paper-order-1 / external-paper-order (filled)" in markdown
    assert "Broker reports filled quantity" in markdown


def test_daily_report_can_include_data_quality_evidence() -> None:
    service = populated_service()
    data_quality_report = MarketDataQualityChecker().assess_latest_prices(
        None,
        symbols=("SPY",),
        generated_at=NOW,
    )
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
        data_quality_report=data_quality_report,
    )
    markdown = render_markdown(daily_report)

    assert daily_report.data_quality_report == data_quality_report
    assert "Data quality status is failed" in daily_report.ai_summary.summary
    assert "data_quality_report" in daily_report.ai_summary.evidence
    assert "- Status: failed" in markdown
    assert "- Feeds: -" in markdown
    assert "- Ingested window: -" in markdown


def test_daily_report_lists_daily_bar_ingestion_window() -> None:
    service = populated_service()
    bar = DailyBar(
        symbol="SPY",
        trading_date=date(2026, 5, 29),
        bar_at=datetime(2026, 5, 29, 21, tzinfo=UTC),
        ingested_at=NOW,
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100"),
        volume=Decimal("1000000"),
        source="daily-report-test",
        data_feed=DataFeed.SIP,
    )
    data_quality_report = MarketDataQualityChecker().assess_daily_bars(
        (bar,),
        symbols=("SPY",),
        start=bar.trading_date,
        end=bar.trading_date,
        generated_at=NOW,
        expected_feed=DataFeed.SIP,
    )
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
        data_quality_report=data_quality_report,
    )

    markdown = render_markdown(daily_report)

    assert f"- Ingested window: {NOW.isoformat()}" in markdown


def test_markdown_report_can_be_written_for_review(tmp_path) -> None:
    service = populated_service()
    daily_report = DailyReportGenerator().build(
        service.portfolio_report(as_of=NOW),
        generated_at=NOW,
    )

    report_path = write_markdown_report(daily_report, tmp_path)

    assert report_path.name == "daily-report-2026-05-29.md"
    assert report_path.read_text(encoding="utf-8").startswith(
        "# Daily Trading Report - 2026-05-29"
    )
