"""Research-only semiconductor sleeve with broad-market drawdown breaker."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from trading_app.schemas import DailyBar, validate_symbol
from trading_app.strategies.catalog import (
    StrategyAuthority,
    StrategyDefinition,
    market_drawdown_circuit_breaker_definition,
)


class MarketDrawdownCircuitBreakerStrategy:
    """Select semiconductor strength unless broad-market drawdown trips."""

    strategy_id = "market_drawdown_circuit_breaker"
    strategy_version = "0.1.0"

    def __init__(
        self,
        *,
        risk_symbols: tuple[str, ...] = ("SOXX", "SMH"),
        risk_off_weights: dict[str, Decimal] | None = None,
        benchmark: str = "SPY",
        momentum_lookback_days: int = 126,
        drawdown_symbols: tuple[str, ...] = ("SPY", "QQQ"),
        drawdown_lookback_days: int = 252,
        drawdown_threshold: Decimal | None = Decimal("0.12"),
        triggered_risk_exposure: Decimal = Decimal("0"),
        trigger_mode: str = "any",
        version: str | None = None,
    ) -> None:
        if not risk_symbols:
            raise ValueError("risk_symbols cannot be empty")
        self.strategy_version = version or self.strategy_version
        self.risk_symbols = tuple(validate_symbol(symbol) for symbol in risk_symbols)
        self.risk_off_weights = _normalize_weights(
            risk_off_weights or {},
            "risk_off_weights",
            allow_empty=True,
        )
        self.benchmark = validate_symbol(benchmark)
        self.momentum_lookback_days = _positive_int(
            momentum_lookback_days,
            "momentum_lookback_days",
        )
        self.drawdown_symbols = tuple(
            validate_symbol(symbol) for symbol in drawdown_symbols
        )
        if not self.drawdown_symbols and drawdown_threshold is not None:
            raise ValueError("drawdown_symbols cannot be empty when breaker is enabled")
        self.drawdown_lookback_days = _positive_int(
            drawdown_lookback_days,
            "drawdown_lookback_days",
        )
        if drawdown_threshold is not None and drawdown_threshold <= 0:
            raise ValueError("drawdown_threshold must be positive")
        self.drawdown_threshold = drawdown_threshold
        if triggered_risk_exposure < 0 or triggered_risk_exposure > 1:
            raise ValueError("triggered_risk_exposure must be between 0 and 1")
        self.triggered_risk_exposure = triggered_risk_exposure
        if trigger_mode not in {"any", "all"}:
            raise ValueError("trigger_mode must be 'any' or 'all'")
        self.trigger_mode = trigger_mode
        self.required_symbols = tuple(
            sorted(
                set(self.risk_symbols)
                | set(self.risk_off_weights)
                | set(self.drawdown_symbols)
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
        """Return point-in-time target weights."""

        targets, _, _ = self.generate_targets_with_metadata(bars, as_of)
        return targets

    def generate_targets_with_metadata(
        self,
        bars: list[DailyBar] | tuple[DailyBar, ...],
        as_of: date | datetime,
    ) -> tuple[dict[str, Decimal], str, dict[str, Any]]:
        """Return targets plus replay-audit metadata."""

        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        bars_by_symbol = _bars_by_symbol_before(
            bars=bars,
            symbols=self.required_symbols,
            as_of=as_of_date,
        )
        selected_symbol, risk_returns = self._selected_risk_symbol(bars_by_symbol)
        drawdowns = self._drawdowns(bars_by_symbol)
        missing_drawdown = self.drawdown_threshold is not None and len(
            drawdowns
        ) != len(self.drawdown_symbols)
        if selected_symbol is None or missing_drawdown:
            metadata = self._metadata(
                selected_symbol=selected_symbol,
                risk_returns=risk_returns,
                drawdowns=drawdowns,
                breaker_triggered=False,
                risk_exposure=Decimal("0"),
                reason="insufficient_history",
            )
            return (
                {},
                "Insufficient point-in-time history for circuit breaker.",
                metadata,
            )

        breaker_triggered = self._breaker_triggered(drawdowns)
        risk_exposure = (
            self.triggered_risk_exposure if breaker_triggered else Decimal("1")
        )
        targets: dict[str, Decimal] = {}
        if risk_exposure > 0:
            targets[selected_symbol] = risk_exposure

        risk_off_exposure = Decimal("1") - risk_exposure
        if risk_off_exposure > 0 and self.risk_off_weights:
            if not _has_history_for_all(bars_by_symbol, self.risk_off_weights):
                metadata = self._metadata(
                    selected_symbol=selected_symbol,
                    risk_returns=risk_returns,
                    drawdowns=drawdowns,
                    breaker_triggered=breaker_triggered,
                    risk_exposure=Decimal("0"),
                    reason="insufficient_risk_off_history",
                )
                return (
                    {},
                    "Insufficient point-in-time risk-off history for circuit breaker.",
                    metadata,
                )
            _add_scaled_weights(targets, self.risk_off_weights, risk_off_exposure)

        metadata = self._metadata(
            selected_symbol=selected_symbol,
            risk_returns=risk_returns,
            drawdowns=drawdowns,
            breaker_triggered=breaker_triggered,
            risk_exposure=risk_exposure,
            reason="breaker_triggered" if breaker_triggered else "risk_on",
        )
        explanation = (
            f"Selected {selected_symbol}; market drawdown breaker "
            f"{'triggered' if breaker_triggered else 'clear'} as of "
            f"{as_of_date.isoformat()}."
        )
        return _positive_targets(targets), explanation, metadata

    def definition(
        self,
        *,
        authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
    ) -> StrategyDefinition:
        """Return the research card for this configured strategy version."""

        return market_drawdown_circuit_breaker_definition(
            version=self.strategy_version,
            risk_symbols=self.risk_symbols,
            risk_off_weights={
                symbol: str(weight) for symbol, weight in self.risk_off_weights.items()
            },
            benchmark=self.benchmark,
            momentum_lookback_days=self.momentum_lookback_days,
            drawdown_symbols=self.drawdown_symbols,
            drawdown_lookback_days=self.drawdown_lookback_days,
            drawdown_threshold=(
                str(self.drawdown_threshold)
                if self.drawdown_threshold is not None
                else None
            ),
            triggered_risk_exposure=str(self.triggered_risk_exposure),
            trigger_mode=self.trigger_mode,
            authority=authority,
        )

    def _selected_risk_symbol(
        self,
        bars_by_symbol: dict[str, list[DailyBar]],
    ) -> tuple[str | None, dict[str, Decimal]]:
        returns: dict[str, Decimal] = {}
        for symbol in self.risk_symbols:
            symbol_return = _symbol_return(
                bars_by_symbol.get(symbol, []),
                self.momentum_lookback_days,
            )
            if symbol_return is not None:
                returns[symbol] = symbol_return
        if not returns:
            return None, {}
        return max(returns, key=lambda symbol: (returns[symbol], symbol)), returns

    def _drawdowns(
        self,
        bars_by_symbol: dict[str, list[DailyBar]],
    ) -> dict[str, Decimal]:
        if self.drawdown_threshold is None:
            return {}
        drawdowns: dict[str, Decimal] = {}
        for symbol in self.drawdown_symbols:
            drawdown = _rolling_drawdown(
                bars_by_symbol.get(symbol, []),
                self.drawdown_lookback_days,
            )
            if drawdown is not None:
                drawdowns[symbol] = drawdown
        return drawdowns

    def _breaker_triggered(self, drawdowns: dict[str, Decimal]) -> bool:
        if self.drawdown_threshold is None:
            return False
        threshold = -self.drawdown_threshold
        hits = [
            drawdowns[symbol] <= threshold
            for symbol in self.drawdown_symbols
            if symbol in drawdowns
        ]
        if len(hits) != len(self.drawdown_symbols):
            return False
        return all(hits) if self.trigger_mode == "all" else any(hits)

    def _metadata(
        self,
        *,
        selected_symbol: str | None,
        risk_returns: dict[str, Decimal],
        drawdowns: dict[str, Decimal],
        breaker_triggered: bool,
        risk_exposure: Decimal,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "adapter": "strategy",
            "strategy_family": self.strategy_id,
            "selected_risk_symbol": selected_symbol,
            "risk_symbol_returns": {
                symbol: str(value) for symbol, value in sorted(risk_returns.items())
            },
            "drawdowns": {
                symbol: str(value) for symbol, value in sorted(drawdowns.items())
            },
            "drawdown_threshold": (
                str(self.drawdown_threshold)
                if self.drawdown_threshold is not None
                else None
            ),
            "drawdown_symbols": self.drawdown_symbols,
            "drawdown_lookback_days": self.drawdown_lookback_days,
            "trigger_mode": self.trigger_mode,
            "breaker_triggered": breaker_triggered,
            "risk_exposure": str(risk_exposure),
            "risk_off_exposure": str(Decimal("1") - risk_exposure),
            "risk_off_weights": {
                symbol: str(weight)
                for symbol, weight in sorted(self.risk_off_weights.items())
            },
            "reason": reason,
        }


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


def _positive_int(value: int, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


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


def _symbol_return(bars: list[DailyBar], lookback_days: int) -> Decimal | None:
    if len(bars) <= lookback_days:
        return None
    recent = bars[-1].close_price
    start = bars[-(lookback_days + 1)].close_price
    if start <= 0:
        return None
    return recent / start - Decimal("1")


def _rolling_drawdown(
    bars: list[DailyBar],
    lookback_days: int,
) -> Decimal | None:
    if len(bars) < lookback_days:
        return None
    window = bars[-lookback_days:]
    peak = max(bar.close_price for bar in window)
    latest = window[-1].close_price
    if peak <= 0:
        return None
    return latest / peak - Decimal("1")


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


def _positive_targets(targets: dict[str, Decimal]) -> dict[str, Decimal]:
    return {
        symbol: weight
        for symbol, weight in sorted(targets.items())
        if weight > Decimal("0")
    }
