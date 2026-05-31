"""Model comparison arena and controlled promotion workflow."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, Field

from trading_app.learning.models import (
    ModelRegistryState,
    ModelVersionRecord,
    PromotionAction,
)
from trading_app.learning.registry import ModelRegistry, ModelRegistryError
from trading_app.schemas import TradingModel


class ModelEvidenceType(StrEnum):
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"
    SHADOW = "shadow"
    PAPER = "paper"
    POSTMORTEM = "postmortem"


class ModelMetricSet(TradingModel):
    gross_total_return: float
    net_total_return: float
    benchmark_total_return: float
    max_drawdown: float
    annualized_volatility: float
    turnover: float
    trade_count: int = Field(ge=0)
    average_holding_period_days: float = Field(ge=0)
    estimated_after_tax_total_return: float | None = None


class ModelEvidenceRecord(TradingModel):
    id: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    evidence_type: ModelEvidenceType
    recorded_at: AwareDatetime
    start_date: date
    end_date: date
    benchmark: str = Field(min_length=1)
    data_source: str = Field(min_length=1)
    metrics: ModelMetricSet
    cost_assumptions: dict[str, Any] = Field(default_factory=dict)
    tax_assumptions: dict[str, Any] = Field(default_factory=dict)
    risk_settings: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(min_length=1)
    failure_modes: tuple[str, ...] = ()


class ModelComparisonResult(TradingModel):
    champion: ModelVersionRecord
    challenger: ModelVersionRecord
    champion_evidence_id: str = Field(min_length=1)
    challenger_evidence_id: str = Field(min_length=1)
    champion_score: float
    challenger_score: float
    score_delta: float
    recommendation: PromotionAction
    rationale: str = Field(min_length=1)


class PromotionApproval(TradingModel):
    approved_by: str = Field(min_length=1)
    approved_at: AwareDatetime
    rationale: str = Field(min_length=1)


class ModelPromotionRequest(TradingModel):
    id: str = Field(min_length=1)
    model: ModelVersionRecord
    current_state: ModelRegistryState
    target_state: ModelRegistryState
    created_at: AwareDatetime
    evidence_ids: tuple[str, ...]
    recommendation: PromotionAction
    rationale: str = Field(min_length=1)
    manual_approval_required: bool = True
    approval: PromotionApproval | None = None

    @property
    def approved(self) -> bool:
        return self.approval is not None


class ModelPostmortem(TradingModel):
    id: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    recorded_at: AwareDatetime
    reason: str = Field(min_length=1)
    lessons: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class ModelArenaSnapshot(TradingModel):
    as_of: AwareDatetime
    models: tuple[ModelVersionRecord, ...]
    evidence: tuple[ModelEvidenceRecord, ...]
    comparisons: tuple[ModelComparisonResult, ...]
    promotion_requests: tuple[ModelPromotionRequest, ...]
    postmortems: tuple[ModelPostmortem, ...]


class ModelArena:
    """Compare model versions and require approval for authority increases."""

    _allowed_transitions = {
        ModelRegistryState.IDEA: {
            ModelRegistryState.BACKTEST,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.BACKTEST: {
            ModelRegistryState.VALIDATED,
            ModelRegistryState.PAUSED,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.VALIDATED: {
            ModelRegistryState.SHADOW,
            ModelRegistryState.PAUSED,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.SHADOW: {
            ModelRegistryState.PAPER,
            ModelRegistryState.PAUSED,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.PAPER: {
            ModelRegistryState.CANDIDATE_LIVE,
            ModelRegistryState.PAUSED,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.CANDIDATE_LIVE: {
            ModelRegistryState.LIVE_LIMITED,
            ModelRegistryState.PAUSED,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.LIVE_LIMITED: {
            ModelRegistryState.LIVE_SCALED,
            ModelRegistryState.PAUSED,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.LIVE_SCALED: {
            ModelRegistryState.PAUSED,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.PAUSED: {
            ModelRegistryState.SHADOW,
            ModelRegistryState.PAPER,
            ModelRegistryState.RETIRED,
        },
        ModelRegistryState.RETIRED: set(),
    }

    def __init__(self, *, registry: ModelRegistry) -> None:
        self.registry = registry
        self._evidence: dict[str, ModelEvidenceRecord] = {}
        self._comparisons: list[ModelComparisonResult] = []
        self._promotion_requests: dict[str, ModelPromotionRequest] = {}
        self._postmortems: list[ModelPostmortem] = []

    def record_evidence(self, evidence: ModelEvidenceRecord) -> ModelEvidenceRecord:
        if evidence.id in self._evidence:
            raise ModelRegistryError(f"evidence already exists: {evidence.id}")
        self._evidence[evidence.id] = evidence
        return evidence

    def compare(
        self,
        *,
        champion: ModelVersionRecord,
        challenger: ModelVersionRecord,
        champion_evidence_id: str,
        challenger_evidence_id: str,
    ) -> ModelComparisonResult:
        champion_evidence = self._require_evidence(champion_evidence_id, champion.key)
        challenger_evidence = self._require_evidence(
            challenger_evidence_id, challenger.key
        )
        champion_score = _score(champion_evidence.metrics)
        challenger_score = _score(challenger_evidence.metrics)
        score_delta = challenger_score - champion_score
        recommendation = (
            PromotionAction.PROMOTE_TO_SHADOW
            if challenger.state == ModelRegistryState.VALIDATED and score_delta > 0
            else PromotionAction.WATCH
        )
        rationale = (
            "Challenger has stronger after-cost evidence and can be reviewed for "
            "shadow mode."
            if recommendation == PromotionAction.PROMOTE_TO_SHADOW
            else "Challenger does not yet justify increased trading authority."
        )
        comparison = ModelComparisonResult(
            champion=champion,
            challenger=challenger,
            champion_evidence_id=champion_evidence_id,
            challenger_evidence_id=challenger_evidence_id,
            champion_score=champion_score,
            challenger_score=challenger_score,
            score_delta=score_delta,
            recommendation=recommendation,
            rationale=rationale,
        )
        self._comparisons.append(comparison)
        return comparison

    def request_promotion(
        self,
        *,
        request_id: str,
        strategy_id: str,
        version: str,
        target_state: ModelRegistryState,
        evidence_ids: tuple[str, ...],
        created_at: datetime,
        rationale: str,
        recommendation: PromotionAction = PromotionAction.WATCH,
    ) -> ModelPromotionRequest:
        if request_id in self._promotion_requests:
            raise ModelRegistryError(f"promotion request already exists: {request_id}")
        model = self.registry.get(strategy_id, version)
        if target_state not in self._allowed_transitions[model.state]:
            raise ModelRegistryError(
                f"invalid transition: {model.state.value} -> {target_state.value}"
            )
        if not evidence_ids:
            raise ModelRegistryError("promotion requests require evidence")
        for evidence_id in evidence_ids:
            self._require_evidence(evidence_id, model.key)

        request = ModelPromotionRequest(
            id=request_id,
            model=model,
            current_state=model.state,
            target_state=target_state,
            created_at=created_at,
            evidence_ids=evidence_ids,
            recommendation=recommendation,
            rationale=rationale,
        )
        self._promotion_requests[request.id] = request
        return request

    def approve_promotion(
        self,
        *,
        request_id: str,
        approved_by: str,
        approved_at: datetime,
        rationale: str,
    ) -> ModelPromotionRequest:
        request = self._promotion_requests.get(request_id)
        if request is None:
            raise ModelRegistryError(f"unknown promotion request: {request_id}")
        if not approved_by:
            raise ModelRegistryError("approved_by is required")
        updated_model = self.registry.transition_state(
            strategy_id=request.model.strategy_id,
            version=request.model.version,
            state=request.target_state,
        )
        approved = request.model_copy(
            update={
                "model": updated_model,
                "approval": PromotionApproval(
                    approved_by=approved_by,
                    approved_at=approved_at,
                    rationale=rationale,
                ),
            }
        )
        self._promotion_requests[request_id] = approved
        return approved

    def record_postmortem(self, postmortem: ModelPostmortem) -> ModelPostmortem:
        for evidence_id in postmortem.evidence_ids:
            self._require_evidence(evidence_id, postmortem.model_key)
        self._postmortems.append(postmortem)
        return postmortem

    def snapshot(self, *, as_of: datetime) -> ModelArenaSnapshot:
        return ModelArenaSnapshot(
            as_of=as_of,
            models=self.registry.snapshot(as_of).records,
            evidence=tuple(sorted(self._evidence.values(), key=lambda item: item.id)),
            comparisons=tuple(self._comparisons),
            promotion_requests=tuple(
                sorted(self._promotion_requests.values(), key=lambda item: item.id)
            ),
            postmortems=tuple(self._postmortems),
        )

    def _require_evidence(
        self, evidence_id: str, model_key: str
    ) -> ModelEvidenceRecord:
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            raise ModelRegistryError(f"unknown evidence: {evidence_id}")
        if evidence.model_key != model_key:
            raise ModelRegistryError(
                f"evidence {evidence_id} does not belong to {model_key}"
            )
        return evidence


def _score(metrics: ModelMetricSet) -> float:
    after_tax = metrics.estimated_after_tax_total_return
    return (
        (after_tax if after_tax is not None else metrics.net_total_return)
        - metrics.benchmark_total_return * 0.25
        - abs(metrics.max_drawdown) * 0.5
        - metrics.annualized_volatility * 0.1
        - metrics.turnover * 0.01
    )
