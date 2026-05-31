from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.paper import (
    PaperTaxLotMethod,
    PaperTaxLotTracker,
    PaperTaxTerm,
    PaperTradingService,
    render_tax_lot_csv,
)
from trading_app.schemas import Fill, Order, OrderSide, OrderType

BUY_DATE = datetime(2025, 1, 2, 16, tzinfo=UTC)
SHORT_SELL_DATE = datetime(2025, 6, 2, 16, tzinfo=UTC)
LONG_SELL_DATE = datetime(2026, 2, 2, 16, tzinfo=UTC)


def make_fill(
    fill_id: str,
    *,
    side: OrderSide,
    quantity: Decimal,
    price: Decimal,
    commission: Decimal = Decimal("0"),
    filled_at: datetime = BUY_DATE,
) -> Fill:
    return Fill(
        id=fill_id,
        order_id=f"order-{fill_id}",
        symbol="SPY",
        side=side,
        quantity=quantity,
        price=price,
        commission=commission,
        filled_at=filled_at,
    )


def make_order(
    order_id: str,
    *,
    side: OrderSide,
    quantity: Decimal,
    created_at: datetime,
) -> Order:
    return Order(
        id=order_id,
        symbol="SPY",
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_at=created_at,
    )


def test_tax_lot_tracker_creates_active_lot_with_commission_basis() -> None:
    tracker = PaperTaxLotTracker()

    tracker.apply_fill(
        make_fill(
            "buy-1",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("10"),
        )
    )
    summary = tracker.summary(as_of=BUY_DATE)

    assert len(summary.active_lots) == 1
    assert summary.lot_method == PaperTaxLotMethod.FIFO
    assert summary.active_lots[0].remaining_quantity == Decimal("10")
    assert summary.active_lots[0].cost_basis_per_share == Decimal("101")
    assert summary.realized_lots == ()
    assert not summary.tax_estimate_available


def test_tax_lot_tracker_matches_fifo_and_reduces_sell_commission() -> None:
    tracker = PaperTaxLotTracker()
    tracker.apply_fill(
        make_fill(
            "buy-1",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("10"),
        )
    )
    tracker.apply_fill(
        make_fill(
            "sell-1",
            side=OrderSide.SELL,
            quantity=Decimal("4"),
            price=Decimal("120"),
            commission=Decimal("4"),
            filled_at=SHORT_SELL_DATE,
        )
    )
    summary = tracker.summary(
        as_of=SHORT_SELL_DATE,
        short_term_tax_rate=Decimal("0.30"),
        long_term_tax_rate=Decimal("0.15"),
    )

    assert len(summary.active_lots) == 1
    assert summary.active_lots[0].remaining_quantity == Decimal("6")
    assert len(summary.realized_lots) == 1
    assert summary.realized_lots[0].proceeds_per_share == Decimal("119")
    assert summary.realized_lots[0].realized_gain == Decimal("72")
    assert summary.short_term_realized_gains == Decimal("72")
    assert summary.long_term_realized_gains == Decimal("0")
    assert summary.estimated_tax == Decimal("21.60")
    assert summary.estimated_after_tax_realized_gains == Decimal("50.40")


def test_tax_lot_tracker_supports_lifo_lot_selection() -> None:
    tracker = PaperTaxLotTracker(lot_method=PaperTaxLotMethod.LIFO)
    tracker.apply_fill(
        make_fill(
            "buy-1",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("100"),
            filled_at=BUY_DATE,
        )
    )
    tracker.apply_fill(
        make_fill(
            "buy-2",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("115"),
            filled_at=datetime(2025, 2, 3, 16, tzinfo=UTC),
        )
    )
    tracker.apply_fill(
        make_fill(
            "sell-1",
            side=OrderSide.SELL,
            quantity=Decimal("5"),
            price=Decimal("120"),
            filled_at=SHORT_SELL_DATE,
        )
    )
    summary = tracker.summary(as_of=SHORT_SELL_DATE)

    assert summary.lot_method == PaperTaxLotMethod.LIFO
    assert summary.realized_lots[0].source_lot_id == "lot:buy-2"
    assert summary.realized_lots[0].realized_gain == Decimal("25")
    assert summary.active_lots[0].source_fill_id == "buy-1"


def test_tax_lot_tracker_supports_hifo_lot_selection() -> None:
    tracker = PaperTaxLotTracker(lot_method=PaperTaxLotMethod.HIFO)
    tracker.apply_fill(
        make_fill(
            "buy-1",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("100"),
            filled_at=BUY_DATE,
        )
    )
    tracker.apply_fill(
        make_fill(
            "buy-2",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("118"),
            filled_at=datetime(2025, 2, 3, 16, tzinfo=UTC),
        )
    )
    tracker.apply_fill(
        make_fill(
            "buy-3",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("110"),
            filled_at=datetime(2025, 3, 3, 16, tzinfo=UTC),
        )
    )
    tracker.apply_fill(
        make_fill(
            "sell-1",
            side=OrderSide.SELL,
            quantity=Decimal("5"),
            price=Decimal("120"),
            filled_at=SHORT_SELL_DATE,
        )
    )
    summary = tracker.summary(as_of=SHORT_SELL_DATE)

    assert summary.lot_method == PaperTaxLotMethod.HIFO
    assert summary.realized_lots[0].source_lot_id == "lot:buy-2"
    assert summary.realized_lots[0].realized_gain == Decimal("10")
    assert {lot.source_fill_id for lot in summary.active_lots} == {"buy-1", "buy-3"}


def test_tax_lot_tracker_classifies_long_term_gains_and_is_idempotent() -> None:
    tracker = PaperTaxLotTracker()
    buy = make_fill(
        "buy-1",
        side=OrderSide.BUY,
        quantity=Decimal("2"),
        price=Decimal("100"),
        filled_at=BUY_DATE,
    )
    sell = make_fill(
        "sell-1",
        side=OrderSide.SELL,
        quantity=Decimal("2"),
        price=Decimal("130"),
        filled_at=LONG_SELL_DATE,
    )

    tracker.apply_fill(buy)
    tracker.apply_fill(buy)
    tracker.apply_fill(sell)
    tracker.apply_fill(sell)
    summary = tracker.summary(as_of=LONG_SELL_DATE)

    assert summary.active_lots == ()
    assert len(summary.realized_lots) == 1
    assert summary.realized_lots[0].term == PaperTaxTerm.LONG_TERM
    assert summary.long_term_realized_gains == Decimal("60")
    assert summary.total_realized_gains == Decimal("60")


def test_paper_service_report_includes_tax_summary() -> None:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(
        broker=broker,
        starting_cash=Decimal("10000"),
        tax_lot_method=PaperTaxLotMethod.HIFO,
    )
    service.submit_order(
        make_order(
            "buy-order",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            created_at=BUY_DATE,
        ),
        strategy_id="manual",
        estimated_price=Decimal("100"),
        latest_prices={"SPY": Decimal("100")},
        as_of=BUY_DATE,
    )
    service.ingest_fill_event(
        broker.fill_order(
            "buy-order",
            price=Decimal("100"),
            commission=Decimal("10"),
            filled_at=BUY_DATE,
        )
    )
    service.submit_order(
        make_order(
            "sell-order",
            side=OrderSide.SELL,
            quantity=Decimal("4"),
            created_at=SHORT_SELL_DATE,
        ),
        strategy_id="manual",
        estimated_price=Decimal("120"),
        latest_prices={"SPY": Decimal("120")},
        as_of=SHORT_SELL_DATE,
    )
    service.ingest_fill_event(
        broker.fill_order(
            "sell-order",
            price=Decimal("120"),
            commission=Decimal("4"),
            filled_at=SHORT_SELL_DATE,
        )
    )

    report = service.portfolio_report(as_of=SHORT_SELL_DATE)

    assert report.tax_summary.lot_method == PaperTaxLotMethod.HIFO
    assert report.tax_summary.short_term_realized_gains == Decimal("72")
    assert report.tax_summary.active_lots[0].remaining_quantity == Decimal("6")
    assert report.tax_summary.realized_lots[0].source_fill_id == "paper-fill-2"


def test_tax_lot_csv_export_is_reviewable_and_research_labeled() -> None:
    tracker = PaperTaxLotTracker(lot_method=PaperTaxLotMethod.HIFO)
    tracker.apply_fill(
        make_fill(
            "buy-1",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("100"),
            filled_at=BUY_DATE,
        )
    )
    tracker.apply_fill(
        make_fill(
            "sell-1",
            side=OrderSide.SELL,
            quantity=Decimal("4"),
            price=Decimal("120"),
            filled_at=SHORT_SELL_DATE,
        )
    )

    csv_text = render_tax_lot_csv(tracker.summary(as_of=SHORT_SELL_DATE))

    assert csv_text.startswith("record_type,lot_method,lot_id")
    assert "active,hifo,lot:buy-1,SPY,buy-1,,6" in csv_text
    assert "realized,hifo,realized:sell-1:lot:buy-1:1,SPY,sell-1,lot:buy-1,4" in (
        csv_text
    )
    assert "not filing-grade tax accounting" in csv_text
