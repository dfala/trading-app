from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from trading_app.broker import AlpacaPaperBrokerAdapter, InMemoryPaperBrokerAdapter
from trading_app.market_data.historical import FixtureHistoricalBarFetcher
from trading_app.paper import (
    MarketDataRefreshStatus,
    PaperSessionMode,
    PaperSessionRunner,
    PaperTradingService,
    SessionConnectionStatus,
    build_alpaca_paper_session_from_env,
)
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.schemas import DataFeed, Order, OrderSide, OrderStatus, OrderType

NOW = datetime(2026, 5, 29, 16, tzinfo=UTC)


def make_order(order_id: str = "paper-order-1") -> Order:
    return Order(
        id=order_id,
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("2"),
        created_at=NOW,
    )


def make_service() -> PaperTradingService:
    return PaperTradingService(
        broker=InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000")),
        starting_cash=Decimal("10000"),
        risk_engine=RiskEngine(
            RiskConfig(
                us_tradable_universe=frozenset({"SPY", "XLK"}),
                tradable_symbols=frozenset({"SPY", "XLK"}),
            )
        ),
    )


def test_paper_service_cancels_open_order_through_broker_and_ledger() -> None:
    service = make_service()
    service.submit_order(
        make_order(),
        strategy_id="sector_momentum",
        estimated_price=Decimal("100"),
        latest_prices={"SPY": Decimal("100")},
        as_of=NOW,
    )

    status = service.cancel_order("paper-order-1", canceled_at=NOW)

    assert status.status == OrderStatus.CANCELED
    assert service.ledger.get_order("paper-order-1").status == OrderStatus.CANCELED
    assert service.broker.list_orders(OrderStatus.CANCELED)[0].client_order_id == (
        "paper-order-1"
    )


def test_paper_session_runner_refreshes_market_data_and_portfolio_state() -> None:
    service = make_service()
    service.submit_order(
        make_order(),
        strategy_id="sector_momentum",
        estimated_price=Decimal("100"),
        latest_prices={"SPY": Decimal("100")},
        as_of=NOW,
    )
    event = service.broker.fill_order(
        "paper-order-1",
        price=Decimal("100"),
        filled_at=NOW,
    )
    service.ingest_fill_event(event)
    runner = PaperSessionRunner(
        service=service,
        symbols=("SPY", "XLK"),
        mode=PaperSessionMode.DEMO,
        market_data_fetcher=FixtureHistoricalBarFetcher(source="session-test"),
        feed=DataFeed.IEX,
    )

    state = runner.poll_once(as_of=NOW)

    assert state.connection_status == SessionConnectionStatus.CONNECTED
    assert state.mode == PaperSessionMode.DEMO
    assert state.market_data.status == MarketDataRefreshStatus.FRESH
    assert set(state.market_data.prices) == {"SPY", "XLK"}
    assert state.portfolio_report.reconciliation.reconciled
    assert state.open_order_count == 0
    assert state.market_data.warning is not None


def test_alpaca_paper_session_factory_rejects_blank_env_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", " ")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "\n")

    with pytest.raises(ValueError, match="ALPACA_API_KEY"):
        build_alpaca_paper_session_from_env(symbols=("SPY",))


def test_alpaca_adapter_lists_and_cancels_open_paper_orders() -> None:
    client = FakeAlpacaClient()
    adapter = AlpacaPaperBrokerAdapter(client=client)

    orders = adapter.list_orders(OrderStatus.NEW)
    canceled = adapter.cancel_order("alpaca-order-1")

    assert client.last_order_request.status.value == "open"
    assert orders[0].broker_order_id == "alpaca-order-1"
    assert client.canceled_order_id == "alpaca-order-1"
    assert canceled.status == OrderStatus.CANCELED


def test_alpaca_adapter_passes_order_history_window_to_sdk() -> None:
    client = FakeAlpacaClient()
    adapter = AlpacaPaperBrokerAdapter(client=client)

    adapter.list_orders(
        after=NOW,
        until=NOW,
        symbols=("SPY",),
        limit=25,
    )

    assert client.last_order_request.status.value == "all"
    assert client.last_order_request.after == NOW
    assert client.last_order_request.until == NOW
    assert client.last_order_request.symbols == ["SPY"]
    assert client.last_order_request.limit == 25


class FakeAlpacaClient:
    def __init__(self) -> None:
        self.last_order_request = None
        self.canceled_order_id = None
        self._status = "new"

    def get_orders(self, filter):
        self.last_order_request = filter
        return [self._order(status=self._status)]

    def cancel_order_by_id(self, order_id: str):
        self.canceled_order_id = order_id
        self._status = "canceled"

    def get_order_by_id(self, order_id: str):
        return self._order(status=self._status, order_id=order_id)

    def _order(self, *, status: str, order_id: str = "alpaca-order-1"):
        return SimpleNamespace(
            id=order_id,
            client_order_id="paper-order-1",
            symbol="SPY",
            side="buy",
            type="market",
            qty="2",
            filled_qty="0",
            status=status,
            submitted_at=NOW,
            updated_at=NOW,
            limit_price=None,
            filled_avg_price=None,
        )
