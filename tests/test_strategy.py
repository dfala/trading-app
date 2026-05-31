from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, DataFeed
from trading_app.strategies.benchmark_relative import (
    BenchmarkRelativeStrengthETFStrategy,
)
from trading_app.strategies.cash_rotation import CashRotationETFStrategy
from trading_app.strategies.defensive_regime import DefensiveRegimeSwitchETFStrategy
from trading_app.strategies.mean_reversion import MeanReversionETFStrategy
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy
from trading_app.strategies.trend_following import TrendFollowingETFStrategy
from trading_app.strategies.volatility_aware import VolatilityAwareETFStrategy


def make_bar(symbol: str, trading_date: date, close: str) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year, trading_date.month, trading_date.day, 21, tzinfo=UTC
        ),
        ingested_at=datetime(2024, 12, 31, 23, tzinfo=UTC),
        open_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        close_price=Decimal(close),
        volume=Decimal("1000000"),
        source="test",
        data_feed=DataFeed.IEX,
    )


def test_monthly_sector_momentum_uses_only_prior_data() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "101"),
        make_bar("AAA", date(2024, 1, 3), "102"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "110"),
        make_bar("BBB", date(2024, 1, 3), "120"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "101"),
        make_bar("CCC", date(2024, 1, 3), "102"),
        make_bar("CCC", date(2024, 1, 4), "1000"),
    ]
    strategy = MonthlySectorMomentumStrategy(
        universe=("AAA", "BBB", "CCC"), lookback_days=2, top_n=2
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"BBB": Decimal("0.5"), "CCC": Decimal("0.5")}


def test_monthly_sector_momentum_excludes_symbols_with_missing_lookback() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "101"),
        make_bar("AAA", date(2024, 1, 3), "102"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "110"),
    ]
    strategy = MonthlySectorMomentumStrategy(
        universe=("AAA", "BBB"), lookback_days=2, top_n=1
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"AAA": Decimal("1")}


def test_trend_following_uses_only_prior_data_and_positive_trends() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "101"),
        make_bar("AAA", date(2024, 1, 3), "103"),
        make_bar("AAA", date(2024, 1, 4), "104"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "99"),
        make_bar("BBB", date(2024, 1, 3), "98"),
        make_bar("BBB", date(2024, 1, 4), "97"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "100"),
        make_bar("CCC", date(2024, 1, 3), "100"),
        make_bar("CCC", date(2024, 1, 4), "1000"),
    ]
    strategy = TrendFollowingETFStrategy(
        universe=("AAA", "BBB", "CCC"), trend_window_days=2, top_n=2
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"AAA": Decimal("1")}


def test_trend_following_excludes_missing_and_below_average_symbols() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "110"),
        make_bar("AAA", date(2024, 1, 3), "105"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "101"),
    ]
    strategy = TrendFollowingETFStrategy(
        universe=("AAA", "BBB"), trend_window_days=2, top_n=1
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {}


def test_mean_reversion_uses_prior_data_and_selects_oversold_trend_symbols() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "110"),
        make_bar("AAA", date(2024, 1, 3), "108"),
        make_bar("AAA", date(2024, 1, 4), "104"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "103"),
        make_bar("BBB", date(2024, 1, 3), "102"),
        make_bar("BBB", date(2024, 1, 4), "101"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "100"),
        make_bar("CCC", date(2024, 1, 3), "100"),
        make_bar("CCC", date(2024, 1, 4), "1000"),
    ]
    strategy = MeanReversionETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        reversion_window_days=1,
        trend_filter_days=3,
        top_n=1,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"AAA": Decimal("1")}


def test_mean_reversion_excludes_missing_and_broken_trend_symbols() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "90"),
        make_bar("AAA", date(2024, 1, 3), "80"),
        make_bar("AAA", date(2024, 1, 4), "70"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "99"),
    ]
    strategy = MeanReversionETFStrategy(
        universe=("AAA", "BBB"),
        reversion_window_days=1,
        trend_filter_days=3,
        top_n=1,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 5))

    assert targets == {}


def test_volatility_aware_uses_prior_data_and_scores_positive_smooth_trends() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "101"),
        make_bar("AAA", date(2024, 1, 3), "102"),
        make_bar("AAA", date(2024, 1, 4), "103"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "110"),
        make_bar("BBB", date(2024, 1, 3), "90"),
        make_bar("BBB", date(2024, 1, 4), "120"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "100"),
        make_bar("CCC", date(2024, 1, 3), "100"),
        make_bar("CCC", date(2024, 1, 4), "1000"),
    ]
    strategy = VolatilityAwareETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        lookback_days=2,
        volatility_window_days=2,
        top_n=1,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"AAA": Decimal("1")}


def test_volatility_aware_excludes_missing_and_high_volatility_symbols() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "101"),
        make_bar("AAA", date(2024, 1, 3), "102"),
        make_bar("AAA", date(2024, 1, 4), "103"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "120"),
        make_bar("BBB", date(2024, 1, 3), "90"),
        make_bar("BBB", date(2024, 1, 4), "140"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "101"),
    ]
    strategy = VolatilityAwareETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        lookback_days=2,
        volatility_window_days=2,
        top_n=2,
        max_volatility=Decimal("0.05"),
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 5))

    assert targets == {"AAA": Decimal("1")}


def test_benchmark_relative_uses_prior_data_and_selects_relative_strength() -> None:
    bars = [
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
        make_bar("SPY", date(2024, 1, 4), "103"),
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "102"),
        make_bar("AAA", date(2024, 1, 3), "104"),
        make_bar("AAA", date(2024, 1, 4), "106"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "101"),
        make_bar("BBB", date(2024, 1, 3), "101"),
        make_bar("BBB", date(2024, 1, 4), "101"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "100"),
        make_bar("CCC", date(2024, 1, 3), "100"),
        make_bar("CCC", date(2024, 1, 4), "100"),
        make_bar("CCC", date(2024, 1, 5), "1000"),
    ]
    strategy = BenchmarkRelativeStrengthETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        lookback_days=2,
        tracking_window_days=2,
        top_n=1,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 5))

    assert targets == {"AAA": Decimal("1")}


def test_benchmark_relative_excludes_missing_benchmark_and_underperformers() -> None:
    bars = [
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "103"),
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "101"),
        make_bar("AAA", date(2024, 1, 3), "102"),
    ]
    strategy = BenchmarkRelativeStrengthETFStrategy(
        universe=("AAA", "BBB"),
        lookback_days=2,
        tracking_window_days=2,
        top_n=1,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {}


def test_defensive_regime_uses_prior_data_and_selects_risk_on_momentum() -> None:
    bars = [
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "102"),
        make_bar("SPY", date(2024, 1, 3), "104"),
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "110"),
        make_bar("AAA", date(2024, 1, 3), "120"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "103"),
        make_bar("BBB", date(2024, 1, 3), "104"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "100"),
        make_bar("CCC", date(2024, 1, 3), "100"),
        make_bar("CCC", date(2024, 1, 4), "1000"),
    ]
    strategy = DefensiveRegimeSwitchETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        defensive_symbols=("BBB", "CCC"),
        regime_lookback_days=2,
        risk_on_top_n=2,
        risk_off_top_n=1,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"AAA": Decimal("0.5"), "BBB": Decimal("0.5")}


def test_defensive_regime_switches_to_defensive_symbols_when_spy_is_weak() -> None:
    bars = [
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "96"),
        make_bar("SPY", date(2024, 1, 3), "90"),
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "120"),
        make_bar("AAA", date(2024, 1, 3), "130"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "101"),
        make_bar("BBB", date(2024, 1, 3), "102"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "99"),
        make_bar("CCC", date(2024, 1, 3), "98"),
    ]
    strategy = DefensiveRegimeSwitchETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        defensive_symbols=("BBB", "CCC"),
        regime_lookback_days=2,
        risk_on_top_n=1,
        risk_off_top_n=2,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"BBB": Decimal("1")}


def test_defensive_regime_returns_cash_when_no_defensive_candidate_qualifies() -> None:
    bars = [
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "96"),
        make_bar("SPY", date(2024, 1, 3), "90"),
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "120"),
        make_bar("AAA", date(2024, 1, 3), "130"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "98"),
        make_bar("BBB", date(2024, 1, 3), "96"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "99"),
        make_bar("CCC", date(2024, 1, 3), "98"),
    ]
    strategy = DefensiveRegimeSwitchETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        defensive_symbols=("BBB", "CCC"),
        regime_lookback_days=2,
        risk_on_top_n=1,
        risk_off_top_n=2,
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {}


def test_cash_rotation_uses_prior_data_and_invests_when_opportunity_is_strong() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "110"),
        make_bar("AAA", date(2024, 1, 3), "120"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "103"),
        make_bar("BBB", date(2024, 1, 3), "106"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "98"),
        make_bar("CCC", date(2024, 1, 3), "96"),
        make_bar("CCC", date(2024, 1, 4), "1000"),
    ]
    strategy = CashRotationETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        lookback_days=2,
        top_n=2,
        min_breadth=Decimal("0.50"),
        min_average_top_return=Decimal("0.02"),
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {"AAA": Decimal("0.5"), "BBB": Decimal("0.5")}


def test_cash_rotation_returns_cash_when_breadth_is_weak() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "105"),
        make_bar("AAA", date(2024, 1, 3), "110"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "98"),
        make_bar("BBB", date(2024, 1, 3), "96"),
        make_bar("CCC", date(2024, 1, 1), "100"),
        make_bar("CCC", date(2024, 1, 2), "99"),
        make_bar("CCC", date(2024, 1, 3), "98"),
    ]
    strategy = CashRotationETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        lookback_days=2,
        top_n=1,
        min_breadth=Decimal("0.50"),
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {}


def test_cash_rotation_returns_cash_when_top_returns_are_too_small() -> None:
    bars = [
        make_bar("AAA", date(2024, 1, 1), "100"),
        make_bar("AAA", date(2024, 1, 2), "101"),
        make_bar("AAA", date(2024, 1, 3), "102"),
        make_bar("BBB", date(2024, 1, 1), "100"),
        make_bar("BBB", date(2024, 1, 2), "100.5"),
        make_bar("BBB", date(2024, 1, 3), "101"),
    ]
    strategy = CashRotationETFStrategy(
        universe=("AAA", "BBB"),
        lookback_days=2,
        top_n=2,
        min_breadth=Decimal("1"),
        min_average_top_return=Decimal("0.05"),
    )

    targets = strategy.generate_targets(bars, as_of=date(2024, 1, 4))

    assert targets == {}
