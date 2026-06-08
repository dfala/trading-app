from __future__ import annotations

from datetime import date, timedelta

from trading_app.research.recent_windows import (
    ReturnCurvePoint,
    assess_recent_window_concentration,
    late_entry_risk_summary,
)


def test_recent_window_concentration_flags_late_entry_risk() -> None:
    points = tuple(
        ReturnCurvePoint(
            trading_date=date(2026, 1, 1) + timedelta(days=index),
            model_return=0.10
            if index < 37
            else 0.10 + min(index - 36, 27) * 0.02,
            benchmark_return=0.02,
            excess_return=0.08
            if index < 37
            else 0.08 + min(index - 36, 27) * 0.02,
        )
        for index in range(100)
    )

    assessments = assess_recent_window_concentration(points)
    by_window = {assessment.trading_days: assessment for assessment in assessments}

    assert by_window[63].late_entry_risk
    assert by_window[63].excess_contribution_share is not None
    assert by_window[63].excess_contribution_share > 0.35
    assert "Latest 63 trading days" in (late_entry_risk_summary(assessments) or "")


def test_recent_window_concentration_flags_six_month_edge_concentration() -> None:
    points = []
    for index in range(180):
        if index < 54:
            excess = 0.45
        elif index < 117:
            excess = 0.45 + (index - 53) * (0.25 / 63)
        else:
            excess = 0.70 + (index - 116) * (0.30 / 63)
        points.append(
            ReturnCurvePoint(
                trading_date=date(2026, 1, 1) + timedelta(days=index),
                model_return=excess,
                benchmark_return=0.0,
                excess_return=excess,
            )
        )

    assessments = assess_recent_window_concentration(tuple(points))
    by_window = {assessment.trading_days: assessment for assessment in assessments}

    assert not by_window[63].late_entry_risk
    assert by_window[126].late_entry_risk
    assert by_window[126].excess_contribution_share is not None
    assert by_window[126].excess_contribution_share > 0.50
