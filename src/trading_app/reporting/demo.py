"""Generate a deterministic daily paper-trading report."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.paper import PaperTradingService
from trading_app.reporting import DailyReportGenerator, render_markdown
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
                max_orders_per_day=1,
            )
        ),
    )

    accepted_order = Order(
        id="daily-order-1",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("5"),
        created_at=as_of,
    )
    service.submit_order(
        accepted_order,
        strategy_id="sector_momentum",
        estimated_price=Decimal("500"),
        latest_prices={"SPY": Decimal("500")},
        as_of=as_of,
    )
    service.ingest_fill_event(
        broker.fill_order(
            accepted_order.id,
            price=Decimal("500"),
            filled_at=as_of,
        )
    )

    rejected_order = Order(
        id="daily-order-2",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=as_of,
    )
    service.submit_order(
        rejected_order,
        strategy_id="sector_momentum",
        estimated_price=Decimal("505"),
        latest_prices={"SPY": Decimal("505")},
        as_of=as_of,
    )

    paper_report = service.portfolio_report(as_of=as_of)
    daily_report = DailyReportGenerator().build(
        paper_report,
        generated_at=as_of,
    )
    print(render_markdown(daily_report))


if __name__ == "__main__":
    main()
