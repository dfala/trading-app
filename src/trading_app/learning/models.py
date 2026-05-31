"""Model registry and nightly learning loop schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, Field, field_validator

from trading_app.schemas import TradingModel, validate_symbol


class ModelRegistryState(StrEnum):
    IDEA = "idea"
    BACKTEST = "backtest"
    VALIDATED = "validated"
    SHADOW = "shadow"
    PAPER = "paper"
    CANDIDATE_LIVE = "candidate_live"
    LIVE_LIMITED = "live_limited"
    LIVE_SCALED = "live_scaled"
    PAUSED = "paused"
    RETIRED = "retired"


class PromotionAction(StrEnum):
    KEEP_CHAMPION = "keep_champion"
    WATCH = "watch"
    PROMOTE_TO_SHADOW = "promote_to_shadow"
    PAUSE = "pause"
    RETIRE = "retire"


class ModelVersionRecord(TradingModel):
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    state: ModelRegistryState
    parameters: dict[str, Any] = Field(default_factory=dict)
    hypothesis: str = Field(min_length=1)
    created_at: AwareDatetime
    parent_version: str | None = Field(default=None, min_length=1)
    is_active: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.strategy_id}:{self.version}"


class ModelRegistrySnapshot(TradingModel):
    as_of: AwareDatetime
    records: tuple[ModelVersionRecord, ...]
    active_keys: tuple[str, ...]


class FeatureObservation(TradingModel):
    symbol: str
    observed_on: date
    values: dict[str, Decimal]

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class FeatureUpdateRecord(TradingModel):
    id: str = Field(min_length=1)
    as_of: AwareDatetime
    started_on: date
    ended_on: date
    symbols: tuple[str, ...]
    feature_names: tuple[str, ...]
    observation_count: int = Field(ge=0)
    latest_observations: tuple[FeatureObservation, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbols", "feature_names")
    @classmethod
    def _require_non_empty_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("value cannot be empty")
        return values


class CandidateSpec(TradingModel):
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    hypothesis: str = Field(min_length=1)
    parent_version: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateTrainingRecord(TradingModel):
    candidate: ModelVersionRecord
    trained_at: AwareDatetime
    feature_update_id: str = Field(min_length=1)
    training_notes: str = Field(min_length=1)


class WalkForwardFold(TradingModel):
    index: int = Field(ge=0)
    train_start: date
    train_end: date
    test_start: date
    test_end: date


class WalkForwardMetrics(TradingModel):
    net_total_return: float
    benchmark_total_return: float
    excess_return: float
    annualized_volatility: float
    max_drawdown: float
    trade_count: int = Field(ge=0)
    turnover: float
    score: float


class WalkForwardFoldResult(TradingModel):
    fold: WalkForwardFold
    metrics: WalkForwardMetrics


class CandidateEvaluation(TradingModel):
    model: ModelVersionRecord
    fold_results: tuple[WalkForwardFoldResult, ...]
    aggregate_score: float
    aggregate_excess_return: float
    aggregate_max_drawdown: float
    passed: bool


class ChampionChallengerComparison(TradingModel):
    champion: ModelVersionRecord
    challenger: ModelVersionRecord
    champion_score: float
    challenger_score: float
    score_delta: float
    recommendation: PromotionAction
    rationale: str = Field(min_length=1)


class PromotionRecommendation(TradingModel):
    action: PromotionAction
    model: ModelVersionRecord
    target_state: ModelRegistryState | None = None
    manual_review_required: bool = True
    confidence: float = Field(default=0, ge=0, le=1)
    rationale: str = Field(min_length=1)
    evidence: tuple[str, ...]


class NightlyLearningRun(TradingModel):
    id: str = Field(min_length=1)
    as_of: AwareDatetime
    feature_update: FeatureUpdateRecord
    trained_candidates: tuple[CandidateTrainingRecord, ...]
    champion_evaluation: CandidateEvaluation
    candidate_evaluations: tuple[CandidateEvaluation, ...]
    comparisons: tuple[ChampionChallengerComparison, ...]
    recommendations: tuple[PromotionRecommendation, ...]
    registry_before: ModelRegistrySnapshot
    registry_after: ModelRegistrySnapshot
    active_model_unchanged: bool
    research_memo: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NightlyLearningConfig(TradingModel):
    train_window_days: int = Field(default=20, gt=0)
    test_window_days: int = Field(default=10, gt=0)
    max_folds: int = Field(default=3, gt=0)
    min_score_delta_for_shadow: float = 0.0
    min_average_excess_return: float = 0.0
    max_drawdown_floor: float = -0.25
    auto_shadow_approved_candidates: bool = False
    starting_cash: Decimal = Decimal("100000")
    slippage_bps: Decimal = Decimal("5")
