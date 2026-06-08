from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.live.readiness import LIVE_RISK_CONFIRMATION
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.runtime import (
    LIVE_SANDBOX_ALLOWED_SYMBOLS,
    LIVE_SANDBOX_ORDER_PREFIX,
    LiveSandboxConfig,
    LiveSandboxRuntime,
    LiveSandboxStatus,
    live_sandbox_service,
)
from trading_app.runtime.live_sandbox import LiveSandboxControlAction
from trading_app.schemas import Order, OrderSide, OrderStatus, OrderType

MARKET_HOURS = datetime(2026, 6, 2, 14, 0, tzinfo=UTC)


def test_live_sandbox_defaults_to_disabled_with_kill_switch_on() -> None:
    runtime = LiveSandboxRuntime.disabled()

    snapshot = runtime.snapshot(as_of=MARKET_HOURS)

    assert snapshot.status == LiveSandboxStatus.DISABLED
    assert not snapshot.enabled
    assert not snapshot.control_state.live_autonomy_enabled
    assert snapshot.control_state.live_kill_switch_enabled
    assert "disabled" in " ".join(snapshot.blocked_reasons)


def test_live_sandbox_arms_and_submits_tagged_orders_under_cap() -> None:
    runtime, broker = make_live_sandbox_runtime()
    result = runtime.apply_control(
        LiveSandboxControlAction.ENABLE_LIVE_AUTONOMY,
        requested_at=MARKET_HOURS,
    )

    cycle = runtime.run_once(
        as_of=MARKET_HOURS,
        latest_prices=latest_prices(MARKET_HOURS),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="live-test"),
    )

    assert result.accepted
    assert cycle.status == LiveSandboxStatus.RUNNING
    assert cycle.orders_submitted == 2
    assert sum(intent.estimated_notional for intent in cycle.order_intents) <= Decimal(
        "100"
    )
    assert all(
        order.client_order_id.startswith(LIVE_SANDBOX_ORDER_PREFIX)
        for order in broker.submitted_orders
        if order.client_order_id
    )


def test_live_sandbox_open_tagged_order_blocks_duplicate_cycle() -> None:
    runtime, _ = make_live_sandbox_runtime()
    runtime.apply_control("enable_live_autonomy", requested_at=MARKET_HOURS)
    runtime.run_once(
        as_of=MARKET_HOURS,
        latest_prices=latest_prices(MARKET_HOURS),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="live-test"),
    )

    next_cycle = runtime.run_once(
        as_of=datetime(2026, 6, 2, 14, 1, tzinfo=UTC),
        latest_prices=latest_prices(datetime(2026, 6, 2, 14, 1, tzinfo=UTC)),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="live-test"),
    )

    assert next_cycle.status == LiveSandboxStatus.BLOCKED
    assert any("still open" in reason for reason in next_cycle.blocked_reasons)


def test_live_sandbox_kill_switch_cancels_tagged_open_orders() -> None:
    runtime, broker = make_live_sandbox_runtime()
    runtime.apply_control("enable_live_autonomy", requested_at=MARKET_HOURS)
    runtime.run_once(
        as_of=MARKET_HOURS,
        latest_prices=latest_prices(MARKET_HOURS),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="live-test"),
    )

    result = runtime.apply_control(
        "enable_live_kill_switch",
        requested_at=datetime(2026, 6, 2, 14, 2, tzinfo=UTC),
    )

    assert result.accepted
    assert result.canceled_order_ids
    assert runtime.control_state.live_kill_switch_enabled
    assert all(
        order.status == OrderStatus.CANCELED for order in broker.submitted_orders
    )


def test_live_sandbox_external_position_conflict_blocks_autonomy() -> None:
    runtime, broker = make_live_sandbox_runtime()
    broker.submit_order(
        Order(
            id="external-live-order",
            symbol="XLU",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            created_at=MARKET_HOURS,
        )
    )
    broker.fill_order(
        "external-live-order",
        price=Decimal("100"),
        filled_at=MARKET_HOURS,
    )
    runtime.apply_control("enable_live_autonomy", requested_at=MARKET_HOURS)

    cycle = runtime.run_once(
        as_of=datetime(2026, 6, 2, 14, 3, tzinfo=UTC),
        latest_prices=latest_prices(datetime(2026, 6, 2, 14, 3, tzinfo=UTC)),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="live-test"),
    )

    assert cycle.status == LiveSandboxStatus.BLOCKED
    assert any("External live position" in reason for reason in cycle.blocked_reasons)


def make_live_sandbox_runtime() -> tuple[
    LiveSandboxRuntime,
    InMemoryPaperBrokerAdapter,
]:
    config = LiveSandboxConfig(enabled=True, confirmation=LIVE_RISK_CONFIRMATION)
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("100"))
    service = live_sandbox_service(broker=broker, config=config)
    return LiveSandboxRuntime(config=config, service=service), broker


def latest_prices(as_of: datetime):
    return FixtureLatestPriceFetcher(
        {symbol: Decimal("100") for symbol in LIVE_SANDBOX_ALLOWED_SYMBOLS},
        observed_at=as_of,
        source="live-test",
    ).fetch_latest_prices(LIVE_SANDBOX_ALLOWED_SYMBOLS, as_of=as_of)
