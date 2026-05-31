"""Research-only ETF trend-following strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyDefinition,
    trend_following_etf_definition,
)


class TrendFollowingETFStrategy:
    """Select ETFs with persistent positive trend using prior completed bars."""

    strategy_id = "trend_following_etf"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
        trend_window_days: int = 63,
        top_n: int = 3,
        min_trend_return: Decimal = Decimal("0"),
    ) -> None:
        if trend_window_days <= 0:
            raise ValueError("trend_window_days must be positive")
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if top_n > len(universe):
            raise ValueError("top_n cannot exceed universe size")

        self.universe = tuple(validate_symbol(symbol) for symbol in universe)
        self.trend_window_days = trend_window_days
        self.top_n = top_n
        self.min_trend_return = min_trend_return

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
        for symbol, symbol_bars in bars_by_symbol.items():
            sorted_bars = sorted(symbol_bars, key=lambda bar: bar.trading_date)
            if len(sorted_bars) <= self.trend_window_days:
                continue
            recent_window = sorted_bars[-self.trend_window_days :]
            recent = sorted_bars[-1]
            lookback = sorted_bars[-(self.trend_window_days + 1)]
            average_close = sum(
                (bar.close_price for bar in recent_window), Decimal("0")
            ) / Decimal(len(recent_window))
            trend_return = recent.close_price / lookback.close_price - Decimal("1")
            if trend_return <= self.min_trend_return:
                continue
            if recent.close_price <= average_close:
                continue
            scores.append((trend_return, symbol))

        if not scores:
            return {}

        selected = [
            symbol
            for _, symbol in sorted(
                scores, key=lambda item: (item[0], item[1]), reverse=True
            )[: self.top_n]
        ]
        weight = Decimal("1") / Decimal(len(selected))
        return {symbol: weight for symbol in selected}

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return trend_following_etf_definition(
            version=self.strategy_version,
            universe=self.universe,
            trend_window_days=self.trend_window_days,
            top_n=self.top_n,
            min_trend_return=str(self.min_trend_return),
            authority=authority,
        )
