"""Historical daily-bar fetchers."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Protocol

import pandas as pd

from trading_app.alpaca_credentials import resolve_alpaca_credentials
from trading_app.alpaca_http import install_default_alpaca_http_timeout
from trading_app.schemas import (
    AdjustmentType,
    BarTimeframe,
    DailyBar,
    DataFeed,
    MarketSession,
    validate_symbol,
)


class HistoricalBarFetcher(Protocol):
    """Fetch daily bars from a concrete data source."""

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        feed: DataFeed = DataFeed.IEX,
    ) -> tuple[DailyBar, ...]:
        """Fetch daily bars for inclusive start/end dates."""


class FixtureHistoricalBarFetcher:
    """Deterministic daily-bar source for tests and local demos."""

    def __init__(self, source: str = "fixture") -> None:
        self.source = source

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        feed: DataFeed = DataFeed.IEX,
    ) -> tuple[DailyBar, ...]:
        if end < start:
            return ()

        normalized_symbols = [validate_symbol(symbol) for symbol in symbols]
        bars: list[DailyBar] = []
        trading_days = _business_days(start, end)
        ingested_at = datetime.combine(end, time(hour=23), tzinfo=UTC)

        for symbol_index, symbol in enumerate(normalized_symbols):
            base = Decimal("80") + Decimal(symbol_index * 7)
            daily_step = Decimal("0.05") + Decimal(symbol_index) * Decimal("0.03")
            for day_index, trading_day in enumerate(trading_days):
                close = (base + Decimal(day_index) * daily_step).quantize(
                    Decimal("0.0001")
                )
                open_price = (close * Decimal("0.9975")).quantize(Decimal("0.0001"))
                high_price = (close * Decimal("1.01")).quantize(Decimal("0.0001"))
                low_price = (close * Decimal("0.99")).quantize(Decimal("0.0001"))
                volume = Decimal(1_000_000 + symbol_index * 10_000 + day_index * 100)
                bars.append(
                    DailyBar(
                        symbol=symbol,
                        trading_date=trading_day,
                        bar_at=datetime.combine(trading_day, time(hour=21), tzinfo=UTC),
                        ingested_at=ingested_at,
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        close_price=close,
                        volume=volume,
                        source=self.source,
                        data_feed=feed,
                        timeframe=BarTimeframe.DAY,
                        adjustment=AdjustmentType.ALL,
                        metadata={"session": MarketSession.REGULAR.value},
                    )
                )

        return tuple(sorted(bars, key=lambda bar: (bar.trading_date, bar.symbol)))


class AlpacaHistoricalBarFetcher:
    """Fetch adjusted daily U.S. stock bars from Alpaca market data."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        client=None,
        source: str = "alpaca",
    ) -> None:
        self.source = source
        if client is not None:
            self._client = client
            install_default_alpaca_http_timeout(self._client)
            return

        resolved_api_key, resolved_secret_key = resolve_alpaca_credentials(
            api_key=api_key,
            secret_key=secret_key,
        )

        from alpaca.data.historical import StockHistoricalDataClient

        self._client = StockHistoricalDataClient(
            api_key=resolved_api_key,
            secret_key=resolved_secret_key,
        )
        install_default_alpaca_http_timeout(self._client)

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        feed: DataFeed = DataFeed.IEX,
    ) -> tuple[DailyBar, ...]:
        if end < start:
            return ()

        normalized_symbols = [validate_symbol(symbol) for symbol in symbols]
        request = self._build_request(normalized_symbols, start, end, feed)
        response = self._client.get_stock_bars(request_params=request)
        return _daily_bars_from_dataframe(
            response.df,
            source=self.source,
            feed=feed,
            adjustment=AdjustmentType.ALL,
            ingested_at=datetime.now(tz=UTC),
        )

    @staticmethod
    def _build_request(symbols: list[str], start: date, end: date, feed: DataFeed):
        from alpaca.data.enums import Adjustment
        from alpaca.data.enums import DataFeed as AlpacaDataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        if feed not in {DataFeed.IEX, DataFeed.SIP}:
            raise ValueError("Alpaca historical daily bars support IEX or SIP feed")

        return StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start,
            end=end + timedelta(days=1),
            adjustment=Adjustment.ALL,
            feed=getattr(AlpacaDataFeed, feed.value),
        )


def _daily_bars_from_dataframe(
    dataframe: pd.DataFrame,
    *,
    source: str,
    feed: DataFeed,
    adjustment: AdjustmentType,
    ingested_at: datetime,
) -> tuple[DailyBar, ...]:
    if dataframe.empty:
        return ()

    df = dataframe.reset_index()
    if "timestamp" not in df.columns and "level_1" in df.columns:
        df = df.rename(columns={"level_1": "timestamp"})
    if "symbol" not in df.columns and "level_0" in df.columns:
        df = df.rename(columns={"level_0": "symbol"})

    bars: list[DailyBar] = []
    for row in df.to_dict("records"):
        timestamp = row["timestamp"]
        if not isinstance(timestamp, datetime):
            timestamp = pd.Timestamp(timestamp).to_pydatetime()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        bars.append(
            DailyBar(
                symbol=str(row["symbol"]),
                trading_date=timestamp.date(),
                bar_at=timestamp,
                ingested_at=ingested_at,
                open_price=_to_decimal(row["open"]),
                high_price=_to_decimal(row["high"]),
                low_price=_to_decimal(row["low"]),
                close_price=_to_decimal(row["close"]),
                volume=_to_decimal(row["volume"]),
                source=source,
                data_feed=feed,
                timeframe=BarTimeframe.DAY,
                adjustment=adjustment,
            )
        )

    return tuple(sorted(bars, key=lambda bar: (bar.trading_date, bar.symbol)))


def _business_days(start: date, end: date) -> list[date]:
    current = start
    days: list[date] = []
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _to_decimal(value) -> Decimal:
    return Decimal(str(value))
