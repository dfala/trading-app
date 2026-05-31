"""Trading strategy implementations."""

from trading_app.strategies.benchmark_relative import (
    BenchmarkRelativeStrengthETFStrategy,
)
from trading_app.strategies.cash_rotation import CashRotationETFStrategy
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyCadence,
    StrategyCatalog,
    StrategyDefinition,
    StrategyFamily,
    StrategyImplementationStatus,
    benchmark_relative_strength_etf_definition,
    build_default_strategy_catalog,
    cash_rotation_model_definition,
    defensive_regime_switch_definition,
    mean_reversion_etf_definition,
    monthly_sector_momentum_definition,
    strategy_definition_metadata,
    trend_following_etf_definition,
    volatility_aware_etf_definition,
)
from trading_app.strategies.defensive_regime import DefensiveRegimeSwitchETFStrategy
from trading_app.strategies.mean_reversion import MeanReversionETFStrategy
from trading_app.strategies.sector_momentum import (
    DEFAULT_SECTOR_ETFS,
    MonthlySectorMomentumStrategy,
)
from trading_app.strategies.trend_following import TrendFollowingETFStrategy
from trading_app.strategies.volatility_aware import VolatilityAwareETFStrategy

__all__ = [
    "DEFAULT_SECTOR_ETFS",
    "BenchmarkRelativeStrengthETFStrategy",
    "CashRotationETFStrategy",
    "DefensiveRegimeSwitchETFStrategy",
    "MeanReversionETFStrategy",
    "MonthlySectorMomentumStrategy",
    "SECTOR_ETF_UNIVERSE",
    "StrategyAuthority",
    "StrategyCadence",
    "StrategyCatalog",
    "StrategyDefinition",
    "StrategyFamily",
    "StrategyImplementationStatus",
    "TrendFollowingETFStrategy",
    "VolatilityAwareETFStrategy",
    "benchmark_relative_strength_etf_definition",
    "build_default_strategy_catalog",
    "cash_rotation_model_definition",
    "defensive_regime_switch_definition",
    "mean_reversion_etf_definition",
    "monthly_sector_momentum_definition",
    "strategy_definition_metadata",
    "trend_following_etf_definition",
    "volatility_aware_etf_definition",
]
