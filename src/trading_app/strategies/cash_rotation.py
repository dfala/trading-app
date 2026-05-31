"""Research-only cash rotation ETF strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyDefinition,
    cash_rotation_model_definition,
)


class CashRotationETFStrategy:
    """Invest only when ETF opportunity breadth is strong enough."""

    strategy_id = "cash_rotation_model"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
        lookback_days: int = 63,
        top_n: int = 3,
        min_symbol_return: Decimal = Decimal("0"),
        min_breadth: Decimal = Decimal("0.40"),
        min_average_top_return: Decimal = Decimal("0.02"),
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if top_n > len(universe):
            raise ValueError("top_n cannot exceed universe size")
        if min_breadth < 0 or min_breadth > 1:
            raise ValueError("min_breadth must be between 0 and 1")

        self.universe = tuple(validate_symbol(symbol) for symbol in universe)
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.min_symbol_return = min_symbol_return
        self.min_breadth = min_breadth
        self.min_average_top_return = min_average_top_return

    def generate_targets(
        self, bars: list[DailyBar] | tuple[DailyBar, ...], as_of: date | datetime
    ) -> dict[str, Decimal]:
        """Generate ETF targets or cash using completed prior bars."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        bars_by_symbol: dict[str, list[DailyBar]] = {
            symbol: [] for symbol in self.universe
        }
        for bar in bars:
            if bar.symbol in bars_by_symbol and bar.trading_date < as_of_date:
                bars_by_symbol[bar.symbol].append(bar)

        scores: list[tuple[Decimal, str]] = []
        eligible_symbols = 0
        positive_symbols = 0
        for symbol, symbol_bars in bars_by_symbol.items():
            sorted_bars = sorted(symbol_bars, key=lambda bar: bar.trading_date)
            if len(sorted_bars) <= self.lookback_days:
                continue

            eligible_symbols += 1
            trailing_return = _trailing_return(sorted_bars, self.lookback_days)
            if trailing_return > self.min_symbol_return:
                positive_symbols += 1
                scores.append((trailing_return, symbol))

        if not eligible_symbols or not scores:
            return {}

        breadth = Decimal(positive_symbols) / Decimal(eligible_symbols)
        selected_scores = sorted(
            scores, key=lambda item: (item[0], item[1]), reverse=True
        )[: self.top_n]
        average_top_return = sum(
            (score for score, _ in selected_scores), Decimal("0")
        ) / Decimal(len(selected_scores))
        if (
            breadth < self.min_breadth
            or average_top_return <= self.min_average_top_return
        ):
            return {}

        weight = Decimal("1") / Decimal(len(selected_scores))
        return {symbol: weight for _, symbol in sorted(selected_scores)}

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return cash_rotation_model_definition(
            version=self.strategy_version,
            universe=self.universe,
            lookback_days=self.lookback_days,
            top_n=self.top_n,
            min_symbol_return=str(self.min_symbol_return),
            min_breadth=str(self.min_breadth),
            min_average_top_return=str(self.min_average_top_return),
            authority=authority,
        )


def _trailing_return(bars: list[DailyBar], lookback_days: int) -> Decimal:
    recent = bars[-1]
    lookback = bars[-(lookback_days + 1)]
    return recent.close_price / lookback.close_price - Decimal("1")
