"""Parquet storage and DuckDB query helpers for daily bars."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from trading_app.schemas import (
    AdjustmentType,
    BarTimeframe,
    DailyBar,
    DataFeed,
    validate_symbol,
)

DEFAULT_BAR_ROOT = Path("data/market_data/bars")


class ParquetBarStore:
    """Store and load daily bars as replayable Parquet archives."""

    def __init__(self, root: Path | str = DEFAULT_BAR_ROOT) -> None:
        self.root = Path(root)

    def write_bars(self, bars: list[DailyBar] | tuple[DailyBar, ...]) -> None:
        grouped: dict[tuple[str, str, str], list[DailyBar]] = {}
        for bar in bars:
            key = (bar.data_feed.value, bar.timeframe.value, bar.symbol)
            grouped.setdefault(key, []).append(bar)

        for (feed, timeframe, symbol), group in grouped.items():
            path = self._bar_file(feed=feed, timeframe=timeframe, symbol=symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            records = [_bar_to_record(bar) for bar in sorted(group, key=_bar_sort_key)]
            table = pa.Table.from_pylist(records)
            pq.write_table(table, path)

    def read_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        feed: DataFeed = DataFeed.IEX,
    ) -> tuple[DailyBar, ...]:
        return DuckDBBarQuery(self.root).load_daily_bars(symbols, start, end, feed)

    def _bar_file(self, *, feed: str, timeframe: str, symbol: str) -> Path:
        return (
            self.root
            / f"feed={feed}"
            / f"timeframe={timeframe}"
            / f"symbol={symbol}"
            / "bars.parquet"
        )


class DuckDBBarQuery:
    """Query Parquet bar archives directly through DuckDB."""

    def __init__(self, root: Path | str = DEFAULT_BAR_ROOT) -> None:
        self.root = Path(root)

    def load_daily_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        feed: DataFeed = DataFeed.IEX,
    ) -> tuple[DailyBar, ...]:
        if end < start:
            return ()

        normalized_symbols = [validate_symbol(symbol) for symbol in symbols]
        paths = [
            str(
                self.root
                / f"feed={feed.value}"
                / f"timeframe={BarTimeframe.DAY.value}"
                / f"symbol={symbol}"
                / "bars.parquet"
            )
            for symbol in normalized_symbols
            if (
                self.root
                / f"feed={feed.value}"
                / f"timeframe={BarTimeframe.DAY.value}"
                / f"symbol={symbol}"
                / "bars.parquet"
            ).exists()
        ]
        if not paths:
            return ()

        connection = duckdb.connect(":memory:")
        try:
            relation = connection.read_parquet(paths)
            symbol_values = ", ".join(f"'{symbol}'" for symbol in normalized_symbols)
            df = (
                relation.filter(
                    "timeframe = '1D' "
                    f"AND data_feed = '{feed.value}' "
                    f"AND symbol IN ({symbol_values}) "
                    f"AND trading_date >= '{start.isoformat()}' "
                    f"AND trading_date <= '{end.isoformat()}'"
                )
                .order("trading_date, symbol")
                .to_df()
            )
        finally:
            connection.close()

        return _bars_from_dataframe(df)


def _bar_to_record(bar: DailyBar) -> dict[str, str]:
    return {
        "symbol": bar.symbol,
        "trading_date": bar.trading_date.isoformat(),
        "bar_at": bar.bar_at.isoformat(),
        "ingested_at": bar.ingested_at.isoformat(),
        "open_price": str(bar.open_price),
        "high_price": str(bar.high_price),
        "low_price": str(bar.low_price),
        "close_price": str(bar.close_price),
        "volume": str(bar.volume),
        "source": bar.source,
        "data_feed": bar.data_feed.value,
        "timeframe": bar.timeframe.value,
        "adjustment": bar.adjustment.value,
    }


def _bars_from_dataframe(dataframe: pd.DataFrame) -> tuple[DailyBar, ...]:
    if dataframe.empty:
        return ()

    bars: list[DailyBar] = []
    for row in dataframe.to_dict("records"):
        bars.append(
            DailyBar(
                symbol=str(row["symbol"]),
                trading_date=date.fromisoformat(str(row["trading_date"])),
                bar_at=datetime.fromisoformat(str(row["bar_at"])),
                ingested_at=_ingested_at_from_row(row),
                open_price=Decimal(str(row["open_price"])),
                high_price=Decimal(str(row["high_price"])),
                low_price=Decimal(str(row["low_price"])),
                close_price=Decimal(str(row["close_price"])),
                volume=Decimal(str(row["volume"])),
                source=str(row["source"]),
                data_feed=DataFeed(str(row["data_feed"])),
                timeframe=BarTimeframe(str(row["timeframe"])),
                adjustment=AdjustmentType(str(row["adjustment"])),
            )
        )

    return tuple(sorted(bars, key=_bar_sort_key))


def _bar_sort_key(bar: DailyBar) -> tuple[date, str]:
    return (bar.trading_date, bar.symbol)


def _ingested_at_from_row(row: dict) -> datetime:
    value = row.get("ingested_at")
    if value is None:
        return datetime.fromisoformat(str(row["bar_at"]))
    return datetime.fromisoformat(str(value))
