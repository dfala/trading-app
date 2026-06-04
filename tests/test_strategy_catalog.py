from __future__ import annotations

from decimal import Decimal

import pytest

from trading_app.strategies import (
    BenchmarkRelativeStrengthETFStrategy,
    CashRotationETFStrategy,
    DefensiveRegimeSwitchETFStrategy,
    MarketDrawdownCircuitBreakerStrategy,
    MeanReversionETFStrategy,
    MonthlySectorMomentumStrategy,
    RiskManagedSemiconductorStrategy,
    StrategyAuthority,
    StrategyCadence,
    StrategyDefinition,
    StrategyFamily,
    StrategyImplementationStatus,
    TrendFollowingETFStrategy,
    VolatilityAwareETFStrategy,
    build_default_strategy_catalog,
    strategy_definition_metadata,
)


def test_strategy_definition_rejects_invalid_symbol_scope() -> None:
    with pytest.raises(ValueError, match="uppercase"):
        StrategyDefinition(
            strategy_id="bad",
            version="0.1.0",
            name="Bad Strategy",
            family=StrategyFamily.MOMENTUM,
            implementation_status=StrategyImplementationStatus.RESEARCH_IDEA,
            authority=StrategyAuthority.RESEARCH_ONLY,
            hypothesis="Invalid symbol test.",
            universe=("spy",),
            benchmark="SPY",
            data_requirements=("daily bars",),
            feature_names=("momentum",),
            trading_cadence=StrategyCadence.DAILY_CLOSE,
            holding_period="one month",
            signal_logic="rank",
            sizing_logic="equal weight",
            exit_logic="rebalance",
            risk_assumptions=("long-only",),
            failure_modes=("bad data",),
            constraints=("U.S.-listed ETFs only",),
            ai_role=("explain",),
        )


def test_monthly_sector_momentum_definition_is_complete() -> None:
    strategy = MonthlySectorMomentumStrategy(
        universe=("AAA", "BBB", "SPY"),
        lookback_days=5,
        top_n=1,
    )

    definition = strategy.definition()

    assert definition.strategy_id == strategy.strategy_id
    assert definition.version == strategy.strategy_version
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.PAPER
    assert definition.benchmark == "SPY"
    assert definition.universe == ("AAA", "BBB", "SPY")
    assert definition.parameters["lookback_days"] == 5
    assert definition.parameters["top_n"] == 1
    assert any("No margin" in item for item in definition.risk_assumptions)
    assert any("Momentum reversals" in item for item in definition.failure_modes)


def test_default_strategy_catalog_covers_research_families() -> None:
    catalog = build_default_strategy_catalog()
    definitions = catalog.all()
    implemented = catalog.implemented()
    families = {definition.family for definition in definitions}

    assert len(definitions) >= 9
    assert {definition.strategy_id for definition in implemented} == {
        "benchmark_relative_strength_etf",
        "cash_rotation_model",
        "defensive_regime_switch",
        "market_drawdown_circuit_breaker",
        "mean_reversion_etf",
        "monthly_sector_momentum",
        "risk_managed_semiconductor",
        "static_etf_allocation",
        "trend_following_etf",
        "volatility_aware_etf",
    }
    assert StrategyFamily.STATIC_ALLOCATION in families
    assert StrategyFamily.RISK_MANAGED_SEMICONDUCTOR in families
    assert StrategyFamily.MARKET_DRAWDOWN_CIRCUIT_BREAKER in families
    assert StrategyFamily.MOMENTUM in families
    assert StrategyFamily.TREND_FOLLOWING in families
    assert StrategyFamily.MEAN_REVERSION in families
    assert StrategyFamily.VOLATILITY_AWARE in families
    assert StrategyFamily.AI_EVENT_CLASSIFICATION in families
    assert all(definition.benchmark == "SPY" for definition in definitions)
    assert all(
        definition.authority == StrategyAuthority.RESEARCH_ONLY
        for definition in definitions
        if definition.implementation_status
        == StrategyImplementationStatus.RESEARCH_IDEA
    )


def test_trend_following_definition_is_complete_and_research_only() -> None:
    strategy = TrendFollowingETFStrategy(
        universe=("AAA", "BBB", "SPY"),
        trend_window_days=5,
        top_n=1,
    )

    definition = strategy.definition()

    assert definition.strategy_id == "trend_following_etf"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.TREND_FOLLOWING
    assert definition.benchmark == "SPY"
    assert definition.universe == ("AAA", "BBB", "SPY")
    assert definition.parameters["trend_window_days"] == 5
    assert definition.parameters["top_n"] == 1
    assert any("Research-only" in item for item in definition.constraints)
    assert any("Whipsaw" in item for item in definition.failure_modes)


def test_risk_managed_semiconductor_definition_is_complete_and_research_only() -> None:
    strategy = RiskManagedSemiconductorStrategy(
        sleeve_weights={"SOXX": Decimal("1")},
        risk_off_weights={"SPY": Decimal("1")},
        trend_window_days=200,
        relative_momentum_days=126,
        relative_momentum_symbols=("SPY", "QQQ"),
        volatility_window_days=63,
        target_volatility=Decimal("0.20"),
        drawdown_limit=Decimal("-0.15"),
    )

    definition = strategy.definition()

    assert definition.strategy_id == "risk_managed_semiconductor"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.RISK_MANAGED_SEMICONDUCTOR
    assert definition.benchmark == "SPY"
    assert definition.universe == ("SOXX", "QQQ")
    assert definition.parameters["sleeve_weights"] == {"SOXX": "1"}
    assert definition.parameters["risk_off_weights"] == {"SPY": "1"}
    assert definition.parameters["relative_momentum_days"] == 126
    assert any("No leverage" in item for item in definition.risk_assumptions)
    assert any("whipsaw" in item for item in definition.failure_modes)


def test_market_drawdown_circuit_breaker_definition_is_complete() -> None:
    strategy = MarketDrawdownCircuitBreakerStrategy(
        risk_symbols=("SOXX", "SMH"),
        risk_off_weights={},
        momentum_lookback_days=126,
        drawdown_symbols=("SPY", "QQQ"),
        drawdown_lookback_days=252,
        drawdown_threshold=Decimal("0.12"),
        triggered_risk_exposure=Decimal("0"),
    )

    definition = strategy.definition()

    assert definition.strategy_id == "market_drawdown_circuit_breaker"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.MARKET_DRAWDOWN_CIRCUIT_BREAKER
    assert definition.benchmark == "SPY"
    assert definition.universe == ("SOXX", "SMH", "QQQ")
    assert definition.parameters["risk_symbols"] == ("SOXX", "SMH")
    assert definition.parameters["drawdown_symbols"] == ("SPY", "QQQ")
    assert definition.parameters["drawdown_threshold"] == "0.12"
    assert any("No leverage" in item for item in definition.risk_assumptions)
    assert any("overfit" in item for item in definition.failure_modes)


def test_mean_reversion_definition_is_complete_and_research_only() -> None:
    strategy = MeanReversionETFStrategy(
        universe=("AAA", "BBB", "SPY"),
        reversion_window_days=2,
        trend_filter_days=3,
        top_n=1,
    )

    definition = strategy.definition()

    assert definition.strategy_id == "mean_reversion_etf"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.MEAN_REVERSION
    assert definition.benchmark == "SPY"
    assert definition.universe == ("AAA", "BBB", "SPY")
    assert definition.parameters["reversion_window_days"] == 2
    assert definition.parameters["trend_filter_days"] == 3
    assert definition.parameters["top_n"] == 1
    assert any("Research-only" in item for item in definition.constraints)
    assert any("falling knives" in item for item in definition.failure_modes)


def test_volatility_aware_definition_is_complete_and_research_only() -> None:
    strategy = VolatilityAwareETFStrategy(
        universe=("AAA", "BBB", "SPY"),
        lookback_days=5,
        volatility_window_days=3,
        top_n=1,
        max_volatility=None,
    )

    definition = strategy.definition()

    assert definition.strategy_id == "volatility_aware_etf"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.VOLATILITY_AWARE
    assert definition.benchmark == "SPY"
    assert definition.universe == ("AAA", "BBB", "SPY")
    assert definition.parameters["lookback_days"] == 5
    assert definition.parameters["volatility_window_days"] == 3
    assert definition.parameters["top_n"] == 1
    assert any("Research-only" in item for item in definition.constraints)
    assert any("Volatility can spike" in item for item in definition.failure_modes)


def test_benchmark_relative_definition_is_complete_and_research_only() -> None:
    strategy = BenchmarkRelativeStrengthETFStrategy(
        universe=("AAA", "BBB", "SPY"),
        benchmark="SPY",
        lookback_days=5,
        tracking_window_days=3,
        top_n=1,
    )

    definition = strategy.definition()

    assert definition.strategy_id == "benchmark_relative_strength_etf"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.BENCHMARK_RELATIVE
    assert definition.benchmark == "SPY"
    assert definition.universe == ("AAA", "BBB", "SPY")
    assert definition.parameters["lookback_days"] == 5
    assert definition.parameters["tracking_window_days"] == 3
    assert definition.parameters["top_n"] == 1
    assert any("Research-only" in item for item in definition.constraints)
    assert any("still decline" in item for item in definition.failure_modes)


def test_defensive_regime_definition_is_complete_and_research_only() -> None:
    strategy = DefensiveRegimeSwitchETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        defensive_symbols=("BBB", "CCC"),
        benchmark="SPY",
        regime_lookback_days=5,
        risk_on_top_n=2,
        risk_off_top_n=1,
    )

    definition = strategy.definition()

    assert definition.strategy_id == "defensive_regime_switch"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.DEFENSIVE_REGIME
    assert definition.benchmark == "SPY"
    assert definition.universe == ("AAA", "BBB", "CCC")
    assert definition.parameters["defensive_symbols"] == ("BBB", "CCC")
    assert definition.parameters["regime_lookback_days"] == 5
    assert definition.parameters["risk_on_top_n"] == 2
    assert definition.parameters["risk_off_top_n"] == 1
    assert any("Research-only" in item for item in definition.constraints)
    assert any("False defensive signals" in item for item in definition.failure_modes)


def test_cash_rotation_definition_is_complete_and_research_only() -> None:
    strategy = CashRotationETFStrategy(
        universe=("AAA", "BBB", "CCC"),
        lookback_days=5,
        top_n=2,
        min_breadth=Decimal("0.50"),
        min_average_top_return=Decimal("0.03"),
    )

    definition = strategy.definition()

    assert definition.strategy_id == "cash_rotation_model"
    assert definition.implementation_status == StrategyImplementationStatus.IMPLEMENTED
    assert definition.authority == StrategyAuthority.RESEARCH_ONLY
    assert definition.family == StrategyFamily.CASH_ROTATION
    assert definition.benchmark == "SPY"
    assert definition.universe == ("AAA", "BBB", "CCC")
    assert definition.parameters["lookback_days"] == 5
    assert definition.parameters["top_n"] == 2
    assert definition.parameters["min_breadth"] == "0.50"
    assert any("Research-only" in item for item in definition.constraints)
    assert any("idle cash" in item for item in definition.failure_modes)


def test_strategy_definition_metadata_is_json_safe() -> None:
    definition = MonthlySectorMomentumStrategy(
        universe=("AAA", "BBB"),
        lookback_days=5,
        top_n=1,
    ).definition(authority=StrategyAuthority.RESEARCH_ONLY)

    metadata = strategy_definition_metadata(definition)

    assert metadata["strategy_definition"]["strategy_id"] == "monthly_sector_momentum"
    assert metadata["strategy_definition"]["authority"] == "research_only"
    assert metadata["strategy_definition"]["universe"] == ["AAA", "BBB"]
