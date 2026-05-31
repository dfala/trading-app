"""Research-only defensive regime ETF strategy."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    SECTOR_ETF_UNIVERSE,
    StrategyAuthority,
    StrategyDefinition,
    defensive_regime_switch_definition,
)


class DefensiveRegimeSwitchETFStrategy:
    """Rotate from sector momentum to defensive ETFs or cash in weak regimes."""

    strategy_id = "defensive_regime_switch"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
        defensive_symbols: tuple[str, ...] = ("XLP", "XLU", "XLV"),
        benchmark: str = "SPY",
        regime_lookback_days: int = 126,
        risk_on_top_n: int = 3,
        risk_off_top_n: int = 2,
        max_benchmark_drawdown: Decimal = Decimal("-0.10"),
        min_benchmark_return: Decimal = Decimal("0"),
        min_defensive_return: Decimal = Decimal("0"),
    ) -> None:
        if regime_lookback_days <= 0:
            raise ValueError("regime_lookback_days must be positive")
        if risk_on_top_n <= 0:
            raise ValueError("risk_on_top_n must be positive")
        if risk_off_top_n <= 0:
            raise ValueError("risk_off_top_n must be positive")
        if risk_on_top_n > len(universe):
            raise ValueError("risk_on_top_n cannot exceed universe size")
        if max_benchmark_drawdown >= 0:
            raise ValueError("max_benchmark_drawdown must be negative")

        normalized_universe = tuple(validate_symbol(symbol) for symbol in universe)
        normalized_defensive = tuple(
            validate_symbol(symbol) for symbol in defensive_symbols
        )
        unknown_defensive = sorted(set(normalized_defensive) - set(normalized_universe))
        if unknown_defensive:
            raise ValueError("defensive_symbols must be included in universe")
        if risk_off_top_n > len(normalized_defensive):
            raise ValueError("risk_off_top_n cannot exceed defensive universe size")

        self.universe = normalized_universe
        self.defensive_symbols = normalized_defensive
        self.benchmark = validate_symbol(benchmark)
        self.regime_lookback_days = regime_lookback_days
        self.risk_on_top_n = risk_on_top_n
        self.risk_off_top_n = risk_off_top_n
        self.max_benchmark_drawdown = max_benchmark_drawdown
        self.min_benchmark_return = min_benchmark_return
        self.min_defensive_return = min_defensive_return

    def generate_targets(
        self, bars: list[DailyBar] | tuple[DailyBar, ...], as_of: date | datetime
    ) -> dict[str, Decimal]:
        """Generate targets using only completed prior bars."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        bars_by_symbol: dict[str, list[DailyBar]] = {
            symbol: [] for symbol in (*self.universe, self.benchmark)
        }
        for bar in bars:
            if bar.symbol in bars_by_symbol and bar.trading_date < as_of_date:
                bars_by_symbol[bar.symbol].append(bar)

        benchmark_bars = sorted(
            bars_by_symbol[self.benchmark], key=lambda bar: bar.trading_date
        )
        if len(benchmark_bars) <= self.regime_lookback_days:
            return {}

        regime_is_weak = self._regime_is_weak(benchmark_bars)
        candidate_symbols = self.defensive_symbols if regime_is_weak else self.universe
        min_return = self.min_defensive_return if regime_is_weak else Decimal("-1")
        top_n = self.risk_off_top_n if regime_is_weak else self.risk_on_top_n

        scores: list[tuple[Decimal, str]] = []
        for symbol in candidate_symbols:
            symbol_bars = sorted(
                bars_by_symbol[symbol], key=lambda bar: bar.trading_date
            )
            if len(symbol_bars) <= self.regime_lookback_days:
                continue
            trailing_return = _trailing_return(
                symbol_bars,
                self.regime_lookback_days,
            )
            if trailing_return <= min_return:
                continue
            scores.append((trailing_return, symbol))

        if not scores:
            return {}

        selected = [
            symbol
            for _, symbol in sorted(
                scores, key=lambda item: (item[0], item[1]), reverse=True
            )[:top_n]
        ]
        weight = Decimal("1") / Decimal(len(selected))
        return {symbol: weight for symbol in sorted(selected)}

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return defensive_regime_switch_definition(
            version=self.strategy_version,
            universe=self.universe,
            defensive_symbols=self.defensive_symbols,
            benchmark=self.benchmark,
            regime_lookback_days=self.regime_lookback_days,
            risk_on_top_n=self.risk_on_top_n,
            risk_off_top_n=self.risk_off_top_n,
            max_benchmark_drawdown=str(self.max_benchmark_drawdown),
            min_benchmark_return=str(self.min_benchmark_return),
            min_defensive_return=str(self.min_defensive_return),
            authority=authority,
        )

    def _regime_is_weak(self, benchmark_bars: list[DailyBar]) -> bool:
        recent_window = benchmark_bars[-self.regime_lookback_days :]
        recent = benchmark_bars[-1]
        trailing_return = _trailing_return(
            benchmark_bars,
            self.regime_lookback_days,
        )
        average_close = sum(
            (bar.close_price for bar in recent_window), Decimal("0")
        ) / Decimal(len(recent_window))
        peak_close = max(bar.close_price for bar in recent_window)
        drawdown = recent.close_price / peak_close - Decimal("1")
        return (
            trailing_return <= self.min_benchmark_return
            or recent.close_price <= average_close
            or drawdown <= self.max_benchmark_drawdown
        )


def _trailing_return(bars: list[DailyBar], lookback_days: int) -> Decimal:
    recent = bars[-1]
    lookback = bars[-(lookback_days + 1)]
    return recent.close_price / lookback.close_price - Decimal("1")
