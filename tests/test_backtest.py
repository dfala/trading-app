from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from trading_app.backtest.runner import BacktestConfig, BacktestRunner
from trading_app.risk import RiskConfig, RiskEngine, RiskRule
from trading_app.schemas import DailyBar, DataFeed, OrderSide
from trading_app.strategies.benchmark_relative import (
    BenchmarkRelativeStrengthETFStrategy,
)
from trading_app.strategies.cash_rotation import CashRotationETFStrategy
from trading_app.strategies.defensive_regime import DefensiveRegimeSwitchETFStrategy
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy
from trading_app.strategies.trend_following import TrendFollowingETFStrategy


class CashTargetAfterFirstMonthStrategy:
    strategy_id = "cash_target_after_first_month"

    def generate_targets(self, _bars, as_of: date) -> dict[str, Decimal]:
        if as_of < date(2024, 2, 1):
            return {"AAA": Decimal("1")}
        return {}


def make_bar(symbol: str, trading_date: date, close: Decimal) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year, trading_date.month, trading_date.day, 21, tzinfo=UTC
        ),
        ingested_at=datetime(2024, 12, 31, 23, tzinfo=UTC),
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=Decimal("1000000"),
        source="test",
        data_feed=DataFeed.IEX,
    )


def business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def regime_change_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(
        business_days(date(2024, 1, 1), date(2024, 3, 15))
    ):
        aaa_close = Decimal("100") + Decimal(index) * Decimal("0.50")
        bbb_close = Decimal("100") + Decimal(index) * Decimal("0.05")
        if trading_day >= date(2024, 2, 20):
            bbb_close += Decimal(index - 35) * Decimal("2.50")
        spy_close = Decimal("100") + Decimal(index) * Decimal("0.20")

        bars.append(make_bar("AAA", trading_day, aaa_close))
        bars.append(make_bar("BBB", trading_day, bbb_close))
        benchmark.append(make_bar("SPY", trading_day, spy_close))

    return tuple(bars), tuple(benchmark)


def test_backtest_runs_sector_momentum_and_benchmark() -> None:
    bars, benchmark = regime_change_bars()
    result = BacktestRunner().run(
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"), lookback_days=5, top_n=1
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(
            starting_cash=Decimal("100000"),
            commission_per_trade=Decimal("1"),
            slippage_bps=Decimal("10"),
            short_term_tax_rate=Decimal("0.30"),
            long_term_tax_rate=Decimal("0.15"),
        ),
    )

    assert result.trade_count >= 3
    assert result.net_total_return < result.gross_total_return
    assert result.benchmark_total_return == pytest.approx(
        float(benchmark[-1].close_price / benchmark[0].close_price - Decimal("1"))
    )
    assert result.turnover > 0
    assert result.average_holding_period_days > 0
    assert result.data_warning is not None
    assert result.data_quality_report.status.value == "warning"
    assert result.data_quality_report.can_use_for_research
    assert result.tax_summary.estimated_after_tax_total_return is not None


def test_backtest_sells_before_buys_and_never_shorts() -> None:
    bars, benchmark = regime_change_bars()
    result = BacktestRunner().run(
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"), lookback_days=5, top_n=1
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(
            starting_cash=Decimal("100000"), slippage_bps=Decimal("0")
        ),
    )

    sell_indexes = [
        index
        for index, trade in enumerate(result.trades)
        if trade.side == OrderSide.SELL
    ]
    assert sell_indexes
    for sell_index in sell_indexes:
        same_day_later_trades = [
            trade
            for trade in result.trades[sell_index + 1 :]
            if trade.trading_date == result.trades[sell_index].trading_date
        ]
        assert all(trade.side == OrderSide.BUY for trade in same_day_later_trades)
    assert all(point.equity >= 0 for point in result.equity_curve)


def test_tax_buckets_classify_realized_gains() -> None:
    bars, benchmark = regime_change_bars()
    result = BacktestRunner().run(
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"), lookback_days=5, top_n=1
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(
            starting_cash=Decimal("100000"), slippage_bps=Decimal("0")
        ),
    )

    assert result.tax_summary.short_term_realized_gains != Decimal("0")
    assert result.tax_summary.long_term_realized_gains == Decimal("0")
    assert result.tax_summary.estimated_after_tax_total_return is None


def test_risk_rejections_block_backtest_trades() -> None:
    bars, benchmark = regime_change_bars()
    result = BacktestRunner().run(
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"), lookback_days=5, top_n=1
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(starting_cash=Decimal("100000")),
        risk_engine=RiskEngine(RiskConfig(blocked_symbols=frozenset({"AAA", "BBB"}))),
    )

    assert result.trade_count == 0
    assert result.risk_decisions
    assert any(
        rejection.rule == RiskRule.SYMBOL_BLOCKLIST
        for decision in result.risk_decisions
        for rejection in decision.rejections
    )


def test_backtest_runs_research_only_trend_following_candidate() -> None:
    bars, benchmark = regime_change_bars()

    result = BacktestRunner().run(
        strategy=TrendFollowingETFStrategy(
            universe=("AAA", "BBB"),
            trend_window_days=5,
            top_n=1,
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(starting_cash=Decimal("100000")),
    )

    assert result.trade_count > 0
    assert result.symbols == ("AAA", "BBB", "SPY")
    assert result.data_warning is not None


def test_backtest_provides_benchmark_bars_to_relative_strength_strategy() -> None:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(
        business_days(date(2024, 1, 1), date(2024, 3, 15))
    ):
        bars.append(make_bar("AAA", trading_day, Decimal("100") + Decimal(index)))
        bars.append(make_bar("BBB", trading_day, Decimal("100")))
        benchmark.append(
            make_bar(
                "SPY",
                trading_day,
                Decimal("100") + Decimal(index) / Decimal("4"),
            )
        )

    result = BacktestRunner().run(
        strategy=BenchmarkRelativeStrengthETFStrategy(
            universe=("AAA", "BBB"),
            lookback_days=5,
            tracking_window_days=5,
            top_n=1,
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(slippage_bps=Decimal("0")),
    )

    assert result.trade_count > 0
    assert {trade.symbol for trade in result.trades} == {"AAA"}


def test_backtest_runs_defensive_regime_candidate_with_benchmark_bars() -> None:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(
        business_days(date(2024, 1, 1), date(2024, 3, 15))
    ):
        bars.append(make_bar("AAA", trading_day, Decimal("100") + Decimal(index) * 2))
        bars.append(make_bar("XLP", trading_day, Decimal("100") + Decimal(index)))
        bars.append(make_bar("XLU", trading_day, Decimal("100") - Decimal(index)))
        benchmark.append(make_bar("SPY", trading_day, Decimal("120") - Decimal(index)))

    result = BacktestRunner().run(
        strategy=DefensiveRegimeSwitchETFStrategy(
            universe=("AAA", "XLP", "XLU"),
            defensive_symbols=("XLP", "XLU"),
            regime_lookback_days=5,
            risk_on_top_n=1,
            risk_off_top_n=2,
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(slippage_bps=Decimal("0")),
    )

    assert result.trade_count > 0
    assert {trade.symbol for trade in result.trades} == {"XLP"}


def test_backtest_runs_cash_rotation_candidate_and_can_hold_cash() -> None:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(
        business_days(date(2024, 1, 1), date(2024, 3, 15))
    ):
        if trading_day < date(2024, 2, 1):
            aaa_close = Decimal("100") + Decimal(index) * Decimal("2")
            bbb_close = Decimal("100") + Decimal(index)
        else:
            aaa_close = Decimal("150") - Decimal(index - 22) * Decimal("3")
            bbb_close = Decimal("125") - Decimal(index - 22) * Decimal("2")
        bars.append(make_bar("AAA", trading_day, aaa_close))
        bars.append(make_bar("BBB", trading_day, bbb_close))
        benchmark.append(make_bar("SPY", trading_day, Decimal("100")))

    result = BacktestRunner().run(
        strategy=CashRotationETFStrategy(
            universe=("AAA", "BBB"),
            lookback_days=5,
            top_n=2,
            min_breadth=Decimal("0.50"),
            min_average_top_return=Decimal("0.02"),
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(slippage_bps=Decimal("0")),
    )

    assert [trade.side for trade in result.trades] == [
        OrderSide.BUY,
        OrderSide.BUY,
        OrderSide.SELL,
        OrderSide.SELL,
    ]
    assert {trade.symbol for trade in result.trades} == {"AAA", "BBB"}


def test_empty_backtest_targets_sell_existing_positions_to_cash() -> None:
    bars = [
        make_bar("AAA", trading_day, Decimal("100"))
        for trading_day in business_days(date(2024, 1, 1), date(2024, 2, 15))
    ]
    benchmark = [
        make_bar("SPY", trading_day, Decimal("100"))
        for trading_day in business_days(date(2024, 1, 1), date(2024, 2, 15))
    ]

    result = BacktestRunner().run(
        strategy=CashTargetAfterFirstMonthStrategy(),
        bars=bars,
        benchmark_bars=benchmark,
        config=BacktestConfig(slippage_bps=Decimal("0")),
    )

    assert [trade.side for trade in result.trades] == [OrderSide.BUY, OrderSide.SELL]
    assert result.trades[-1].trading_date >= date(2024, 2, 1)
