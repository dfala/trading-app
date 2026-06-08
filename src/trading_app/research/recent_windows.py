"""Recent-window concentration checks for replay return curves."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

RECENT_WINDOW_TRADING_DAYS = (21, 63, 126, 252)
LATE_ENTRY_EXCESS_SHARE_THRESHOLDS = {
    21: 0.35,
    63: 0.35,
    126: 0.50,
    252: 0.70,
}


@dataclass(frozen=True)
class ReturnCurvePoint:
    trading_date: date
    model_return: float
    benchmark_return: float
    excess_return: float


@dataclass(frozen=True)
class RecentWindowAssessment:
    trading_days: int
    start_date: date
    end_date: date
    model_return_delta: float
    benchmark_return_delta: float
    excess_return_delta: float
    excess_contribution_share: float | None
    late_entry_risk: bool


def return_curve_points_from_equity_curve(
    equity_curve: Iterable,
    *,
    starting_cash: Decimal,
) -> tuple[ReturnCurvePoint, ...]:
    points: list[ReturnCurvePoint] = []
    for point in equity_curve:
        model_return = point.equity / starting_cash - Decimal("1")
        benchmark_return = point.benchmark_equity / starting_cash - Decimal("1")
        points.append(
            ReturnCurvePoint(
                trading_date=point.trading_date,
                model_return=float(model_return),
                benchmark_return=float(benchmark_return),
                excess_return=float(model_return - benchmark_return),
            )
        )
    return tuple(points)


def assess_recent_window_concentration(
    points: tuple[ReturnCurvePoint, ...],
    *,
    windows: tuple[int, ...] = RECENT_WINDOW_TRADING_DAYS,
    share_thresholds: dict[int, float] = LATE_ENTRY_EXCESS_SHARE_THRESHOLDS,
) -> tuple[RecentWindowAssessment, ...]:
    if not points:
        return ()
    last = points[-1]
    full_excess = last.excess_return
    assessments: list[RecentWindowAssessment] = []
    for trading_days in windows:
        if len(points) <= trading_days:
            continue
        start = points[-(trading_days + 1)]
        excess_delta = last.excess_return - start.excess_return
        share = (
            excess_delta / full_excess
            if abs(full_excess) > 0.000000001
            else None
        )
        share_threshold = share_thresholds.get(trading_days)
        late_entry_risk = (
            share_threshold is not None
            and full_excess > 0
            and excess_delta > 0
            and share is not None
            and share >= share_threshold
        )
        assessments.append(
            RecentWindowAssessment(
                trading_days=trading_days,
                start_date=start.trading_date,
                end_date=last.trading_date,
                model_return_delta=last.model_return - start.model_return,
                benchmark_return_delta=(
                    last.benchmark_return - start.benchmark_return
                ),
                excess_return_delta=excess_delta,
                excess_contribution_share=share,
                late_entry_risk=late_entry_risk,
            )
        )
    return tuple(assessments)


def recent_window_map(
    assessments: tuple[RecentWindowAssessment, ...],
    attr: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for assessment in assessments:
        value = getattr(assessment, attr)
        if value is not None:
            values[f"{assessment.trading_days}d"] = float(value)
    return values


def late_entry_risk_summary(
    assessments: tuple[RecentWindowAssessment, ...],
) -> str | None:
    risky = [assessment for assessment in assessments if assessment.late_entry_risk]
    if not risky:
        return None
    selected = max(
        risky,
        key=lambda assessment: assessment.excess_contribution_share or 0.0,
    )
    share = selected.excess_contribution_share or 0.0
    return (
        f"Latest {selected.trading_days} trading days account for "
        f"{share:.1%} of full-period excess return; keep in late-entry review "
        "until 3/6/12-month consistency checks pass."
    )
