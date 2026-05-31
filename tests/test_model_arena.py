from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from trading_app.learning import (
    ModelArena,
    ModelEvidenceRecord,
    ModelEvidenceType,
    ModelMetricSet,
    ModelPostmortem,
    ModelRegistry,
    ModelRegistryError,
    ModelRegistryState,
    ModelVersionRecord,
    PromotionAction,
)

NOW = datetime(2026, 5, 29, 23, tzinfo=UTC)


def model_record(version: str, state: ModelRegistryState) -> ModelVersionRecord:
    return ModelVersionRecord(
        strategy_id="monthly_sector_momentum",
        version=version,
        state=state,
        parameters={"lookback_days": 126},
        hypothesis=f"Version {version} sector momentum hypothesis.",
        created_at=NOW,
        is_active=version == "1.0.0",
    )


def evidence(
    evidence_id: str,
    model_key: str,
    *,
    net_return: float,
    after_tax_return: float | None = None,
) -> ModelEvidenceRecord:
    return ModelEvidenceRecord(
        id=evidence_id,
        model_key=model_key,
        evidence_type=ModelEvidenceType.WALK_FORWARD,
        recorded_at=NOW,
        start_date=date(2025, 1, 1),
        end_date=date(2026, 5, 29),
        benchmark="SPY",
        data_source="fixture",
        metrics=ModelMetricSet(
            gross_total_return=net_return + 0.01,
            net_total_return=net_return,
            benchmark_total_return=0.03,
            max_drawdown=-0.04,
            annualized_volatility=0.12,
            turnover=0.45,
            trade_count=12,
            average_holding_period_days=28,
            estimated_after_tax_total_return=after_tax_return,
        ),
        cost_assumptions={"slippage_bps": 5},
        tax_assumptions=(
            {"short_term_rate": 0.35, "long_term_rate": 0.15}
            if after_tax_return is not None
            else {}
        ),
        risk_settings={"no_short_selling": True},
        notes="Evidence was generated from deterministic fixtures.",
    )


def test_model_arena_compares_after_cost_and_after_tax_evidence() -> None:
    registry = ModelRegistry()
    champion = registry.register(model_record("1.0.0", ModelRegistryState.PAPER))
    challenger = registry.register(model_record("1.1.0", ModelRegistryState.VALIDATED))
    arena = ModelArena(registry=registry)
    arena.record_evidence(evidence("champion-evidence", champion.key, net_return=0.04))
    arena.record_evidence(
        evidence(
            "challenger-evidence",
            challenger.key,
            net_return=0.07,
            after_tax_return=0.052,
        )
    )

    comparison = arena.compare(
        champion=champion,
        challenger=challenger,
        champion_evidence_id="champion-evidence",
        challenger_evidence_id="challenger-evidence",
    )

    assert comparison.recommendation == PromotionAction.PROMOTE_TO_SHADOW
    assert comparison.challenger_score > comparison.champion_score
    assert comparison.score_delta > 0


def test_promotion_workflow_requires_evidence_and_manual_approval() -> None:
    registry = ModelRegistry()
    challenger = registry.register(model_record("1.1.0", ModelRegistryState.VALIDATED))
    arena = ModelArena(registry=registry)
    arena.record_evidence(
        evidence("challenger-evidence", challenger.key, net_return=0.06)
    )

    request = arena.request_promotion(
        request_id="promote-shadow",
        strategy_id=challenger.strategy_id,
        version=challenger.version,
        target_state=ModelRegistryState.SHADOW,
        evidence_ids=("challenger-evidence",),
        created_at=NOW,
        rationale="Evidence clears the shadow-review gate.",
        recommendation=PromotionAction.PROMOTE_TO_SHADOW,
    )

    assert request.manual_approval_required
    assert not request.approved
    assert registry.get(challenger.strategy_id, challenger.version).state == (
        ModelRegistryState.VALIDATED
    )

    approved = arena.approve_promotion(
        request_id="promote-shadow",
        approved_by="human-operator",
        approved_at=NOW,
        rationale="Approved for shadow observation only.",
    )

    assert approved.approved
    assert registry.get(challenger.strategy_id, challenger.version).state == (
        ModelRegistryState.SHADOW
    )


def test_promotion_workflow_blocks_skipped_gates_and_preserves_postmortems() -> None:
    registry = ModelRegistry()
    candidate = registry.register(model_record("1.2.0", ModelRegistryState.BACKTEST))
    arena = ModelArena(registry=registry)
    arena.record_evidence(evidence("failed-evidence", candidate.key, net_return=-0.05))

    with pytest.raises(ModelRegistryError):
        arena.request_promotion(
            request_id="skip-to-paper",
            strategy_id=candidate.strategy_id,
            version=candidate.version,
            target_state=ModelRegistryState.PAPER,
            evidence_ids=("failed-evidence",),
            created_at=NOW,
            rationale="This should not skip gates.",
        )

    arena.record_postmortem(
        ModelPostmortem(
            id="postmortem-1.2.0",
            model_key=candidate.key,
            recorded_at=NOW,
            reason="Backtest failed after realistic costs.",
            lessons=("Avoid optimizing only for gross return.",),
            evidence_ids=("failed-evidence",),
        )
    )
    snapshot = arena.snapshot(as_of=NOW)

    assert snapshot.postmortems[0].reason == "Backtest failed after realistic costs."
    assert snapshot.evidence[0].id == "failed-evidence"
