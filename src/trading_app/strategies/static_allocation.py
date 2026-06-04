"""Research-only static ETF allocation strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    StrategyAuthority,
    StrategyDefinition,
    static_etf_allocation_definition,
)


class StaticETFAllocationStrategy:
    """Maintain fixed ETF weights using only prior completed bars."""

    strategy_id = "static_etf_allocation"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        weights: dict[str, Decimal],
        benchmark: str = "SPY",
    ) -> None:
        if not weights:
            raise ValueError("weights cannot be empty")
        normalized_weights: dict[str, Decimal] = {}
        for symbol, weight in weights.items():
            normalized_symbol = validate_symbol(symbol)
            if weight <= 0:
                raise ValueError("weights must be positive")
            normalized_weights[normalized_symbol] = weight
        total_weight = sum(normalized_weights.values(), Decimal("0"))
        if total_weight <= 0:
            raise ValueError("weights must sum to a positive value")

        self.weights = {
            symbol: weight / total_weight
            for symbol, weight in sorted(normalized_weights.items())
        }
        self.universe = tuple(self.weights)
        self.benchmark = validate_symbol(benchmark)

    def generate_targets(
        self,
        bars: list[DailyBar] | tuple[DailyBar, ...],
        as_of: date | datetime,
    ) -> dict[str, Decimal]:
        """Return fixed weights once every configured ETF has prior history."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        symbols_with_history = {
            bar.symbol
            for bar in bars
            if bar.symbol in self.weights and bar.trading_date < as_of_date
        }
        if symbols_with_history != set(self.weights):
            return {}
        return dict(self.weights)

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return static_etf_allocation_definition(
            version=self.strategy_version,
            weights={symbol: str(weight) for symbol, weight in self.weights.items()},
            benchmark=self.benchmark,
            authority=authority,
        )
