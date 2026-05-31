"""Broker-facing models for paper trading and reconciliation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, Field, field_validator

from trading_app.schemas import (
    NonNegativeDecimal,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioSnapshot,
    Price,
    Quantity,
    TradingModel,
    validate_symbol,
)


class ReconciliationIssueType(StrEnum):
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
    CASH_MISMATCH = "CASH_MISMATCH"
    POSITION_QUANTITY_MISMATCH = "POSITION_QUANTITY_MISMATCH"
    MISSING_BROKER_POSITION = "MISSING_BROKER_POSITION"
    MISSING_LEDGER_POSITION = "MISSING_LEDGER_POSITION"
    UNKNOWN_BROKER_ORDER = "UNKNOWN_BROKER_ORDER"


class BrokerOrderState(TradingModel):
    broker_order_id: str = Field(min_length=1)
    client_order_id: str | None = Field(default=None, min_length=1)
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Quantity
    filled_quantity: NonNegativeDecimal = Decimal("0")
    status: OrderStatus
    submitted_at: AwareDatetime
    updated_at: AwareDatetime | None = None
    limit_price: Price | None = None
    average_fill_price: Price | None = None
    provider: str = Field(min_length=1)
    provider_status: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class BrokerFillEvent(TradingModel):
    id: str = Field(min_length=1)
    broker_order_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    symbol: str
    side: OrderSide
    quantity: Quantity
    price: Price
    commission: NonNegativeDecimal = Decimal("0")
    filled_at: AwareDatetime
    provider: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class BrokerPositionState(TradingModel):
    symbol: str
    quantity: Quantity
    average_entry_price: Price
    market_value: NonNegativeDecimal | None = None
    current_price: Price | None = None

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class BrokerPortfolioState(TradingModel):
    cash: NonNegativeDecimal
    positions: tuple[BrokerPositionState, ...] = ()
    as_of: AwareDatetime
    provider: str = Field(min_length=1)
    account_id: str | None = Field(default=None, min_length=1)
    buying_power: NonNegativeDecimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerStatementSnapshot(TradingModel):
    statement_id: str = Field(min_length=1)
    as_of: AwareDatetime
    provider: str = Field(min_length=1)
    account_id: str | None = Field(default=None, min_length=1)
    cash: NonNegativeDecimal
    positions: tuple[BrokerPositionState, ...] = ()
    source: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerReconciliationIssue(TradingModel):
    issue_type: ReconciliationIssueType
    symbol: str | None = None
    expected: Decimal
    actual: Decimal
    difference: Decimal
    message: str = Field(min_length=1)
    broker_order_id: str | None = Field(default=None, min_length=1)
    client_order_id: str | None = Field(default=None, min_length=1)
    provider: str | None = Field(default=None, min_length=1)
    provider_status: str | None = Field(default=None, min_length=1)
    filled_quantity: Decimal | None = None


class BrokerReconciliationReport(TradingModel):
    as_of: AwareDatetime
    reconciled: bool
    ledger_snapshot: PortfolioSnapshot
    broker_portfolio: BrokerPortfolioState
    issues: tuple[BrokerReconciliationIssue, ...] = ()
    cash_tolerance: NonNegativeDecimal
    quantity_tolerance: NonNegativeDecimal


class BrokerStatementReconciliationReport(TradingModel):
    as_of: AwareDatetime
    reconciled: bool
    ledger_snapshot: PortfolioSnapshot
    statement: BrokerStatementSnapshot
    issues: tuple[BrokerReconciliationIssue, ...] = ()
    cash_tolerance: NonNegativeDecimal
    quantity_tolerance: NonNegativeDecimal
    statement_path: str | None = None
    statement_sha256: str | None = Field(default=None, min_length=64, max_length=64)


def aware_datetime(value: datetime | str | None) -> datetime | None:
    """Normalize broker timestamps to timezone-aware datetimes."""

    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("broker timestamp must be timezone-aware")
    return value
