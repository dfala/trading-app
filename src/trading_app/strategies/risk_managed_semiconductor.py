"""Research-only risk-managed semiconductor ETF sleeve."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from math import sqrt
from statistics import pstdev

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    StrategyAuthority,
    StrategyDefinition,
    risk_managed_semiconductor_definition,
)


class RiskManagedSemiconductorStrategy:
    """Scale a semiconductor sleeve using point-in-time risk overlays."""

    strategy_id = "risk_managed_semiconductor"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        sleeve_weights: dict[str, Decimal],
        risk_off_weights: dict[str, Decimal] | None = None,
        benchmark: str = "SPY",
        trend_window_days: int | None = 200,
        relative_momentum_days: int | None = None,
        relative_momentum_symbols: tuple[str, ...] = (),
        volatility_window_days: int | None = None,
        target_volatility: Decimal | None = None,
        volatility_exposure_bands: tuple[tuple[Decimal, Decimal], ...] = (),
        drawdown_limit: Decimal | None = None,
        drawdown_exposure_bands: tuple[tuple[Decimal, Decimal], ...] = (),
    ) -> None:
        self.sleeve_weights = _normalize_weights(sleeve_weights, "sleeve_weights")
        self.risk_off_weights = _normalize_weights(
            risk_off_weights or {},
            "risk_off_weights",
            allow_empty=True,
        )
        self.benchmark = validate_symbol(benchmark)
        self.trend_window_days = _optional_positive_int(
            trend_window_days,
            "trend_window_days",
        )
        self.relative_momentum_days = _optional_positive_int(
            relative_momentum_days,
            "relative_momentum_days",
        )
        self.relative_momentum_symbols = tuple(
            validate_symbol(symbol) for symbol in relative_momentum_symbols
        )
        self.volatility_window_days = _optional_positive_int(
            volatility_window_days,
            "volatility_window_days",
        )
        if target_volatility is not None and target_volatility <= 0:
            raise ValueError("target_volatility must be positive")
        self.target_volatility = target_volatility
        self.volatility_exposure_bands = _normalize_exposure_bands(
            volatility_exposure_bands,
            "volatility_exposure_bands",
        )
        if self.volatility_exposure_bands and self.volatility_window_days is None:
            raise ValueError(
                "volatility_window_days is required for volatility exposure bands"
            )
        if self.volatility_exposure_bands and self.target_volatility is not None:
            raise ValueError(
                "target_volatility cannot be combined with volatility_exposure_bands"
            )
        if drawdown_limit is not None and drawdown_limit >= 0:
            raise ValueError("drawdown_limit must be negative")
        self.drawdown_limit = drawdown_limit
        self.drawdown_exposure_bands = _normalize_exposure_bands(
            drawdown_exposure_bands,
            "drawdown_exposure_bands",
        )
        if self.drawdown_exposure_bands and self.drawdown_limit is not None:
            raise ValueError(
                "drawdown_limit cannot be combined with drawdown_exposure_bands"
            )
        self.required_symbols = tuple(
            sorted(
                set(self.sleeve_weights)
                | set(self.risk_off_weights)
                | set(self.relative_momentum_symbols)
                | {self.benchmark}
            )
        )
        self.universe = tuple(
            symbol for symbol in self.required_symbols if symbol != self.benchmark
        )

    def generate_targets(
        self,
        bars: list[DailyBar] | tuple[DailyBar, ...],
        as_of: date | datetime,
    ) -> dict[str, Decimal]:
        """Return sleeve/risk-off weights using only bars before as_of."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        bars_by_symbol = _bars_by_symbol_before(
            bars=bars,
            symbols=self.required_symbols,
            as_of=as_of_date,
        )
        sleeve_series = _weighted_index_series(bars_by_symbol, self.sleeve_weights)
        if len(sleeve_series) < 2:
            return {}

        sleeve_exposure = (
            Decimal("1")
            if self._risk_gates_pass(
                bars_by_symbol,
                sleeve_series,
            )
            else Decimal("0")
        )
        if sleeve_exposure > 0:
            sleeve_exposure *= self._volatility_scale(sleeve_series)
            sleeve_exposure *= self._drawdown_scale(sleeve_series)

        targets: dict[str, Decimal] = {}
        _add_scaled_weights(targets, self.sleeve_weights, sleeve_exposure)

        risk_off_exposure = Decimal("1") - sleeve_exposure
        if risk_off_exposure > 0 and self.risk_off_weights:
            if not _has_history_for_all(bars_by_symbol, self.risk_off_weights):
                return {}
            _add_scaled_weights(targets, self.risk_off_weights, risk_off_exposure)

        return {
            symbol: weight
            for symbol, weight in sorted(targets.items())
            if weight > Decimal("0")
        }

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return risk_managed_semiconductor_definition(
            version=self.strategy_version,
            sleeve_weights={
                symbol: str(weight) for symbol, weight in self.sleeve_weights.items()
            },
            risk_off_weights={
                symbol: str(weight) for symbol, weight in self.risk_off_weights.items()
            },
            benchmark=self.benchmark,
            trend_window_days=self.trend_window_days,
            relative_momentum_days=self.relative_momentum_days,
            relative_momentum_symbols=self.relative_momentum_symbols,
            volatility_window_days=self.volatility_window_days,
            target_volatility=(
                str(self.target_volatility)
                if self.target_volatility is not None
                else None
            ),
            volatility_exposure_bands=tuple(
                (str(threshold), str(exposure))
                for threshold, exposure in self.volatility_exposure_bands
            ),
            drawdown_limit=(
                str(self.drawdown_limit) if self.drawdown_limit is not None else None
            ),
            drawdown_exposure_bands=tuple(
                (str(threshold), str(exposure))
                for threshold, exposure in self.drawdown_exposure_bands
            ),
            authority=authority,
        )

    def _risk_gates_pass(
        self,
        bars_by_symbol: dict[str, list[DailyBar]],
        sleeve_series: list[tuple[date, Decimal]],
    ) -> bool:
        latest = sleeve_series[-1][1]
        if self.trend_window_days is not None:
            if len(sleeve_series) < self.trend_window_days:
                return False
            trend_window = sleeve_series[-self.trend_window_days :]
            moving_average = sum(
                (value for _, value in trend_window),
                Decimal("0"),
            ) / Decimal(len(trend_window))
            if latest <= moving_average:
                return False

        if self.relative_momentum_days is not None:
            if len(sleeve_series) <= self.relative_momentum_days:
                return False
            sleeve_start = sleeve_series[-(self.relative_momentum_days + 1)][1]
            sleeve_return = latest / sleeve_start - Decimal("1")
            for comparator in self.relative_momentum_symbols:
                comparator_return = _symbol_return(
                    bars_by_symbol.get(comparator, []),
                    self.relative_momentum_days,
                )
                if comparator_return is None or sleeve_return <= comparator_return:
                    return False

        if self.drawdown_limit is not None:
            peak = max(value for _, value in sleeve_series)
            drawdown = latest / peak - Decimal("1")
            if drawdown <= self.drawdown_limit:
                return False

        return True

    def _volatility_scale(self, sleeve_series: list[tuple[date, Decimal]]) -> Decimal:
        if self.volatility_window_days is None:
            return Decimal("1")
        if len(sleeve_series) <= self.volatility_window_days:
            return Decimal("0")
        realized = _annualized_realized_volatility(
            sleeve_series[-(self.volatility_window_days + 1) :]
        )
        if realized is None or realized <= 0:
            return Decimal("1")
        if self.volatility_exposure_bands:
            return _exposure_for_threshold(realized, self.volatility_exposure_bands)
        if self.target_volatility is None:
            return Decimal("1")
        return min(Decimal("1"), self.target_volatility / realized)

    def _drawdown_scale(self, sleeve_series: list[tuple[date, Decimal]]) -> Decimal:
        if not self.drawdown_exposure_bands:
            return Decimal("1")
        peak = max(value for _, value in sleeve_series)
        latest = sleeve_series[-1][1]
        drawdown = max(Decimal("0"), Decimal("1") - latest / peak)
        return _exposure_for_threshold(drawdown, self.drawdown_exposure_bands)


def _normalize_weights(
    weights: dict[str, Decimal],
    name: str,
    *,
    allow_empty: bool = False,
) -> dict[str, Decimal]:
    if not weights:
        if allow_empty:
            return {}
        raise ValueError(f"{name} cannot be empty")

    normalized: dict[str, Decimal] = {}
    for symbol, weight in weights.items():
        if weight <= 0:
            raise ValueError(f"{name} must contain positive weights")
        normalized[validate_symbol(symbol)] = weight

    total = sum(normalized.values(), Decimal("0"))
    if total <= 0:
        raise ValueError(f"{name} must sum to a positive value")
    return {symbol: weight / total for symbol, weight in sorted(normalized.items())}


def _optional_positive_int(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _normalize_exposure_bands(
    bands: tuple[tuple[Decimal, Decimal], ...],
    name: str,
) -> tuple[tuple[Decimal, Decimal], ...]:
    normalized: list[tuple[Decimal, Decimal]] = []
    for threshold, exposure in bands:
        if threshold < 0:
            raise ValueError(f"{name} thresholds cannot be negative")
        if exposure < 0 or exposure > 1:
            raise ValueError(f"{name} exposures must be between 0 and 1")
        normalized.append((threshold, exposure))
    return tuple(sorted(normalized, key=lambda band: band[0]))


def _exposure_for_threshold(
    value: Decimal,
    bands: tuple[tuple[Decimal, Decimal], ...],
) -> Decimal:
    for threshold, exposure in bands:
        if value <= threshold:
            return exposure
    return bands[-1][1]


def _bars_by_symbol_before(
    *,
    bars: Iterable[DailyBar],
    symbols: tuple[str, ...],
    as_of: date,
) -> dict[str, list[DailyBar]]:
    wanted = set(symbols)
    grouped: dict[str, list[DailyBar]] = {symbol: [] for symbol in symbols}
    for bar in bars:
        if bar.symbol in wanted and bar.trading_date < as_of:
            grouped[bar.symbol].append(bar)
    for symbol in grouped:
        grouped[symbol].sort(key=lambda bar: bar.trading_date)
    return grouped


def _weighted_index_series(
    bars_by_symbol: dict[str, list[DailyBar]],
    weights: dict[str, Decimal],
) -> list[tuple[date, Decimal]]:
    date_sets = [
        {bar.trading_date for bar in bars_by_symbol.get(symbol, [])}
        for symbol in weights
    ]
    if not date_sets:
        return []
    common_dates = sorted(set.intersection(*date_sets))
    if len(common_dates) < 2:
        return []

    bars_by_symbol_date = {
        symbol: {bar.trading_date: bar for bar in bars_by_symbol.get(symbol, [])}
        for symbol in weights
    }
    base_date = common_dates[0]
    base_prices = {
        symbol: bars_by_symbol_date[symbol][base_date].close_price for symbol in weights
    }
    if any(price <= 0 for price in base_prices.values()):
        return []

    series: list[tuple[date, Decimal]] = []
    for trading_date in common_dates:
        index_value = sum(
            (
                weights[symbol]
                * bars_by_symbol_date[symbol][trading_date].close_price
                / base_prices[symbol]
            )
            for symbol in weights
        )
        series.append((trading_date, index_value))
    return series


def _symbol_return(bars: list[DailyBar], lookback_days: int) -> Decimal | None:
    if len(bars) <= lookback_days:
        return None
    recent = bars[-1].close_price
    start = bars[-(lookback_days + 1)].close_price
    if start <= 0:
        return None
    return recent / start - Decimal("1")


def _annualized_realized_volatility(
    sleeve_series: list[tuple[date, Decimal]],
) -> Decimal | None:
    returns = [
        float(current / previous - Decimal("1"))
        for (_, previous), (_, current) in zip(
            sleeve_series,
            sleeve_series[1:],
            strict=False,
        )
        if previous > 0
    ]
    if not returns:
        return None
    return Decimal(str(pstdev(returns) * sqrt(252)))


def _has_history_for_all(
    bars_by_symbol: dict[str, list[DailyBar]],
    weights: dict[str, Decimal],
) -> bool:
    return all(bars_by_symbol.get(symbol) for symbol in weights)


def _add_scaled_weights(
    targets: dict[str, Decimal],
    weights: dict[str, Decimal],
    scale: Decimal,
) -> None:
    if scale <= 0:
        return
    for symbol, weight in weights.items():
        targets[symbol] = targets.get(symbol, Decimal("0")) + weight * scale
