from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.dashboard.server import dashboard_response
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime import (
    AlwaysOnPaperRuntime,
    AlwaysOnPaperRuntimeConfig,
    OperatorControlAction,
    OperatorControlRequest,
    RuntimeAlertCode,
    RuntimeAlertEngine,
    RuntimeControlCenter,
    RuntimePersistenceStore,
)
from trading_app.schemas import DataFeed, Order, OrderSide, OrderType
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)


def make_runtime(
    *,
    latest_observed_at: datetime = AFTER_CLOSE,
    output_dir=None,
) -> AlwaysOnPaperRuntime:
    symbols = ("AAA", "BBB", "SPY")
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(symbols),
            tradable_symbols=frozenset(symbols),
        )
    )
    service = PaperTradingService(
        broker=InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000")),
        starting_cash=Decimal("10000"),
        risk_engine=risk_engine,
    )
    return AlwaysOnPaperRuntime(
        service=service,
        latest_price_fetcher=FixtureLatestPriceFetcher(
            {"AAA": Decimal("100"), "BBB": Decimal("120"), "SPY": Decimal("500")},
            observed_at=latest_observed_at,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="operator-test"),
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"),
            lookback_days=5,
            top_n=1,
        ),
        risk_engine=risk_engine,
        config=AlwaysOnPaperRuntimeConfig(
            symbols=symbols,
            output_dir=output_dir or AlwaysOnPaperRuntimeConfig().output_dir,
            feed=DataFeed.IEX,
        ),
    )


def test_control_center_applies_pause_resume_and_paper_kill_switch() -> None:
    center = RuntimeControlCenter()

    paused = center.apply(
        OperatorControlRequest(
            action=OperatorControlAction.PAUSE_RUNTIME,
            requested_at=AFTER_CLOSE,
            requested_by="test",
        )
    )
    kill_on = center.apply(
        OperatorControlRequest(
            action=OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
            requested_at=AFTER_CLOSE,
            requested_by="test",
        )
    )
    resumed = center.apply(
        OperatorControlRequest(
            action=OperatorControlAction.RESUME_RUNTIME,
            requested_at=AFTER_CLOSE,
            requested_by="test",
        )
    )

    assert paused.control_state.paused
    assert kill_on.control_state.paper_kill_switch_enabled
    assert not resumed.control_state.paused
    assert center.state.paper_kill_switch_enabled
    assert len(center.history) == 3


def test_paused_runtime_blocks_scheduled_orders_but_keeps_monitoring(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.apply_control(
        OperatorControlAction.PAUSE_RUNTIME,
        requested_at=AFTER_CLOSE,
        requested_by="test",
    )

    cycle = runtime.run_once(as_of=AFTER_CLOSE)

    assert cycle.prices_refreshed
    assert cycle.broker_synced
    assert not cycle.strategy_evaluated
    assert cycle.orders_submitted == 0
    assert not runtime.service.submissions
    assert RuntimeAlertCode.OPERATOR_PAUSED in {alert.code for alert in cycle.alerts}


def test_paper_kill_switch_blocks_then_allows_scheduled_orders(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.apply_control(
        OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
        requested_at=AFTER_CLOSE,
        requested_by="test",
    )

    blocked = runtime.run_once(as_of=AFTER_CLOSE)
    runtime.apply_control(
        OperatorControlAction.DISABLE_PAPER_KILL_SWITCH,
        requested_at=AFTER_CLOSE + timedelta(minutes=1),
        requested_by="test",
    )
    resumed = runtime.run_once(as_of=AFTER_CLOSE + timedelta(minutes=5))

    assert blocked.orders_submitted == 0
    assert RuntimeAlertCode.PAPER_KILL_SWITCH_ENABLED in {
        alert.code for alert in blocked.alerts
    }
    assert resumed.strategy_evaluated
    assert resumed.orders_submitted == 1


def test_force_reconciliation_and_generate_report_controls_persist(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)

    runtime.apply_control(
        OperatorControlAction.FORCE_RECONCILIATION,
        requested_at=AFTER_CLOSE,
        requested_by="test",
    )
    runtime.apply_control(
        OperatorControlAction.GENERATE_REPORT,
        requested_at=AFTER_CLOSE,
        requested_by="test",
    )
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert len(recovered.control_results) == 2
    assert recovered.control_state is not None
    assert recovered.daily_report is not None
    assert recovered.daily_report_path is not None
    assert recovered.daily_report_path.exists()
    assert recovered.daily_report.report_metadata is not None
    assert recovered.daily_report.report_metadata.markdown_path == str(
        recovered.daily_report_path
    )
    assert [action.action for action in recovered.daily_report.operator_actions] == [
        "force_reconciliation",
        "generate_report",
    ]
    assert (tmp_path / "state" / "latest-reconciliation.json").exists()


def test_alert_engine_flags_data_risk_and_reconciliation_problems(tmp_path) -> None:
    runtime = make_runtime(
        latest_observed_at=AFTER_CLOSE - timedelta(hours=2),
        output_dir=tmp_path,
    )
    stale_cycle = runtime.run_once(as_of=AFTER_CLOSE)

    rejected_order = Order(
        id="bad-symbol-order",
        symbol="ZZZ",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=AFTER_CLOSE,
    )
    runtime.service.submit_order(
        rejected_order,
        strategy_id="manual",
        estimated_price=Decimal("10"),
        latest_prices={"ZZZ": Decimal("10")},
        as_of=AFTER_CLOSE,
    )
    runtime.service.broker._cash = Decimal("9999")
    alerts = RuntimeAlertEngine().evaluate(runtime.snapshot(as_of=AFTER_CLOSE))
    codes = {alert.code for alert in (*stale_cycle.alerts, *alerts)}

    assert RuntimeAlertCode.MARKET_DATA_STALE in codes
    assert RuntimeAlertCode.RISK_REJECTION in codes
    assert RuntimeAlertCode.RECONCILIATION_BREAK in codes


def test_dashboard_control_route_accepts_actions_and_reports_errors() -> None:
    center = RuntimeControlCenter()

    accepted_status, accepted_type, accepted_body = dashboard_response(
        "/api/control",
        method="POST",
        body=json.dumps({"action": "pause_runtime", "requested_by": "test"}),
        control_handler=center.apply,
    )
    unavailable_status, _, unavailable_body = dashboard_response(
        "/api/control",
        method="POST",
        body=json.dumps({"action": "pause_runtime"}),
    )
    invalid_status, _, invalid_body = dashboard_response(
        "/api/control",
        method="POST",
        body=json.dumps({"action": "unknown"}),
        control_handler=center.apply,
    )

    assert accepted_status.value == 200
    assert accepted_type.startswith("application/json")
    assert json.loads(accepted_body)["control_state"]["paused"]
    assert unavailable_status.value == 503
    assert "unavailable" in unavailable_body
    assert invalid_status.value == 400
    assert "unknown" in invalid_body
