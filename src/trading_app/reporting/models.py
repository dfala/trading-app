"""Daily reporting and AI-governance models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, Field

from trading_app.broker.models import BrokerReconciliationReport
from trading_app.market_data import MarketDataQualityReport
from trading_app.paper import PaperTaxLotMethod, PaperTaxTerm
from trading_app.risk import RiskRule
from trading_app.schemas import OrderSide, OrderStatus, TradingModel
from trading_app.strategies import StrategyDefinition


class ReportSeverity(StrEnum):
    OK = "OK"
    ATTENTION = "ATTENTION"
    BLOCKED = "BLOCKED"


class DailyModelReport(TradingModel):
    strategy_id: str = Field(min_length=1)
    submitted_orders: int = Field(ge=0)
    accepted_orders: int = Field(ge=0)
    rejected_orders: int = Field(ge=0)
    broker_submitted_orders: int = Field(ge=0)
    filled_orders: int = Field(ge=0)
    symbols: tuple[str, ...] = ()
    estimated_notional: Decimal


class DailyReportMetadata(TradingModel):
    report_id: str = Field(min_length=1)
    schema_version: str = Field(default="daily-report-v2", min_length=1)
    generated_at: AwareDatetime
    markdown_path: str | None = Field(default=None, min_length=1)
    evidence_sources: tuple[str, ...] = ()


class DailyPnlReport(TradingModel):
    starting_cash: Decimal | None = None
    ending_cash: Decimal
    cash_change: Decimal | None = None
    estimated_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal
    open_positions: int = Field(ge=0)
    open_position_symbols: tuple[str, ...] = ()


class DailyRiskReport(TradingModel):
    severity: ReportSeverity
    risk_decisions: int = Field(ge=0)
    approved_orders: int = Field(ge=0)
    rejected_orders: int = Field(ge=0)
    rejection_count: int = Field(ge=0)
    rejection_rules: tuple[RiskRule, ...] = ()
    reconciliation_reconciled: bool
    reconciliation_issue_count: int = Field(ge=0)


class DailyTaxReport(TradingModel):
    realized_lot_count: int = Field(ge=0)
    active_lot_count: int = Field(ge=0)
    lot_method: PaperTaxLotMethod = PaperTaxLotMethod.FIFO
    short_term_realized_gains: Decimal = Decimal("0")
    long_term_realized_gains: Decimal = Decimal("0")
    total_realized_gains: Decimal = Decimal("0")
    estimated_tax: Decimal | None = None
    estimated_after_tax_realized_gains: Decimal | None = None
    tax_estimate_available: bool = False
    realized_terms: tuple[PaperTaxTerm, ...] = ()
    notes: tuple[str, ...] = ()


class DailyFillDetail(TradingModel):
    fill_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    filled_at: AwareDatetime
    ledger_effect: str = Field(min_length=1)


class DailyOperatorActionDetail(TradingModel):
    action: str = Field(min_length=1)
    requested_at: AwareDatetime
    requested_by: str = Field(min_length=1)
    status: str = Field(min_length=1)
    message: str = Field(min_length=1)
    reason: str = ""


class DailyRuntimeEventDetail(TradingModel):
    timestamp: AwareDatetime
    severity: str = Field(min_length=1)
    category: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class DailyLearningRecommendationDetail(TradingModel):
    action: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    manual_review_required: bool = True
    rationale: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class DailyLearningReport(TradingModel):
    status: str = Field(min_length=1)
    active_model_unchanged: bool = True
    research_memo: str = Field(min_length=1)
    recommendations: tuple[DailyLearningRecommendationDetail, ...] = ()


class DailyBenchmarkReport(TradingModel):
    benchmark_symbol: str = Field(default="SPY", min_length=1)
    comparison_available: bool = False
    model_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    excess_return: Decimal | None = None
    reason: str = Field(min_length=1)


class RejectedSignalDetail(TradingModel):
    order_id: str = Field(min_length=1)
    symbol: str
    rule: RiskRule
    message: str = Field(min_length=1)
    checked_at: AwareDatetime


class RejectedSignalReport(TradingModel):
    rejected_signals: tuple[RejectedSignalDetail, ...]


class TradeExplanation(TradingModel):
    order_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    symbol: str
    side: OrderSide
    quantity: Decimal
    status: OrderStatus
    accepted: bool
    broker_submitted: bool
    broker_order_id: str | None = Field(default=None, min_length=1)
    fill_ids: tuple[str, ...] = ()
    signal_rationale: str = Field(
        default="Strategy-generated paper order.", min_length=1
    )
    ledger_trace: tuple[str, ...] = ()
    explanation: str = Field(min_length=1)
    evidence: tuple[str, ...]


class AIGovernanceSummary(TradingModel):
    generated_by: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: tuple[str, ...]
    prohibited_actions: tuple[str, ...]


class DailyTradingReport(TradingModel):
    report_metadata: DailyReportMetadata | None = None
    trading_day: date
    generated_at: AwareDatetime
    model_reports: tuple[DailyModelReport, ...]
    pnl_report: DailyPnlReport
    risk_report: DailyRiskReport
    fill_report: tuple[DailyFillDetail, ...] = ()
    rejected_signal_report: RejectedSignalReport
    trade_explanations: tuple[TradeExplanation, ...]
    operator_actions: tuple[DailyOperatorActionDetail, ...] = ()
    runtime_events: tuple[DailyRuntimeEventDetail, ...] = ()
    learning_report: DailyLearningReport | None = None
    benchmark_report: DailyBenchmarkReport | None = None
    ai_summary: AIGovernanceSummary
    reconciliation: BrokerReconciliationReport
    data_quality_report: MarketDataQualityReport | None = None
    tax_report: DailyTaxReport
    active_strategy_definition: StrategyDefinition | None = None
