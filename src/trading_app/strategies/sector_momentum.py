"""Monthly sector ETF momentum strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyDefinition,
    monthly_sector_momentum_definition,
)

DEFAULT_SECTOR_ETFS = SECTOR_ETF_UNIVERSE


class MonthlySectorMomentumStrategy:
    """Select top sector ETFs by trailing close-to-close momentum."""

    strategy_id = "monthly_sector_momentum"
    strategy_version = "1.0.0"

    def __init__(
        self,
        *,
        universe: tuple[str, ...] = DEFAULT_SECTOR_ETFS,
        lookback_days: int = 126,
        top_n: int = 3,
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if top_n > len(universe):
            raise ValueError("top_n cannot exceed universe size")

        self.universe = tuple(validate_symbol(symbol) for symbol in universe)
        self.lookback_days = lookback_days
        self.top_n = top_n

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

        momentum_scores: list[tuple[Decimal, str]] = []
        for symbol, symbol_bars in bars_by_symbol.items():
            sorted_bars = sorted(symbol_bars, key=lambda bar: bar.trading_date)
            if len(sorted_bars) <= self.lookback_days:
                continue
            recent = sorted_bars[-1]
            lookback = sorted_bars[-(self.lookback_days + 1)]
            momentum = recent.close_price / lookback.close_price - Decimal("1")
            momentum_scores.append((momentum, symbol))

        if not momentum_scores:
            return {}

        selected = [
            symbol
            for _, symbol in sorted(
                momentum_scores, key=lambda item: (item[0], item[1]), reverse=True
            )[: self.top_n]
        ]
        weight = Decimal("1") / Decimal(len(selected))
        return {symbol: weight for symbol in selected}

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.PAPER,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return monthly_sector_momentum_definition(
            version=self.strategy_version,
            universe=self.universe,
            lookback_days=self.lookback_days,
            top_n=self.top_n,
            authority=authority,
        )
