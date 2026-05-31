"""Command-line entry point for fetching historical daily bars."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from trading_app.market_data.historical import AlpacaHistoricalBarFetcher
from trading_app.market_data.storage import DEFAULT_BAR_ROOT, ParquetBarStore
from trading_app.schemas import DataFeed, validate_symbol


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch adjusted daily U.S. stock bars."
    )
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols.")
    parser.add_argument("--start", required=True, help="Inclusive YYYY-MM-DD start.")
    parser.add_argument("--end", required=True, help="Inclusive YYYY-MM-DD end.")
    parser.add_argument(
        "--feed",
        default=DataFeed.IEX.value,
        choices=[DataFeed.IEX.value, DataFeed.SIP.value],
    )
    parser.add_argument(
        "--root", default=str(DEFAULT_BAR_ROOT), help="Parquet root path."
    )
    args = parser.parse_args()

    symbols = [
        validate_symbol(symbol.strip())
        for symbol in args.symbols.split(",")
        if symbol.strip()
    ]
    feed = DataFeed(args.feed)
    fetcher = AlpacaHistoricalBarFetcher()
    bars = fetcher.fetch_daily_bars(
        symbols=symbols,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        feed=feed,
    )
    ParquetBarStore(Path(args.root)).write_bars(bars)
    print(f"stored {len(bars)} daily bars for {len(symbols)} symbols at {args.root}")


if __name__ == "__main__":
    main()
