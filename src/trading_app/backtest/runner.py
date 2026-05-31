"""Simple long-only historical backtest runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import ROUND_DOWN, Decimal
from math import sqrt
from zoneinfo import ZoneInfo

import pandas as pd

from trading_app.ledger import Ledger
from trading_app.market_data import MarketDataQualityChecker, MarketDataQualityReport
from trading_app.risk import ProposedOrder, RiskContext, RiskDecision, RiskEngine
from trading_app.schemas import (
    DailyBar,
    DataFeed,
    Fill,
    Order,
    OrderSide,
    OrderType,
)

BPS_DENOMINATOR = Decimal("10000")
QUANTITY_INCREMENT = Decimal("0.000001")
MARKET_TIMEZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class BacktestConfig:
    starting_cash: Decimal = Decimal("100000")
    commission_per_trade: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("5")
    sell_fee_bps: Decimal = Decimal("0")
    short_term_tax_rate: Decimal | None = None
    long_term_tax_rate: Decimal | None = None


@dataclass(frozen=True)
class EquityPoint:
    trading_date: date
    equity: Decimal


@dataclass(frozen=True)
class BacktestTrade:
    trading_date: date
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fees: Decimal
    gross_value: Decimal
    order_id: str
    fill_id: str


@dataclass(frozen=True)
class TaxSummary:
    short_term_realized_gains: Decimal
    long_term_realized_gains: Decimal
    estimated_tax: Decimal | None
    estimated_after_tax_total_return: float | None


@dataclass(frozen=True)
class BacktestResult:
    gross_total_return: float
    net_total_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    trade_count: int
    turnover: float
    average_holding_period_days: float
    benchmark_total_return: float
    excess_return_vs_benchmark: float
    equity_curve: tuple[EquityPoint, ...]
    gross_equity_curve: tuple[EquityPoint, ...]
    benchmark_curve: tuple[EquityPoint, ...]
    trades: tuple[BacktestTrade, ...]
    risk_decisions: tuple[RiskDecision, ...]
    tax_summary: TaxSummary
    data_feed: DataFeed
    data_sources: tuple[str, ...]
    symbols: tuple[str, ...]
    data_warning: str | None
    data_quality_report: MarketDataQualityReport
    cost_assumptions: BacktestConfig


class BacktestRunner:
    """Run a deterministic daily-close, long-only backtest."""

    def run(
        self,
        strategy,
        bars: list[DailyBar] | tuple[DailyBar, ...],
        benchmark_bars: list[DailyBar] | tuple[DailyBar, ...],
        config: BacktestConfig,
        risk_engine: RiskEngine | None = None,
        trading_start: date | None = None,
    ) -> BacktestResult:
        if not bars:
            raise ValueError("bars cannot be empty")
        if not benchmark_bars:
            raise ValueError("benchmark_bars cannot be empty")
        evaluation_benchmark_bars = tuple(
            bar
            for bar in benchmark_bars
            if trading_start is None or bar.trading_date >= trading_start
        )
        if not evaluation_benchmark_bars:
            raise ValueError("benchmark_bars contain no evaluation dates")

        active_risk_engine = risk_engine or RiskEngine()
        strategy_input_bars = tuple(bars) + tuple(benchmark_bars)
        net = self._simulate(
            strategy,
            tuple(bars),
            config,
            active_risk_engine,
            strategy_input_bars=strategy_input_bars,
            trading_start=trading_start,
        )
        gross = self._simulate(
            strategy,
            tuple(bars),
            BacktestConfig(
                starting_cash=config.starting_cash,
                commission_per_trade=Decimal("0"),
                slippage_bps=Decimal("0"),
                sell_fee_bps=Decimal("0"),
            ),
            RiskEngine(),
            strategy_input_bars=strategy_input_bars,
            trading_start=trading_start,
        )
        benchmark_curve = _benchmark_curve(
            evaluation_benchmark_bars, config.starting_cash
        )
        tax_summary = _tax_summary(
            net.tax_tracker,
            ending_equity=net.equity_curve[-1].equity,
            starting_cash=config.starting_cash,
            config=config,
        )

        net_total_return = _total_return(
            config.starting_cash, net.equity_curve[-1].equity
        )
        benchmark_total_return = _total_return(
            config.starting_cash, benchmark_curve[-1].equity
        )
        all_result_bars = tuple(bars) + tuple(benchmark_bars)
        data_feed = _single_data_feed(all_result_bars)
        data_quality_report = MarketDataQualityChecker().assess_daily_bars(
            all_result_bars,
            symbols=tuple(sorted({bar.symbol for bar in all_result_bars})),
            start=min(bar.trading_date for bar in all_result_bars),
            end=max(bar.trading_date for bar in all_result_bars),
            generated_at=_as_dt(max(bar.trading_date for bar in all_result_bars)),
            expected_feed=data_feed,
            as_of_date=max(bar.trading_date for bar in all_result_bars),
        )
        return BacktestResult(
            gross_total_return=_total_return(
                config.starting_cash, gross.equity_curve[-1].equity
            ),
            net_total_return=net_total_return,
            annualized_return=_annualized_return(
                config.starting_cash,
                net.equity_curve[-1].equity,
                net.equity_curve[0].trading_date,
                net.equity_curve[-1].trading_date,
            ),
            annualized_volatility=_annualized_volatility(net.equity_curve),
            max_drawdown=_max_drawdown(net.equity_curve),
            trade_count=len(net.trades),
            turnover=_turnover(net.trades, net.equity_curve),
            average_holding_period_days=net.tax_tracker.average_holding_period_days,
            benchmark_total_return=benchmark_total_return,
            excess_return_vs_benchmark=net_total_return - benchmark_total_return,
            equity_curve=net.equity_curve,
            gross_equity_curve=gross.equity_curve,
            benchmark_curve=benchmark_curve,
            trades=net.trades,
            risk_decisions=active_risk_engine.decision_log,
            tax_summary=tax_summary,
            data_feed=data_feed,
            data_sources=tuple(sorted({bar.source for bar in all_result_bars})),
            symbols=tuple(sorted({bar.symbol for bar in all_result_bars})),
            data_warning=_data_warning(data_feed, data_quality_report),
            data_quality_report=data_quality_report,
            cost_assumptions=config,
        )

    def _simulate(
        self,
        strategy,
        bars: tuple[DailyBar, ...],
        config: BacktestConfig,
        risk_engine: RiskEngine,
        strategy_input_bars: tuple[DailyBar, ...] | None = None,
        trading_start: date | None = None,
    ) -> _SimulationResult:
        ledger = Ledger(config.starting_cash)
        tax_tracker = _TaxLotTracker()
        bars_by_date = _bars_by_date(bars)
        strategy_bars_by_date = _bars_by_date(strategy_input_bars or bars)
        trading_dates = sorted(bars_by_date)
        evaluation_dates = [
            trading_day
            for trading_day in trading_dates
            if trading_start is None or trading_day >= trading_start
        ]
        if not evaluation_dates:
            raise ValueError("bars contain no evaluation dates")
        rebalance_dates = _first_trading_day_by_month(evaluation_dates)
        all_bars_until_now: list[DailyBar] = []
        trades: list[BacktestTrade] = []
        equity_curve: list[EquityPoint] = []
        trade_index = 0

        for trading_day in trading_dates:
            day_bars = bars_by_date[trading_day]
            all_bars_until_now.extend(
                strategy_bars_by_date.get(trading_day, {}).values()
            )
            if trading_start is not None and trading_day < trading_start:
                continue
            prices = {symbol: bar.close_price for symbol, bar in day_bars.items()}

            if trading_day in rebalance_dates:
                targets = strategy.generate_targets(
                    tuple(all_bars_until_now), trading_day
                )
                trade_index = self._rebalance(
                    ledger=ledger,
                    tax_tracker=tax_tracker,
                    trades=trades,
                    trade_index=trade_index,
                    trading_day=trading_day,
                    prices=prices,
                    targets=targets,
                    config=config,
                    strategy_id=getattr(strategy, "strategy_id", "unknown_strategy"),
                    risk_engine=risk_engine,
                )

            equity_curve.append(
                EquityPoint(
                    trading_date=trading_day,
                    equity=_mark_to_market(ledger, prices, trading_day),
                )
            )

        return _SimulationResult(
            equity_curve=tuple(equity_curve),
            trades=tuple(trades),
            tax_tracker=tax_tracker,
        )

    def _rebalance(
        self,
        *,
        ledger: Ledger,
        tax_tracker: _TaxLotTracker,
        trades: list[BacktestTrade],
        trade_index: int,
        trading_day: date,
        prices: dict[str, Decimal],
        targets: dict[str, Decimal],
        config: BacktestConfig,
        strategy_id: str,
        risk_engine: RiskEngine,
    ) -> int:
        equity = _mark_to_market(ledger, prices, trading_day)
        target_values = {symbol: equity * weight for symbol, weight in targets.items()}
        current_symbols = {
            position.symbol
            for position in ledger.snapshot(_as_dt(trading_day)).positions
        }
        symbols_to_consider = sorted(current_symbols | set(targets))

        for symbol in symbols_to_consider:
            if symbol not in prices:
                continue
            position = ledger.get_position(symbol)
            current_quantity = (
                position.quantity if position is not None else Decimal("0")
            )
            current_value = current_quantity * prices[symbol]
            target_value = target_values.get(symbol, Decimal("0"))
            if current_value <= target_value:
                continue

            quantity = (
                current_quantity
                if target_value == 0
                else (current_value - target_value)
                / _sell_price(prices[symbol], config)
            )
            quantity = _round_quantity_down(min(quantity, current_quantity))
            if quantity <= 0:
                continue
            trade_index = _execute_trade(
                ledger=ledger,
                tax_tracker=tax_tracker,
                trades=trades,
                trade_index=trade_index,
                trading_day=trading_day,
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                raw_close=prices[symbol],
                config=config,
                risk_engine=risk_engine,
                strategy_id=strategy_id,
                latest_prices=prices,
                orders_today=_orders_today(trades, trading_day),
                notional_traded_today=_notional_traded_today(trades, trading_day),
            )

        for symbol in sorted(targets):
            if symbol not in prices:
                continue
            position = ledger.get_position(symbol)
            current_quantity = (
                position.quantity if position is not None else Decimal("0")
            )
            current_value = current_quantity * prices[symbol]
            target_value = target_values[symbol]
            if current_value >= target_value:
                continue

            buy_price = _buy_price(prices[symbol], config)
            desired_quantity = (target_value - current_value) / buy_price
            affordable_quantity = (
                (ledger.cash - config.commission_per_trade) / buy_price
                if ledger.cash > config.commission_per_trade
                else Decimal("0")
            )
            quantity = _round_quantity_down(min(desired_quantity, affordable_quantity))
            if quantity <= 0:
                continue
            trade_index = _execute_trade(
                ledger=ledger,
                tax_tracker=tax_tracker,
                trades=trades,
                trade_index=trade_index,
                trading_day=trading_day,
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                raw_close=prices[symbol],
                config=config,
                risk_engine=risk_engine,
                strategy_id=strategy_id,
                latest_prices=prices,
                orders_today=_orders_today(trades, trading_day),
                notional_traded_today=_notional_traded_today(trades, trading_day),
            )

        return trade_index


@dataclass(frozen=True)
class _SimulationResult:
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[BacktestTrade, ...]
    tax_tracker: _TaxLotTracker


@dataclass
class _TaxLot:
    symbol: str
    quantity: Decimal
    cost_basis_per_share: Decimal
    acquired_on: date


class _TaxLotTracker:
    def __init__(self) -> None:
        self._lots: dict[str, list[_TaxLot]] = {}
        self.short_term_realized_gains = Decimal("0")
        self.long_term_realized_gains = Decimal("0")
        self._holding_period_days: list[int] = []

    @property
    def average_holding_period_days(self) -> float:
        if not self._holding_period_days:
            return 0.0
        return sum(self._holding_period_days) / len(self._holding_period_days)

    def buy(
        self,
        symbol: str,
        quantity: Decimal,
        cost_basis_per_share: Decimal,
        acquired_on: date,
    ) -> None:
        self._lots.setdefault(symbol, []).append(
            _TaxLot(
                symbol=symbol,
                quantity=quantity,
                cost_basis_per_share=cost_basis_per_share,
                acquired_on=acquired_on,
            )
        )

    def sell(
        self,
        symbol: str,
        quantity: Decimal,
        proceeds_per_share: Decimal,
        sold_on: date,
    ) -> None:
        remaining = quantity
        lots = self._lots.get(symbol, [])
        while remaining > 0 and lots:
            lot = lots[0]
            matched = min(remaining, lot.quantity)
            gain = (proceeds_per_share - lot.cost_basis_per_share) * matched
            holding_days = (sold_on - lot.acquired_on).days
            self._holding_period_days.append(holding_days)
            if holding_days >= 365:
                self.long_term_realized_gains += gain
            else:
                self.short_term_realized_gains += gain
            lot.quantity -= matched
            remaining -= matched
            if lot.quantity == 0:
                lots.pop(0)
        if remaining > 0:
            raise ValueError("tax lot tracker cannot sell more than held quantity")


def _execute_trade(
    *,
    ledger: Ledger,
    tax_tracker: _TaxLotTracker,
    trades: list[BacktestTrade],
    trade_index: int,
    trading_day: date,
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    raw_close: Decimal,
    config: BacktestConfig,
    risk_engine: RiskEngine,
    strategy_id: str,
    latest_prices: dict[str, Decimal],
    orders_today: int,
    notional_traded_today: Decimal,
) -> int:
    trade_index += 1
    price = (
        _buy_price(raw_close, config)
        if side == OrderSide.BUY
        else _sell_price(raw_close, config)
    )
    gross_value = quantity * price
    fees = config.commission_per_trade
    if side == OrderSide.SELL:
        fees += gross_value * config.sell_fee_bps / BPS_DENOMINATOR

    order_id = f"bt-order-{trade_index}"
    fill_id = f"bt-fill-{trade_index}"
    order = Order(
        id=order_id,
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_at=_as_dt(trading_day),
    )
    fill = Fill(
        id=fill_id,
        order_id=order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        commission=fees,
        filled_at=_as_dt(trading_day),
    )
    proposal = ProposedOrder(
        order=order,
        estimated_price=price,
        estimated_commission=fees,
        strategy_id=strategy_id,
    )
    context = RiskContext(
        as_of=_as_dt(trading_day),
        portfolio=ledger.snapshot(_as_dt(trading_day)),
        latest_prices=latest_prices,
        orders_today=orders_today,
        notional_traded_today=notional_traded_today,
    )
    decision = risk_engine.evaluate_order(proposal, context)
    if not decision.approved:
        return trade_index

    ledger.record_order(order)
    ledger.record_fill(fill)

    if side == OrderSide.BUY:
        tax_tracker.buy(
            symbol=symbol,
            quantity=quantity,
            cost_basis_per_share=price + fees / quantity,
            acquired_on=trading_day,
        )
    else:
        tax_tracker.sell(
            symbol=symbol,
            quantity=quantity,
            proceeds_per_share=price - fees / quantity,
            sold_on=trading_day,
        )

    trades.append(
        BacktestTrade(
            trading_date=trading_day,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            fees=fees,
            gross_value=gross_value,
            order_id=order_id,
            fill_id=fill_id,
        )
    )
    return trade_index


def _bars_by_date(bars: tuple[DailyBar, ...]) -> dict[date, dict[str, DailyBar]]:
    grouped: dict[date, dict[str, DailyBar]] = {}
    for bar in bars:
        grouped.setdefault(bar.trading_date, {})[bar.symbol] = bar
    return grouped


def _single_data_feed(bars: tuple[DailyBar, ...]) -> DataFeed:
    feeds = {bar.data_feed for bar in bars}
    if len(feeds) != 1:
        raise ValueError("backtests cannot mix data feeds")
    return feeds.pop()


def _data_warning(
    data_feed: DataFeed,
    data_quality_report: MarketDataQualityReport,
) -> str | None:
    warnings = []
    if data_feed == DataFeed.IEX:
        warnings.append(
            "IEX data is development-grade and not suitable for final model ranking."
        )
    if data_quality_report.warnings or data_quality_report.failures:
        warnings.append(data_quality_report.summary)
    return " ".join(warnings) if warnings else None


def _first_trading_day_by_month(trading_dates: list[date]) -> set[date]:
    first_by_month: dict[tuple[int, int], date] = {}
    for trading_day in trading_dates:
        first_by_month.setdefault((trading_day.year, trading_day.month), trading_day)
    return set(first_by_month.values())


def _mark_to_market(
    ledger: Ledger, prices: dict[str, Decimal], trading_day: date
) -> Decimal:
    equity = ledger.cash
    for position in ledger.snapshot(_as_dt(trading_day)).positions:
        if position.symbol in prices:
            equity += position.quantity * prices[position.symbol]
    return equity


def _buy_price(close: Decimal, config: BacktestConfig) -> Decimal:
    return close * (Decimal("1") + config.slippage_bps / BPS_DENOMINATOR)


def _sell_price(close: Decimal, config: BacktestConfig) -> Decimal:
    return close * (Decimal("1") - config.slippage_bps / BPS_DENOMINATOR)


def _round_quantity_down(quantity: Decimal) -> Decimal:
    return quantity.quantize(QUANTITY_INCREMENT, rounding=ROUND_DOWN)


def _benchmark_curve(
    benchmark_bars: tuple[DailyBar, ...], starting_cash: Decimal
) -> tuple[EquityPoint, ...]:
    sorted_bars = sorted(benchmark_bars, key=lambda bar: bar.trading_date)
    first_close = sorted_bars[0].close_price
    return tuple(
        EquityPoint(
            trading_date=bar.trading_date,
            equity=starting_cash * (bar.close_price / first_close),
        )
        for bar in sorted_bars
    )


def _tax_summary(
    tax_tracker: _TaxLotTracker,
    *,
    ending_equity: Decimal,
    starting_cash: Decimal,
    config: BacktestConfig,
) -> TaxSummary:
    estimated_tax: Decimal | None = None
    estimated_after_tax_total_return: float | None = None
    if config.short_term_tax_rate is not None and config.long_term_tax_rate is not None:
        estimated_tax = (
            max(tax_tracker.short_term_realized_gains, Decimal("0"))
            * config.short_term_tax_rate
            + max(tax_tracker.long_term_realized_gains, Decimal("0"))
            * config.long_term_tax_rate
        )
        estimated_after_tax_total_return = _total_return(
            starting_cash, ending_equity - estimated_tax
        )

    return TaxSummary(
        short_term_realized_gains=tax_tracker.short_term_realized_gains,
        long_term_realized_gains=tax_tracker.long_term_realized_gains,
        estimated_tax=estimated_tax,
        estimated_after_tax_total_return=estimated_after_tax_total_return,
    )


def _total_return(starting_cash: Decimal, ending_equity: Decimal) -> float:
    return float(ending_equity / starting_cash - Decimal("1"))


def _annualized_return(
    starting_cash: Decimal,
    ending_equity: Decimal,
    start: date,
    end: date,
) -> float:
    days = max((end - start).days, 1)
    return float((float(ending_equity / starting_cash) ** (365 / days)) - 1)


def _annualized_volatility(equity_curve: tuple[EquityPoint, ...]) -> float:
    if len(equity_curve) < 3:
        return 0.0
    series = pd.Series([float(point.equity) for point in equity_curve])
    returns = series.pct_change().dropna()
    if returns.empty:
        return 0.0
    return float(returns.std(ddof=0) * sqrt(252))


def _max_drawdown(equity_curve: tuple[EquityPoint, ...]) -> float:
    running_max = Decimal("0")
    max_drawdown = Decimal("0")
    for point in equity_curve:
        running_max = max(running_max, point.equity)
        if running_max > 0:
            drawdown = point.equity / running_max - Decimal("1")
            max_drawdown = min(max_drawdown, drawdown)
    return float(max_drawdown)


def _turnover(
    trades: tuple[BacktestTrade, ...], equity_curve: tuple[EquityPoint, ...]
) -> float:
    if not trades or not equity_curve:
        return 0.0
    traded_value = sum((trade.gross_value for trade in trades), Decimal("0"))
    average_equity = sum(
        (point.equity for point in equity_curve), Decimal("0")
    ) / Decimal(len(equity_curve))
    if average_equity == 0:
        return 0.0
    return float(traded_value / average_equity)


def _orders_today(trades: list[BacktestTrade], trading_day: date) -> int:
    return sum(1 for trade in trades if trade.trading_date == trading_day)


def _notional_traded_today(trades: list[BacktestTrade], trading_day: date) -> Decimal:
    return sum(
        (trade.gross_value for trade in trades if trade.trading_date == trading_day),
        Decimal("0"),
    )


def _as_dt(trading_day: date) -> datetime:
    local_close = datetime.combine(trading_day, time(hour=16), tzinfo=MARKET_TIMEZONE)
    return local_close.astimezone(UTC)
