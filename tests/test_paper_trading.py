from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from trading_app.broker import (
    AlpacaPaperBrokerAdapter,
    BrokerOrderState,
    BrokerPortfolioState,
    BrokerPositionState,
    BrokerStatementSnapshot,
    InMemoryPaperBrokerAdapter,
    ReconciliationIssueType,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine, RiskRule
from trading_app.schemas import Order, OrderSide, OrderStatus, OrderType

NOW = datetime(2026, 5, 29, 16, tzinfo=UTC)


def make_order(
    order_id: str = "paper-order-1",
    *,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("5"),
) -> Order:
    return Order(
        id=order_id,
        symbol="SPY",
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_at=NOW,
    )


def test_alpaca_adapter_submits_market_order_and_maps_response() -> None:
    client = FakeAlpacaClient()
    adapter = AlpacaPaperBrokerAdapter(client=client)

    state = adapter.submit_order(make_order())

    assert client.submitted_order_data is not None
    assert client.submitted_order_data.symbol == "SPY"
    assert client.submitted_order_data.client_order_id == "paper-order-1"
    assert client.submitted_order_data.qty == 5.0
    assert client.submitted_order_data.type.value == "market"
    assert state.broker_order_id == "alpaca-order-1"
    assert state.client_order_id == "paper-order-1"
    assert state.status == OrderStatus.NEW
    assert state.provider == "alpaca-paper"
    portfolio = adapter.get_portfolio(NOW)
    assert portfolio.cash == Decimal("10000")
    assert portfolio.positions[0].symbol == "SPY"
    assert portfolio.positions[0].quantity == Decimal("2")


def test_alpaca_adapter_validates_order_history_symbol_filters() -> None:
    client = FakeAlpacaClient()
    adapter = AlpacaPaperBrokerAdapter(client=client)

    assert adapter.list_orders(symbols=("SPY",)) == ()
    with pytest.raises(ValueError, match="symbol must be uppercase"):
        adapter.list_orders(symbols=("spy",))

    assert len(client.order_filters) == 1
    assert client.order_filters[0].symbols == ["SPY"]


def test_alpaca_paper_adapter_rejects_live_trading_flag_even_with_client(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_LIVE_TRADING_ENABLED", " TRUE ")

    with pytest.raises(ValueError, match="ALPACA_LIVE_TRADING_ENABLED=true"):
        AlpacaPaperBrokerAdapter(client=FakeAlpacaClient())


def test_alpaca_paper_adapter_rejects_live_endpoint_override_even_with_client(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_BASE_URL", "https://api.alpaca.markets")

    with pytest.raises(ValueError, match="ALPACA_API_BASE_URL=live_endpoint"):
        AlpacaPaperBrokerAdapter(client=FakeAlpacaClient())


def test_alpaca_paper_adapter_rejects_quoted_live_boundary_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_LIVE_TRADING_ENABLED", '"true"')
    monkeypatch.setenv("APCA_API_BASE_URL", "'https://api.alpaca.markets'")

    with pytest.raises(ValueError, match="APCA_API_BASE_URL=live_endpoint"):
        AlpacaPaperBrokerAdapter(client=FakeAlpacaClient())


def test_alpaca_paper_adapter_rejects_blank_credentials() -> None:
    with pytest.raises(ValueError, match="ALPACA_API_KEY"):
        AlpacaPaperBrokerAdapter(api_key=" ", secret_key="\n")


def test_paper_service_rejects_order_before_broker_submission() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(
        broker=broker,
        starting_cash=Decimal("10000"),
        risk_engine=RiskEngine(RiskConfig(blocked_symbols=frozenset({"SPY"}))),
    )

    submission = service.submit_order(
        make_order(),
        strategy_id="blocked_strategy",
        estimated_price=Decimal("100"),
        as_of=NOW,
    )

    assert not submission.accepted
    assert not submission.broker_submitted
    assert service.ledger.get_order("paper-order-1") is None
    assert broker.submitted_orders == ()
    assert submission.risk_decision.rejections[0].rule == RiskRule.SYMBOL_BLOCKLIST
    assert "Risk rejected" in submission.explanation


def test_paper_fill_updates_ledger_status_and_reconciles() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(
        broker=broker,
        starting_cash=Decimal("10000"),
        risk_engine=RiskEngine(
            RiskConfig(
                us_tradable_universe=frozenset({"SPY"}),
                tradable_symbols=frozenset({"SPY"}),
            )
        ),
    )

    submission = service.submit_order(
        make_order(),
        strategy_id="sector_momentum",
        estimated_price=Decimal("100"),
        as_of=NOW,
        latest_prices={"SPY": Decimal("100")},
    )
    event = broker.fill_order(
        "paper-order-1",
        price=Decimal("100"),
        commission=Decimal("1"),
        filled_at=NOW,
    )
    service.ingest_fill_event(event)
    report = service.portfolio_report(as_of=NOW)

    assert submission.accepted
    assert submission.broker_submitted
    assert report.ledger_snapshot.cash == Decimal("9499")
    assert report.ledger_snapshot.positions[0].symbol == "SPY"
    assert report.ledger_snapshot.positions[0].quantity == Decimal("5")
    assert report.ledger_snapshot.positions[0].average_cost == Decimal("100.2")
    assert report.order_statuses[0].status == OrderStatus.FILLED
    assert report.reconciliation.reconciled
    assert report.reconciliation.issues == ()
    assert report.submissions[0].explanation.startswith("Risk approved")


def test_order_status_events_are_tracked_and_cancel_open_ledger_orders() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(broker=broker, starting_cash=Decimal("10000"))
    submission = service.submit_order(
        make_order(),
        strategy_id="sector_momentum",
        estimated_price=Decimal("100"),
        as_of=NOW,
        latest_prices={"SPY": Decimal("100")},
    )
    canceled_broker_order = submission.broker_order.model_copy(
        update={
            "status": OrderStatus.CANCELED,
            "provider_status": "canceled",
            "updated_at": NOW,
        }
    )

    status = service.ingest_order_state(canceled_broker_order, as_of=NOW)

    assert status.status == OrderStatus.CANCELED
    assert service.ledger.get_order("paper-order-1").status == OrderStatus.CANCELED


def test_reconciliation_reports_cash_and_position_differences() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(broker=broker, starting_cash=Decimal("10000"))
    service.submit_order(
        make_order(),
        strategy_id="sector_momentum",
        estimated_price=Decimal("100"),
        as_of=NOW,
        latest_prices={"SPY": Decimal("100")},
    )
    event = broker.fill_order(
        "paper-order-1",
        price=Decimal("100"),
        filled_at=NOW,
    )
    service.ingest_fill_event(event)
    mismatched_broker_state = BrokerPortfolioState(
        cash=Decimal("9501"),
        positions=(
            BrokerPositionState(
                symbol="SPY",
                quantity=Decimal("4"),
                average_entry_price=Decimal("100"),
            ),
        ),
        as_of=NOW,
        provider="memory-paper",
    )

    report = service.reconcile(as_of=NOW, broker_portfolio=mismatched_broker_state)

    assert not report.reconciled
    assert {issue.issue_type for issue in report.issues} == {
        ReconciliationIssueType.CASH_MISMATCH,
        ReconciliationIssueType.POSITION_QUANTITY_MISMATCH,
    }


def test_reconciliation_reports_unknown_filled_broker_orders() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(broker=broker, starting_cash=Decimal("10000"))
    unknown_broker_order = BrokerOrderState(
        broker_order_id="broker-only-order",
        client_order_id="external-paper-order",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        filled_quantity=Decimal("1"),
        status=OrderStatus.FILLED,
        submitted_at=NOW,
        updated_at=NOW,
        average_fill_price=Decimal("100"),
        provider="alpaca-paper",
        provider_status="filled",
    )
    broker_state = BrokerPortfolioState(
        cash=Decimal("10000"),
        positions=(),
        as_of=NOW,
        provider="alpaca-paper",
    )

    report = service.reconcile(
        as_of=NOW,
        broker_portfolio=broker_state,
        broker_orders=(unknown_broker_order,),
    )

    assert not report.reconciled
    assert report.issues[0].issue_type == ReconciliationIssueType.UNKNOWN_BROKER_ORDER
    assert report.issues[0].symbol == "SPY"
    assert report.issues[0].actual == Decimal("1")
    assert report.issues[0].broker_order_id == "broker-only-order"
    assert report.issues[0].client_order_id == "external-paper-order"
    assert report.issues[0].provider == "alpaca-paper"
    assert report.issues[0].provider_status == "filled"
    assert report.issues[0].filled_quantity == Decimal("1")


def test_statement_reconciliation_compares_saved_broker_statement() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(broker=broker, starting_cash=Decimal("10000"))
    service.submit_order(
        make_order(),
        strategy_id="sector_momentum",
        estimated_price=Decimal("100"),
        as_of=NOW,
        latest_prices={"SPY": Decimal("100")},
    )
    service.ingest_fill_event(
        broker.fill_order(
            "paper-order-1",
            price=Decimal("100"),
            filled_at=NOW,
        )
    )
    statement = BrokerStatementSnapshot(
        statement_id="statement-2026-05-29",
        as_of=NOW,
        provider="alpaca-paper",
        account_id="paper-account-1",
        cash=Decimal("9500"),
        positions=(
            BrokerPositionState(
                symbol="SPY",
                quantity=Decimal("5"),
                average_entry_price=Decimal("100"),
            ),
        ),
        source="manual-statement-export",
    )

    report = service.reconcile_statement(statement)

    assert report.reconciled
    assert report.statement.statement_id == "statement-2026-05-29"
    assert report.issues == ()
    assert report.model_dump(mode="json")["statement"]["source"] == (
        "manual-statement-export"
    )


def test_statement_reconciliation_reports_statement_mismatches() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(broker=broker, starting_cash=Decimal("10000"))
    service.submit_order(
        make_order(),
        strategy_id="sector_momentum",
        estimated_price=Decimal("100"),
        as_of=NOW,
        latest_prices={"SPY": Decimal("100")},
    )
    service.ingest_fill_event(
        broker.fill_order(
            "paper-order-1",
            price=Decimal("100"),
            filled_at=NOW,
        )
    )
    statement = BrokerStatementSnapshot(
        statement_id="statement-mismatch",
        as_of=NOW,
        provider="alpaca-paper",
        cash=Decimal("9501"),
        positions=(
            BrokerPositionState(
                symbol="SPY",
                quantity=Decimal("4"),
                average_entry_price=Decimal("100"),
            ),
        ),
        source="manual-statement-export",
    )

    report = service.reconcile_statement(statement)

    assert not report.reconciled
    assert {issue.issue_type for issue in report.issues} == {
        ReconciliationIssueType.CASH_MISMATCH,
        ReconciliationIssueType.POSITION_QUANTITY_MISMATCH,
    }
    assert report.issues[0].message


class FakeAlpacaClient:
    def __init__(self) -> None:
        self.submitted_order_data = None
        self.order_filters = []

    def submit_order(self, order_data):
        self.submitted_order_data = order_data
        return SimpleNamespace(
            id="alpaca-order-1",
            client_order_id=order_data.client_order_id,
            symbol=order_data.symbol,
            side=order_data.side.value,
            type=order_data.type.value,
            qty=str(order_data.qty),
            filled_qty="0",
            status="new",
            submitted_at=NOW,
            updated_at=None,
            limit_price=None,
            filled_avg_price=None,
        )

    def get_account(self):
        return SimpleNamespace(
            cash="10000",
            buying_power="20000",
            id="paper-account-1",
        )

    def get_all_positions(self):
        return [
            SimpleNamespace(
                symbol="SPY",
                qty="2",
                avg_entry_price="500",
                market_value="1000",
                current_price="500",
            )
        ]

    def get_orders(self, filter):
        self.order_filters.append(filter)
        return []
