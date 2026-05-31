"""Research-only volatility-aware ETF allocation strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyDefinition,
    volatility_aware_etf_definition,
)


class VolatilityAwareETFStrategy:
    """Rank positive-trend ETFs by return per unit of recent volatility."""

    strategy_id = "volatility_aware_etf"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
        lookback_days: int = 63,
        volatility_window_days: int = 21,
        top_n: int = 3,
        min_trailing_return: Decimal = Decimal("0"),
        max_volatility: Decimal | None = None,
        volatility_floor: Decimal = Decimal("0.000001"),
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if volatility_window_days <= 0:
            raise ValueError("volatility_window_days must be positive")
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if top_n > len(universe):
            raise ValueError("top_n cannot exceed universe size")
        if max_volatility is not None and max_volatility <= 0:
            raise ValueError("max_volatility must be positive")
        if volatility_floor <= 0:
            raise ValueError("volatility_floor must be positive")

        self.universe = tuple(validate_symbol(symbol) for symbol in universe)
        self.lookback_days = lookback_days
        self.volatility_window_days = volatility_window_days
        self.top_n = top_n
        self.min_trailing_return = min_trailing_return
        self.max_volatility = max_volatility
        self.volatility_floor = volatility_floor

    def generate_targets(
        self, bars: list[DailyBar] | tuple[DailyBar, ...], as_of: date | datetime
    ) -> dict[str, Decimal]:
        """Generate inverse-volatility weights using completed prior bars."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        bars_by_symbol: dict[str, list[DailyBar]] = {
            symbol: [] for symbol in self.universe
        }
        for bar in bars:
            if bar.symbol in bars_by_symbol and bar.trading_date < as_of_date:
                bars_by_symbol[bar.symbol].append(bar)

        candidates: list[tuple[Decimal, Decimal, str]] = []
        minimum_history = max(self.lookback_days, self.volatility_window_days) + 1
        for symbol, symbol_bars in bars_by_symbol.items():
            sorted_bars = sorted(symbol_bars, key=lambda bar: bar.trading_date)
            if len(sorted_bars) < minimum_history:
                continue

            recent = sorted_bars[-1]
            lookback = sorted_bars[-(self.lookback_days + 1)]
            trailing_return = recent.close_price / lookback.close_price - Decimal("1")
            if trailing_return <= self.min_trailing_return:
                continue

            volatility_proxy = _average_absolute_daily_return(
                sorted_bars[-(self.volatility_window_days + 1) :]
            )
            if (
                self.max_volatility is not None
                and volatility_proxy > self.max_volatility
            ):
                continue

            volatility = max(volatility_proxy, self.volatility_floor)
            risk_adjusted_score = trailing_return / volatility
            candidates.append((risk_adjusted_score, volatility, symbol))

        if not candidates:
            return {}

        selected = sorted(
            candidates, key=lambda item: (item[0], item[2]), reverse=True
        )[: self.top_n]
        inverse_volatility = {
            symbol: Decimal("1") / volatility for _, volatility, symbol in selected
        }
        total_inverse_volatility = sum(inverse_volatility.values(), Decimal("0"))
        return {
            symbol: weight / total_inverse_volatility
            for symbol, weight in sorted(inverse_volatility.items())
        }

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return volatility_aware_etf_definition(
            version=self.strategy_version,
            universe=self.universe,
            lookback_days=self.lookback_days,
            volatility_window_days=self.volatility_window_days,
            top_n=self.top_n,
            min_trailing_return=str(self.min_trailing_return),
            max_volatility=(
                str(self.max_volatility) if self.max_volatility is not None else None
            ),
            volatility_floor=str(self.volatility_floor),
            authority=authority,
        )


def _average_absolute_daily_return(bars: list[DailyBar]) -> Decimal:
    total = Decimal("0")
    observations = 0
    for previous, current in zip(bars, bars[1:], strict=False):
        total += abs(current.close_price / previous.close_price - Decimal("1"))
        observations += 1
    if observations == 0:
        return Decimal("0")
    return total / Decimal(observations)
