from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, DataFeed
from trading_app.strategies.benchmark_relative import (
    BenchmarkRelativeStrengthETFStrategy,
)
from trading_app.strategies.cash_rotation import CashRotationETFStrategy
from trading_app.strategies.defensive_regime import DefensiveRegimeSwitchETFStrategy
from trading_app.strategies.market_drawdown_circuit_breaker import (
    MarketDrawdownCircuitBreakerStrategy,
)
from trading_app.strategies.mean_reversion import MeanReversionETFStrategy
from trading_app.strategies.risk_managed_semiconductor import (
    RiskManagedSemiconductorStrategy,
)
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy
from trading_app.strategies.static_allocation import StaticETFAllocationStrategy
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


def test_static_allocation_returns_normalized_weights_after_prior_history() -> None:
    strategy = StaticETFAllocationStrategy(
        weights={"QQQ": Decimal("2"), "XLK": Decimal("1")},
    )
    bars = [
        make_bar("QQQ", date(2024, 1, 1), "100"),
        make_bar("XLK", date(2024, 1, 1), "100"),
        make_bar("QQQ", date(2024, 1, 2), "1000"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 2))

    assert targets == {
        "QQQ": Decimal("0.6666666666666666666666666667"),
        "XLK": Decimal("0.3333333333333333333333333333"),
    }


def test_static_allocation_requires_history_for_every_symbol() -> None:
    strategy = StaticETFAllocationStrategy(
        weights={"QQQ": Decimal("1"), "XLK": Decimal("1")},
    )
    bars = [make_bar("QQQ", date(2024, 1, 1), "100")]

    assert strategy.generate_targets(bars, date(2024, 1, 2)) == {}


def test_risk_managed_semiconductor_trend_uses_only_prior_data() -> None:
    strategy = RiskManagedSemiconductorStrategy(
        sleeve_weights={"SOXX": Decimal("1")},
        trend_window_days=3,
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "101"),
        make_bar("SOXX", date(2024, 1, 3), "103"),
        make_bar("SOXX", date(2024, 1, 4), "1"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "100"),
        make_bar("SPY", date(2024, 1, 3), "100"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert targets == {"SOXX": Decimal("1")}


def test_risk_managed_semiconductor_rotates_to_benchmark_when_trend_breaks() -> None:
    strategy = RiskManagedSemiconductorStrategy(
        sleeve_weights={"SOXX": Decimal("1")},
        risk_off_weights={"SPY": Decimal("1")},
        trend_window_days=2,
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "90"),
        make_bar("SOXX", date(2024, 1, 3), "80"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert targets == {"SPY": Decimal("1")}


def test_risk_managed_semiconductor_drawdown_breaker_uses_risk_off() -> None:
    strategy = RiskManagedSemiconductorStrategy(
        sleeve_weights={"SOXX": Decimal("1")},
        risk_off_weights={"QQQ": Decimal("1")},
        trend_window_days=None,
        drawdown_limit=Decimal("-0.15"),
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "120"),
        make_bar("SOXX", date(2024, 1, 3), "90"),
        make_bar("QQQ", date(2024, 1, 1), "100"),
        make_bar("QQQ", date(2024, 1, 2), "101"),
        make_bar("QQQ", date(2024, 1, 3), "102"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert targets == {"QQQ": Decimal("1")}


def test_risk_managed_semiconductor_volatility_target_scales_sleeve() -> None:
    strategy = RiskManagedSemiconductorStrategy(
        sleeve_weights={"SMH": Decimal("1"), "SOXX": Decimal("1")},
        risk_off_weights={"SPY": Decimal("1")},
        trend_window_days=None,
        volatility_window_days=2,
        target_volatility=Decimal("0.01"),
    )
    bars = [
        make_bar("SMH", date(2024, 1, 1), "100"),
        make_bar("SMH", date(2024, 1, 2), "120"),
        make_bar("SMH", date(2024, 1, 3), "90"),
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "120"),
        make_bar("SOXX", date(2024, 1, 3), "90"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert Decimal("0") < targets["SMH"] < Decimal("0.5")
    assert Decimal("0") < targets["SOXX"] < Decimal("0.5")
    assert targets["SPY"] > Decimal("0")
    assert sum(targets.values(), Decimal("0")) == Decimal("1")


def test_risk_managed_semiconductor_soft_volatility_throttle() -> None:
    strategy = RiskManagedSemiconductorStrategy(
        sleeve_weights={"SOXX": Decimal("1")},
        risk_off_weights={"QQQ": Decimal("1")},
        trend_window_days=None,
        volatility_window_days=2,
        volatility_exposure_bands=(
            (Decimal("0.10"), Decimal("1")),
            (Decimal("4.00"), Decimal("0.50")),
            (Decimal("999"), Decimal("0")),
        ),
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "120"),
        make_bar("SOXX", date(2024, 1, 3), "90"),
        make_bar("QQQ", date(2024, 1, 1), "100"),
        make_bar("QQQ", date(2024, 1, 2), "101"),
        make_bar("QQQ", date(2024, 1, 3), "102"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert targets == {"QQQ": Decimal("0.50"), "SOXX": Decimal("0.50")}


def test_risk_managed_semiconductor_drawdown_throttle() -> None:
    strategy = RiskManagedSemiconductorStrategy(
        sleeve_weights={"SOXX": Decimal("1")},
        risk_off_weights={"QQQ": Decimal("1")},
        trend_window_days=None,
        drawdown_exposure_bands=(
            (Decimal("0.12"), Decimal("1")),
            (Decimal("0.18"), Decimal("0.75")),
            (Decimal("0.25"), Decimal("0.50")),
            (Decimal("999"), Decimal("0")),
        ),
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "120"),
        make_bar("SOXX", date(2024, 1, 3), "96"),
        make_bar("QQQ", date(2024, 1, 1), "100"),
        make_bar("QQQ", date(2024, 1, 2), "101"),
        make_bar("QQQ", date(2024, 1, 3), "102"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert targets == {"QQQ": Decimal("0.50"), "SOXX": Decimal("0.50")}


def test_market_drawdown_circuit_breaker_uses_only_prior_data() -> None:
    strategy = MarketDrawdownCircuitBreakerStrategy(
        risk_symbols=("SOXX", "SMH"),
        momentum_lookback_days=2,
        drawdown_symbols=("SPY", "QQQ"),
        drawdown_lookback_days=3,
        drawdown_threshold=Decimal("0.12"),
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "104"),
        make_bar("SOXX", date(2024, 1, 3), "108"),
        make_bar("SOXX", date(2024, 1, 4), "1"),
        make_bar("SMH", date(2024, 1, 1), "100"),
        make_bar("SMH", date(2024, 1, 2), "103"),
        make_bar("SMH", date(2024, 1, 3), "106"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
        make_bar("QQQ", date(2024, 1, 1), "100"),
        make_bar("QQQ", date(2024, 1, 2), "101"),
        make_bar("QQQ", date(2024, 1, 3), "102"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert targets == {"SOXX": Decimal("1")}


def test_market_drawdown_circuit_breaker_moves_to_cash_when_triggered() -> None:
    strategy = MarketDrawdownCircuitBreakerStrategy(
        risk_symbols=("SOXX", "SMH"),
        momentum_lookback_days=2,
        drawdown_symbols=("SPY", "QQQ"),
        drawdown_lookback_days=3,
        drawdown_threshold=Decimal("0.12"),
        triggered_risk_exposure=Decimal("0"),
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "104"),
        make_bar("SOXX", date(2024, 1, 3), "108"),
        make_bar("SMH", date(2024, 1, 1), "100"),
        make_bar("SMH", date(2024, 1, 2), "103"),
        make_bar("SMH", date(2024, 1, 3), "106"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "110"),
        make_bar("SPY", date(2024, 1, 3), "109"),
        make_bar("QQQ", date(2024, 1, 1), "100"),
        make_bar("QQQ", date(2024, 1, 2), "110"),
        make_bar("QQQ", date(2024, 1, 3), "90"),
    ]

    targets, _, metadata = strategy.generate_targets_with_metadata(
        bars,
        date(2024, 1, 4),
    )

    assert targets == {}
    assert metadata["breaker_triggered"] is True
    assert metadata["selected_risk_symbol"] == "SOXX"
    assert metadata["risk_exposure"] == "0"


def test_market_drawdown_circuit_breaker_partial_risk_and_risk_off_weights() -> None:
    strategy = MarketDrawdownCircuitBreakerStrategy(
        risk_symbols=("SOXX", "SMH"),
        risk_off_weights={"SPY": Decimal("1")},
        momentum_lookback_days=2,
        drawdown_symbols=("QQQ",),
        drawdown_lookback_days=3,
        drawdown_threshold=Decimal("0.12"),
        triggered_risk_exposure=Decimal("0.50"),
    )
    bars = [
        make_bar("SOXX", date(2024, 1, 1), "100"),
        make_bar("SOXX", date(2024, 1, 2), "104"),
        make_bar("SOXX", date(2024, 1, 3), "108"),
        make_bar("SMH", date(2024, 1, 1), "100"),
        make_bar("SMH", date(2024, 1, 2), "103"),
        make_bar("SMH", date(2024, 1, 3), "106"),
        make_bar("SPY", date(2024, 1, 1), "100"),
        make_bar("SPY", date(2024, 1, 2), "101"),
        make_bar("SPY", date(2024, 1, 3), "102"),
        make_bar("QQQ", date(2024, 1, 1), "100"),
        make_bar("QQQ", date(2024, 1, 2), "110"),
        make_bar("QQQ", date(2024, 1, 3), "90"),
    ]

    targets = strategy.generate_targets(bars, date(2024, 1, 4))

    assert targets == {"SOXX": Decimal("0.50"), "SPY": Decimal("0.50")}


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
