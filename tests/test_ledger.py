from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trading_app.ledger import Ledger, LedgerError
from trading_app.schemas import Fill, Order, OrderSide, OrderStatus, OrderType

NOW = datetime(2026, 5, 30, 14, 30, tzinfo=UTC)


def make_order(
    order_id: str,
    *,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("10"),
    symbol: str = "SPY",
) -> Order:
    return Order(
        id=order_id,
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_at=NOW,
    )


def make_fill(
    fill_id: str,
    order_id: str,
    *,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("10"),
    price: Decimal = Decimal("100"),
    commission: Decimal = Decimal("0"),
    symbol: str = "SPY",
) -> Fill:
    return Fill(
        id=fill_id,
        order_id=order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        commission=commission,
        filled_at=NOW,
    )


def test_initial_cash_snapshot_is_correct() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))

    snapshot = ledger.snapshot(NOW)

    assert snapshot.cash == Decimal("10000")
    assert snapshot.positions == ()
    assert snapshot.realized_pnl == Decimal("0")
    assert snapshot.total_fees == Decimal("0")


def test_record_order_does_not_change_cash_or_positions() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))

    order = ledger.record_order(make_order("ord-1"))

    assert order.status == OrderStatus.NEW
    assert ledger.snapshot(NOW).cash == Decimal("10000")
    assert ledger.snapshot(NOW).positions == ()


def test_buy_fill_reduces_cash_creates_position_and_marks_order_filled() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("ord-1", quantity=Decimal("10")))

    ledger.record_fill(
        make_fill(
            "fill-1",
            "ord-1",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("1"),
        )
    )

    position = ledger.get_position("SPY")
    order = ledger.get_order("ord-1")

    assert ledger.cash == Decimal("8999")
    assert position is not None
    assert position.quantity == Decimal("10")
    assert position.average_cost == Decimal("100.1")
    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert ledger.total_fees == Decimal("1")


def test_partial_fills_update_order_status_then_filled() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("ord-1", quantity=Decimal("10")))

    ledger.record_fill(make_fill("fill-1", "ord-1", quantity=Decimal("4")))
    partially_filled = ledger.get_order("ord-1")

    assert partially_filled is not None
    assert partially_filled.status == OrderStatus.PARTIALLY_FILLED

    ledger.record_fill(make_fill("fill-2", "ord-1", quantity=Decimal("6")))
    filled = ledger.get_order("ord-1")

    assert filled is not None
    assert filled.status == OrderStatus.FILLED
    assert ledger.get_position("SPY").quantity == Decimal("10")  # type: ignore[union-attr]


def test_multiple_buys_produce_weighted_average_cost() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("ord-1", quantity=Decimal("10")))
    ledger.record_fill(
        make_fill("fill-1", "ord-1", quantity=Decimal("10"), price=Decimal("100"))
    )
    ledger.record_order(make_order("ord-2", quantity=Decimal("10")))
    ledger.record_fill(
        make_fill("fill-2", "ord-2", quantity=Decimal("10"), price=Decimal("110"))
    )

    position = ledger.get_position("SPY")

    assert position is not None
    assert position.quantity == Decimal("20")
    assert position.average_cost == Decimal("105")


def test_sell_fill_increases_cash_reduces_position_and_records_realized_pnl() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("buy-1", quantity=Decimal("10")))
    ledger.record_fill(
        make_fill("buy-fill-1", "buy-1", quantity=Decimal("10"), price=Decimal("100"))
    )
    ledger.record_order(
        make_order("sell-1", side=OrderSide.SELL, quantity=Decimal("4"))
    )

    ledger.record_fill(
        make_fill(
            "sell-fill-1",
            "sell-1",
            side=OrderSide.SELL,
            quantity=Decimal("4"),
            price=Decimal("120"),
            commission=Decimal("1"),
        )
    )

    position = ledger.get_position("SPY")

    assert ledger.cash == Decimal("9479")
    assert ledger.realized_pnl == Decimal("79")
    assert ledger.total_fees == Decimal("1")
    assert position is not None
    assert position.quantity == Decimal("6")
    assert position.average_cost == Decimal("100")
    assert position.realized_pnl == Decimal("79")


def test_full_sell_removes_active_position() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("buy-1", quantity=Decimal("10")))
    ledger.record_fill(
        make_fill("buy-fill-1", "buy-1", quantity=Decimal("10"), price=Decimal("100"))
    )
    ledger.record_order(
        make_order("sell-1", side=OrderSide.SELL, quantity=Decimal("10"))
    )

    ledger.record_fill(
        make_fill(
            "sell-fill-1",
            "sell-1",
            side=OrderSide.SELL,
            quantity=Decimal("10"),
            price=Decimal("110"),
        )
    )

    assert ledger.get_position("SPY") is None
    assert ledger.snapshot(NOW).positions == ()
    assert ledger.realized_pnl == Decimal("100")


def test_rejects_duplicate_order_ids() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("ord-1"))

    with pytest.raises(LedgerError):
        ledger.record_order(make_order("ord-1"))


def test_rejects_duplicate_fill_ids() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("ord-1", quantity=Decimal("20")))
    ledger.record_fill(make_fill("fill-1", "ord-1", quantity=Decimal("10")))

    with pytest.raises(LedgerError):
        ledger.record_fill(make_fill("fill-1", "ord-1", quantity=Decimal("1")))


def test_rejects_overfills_unknown_orders_and_mismatches() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("ord-1", quantity=Decimal("10")))

    with pytest.raises(LedgerError):
        ledger.record_fill(make_fill("fill-1", "ord-1", quantity=Decimal("11")))

    with pytest.raises(LedgerError):
        ledger.record_fill(make_fill("fill-2", "missing"))

    with pytest.raises(LedgerError):
        ledger.record_fill(make_fill("fill-3", "ord-1", symbol="QQQ"))

    with pytest.raises(LedgerError):
        ledger.record_fill(make_fill("fill-4", "ord-1", side=OrderSide.SELL))


def test_rejects_insufficient_cash_buys_and_oversells() -> None:
    ledger = Ledger(starting_cash=Decimal("100"))
    ledger.record_order(make_order("buy-1", quantity=Decimal("2")))

    with pytest.raises(LedgerError):
        ledger.record_fill(
            make_fill("fill-1", "buy-1", quantity=Decimal("2"), price=Decimal("100"))
        )

    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("buy-1", quantity=Decimal("1")))
    ledger.record_fill(
        make_fill("buy-fill-1", "buy-1", quantity=Decimal("1"), price=Decimal("100"))
    )
    ledger.record_order(
        make_order("sell-1", side=OrderSide.SELL, quantity=Decimal("2"))
    )

    with pytest.raises(LedgerError):
        ledger.record_fill(
            make_fill(
                "sell-fill-1",
                "sell-1",
                side=OrderSide.SELL,
                quantity=Decimal("2"),
            )
        )


def test_cancel_open_order_and_reject_canceling_filled_or_unknown_order() -> None:
    ledger = Ledger(starting_cash=Decimal("10000"))
    ledger.record_order(make_order("ord-1"))

    canceled = ledger.cancel_order("ord-1", NOW)

    assert canceled.status == OrderStatus.CANCELED
    assert canceled.updated_at == NOW

    ledger.record_order(make_order("ord-2"))
    ledger.record_fill(make_fill("fill-1", "ord-2"))

    with pytest.raises(LedgerError):
        ledger.cancel_order("ord-2", NOW)

    with pytest.raises(LedgerError):
        ledger.cancel_order("missing", NOW)
