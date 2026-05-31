"""Typed schemas for the trading research app.

These models describe the internal language of the system. Broker-specific
objects should be translated into these schemas at the boundary.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

PositiveDecimal = Annotated[Decimal, Field(gt=Decimal("0"))]
NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal("0"))]
Money = NonNegativeDecimal
Price = PositiveDecimal
Quantity = PositiveDecimal


class TradingModel(BaseModel):
    """Base model with strict validation for project-owned schemas."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=False,
        validate_default=True,
    )


class MarketEventType(StrEnum):
    TRADE = "TRADE"
    QUOTE = "QUOTE"
    BAR = "BAR"


class DataFeed(StrEnum):
    IEX = "IEX"
    SIP = "SIP"
    DELAYED_SIP = "DELAYED_SIP"
    THIRD_PARTY = "THIRD_PARTY"
    BROKER_REPORTED = "BROKER_REPORTED"


class MarketSession(StrEnum):
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"
    OVERNIGHT = "OVERNIGHT"


class BarTimeframe(StrEnum):
    DAY = "1D"


class AdjustmentType(StrEnum):
    ALL = "ALL"
    RAW = "RAW"
    SPLIT = "SPLIT"
    DIVIDEND = "DIVIDEND"


class SignalAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    REDUCE = "REDUCE"
    INCREASE = "INCREASE"
    HOLD = "HOLD"
    EXIT = "EXIT"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


def validate_symbol(symbol: str) -> str:
    """Validate a U.S. stock/ETF symbol in the project's internal format."""

    if not symbol:
        raise ValueError("symbol cannot be empty")
    if symbol != symbol.strip():
        raise ValueError("symbol must not contain surrounding whitespace")
    if symbol != symbol.upper():
        raise ValueError("symbol must be uppercase")
    if len(symbol) > 15:
        raise ValueError("symbol must be 15 characters or fewer")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
    if any(character not in allowed for character in symbol):
        raise ValueError("symbol contains unsupported characters")
    if not symbol[0].isalpha():
        raise ValueError("symbol must start with a letter")
    return symbol


class MarketEvent(TradingModel):
    symbol: str
    event_type: MarketEventType
    event_at: AwareDatetime
    ingested_at: AwareDatetime
    data_feed: DataFeed
    session: MarketSession
    source: str = Field(min_length=1)
    price: Price | None = None
    bid_price: Price | None = None
    ask_price: Price | None = None
    open_price: Price | None = None
    high_price: Price | None = None
    low_price: Price | None = None
    close_price: Price | None = None
    volume: NonNegativeDecimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class DailyBar(TradingModel):
    symbol: str
    trading_date: date
    bar_at: AwareDatetime
    ingested_at: AwareDatetime
    open_price: Price
    high_price: Price
    low_price: Price
    close_price: Price
    volume: NonNegativeDecimal
    source: str = Field(min_length=1)
    data_feed: DataFeed
    timeframe: BarTimeframe = BarTimeframe.DAY
    adjustment: AdjustmentType = AdjustmentType.ALL
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)

    @model_validator(mode="after")
    def _validate_daily_bar_integrity(self) -> DailyBar:
        if self.high_price < max(
            self.open_price,
            self.low_price,
            self.close_price,
        ):
            raise ValueError("high_price must be at least open, low, and close")
        if self.low_price > min(
            self.open_price,
            self.high_price,
            self.close_price,
        ):
            raise ValueError("low_price must be no greater than open, high, and close")
        if self.bar_at.date() != self.trading_date:
            raise ValueError("bar_at date must match trading_date")
        return self


class Signal(TradingModel):
    id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    symbol: str
    action: SignalAction
    generated_at: AwareDatetime
    confidence: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
    reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class Order(TradingModel):
    id: str = Field(min_length=1)
    signal_id: str | None = Field(default=None, min_length=1)
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Quantity
    limit_price: Price | None = None
    status: OrderStatus = OrderStatus.NEW
    created_at: AwareDatetime
    updated_at: AwareDatetime | None = None

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)

    @field_validator("limit_price")
    @classmethod
    def _validate_limit_price(
        cls, limit_price: Price | None, info: ValidationInfo
    ) -> Price | None:
        order_type = info.data.get("order_type")
        if order_type == OrderType.LIMIT and limit_price is None:
            raise ValueError("limit orders require limit_price")
        if order_type == OrderType.MARKET and limit_price is not None:
            raise ValueError("market orders must not include limit_price")
        return limit_price


class Fill(TradingModel):
    id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    symbol: str
    side: OrderSide
    quantity: Quantity
    price: Price
    commission: NonNegativeDecimal = Decimal("0")
    filled_at: AwareDatetime

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class Position(TradingModel):
    symbol: str
    quantity: Quantity
    average_cost: Price
    realized_pnl: Decimal = Decimal("0")

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class PortfolioSnapshot(TradingModel):
    cash: Money
    positions: tuple[Position, ...] = ()
    realized_pnl: Decimal = Decimal("0")
    total_fees: NonNegativeDecimal = Decimal("0")
    as_of: AwareDatetime


class ExperimentRecord(TradingModel):
    id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    created_at: AwareDatetime
    data_feed: DataFeed
    symbol_universe: tuple[str, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol_universe")
    @classmethod
    def _validate_symbol_universe(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        if not symbols:
            raise ValueError("symbol_universe cannot be empty")
        return tuple(validate_symbol(symbol) for symbol in symbols)
