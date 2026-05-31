from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_app.schemas import (
    AdjustmentType,
    BarTimeframe,
    DailyBar,
    DataFeed,
    ExperimentRecord,
    Fill,
    MarketEvent,
    MarketEventType,
    MarketSession,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioSnapshot,
    Position,
    Signal,
    SignalAction,
)

NOW = datetime(2026, 5, 30, 14, 30, tzinfo=UTC)


def test_accepts_valid_core_schemas() -> None:
    daily_bar = DailyBar(
        symbol="SPY",
        trading_date=NOW.date(),
        bar_at=NOW,
        ingested_at=NOW,
        open_price=Decimal("499.00"),
        high_price=Decimal("501.00"),
        low_price=Decimal("498.00"),
        close_price=Decimal("500.25"),
        volume=Decimal("1000000"),
        source="alpaca",
        data_feed=DataFeed.IEX,
        timeframe=BarTimeframe.DAY,
        adjustment=AdjustmentType.ALL,
    )
    market_event = MarketEvent(
        symbol="SPY",
        event_type=MarketEventType.TRADE,
        event_at=NOW,
        ingested_at=NOW,
        data_feed=DataFeed.IEX,
        session=MarketSession.REGULAR,
        source="alpaca",
        price=Decimal("500.25"),
        volume=Decimal("100"),
    )
    signal = Signal(
        id="sig-1",
        strategy_id="sector_momentum",
        strategy_version="1.0.0",
        symbol="SPY",
        action=SignalAction.BUY,
        generated_at=NOW,
        confidence=Decimal("0.75"),
        reason="Momentum rank improved.",
    )
    order = Order(
        id="ord-1",
        signal_id=signal.id,
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("3"),
        created_at=NOW,
    )
    fill = Fill(
        id="fill-1",
        order_id=order.id,
        symbol="SPY",
        side=OrderSide.BUY,
        quantity=Decimal("3"),
        price=Decimal("500.30"),
        commission=Decimal("0"),
        filled_at=NOW,
    )
    position = Position(
        symbol="SPY",
        quantity=Decimal("3"),
        average_cost=Decimal("500.30"),
    )
    snapshot = PortfolioSnapshot(
        cash=Decimal("8499.10"),
        positions=(position,),
        realized_pnl=Decimal("0"),
        total_fees=Decimal("0"),
        as_of=NOW,
    )
    experiment = ExperimentRecord(
        id="exp-1",
        strategy_id="sector_momentum",
        strategy_version="1.0.0",
        hypothesis="U.S. sector momentum persists.",
        created_at=NOW,
        data_feed=DataFeed.IEX,
        symbol_universe=("SPY", "XLK"),
    )

    assert daily_bar.close_price == Decimal("500.25")
    assert market_event.model_dump()["symbol"] == "SPY"
    assert signal.model_dump()["action"] == SignalAction.BUY
    assert order.status == OrderStatus.NEW
    assert fill.model_dump()["price"] == Decimal("500.30")
    assert snapshot.positions == (position,)
    assert experiment.symbol_universe == ("SPY", "XLK")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_at", datetime(2026, 5, 30, 14, 30)),
        ("ingested_at", datetime(2026, 5, 30, 14, 30)),
    ],
)
def test_market_event_rejects_naive_datetimes(field: str, value: datetime) -> None:
    payload = {
        "symbol": "SPY",
        "event_type": MarketEventType.TRADE,
        "event_at": NOW,
        "ingested_at": NOW,
        "data_feed": DataFeed.IEX,
        "session": MarketSession.REGULAR,
        "source": "alpaca",
        "price": Decimal("500.25"),
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        MarketEvent(**payload)


def test_daily_bar_rejects_naive_timestamp_lowercase_symbol_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DailyBar(
            symbol="SPY",
            trading_date=NOW.date(),
            bar_at=datetime(2026, 5, 30, 21),
            ingested_at=NOW,
            open_price=Decimal("499.00"),
            high_price=Decimal("501.00"),
            low_price=Decimal("498.00"),
            close_price=Decimal("500.25"),
            volume=Decimal("1000000"),
            source="alpaca",
            data_feed=DataFeed.IEX,
        )

    with pytest.raises(ValidationError):
        DailyBar(
            symbol="spy",
            trading_date=NOW.date(),
            bar_at=NOW,
            ingested_at=NOW,
            open_price=Decimal("499.00"),
            high_price=Decimal("501.00"),
            low_price=Decimal("498.00"),
            close_price=Decimal("500.25"),
            volume=Decimal("1000000"),
            source="alpaca",
            data_feed=DataFeed.IEX,
            unexpected=True,
        )

    with pytest.raises(ValidationError):
        DailyBar(
            symbol="SPY",
            trading_date=NOW.date(),
            bar_at=NOW,
            ingested_at=datetime(2026, 5, 30, 21),
            open_price=Decimal("499.00"),
            high_price=Decimal("501.00"),
            low_price=Decimal("498.00"),
            close_price=Decimal("500.25"),
            volume=Decimal("1000000"),
            source="alpaca",
            data_feed=DataFeed.IEX,
        )


def test_daily_bar_rejects_inconsistent_ohlc_and_timestamp_date() -> None:
    with pytest.raises(ValidationError, match="high_price"):
        DailyBar(
            symbol="SPY",
            trading_date=NOW.date(),
            bar_at=NOW,
            ingested_at=NOW,
            open_price=Decimal("499.00"),
            high_price=Decimal("498.00"),
            low_price=Decimal("497.00"),
            close_price=Decimal("500.25"),
            volume=Decimal("1000000"),
            source="alpaca",
            data_feed=DataFeed.IEX,
        )

    with pytest.raises(ValidationError, match="low_price"):
        DailyBar(
            symbol="SPY",
            trading_date=NOW.date(),
            bar_at=NOW,
            ingested_at=NOW,
            open_price=Decimal("499.00"),
            high_price=Decimal("501.00"),
            low_price=Decimal("500.00"),
            close_price=Decimal("498.25"),
            volume=Decimal("1000000"),
            source="alpaca",
            data_feed=DataFeed.IEX,
        )

    with pytest.raises(ValidationError, match="bar_at date"):
        DailyBar(
            symbol="SPY",
            trading_date=NOW.date(),
            bar_at=NOW.replace(day=NOW.day - 1),
            ingested_at=NOW,
            open_price=Decimal("499.00"),
            high_price=Decimal("501.00"),
            low_price=Decimal("498.00"),
            close_price=Decimal("500.25"),
            volume=Decimal("1000000"),
            source="alpaca",
            data_feed=DataFeed.IEX,
        )


@pytest.mark.parametrize("symbol", ["spy", " SPY", "SPY ", "$SPY", "1SPY"])
def test_rejects_invalid_symbols(symbol: str) -> None:
    with pytest.raises(ValidationError):
        Signal(
            id="sig-1",
            strategy_id="sector_momentum",
            strategy_version="1.0.0",
            symbol=symbol,
            action=SignalAction.BUY,
            generated_at=NOW,
            confidence=Decimal("0.75"),
            reason="Momentum rank improved.",
        )


def test_rejects_negative_and_zero_values() -> None:
    with pytest.raises(ValidationError):
        DailyBar(
            symbol="SPY",
            trading_date=NOW.date(),
            bar_at=NOW,
            ingested_at=NOW,
            open_price=Decimal("499.00"),
            high_price=Decimal("501.00"),
            low_price=Decimal("498.00"),
            close_price=Decimal("0"),
            volume=Decimal("1000000"),
            source="alpaca",
            data_feed=DataFeed.IEX,
        )

    with pytest.raises(ValidationError):
        Order(
            id="ord-1",
            symbol="SPY",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0"),
            created_at=NOW,
        )

    with pytest.raises(ValidationError):
        Fill(
            id="fill-1",
            order_id="ord-1",
            symbol="SPY",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            price=Decimal("-1"),
            commission=Decimal("0"),
            filled_at=NOW,
        )

    with pytest.raises(ValidationError):
        Fill(
            id="fill-1",
            order_id="ord-1",
            symbol="SPY",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            price=Decimal("0"),
            commission=Decimal("0"),
            filled_at=NOW,
        )

    with pytest.raises(ValidationError):
        Fill(
            id="fill-1",
            order_id="ord-1",
            symbol="SPY",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            price=Decimal("500"),
            commission=Decimal("-0.01"),
            filled_at=NOW,
        )


def test_rejects_stringly_typed_decimals() -> None:
    with pytest.raises(ValidationError):
        Order(
            id="ord-1",
            symbol="SPY",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity="1",
            created_at=NOW,
        )


def test_rejects_unknown_enum_values_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Order(
            id="ord-1",
            symbol="SPY",
            side="LONG",
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
            created_at=NOW,
        )

    with pytest.raises(ValidationError):
        Position(
            symbol="SPY",
            quantity=Decimal("1"),
            average_cost=Decimal("500"),
            unexpected=True,
        )


def test_limit_order_requires_limit_price_and_market_order_rejects_one() -> None:
    with pytest.raises(ValidationError):
        Order(
            id="ord-1",
            symbol="SPY",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            created_at=NOW,
        )

    with pytest.raises(ValidationError):
        Order(
            id="ord-1",
            symbol="SPY",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
            limit_price=Decimal("500"),
            created_at=NOW,
        )


def test_models_serialize_to_json() -> None:
    order = Order(
        id="ord-1",
        symbol="BRK.B",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1.5"),
        created_at=NOW,
    )

    dumped = order.model_dump()
    json_ready = order.model_dump(mode="json")
    json_dumped = order.model_dump_json()

    assert dumped["quantity"] == Decimal("1.5")
    assert json_ready["quantity"] == "1.5"
    assert '"symbol":"BRK.B"' in json_dumped
