"""Portfolio-level governance for model replay candidates."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from statistics import mean
from typing import Iterable

from pydantic import Field

from trading_app.research.replay import ReplayDecision
from trading_app.schemas import TradingModel, validate_symbol

SEMICONDUCTOR_PROXY_SYMBOLS = frozenset(
    validate_symbol(symbol)
    for symbol in (
        "SMH",
        "SOXX",
        "SOXQ",
        "PSI",
        "XSD",
        "SOXL",
        "SOXS",
        "NVDA",
        "AMD",
        "AVGO",
        "MU",
        "MRVL",
        "QCOM",
        "INTC",
        "AMAT",
        "LRCX",
        "KLAC",
        "TSM",
        "ASML",
    )
)
MATERIAL_SEMICONDUCTOR_EXPOSURE = 0.25
SECTOR_SLEEVE_AVERAGE_EXPOSURE = 0.25
SECTOR_SLEEVE_PEAK_EXPOSURE = 0.50
SECTOR_SLEEVE_MATERIAL_DAY_RATIO = 0.35


class PortfolioGovernanceClassification(StrEnum):
    PORTFOLIO_CANDIDATE = "portfolio_candidate"
    SECTOR_SLEEVE = "sector_sleeve"
    LATE_ENTRY_REVIEW = "late_entry_review"
    RESEARCH_ONLY = "research_only"
    UNKNOWN = "unknown"


class PortfolioGovernanceProfile(TradingModel):
    classification: PortfolioGovernanceClassification
    champion_eligible: bool
    average_semiconductor_exposure: float = Field(ge=0)
    peak_semiconductor_exposure: float = Field(ge=0)
    material_semiconductor_exposure_days: int = Field(ge=0)
    material_semiconductor_exposure_ratio: float = Field(ge=0)
    exposure_decision_count: int = Field(ge=0)
    notes: tuple[str, ...] = ()


def build_portfolio_governance_profile(
    *,
    model_key: str,
    symbol_universe: Iterable[str],
    decisions: tuple[ReplayDecision, ...],
    late_entry_risk: bool,
    late_entry_risk_reason: str | None,
) -> PortfolioGovernanceProfile:
    exposures = tuple(_semiconductor_exposure(decision) for decision in decisions)
    average_exposure = mean(exposures) if exposures else 0.0
    peak_exposure = max(exposures) if exposures else 0.0
    material_days = sum(
        1 for exposure in exposures if exposure >= MATERIAL_SEMICONDUCTOR_EXPOSURE
    )
    material_ratio = material_days / len(exposures) if exposures else 0.0
    normalized_universe = {validate_symbol(symbol) for symbol in symbol_universe}
    semis_in_universe = sorted(normalized_universe & SEMICONDUCTOR_PROXY_SYMBOLS)
    notes: list[str] = []
    if late_entry_risk:
        if late_entry_risk_reason:
            notes.append(late_entry_risk_reason)
        return PortfolioGovernanceProfile(
            classification=PortfolioGovernanceClassification.LATE_ENTRY_REVIEW,
            champion_eligible=False,
            average_semiconductor_exposure=average_exposure,
            peak_semiconductor_exposure=peak_exposure,
            material_semiconductor_exposure_days=material_days,
            material_semiconductor_exposure_ratio=material_ratio,
            exposure_decision_count=len(exposures),
            notes=tuple(notes or ("Late-entry concentration review required.",)),
        )

    if _is_baseline_or_control_model(model_key):
        return PortfolioGovernanceProfile(
            classification=PortfolioGovernanceClassification.RESEARCH_ONLY,
            champion_eligible=False,
            average_semiconductor_exposure=average_exposure,
            peak_semiconductor_exposure=peak_exposure,
            material_semiconductor_exposure_days=material_days,
            material_semiconductor_exposure_ratio=material_ratio,
            exposure_decision_count=len(exposures),
            notes=("Benchmark/control model; not eligible for champion authority.",),
        )

    sector_sleeve = (
        model_key.startswith("risk_managed_semiconductor:")
        or model_key.startswith("market_drawdown_circuit_breaker:")
        or average_exposure >= SECTOR_SLEEVE_AVERAGE_EXPOSURE
        or (
            peak_exposure >= SECTOR_SLEEVE_PEAK_EXPOSURE
            and material_ratio >= SECTOR_SLEEVE_MATERIAL_DAY_RATIO
        )
    )
    if sector_sleeve:
        if semis_in_universe:
            notes.append(
                "Semiconductor proxy exposure is concentrated in "
                f"{', '.join(semis_in_universe)}."
            )
        notes.append(
            "Treat as a capped sector sleeve; compare against SMH/SOXX before "
            "allocating portfolio risk."
        )
        return PortfolioGovernanceProfile(
            classification=PortfolioGovernanceClassification.SECTOR_SLEEVE,
            champion_eligible=False,
            average_semiconductor_exposure=average_exposure,
            peak_semiconductor_exposure=peak_exposure,
            material_semiconductor_exposure_days=material_days,
            material_semiconductor_exposure_ratio=material_ratio,
            exposure_decision_count=len(exposures),
            notes=tuple(notes),
        )

    return PortfolioGovernanceProfile(
        classification=PortfolioGovernanceClassification.PORTFOLIO_CANDIDATE,
        champion_eligible=True,
        average_semiconductor_exposure=average_exposure,
        peak_semiconductor_exposure=peak_exposure,
        material_semiconductor_exposure_days=material_days,
        material_semiconductor_exposure_ratio=material_ratio,
        exposure_decision_count=len(exposures),
        notes=("Broad enough for portfolio-candidate review.",),
    )


def _semiconductor_exposure(decision: ReplayDecision) -> float:
    return float(
        sum(
            (
                abs(weight)
                for symbol, weight in decision.target_weights.items()
                if validate_symbol(symbol) in SEMICONDUCTOR_PROXY_SYMBOLS
            ),
            Decimal("0"),
        )
    )


def _is_baseline_or_control_model(model_key: str) -> bool:
    return model_key.startswith("static_etf_allocation:") or model_key.endswith(
        "-no-breaker"
    )
