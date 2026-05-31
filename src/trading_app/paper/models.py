"""Paper-trading result and reporting models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, Field, field_validator

from trading_app.broker.models import (
    BrokerOrderState,
    BrokerPortfolioState,
    BrokerReconciliationReport,
)
from trading_app.risk import RiskDecision, RiskRejection
from trading_app.schemas import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    PortfolioSnapshot,
    TradingModel,
    validate_symbol,
)


class PaperTaxTerm(StrEnum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class PaperTaxLotMethod(StrEnum):
    FIFO = "fifo"
    LIFO = "lifo"
    HIFO = "hifo"


class PaperTaxLot(TradingModel):
    id: str = Field(min_length=1)
    symbol: str
    opened_at: AwareDatetime
    acquired_on: date
    source_fill_id: str = Field(min_length=1)
    remaining_quantity: Decimal = Field(gt=Decimal("0"))
    cost_basis_per_share: Decimal = Field(gt=Decimal("0"))

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class PaperRealizedTaxLot(TradingModel):
    id: str = Field(min_length=1)
    symbol: str
    side: OrderSide
    opened_at: AwareDatetime
    closed_at: AwareDatetime
    acquired_on: date
    sold_on: date
    source_lot_id: str = Field(min_length=1)
    source_fill_id: str = Field(min_length=1)
    quantity: Decimal = Field(gt=Decimal("0"))
    cost_basis_per_share: Decimal = Field(gt=Decimal("0"))
    proceeds_per_share: Decimal
    realized_gain: Decimal
    holding_period_days: int = Field(ge=0)
    term: PaperTaxTerm

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class PaperTaxSummary(TradingModel):
    as_of: AwareDatetime
    lot_method: PaperTaxLotMethod = PaperTaxLotMethod.FIFO
    active_lots: tuple[PaperTaxLot, ...] = ()
    realized_lots: tuple[PaperRealizedTaxLot, ...] = ()
    short_term_realized_gains: Decimal = Decimal("0")
    long_term_realized_gains: Decimal = Decimal("0")
    total_realized_gains: Decimal = Decimal("0")
    estimated_tax: Decimal | None = None
    estimated_after_tax_realized_gains: Decimal | None = None
    tax_estimate_available: bool = False
    notes: tuple[str, ...] = (
        "Paper tax lots are research estimates, not filing-grade tax accounting.",
        "Lot selection method is a research assumption; broker elections may differ.",
        "Wash-sale handling, dividends, and state taxes are not modeled yet.",
    )


class PaperOrderStatus(TradingModel):
    order_id: str = Field(min_length=1)
    broker_order_id: str = Field(min_length=1)
    status: OrderStatus
    provider_status: str = Field(min_length=1)
    updated_at: AwareDatetime


class PaperOrderSubmission(TradingModel):
    accepted: bool
    broker_submitted: bool
    strategy_id: str = Field(min_length=1)
    order: Order
    risk_decision: RiskDecision
    submitted_at: AwareDatetime
    estimated_notional: Decimal
    explanation: str = Field(min_length=1)
    broker_order: BrokerOrderState | None = None


class PaperPortfolioReport(TradingModel):
    as_of: AwareDatetime
    ledger_snapshot: PortfolioSnapshot
    broker_portfolio: BrokerPortfolioState
    reconciliation: BrokerReconciliationReport
    order_statuses: tuple[PaperOrderStatus, ...]
    submissions: tuple[PaperOrderSubmission, ...]
    fills: tuple[Fill, ...] = ()
    risk_rejections: tuple[RiskRejection, ...]
    tax_summary: PaperTaxSummary
