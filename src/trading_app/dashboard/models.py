"""Operator dashboard models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, Field

from trading_app.learning import NightlyLearningRun
from trading_app.learning.autonomous import AutonomousLearningCycleRun
from trading_app.learning.autonomous_service import AutonomousLearningServiceState
from trading_app.market_data import LatestPriceSnapshot
from trading_app.paper import PaperPortfolioReport
from trading_app.reporting import DailyTradingReport
from trading_app.schemas import Fill, TradingModel
from trading_app.strategies import StrategyDefinition


class DashboardMetric(TradingModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    tone: str = Field(min_length=1)


class DashboardModelEvidence(TradingModel):
    model_key: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_report: str | None = None
    benchmark: str = "SPY"
    comparison_start_date: str | None = None
    comparison_end_date: str | None = None
    comparison_generated_at: str | None = None
    rank: int | None = Field(default=None, ge=1)
    comparison_rank: int | None = Field(default=None, ge=1)
    universe_id: str | None = None
    strategy_name: str | None = None
    net_total_return: float | None = None
    benchmark_total_return: float | None = None
    excess_return: float | None = None
    full_delta: float | None = None
    stress_delta: float | None = None
    annualized_return: float | None = None
    annualized_volatility: float | None = None
    worst_drawdown: float | None = None
    risk_adjusted_score: float | None = None
    positive_folds: int | None = Field(default=None, ge=0)
    fold_count: int | None = Field(default=None, ge=0)
    min_fold_delta: float | None = None
    average_fold_delta: float | None = None
    turnover: float | None = None
    trade_count: int | None = Field(default=None, ge=0)
    decision_count: int | None = Field(default=None, ge=0)
    seen_count: int | None = Field(default=None, ge=0)
    gate_status: str | None = None
    status: str | None = None
    latest_run_id: str | None = None
    late_entry_risk: bool | None = None
    late_entry_risk_reason: str | None = None
    portfolio_governance_classification: str | None = None
    champion_eligible: bool | None = None
    average_semiconductor_exposure: float | None = None
    peak_semiconductor_exposure: float | None = None
    material_semiconductor_exposure_ratio: float | None = None
    portfolio_governance_notes: tuple[str, ...] = ()
    note: str | None = None


class DashboardModelCard(TradingModel):
    label: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    state: str = Field(min_length=1)
    score: float
    detail: str = Field(min_length=1)
    evidence: DashboardModelEvidence | None = None


class DashboardPortfolioHistoryPoint(TradingModel):
    as_of: AwareDatetime
    estimated_equity: Decimal
    cash: Decimal | None = None
    realized_pnl: Decimal | None = None


class OperatorDashboardSnapshot(TradingModel):
    generated_at: AwareDatetime
    mode: str = Field(min_length=1)
    broker: str = Field(min_length=1)
    data_feed_status: str = Field(min_length=1)
    kill_switch_enabled: bool
    cash: Decimal
    estimated_equity: Decimal
    realized_pnl: Decimal
    managed_capital: Decimal | None = None
    managed_target_equity: Decimal | None = None
    portfolio_history: tuple[DashboardPortfolioHistoryPoint, ...] = ()
    open_orders: int = Field(ge=0)
    recent_fills: tuple[Fill, ...]
    paper_report: PaperPortfolioReport
    daily_report: DailyTradingReport
    shadow_challenger: Any | None = None
    shadow_challengers: tuple[Any, ...] = ()
    nightly_learning: NightlyLearningRun | None
    latest_prices: LatestPriceSnapshot | None = None
    autonomous_learning: AutonomousLearningCycleRun | None = None
    autonomous_learning_service: AutonomousLearningServiceState | None = None
    metrics: tuple[DashboardMetric, ...]
    model_cards: tuple[DashboardModelCard, ...]
    session_state: Any | None = None
    model_arena: Any | None = None
    live_readiness: Any | None = None
    live_sandbox: Any | None = None
    runtime_state: Any | None = None
    control_state: Any | None = None
    last_control_result: Any | None = None
    alerts: tuple[Any, ...] = ()
    health_report: Any | None = None
    health_report_path: str | None = None
    nightly_learning_path: str | None = None
    completion_audit: Any | None = None
    final_acceptance: Any | None = None
    statement_reconciliation: Any | None = None
    statement_reconciliation_path: str | None = None
    active_strategy_definition: StrategyDefinition | None = None
