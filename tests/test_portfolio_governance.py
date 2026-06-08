from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from trading_app.research.portfolio_governance import (
    PortfolioGovernanceClassification,
    build_portfolio_governance_profile,
)
from trading_app.research.replay import ReplayDecision, ReplayPolicyKind


def test_semiconductor_sleeve_is_not_champion_eligible() -> None:
    profile = build_portfolio_governance_profile(
        model_key="risk_managed_semiconductor:vol-smh-v63-t020-off-cash",
        symbol_universe=("SMH", "SOXX", "QQQ"),
        decisions=(
            _decision({"SMH": Decimal("0.75"), "QQQ": Decimal("0.25")}),
            _decision({"SOXX": Decimal("0.60"), "QQQ": Decimal("0.40")}),
        ),
        late_entry_risk=False,
        late_entry_risk_reason=None,
    )

    assert profile.classification == PortfolioGovernanceClassification.SECTOR_SLEEVE
    assert not profile.champion_eligible
    assert profile.average_semiconductor_exposure == pytest.approx(0.675)
    assert profile.peak_semiconductor_exposure == pytest.approx(0.75)
    assert profile.material_semiconductor_exposure_ratio == pytest.approx(1.0)
    assert "capped sector sleeve" in " ".join(profile.notes)


def test_broad_model_remains_portfolio_candidate() -> None:
    profile = build_portfolio_governance_profile(
        model_key="sector_etf_momentum:grid-l63-n3",
        symbol_universe=("SPY", "QQQ", "XLK"),
        decisions=(
            _decision({"SPY": Decimal("0.45"), "QQQ": Decimal("0.35")}),
            _decision({"SPY": Decimal("0.50"), "XLK": Decimal("0.30")}),
        ),
        late_entry_risk=False,
        late_entry_risk_reason=None,
    )

    assert profile.classification == PortfolioGovernanceClassification.PORTFOLIO_CANDIDATE
    assert profile.champion_eligible
    assert profile.average_semiconductor_exposure == 0.0
    assert profile.peak_semiconductor_exposure == 0.0


def test_late_entry_risk_blocks_champion_review_before_sector_classification() -> None:
    profile = build_portfolio_governance_profile(
        model_key="sector_etf_momentum:grid-l63-n3",
        symbol_universe=("SPY", "QQQ", "SMH"),
        decisions=(_decision({"SPY": Decimal("0.80"), "SMH": Decimal("0.20")}),),
        late_entry_risk=True,
        late_entry_risk_reason=(
            "Latest 252 trading days account for 78.2% of full-period excess return."
        ),
    )

    assert profile.classification == PortfolioGovernanceClassification.LATE_ENTRY_REVIEW
    assert not profile.champion_eligible
    assert profile.notes == (
        "Latest 252 trading days account for 78.2% of full-period excess return.",
    )


def _decision(target_weights: dict[str, Decimal]) -> ReplayDecision:
    return ReplayDecision(
        id="decision-1",
        run_id="test-run",
        sequence_index=0,
        as_of=date(2026, 6, 1),
        policy_key="test-policy",
        policy_kind=ReplayPolicyKind.STRATEGY,
        visible_data_start=None,
        visible_data_end=None,
        feature_snapshot_hash="hash",
        target_weights=target_weights,
        order_plans=(),
        explanation="test decision",
    )
