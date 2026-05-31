"""Command-line entry point for the first sector momentum backtest."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from pathlib import Path

from trading_app.backtest.runner import BacktestConfig, BacktestRunner
from trading_app.market_data.storage import DEFAULT_BAR_ROOT, DuckDBBarQuery
from trading_app.schemas import DataFeed
from trading_app.strategies.sector_momentum import (
    DEFAULT_SECTOR_ETFS,
    MonthlySectorMomentumStrategy,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run monthly sector momentum.")
    parser.add_argument("--start", required=True, help="Inclusive YYYY-MM-DD start.")
    parser.add_argument("--end", required=True, help="Inclusive YYYY-MM-DD end.")
    parser.add_argument(
        "--feed", default=DataFeed.IEX.value, choices=[f.value for f in DataFeed]
    )
    parser.add_argument(
        "--root", default=str(DEFAULT_BAR_ROOT), help="Parquet root path."
    )
    parser.add_argument("--starting-cash", default="100000")
    parser.add_argument("--slippage-bps", default="5")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    feed = DataFeed(args.feed)
    query = DuckDBBarQuery(Path(args.root))
    bars = query.load_daily_bars(list(DEFAULT_SECTOR_ETFS), start, end, feed)
    benchmark_bars = query.load_daily_bars(["SPY"], start, end, feed)
    result = BacktestRunner().run(
        strategy=MonthlySectorMomentumStrategy(),
        bars=bars,
        benchmark_bars=benchmark_bars,
        config=BacktestConfig(
            starting_cash=Decimal(args.starting_cash),
            slippage_bps=Decimal(args.slippage_bps),
        ),
    )

    print(f"net_total_return={result.net_total_return:.4%}")
    print(f"benchmark_total_return={result.benchmark_total_return:.4%}")
    print(f"max_drawdown={result.max_drawdown:.4%}")
    if result.data_warning:
        print(f"warning={result.data_warning}")


if __name__ == "__main__":
    main()
