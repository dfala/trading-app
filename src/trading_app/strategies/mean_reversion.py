"""Research-only ETF mean-reversion strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyDefinition,
    mean_reversion_etf_definition,
)


class MeanReversionETFStrategy:
    """Select short-term oversold ETFs that still pass a trend filter."""

    strategy_id = "mean_reversion_etf"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
        reversion_window_days: int = 5,
        trend_filter_days: int = 63,
        top_n: int = 3,
        max_short_return: Decimal = Decimal("0"),
    ) -> None:
        if reversion_window_days <= 0:
            raise ValueError("reversion_window_days must be positive")
        if trend_filter_days <= 0:
            raise ValueError("trend_filter_days must be positive")
        if trend_filter_days < reversion_window_days:
            raise ValueError("trend_filter_days must be at least reversion_window_days")
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if top_n > len(universe):
            raise ValueError("top_n cannot exceed universe size")

        self.universe = tuple(validate_symbol(symbol) for symbol in universe)
        self.reversion_window_days = reversion_window_days
        self.trend_filter_days = trend_filter_days
        self.top_n = top_n
        self.max_short_return = max_short_return

    def generate_targets(
        self, bars: list[DailyBar] | tuple[DailyBar, ...], as_of: date | datetime
    ) -> dict[str, Decimal]:
        """Generate equal-weight targets using data before the execution date."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        bars_by_symbol: dict[str, list[DailyBar]] = {
            symbol: [] for symbol in self.universe
        }
        for bar in bars:
            if bar.symbol in bars_by_symbol and bar.trading_date < as_of_date:
                bars_by_symbol[bar.symbol].append(bar)

        scores: list[tuple[Decimal, str]] = []
        minimum_history = max(self.trend_filter_days, self.reversion_window_days + 1)
        for symbol, symbol_bars in bars_by_symbol.items():
            sorted_bars = sorted(symbol_bars, key=lambda bar: bar.trading_date)
            if len(sorted_bars) < minimum_history:
                continue
            recent = sorted_bars[-1]
            reversion_lookback = sorted_bars[-(self.reversion_window_days + 1)]
            trend_window = sorted_bars[-self.trend_filter_days :]
            trend_average = sum(
                (bar.close_price for bar in trend_window), Decimal("0")
            ) / Decimal(len(trend_window))
            short_return = (
                recent.close_price / reversion_lookback.close_price - Decimal("1")
            )
            if short_return >= self.max_short_return:
                continue
            if recent.close_price <= trend_average:
                continue
            scores.append((short_return, symbol))

        if not scores:
            return {}

        selected = [
            symbol
            for _, symbol in sorted(scores, key=lambda item: (item[0], item[1]))[
                : self.top_n
            ]
        ]
        weight = Decimal("1") / Decimal(len(selected))
        return {symbol: weight for symbol in selected}

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return mean_reversion_etf_definition(
            version=self.strategy_version,
            universe=self.universe,
            reversion_window_days=self.reversion_window_days,
            trend_filter_days=self.trend_filter_days,
            top_n=self.top_n,
            max_short_return=str(self.max_short_return),
            authority=authority,
        )
