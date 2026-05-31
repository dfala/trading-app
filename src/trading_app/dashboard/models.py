"""Operator dashboard models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, Field

from trading_app.learning import NightlyLearningRun
from trading_app.paper import PaperPortfolioReport
from trading_app.reporting import DailyTradingReport
from trading_app.schemas import Fill, TradingModel
from trading_app.strategies import StrategyDefinition


class DashboardMetric(TradingModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    tone: str = Field(min_length=1)


class DashboardModelCard(TradingModel):
    label: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    state: str = Field(min_length=1)
    score: float
    detail: str = Field(min_length=1)


class OperatorDashboardSnapshot(TradingModel):
    generated_at: AwareDatetime
    mode: str = Field(min_length=1)
    broker: str = Field(min_length=1)
    data_feed_status: str = Field(min_length=1)
    kill_switch_enabled: bool
    cash: Decimal
    estimated_equity: Decimal
    realized_pnl: Decimal
    open_orders: int = Field(ge=0)
    recent_fills: tuple[Fill, ...]
    paper_report: PaperPortfolioReport
    daily_report: DailyTradingReport
    nightly_learning: NightlyLearningRun | None
    metrics: tuple[DashboardMetric, ...]
    model_cards: tuple[DashboardModelCard, ...]
    session_state: Any | None = None
    model_arena: Any | None = None
    live_readiness: Any | None = None
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
