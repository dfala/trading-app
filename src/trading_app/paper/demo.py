"""Small deterministic paper-trading demo."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.schemas import Order, OrderSide, OrderType


def main() -> None:
    as_of = datetime(2026, 5, 29, 16, tzinfo=UTC)
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
    order = Order(
        id="demo-order-1",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("5"),
        created_at=as_of,
    )
    submission = service.submit_order(
        order,
        strategy_id="demo_strategy",
        estimated_price=Decimal("500"),
        as_of=as_of,
        latest_prices={"SPY": Decimal("500")},
    )
    if submission.broker_order is not None:
        fill = broker.fill_order(
            order.id,
            price=Decimal("500"),
            commission=Decimal("0"),
            filled_at=as_of,
        )
        service.ingest_fill_event(fill)

    report = service.portfolio_report(as_of=as_of)
    print("Paper Trading Demo")
    print(f"submitted={submission.broker_submitted}")
    print(f"accepted={submission.accepted}")
    print(f"explanation={submission.explanation}")
    print(f"cash={report.ledger_snapshot.cash}")
    print(f"positions={len(report.ledger_snapshot.positions)}")
    for position in report.ledger_snapshot.positions:
        print(
            "position="
            f"{position.symbol},qty={position.quantity},avg_cost={position.average_cost}"
        )
    print(f"reconciled={report.reconciliation.reconciled}")
    print(f"open_statuses={len(report.order_statuses)}")


if __name__ == "__main__":
    main()
