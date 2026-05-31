"""Research-only benchmark-relative ETF strength strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyDefinition,
    benchmark_relative_strength_etf_definition,
)


class BenchmarkRelativeStrengthETFStrategy:
    """Select ETFs outperforming SPY after accounting for relative noise."""

    strategy_id = "benchmark_relative_strength_etf"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
        benchmark: str = "SPY",
        lookback_days: int = 63,
        tracking_window_days: int = 21,
        top_n: int = 3,
        min_excess_return: Decimal = Decimal("0"),
        min_absolute_return: Decimal = Decimal("0"),
        tracking_error_floor: Decimal = Decimal("0.000001"),
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if tracking_window_days <= 0:
            raise ValueError("tracking_window_days must be positive")
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if top_n > len(universe):
            raise ValueError("top_n cannot exceed universe size")
        if tracking_error_floor <= 0:
            raise ValueError("tracking_error_floor must be positive")

        self.universe = tuple(validate_symbol(symbol) for symbol in universe)
        self.benchmark = validate_symbol(benchmark)
        self.lookback_days = lookback_days
        self.tracking_window_days = tracking_window_days
        self.top_n = top_n
        self.min_excess_return = min_excess_return
        self.min_absolute_return = min_absolute_return
        self.tracking_error_floor = tracking_error_floor

    def generate_targets(
        self, bars: list[DailyBar] | tuple[DailyBar, ...], as_of: date | datetime
    ) -> dict[str, Decimal]:
        """Generate equal-weight targets using prior symbol and benchmark bars."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        required_symbols = set(self.universe) | {self.benchmark}
        bars_by_symbol: dict[str, list[DailyBar]] = {
            symbol: [] for symbol in required_symbols
        }
        for bar in bars:
            if bar.symbol in bars_by_symbol and bar.trading_date < as_of_date:
                bars_by_symbol[bar.symbol].append(bar)

        benchmark_bars = sorted(
            bars_by_symbol[self.benchmark], key=lambda bar: bar.trading_date
        )
        minimum_history = max(self.lookback_days, self.tracking_window_days) + 1
        if len(benchmark_bars) < minimum_history:
            return {}

        benchmark_return = _trailing_return(benchmark_bars, self.lookback_days)
        benchmark_daily_returns = _daily_returns_by_date(benchmark_bars)

        scores: list[tuple[Decimal, str]] = []
        for symbol in self.universe:
            symbol_bars = sorted(
                bars_by_symbol[symbol], key=lambda bar: bar.trading_date
            )
            if len(symbol_bars) < minimum_history:
                continue

            symbol_return = _trailing_return(symbol_bars, self.lookback_days)
            if symbol_return <= self.min_absolute_return:
                continue

            excess_return = symbol_return - benchmark_return
            if excess_return <= self.min_excess_return:
                continue

            tracking_error = _average_absolute_excess_return(
                symbol_daily_returns=_daily_returns_by_date(symbol_bars),
                benchmark_daily_returns=benchmark_daily_returns,
                window_days=self.tracking_window_days,
            )
            if tracking_error is None:
                continue

            score = excess_return / max(tracking_error, self.tracking_error_floor)
            scores.append((score, symbol))

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

        return benchmark_relative_strength_etf_definition(
            version=self.strategy_version,
            universe=self.universe,
            benchmark=self.benchmark,
            lookback_days=self.lookback_days,
            tracking_window_days=self.tracking_window_days,
            top_n=self.top_n,
            min_excess_return=str(self.min_excess_return),
            min_absolute_return=str(self.min_absolute_return),
            tracking_error_floor=str(self.tracking_error_floor),
            authority=authority,
        )


def _trailing_return(bars: list[DailyBar], lookback_days: int) -> Decimal:
    recent = bars[-1]
    lookback = bars[-(lookback_days + 1)]
    return recent.close_price / lookback.close_price - Decimal("1")


def _daily_returns_by_date(bars: list[DailyBar]) -> dict[date, Decimal]:
    returns: dict[date, Decimal] = {}
    for previous, current in zip(bars, bars[1:], strict=False):
        returns[current.trading_date] = (
            current.close_price / previous.close_price - Decimal("1")
        )
    return returns


def _average_absolute_excess_return(
    *,
    symbol_daily_returns: dict[date, Decimal],
    benchmark_daily_returns: dict[date, Decimal],
    window_days: int,
) -> Decimal | None:
    common_dates = sorted(set(symbol_daily_returns) & set(benchmark_daily_returns))
    if len(common_dates) < window_days:
        return None
    recent_dates = common_dates[-window_days:]
    total = sum(
        (
            abs(
                symbol_daily_returns[trading_date]
                - benchmark_daily_returns[trading_date]
            )
            for trading_date in recent_dates
        ),
        Decimal("0"),
    )
    return total / Decimal(window_days)
