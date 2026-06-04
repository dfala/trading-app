from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from trading_app.market_data.historical import (
    AlpacaHistoricalBarFetcher,
    FixtureHistoricalBarFetcher,
)
from trading_app.market_data.storage import DuckDBBarQuery, ParquetBarStore
from trading_app.schemas import DataFeed


def test_fixture_fetcher_returns_deterministic_daily_bars() -> None:
    fetcher = FixtureHistoricalBarFetcher()

    bars = fetcher.fetch_daily_bars(
        symbols=["SPY", "XLK"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 5),
        feed=DataFeed.IEX,
    )

    assert len(bars) == 10
    assert bars[0].symbol == "SPY"
    assert bars[0].trading_date == date(2024, 1, 1)
    assert bars[0].ingested_at == datetime(2024, 1, 5, 23, tzinfo=UTC)
    assert bars[-1].symbol == "XLK"
    assert bars[-1].close_price > bars[0].close_price


def test_alpaca_fetcher_maps_mocked_dataframe_to_daily_bars() -> None:
    class FakeClient:
        def get_stock_bars(self, request_params):
            self.request_params = request_params
            return SimpleNamespace(
                df=pd.DataFrame(
                    [
                        {
                            "symbol": "SPY",
                            "timestamp": datetime(2024, 1, 2, 21, tzinfo=UTC),
                            "open": 470.0,
                            "high": 475.0,
                            "low": 469.0,
                            "close": 474.0,
                            "volume": 1_000_000,
                        }
                    ]
                )
            )

    fake_client = FakeClient()
    fetcher = AlpacaHistoricalBarFetcher(client=fake_client)

    bars = fetcher.fetch_daily_bars(
        symbols=["SPY"],
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
        feed=DataFeed.IEX,
    )

    assert len(bars) == 1
    assert bars[0].symbol == "SPY"
    assert bars[0].close_price == Decimal("474.0")
    assert bars[0].ingested_at.tzinfo is not None
    assert fake_client.request_params is not None


def test_alpaca_historical_fetcher_rejects_blank_credentials() -> None:
    with pytest.raises(ValueError, match="ALPACA_API_KEY"):
        AlpacaHistoricalBarFetcher(api_key="\n", secret_key=" ")


def test_parquet_store_and_duckdb_query_round_trip(tmp_path) -> None:
    bars = FixtureHistoricalBarFetcher().fetch_daily_bars(
        symbols=["SPY", "XLK"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 10),
        feed=DataFeed.IEX,
    )
    store = ParquetBarStore(tmp_path)

    store.write_bars(bars)
    read_back = store.read_bars(
        symbols=["SPY"],
        start=date(2024, 1, 3),
        end=date(2024, 1, 5),
        feed=DataFeed.IEX,
    )
    duckdb_bars = DuckDBBarQuery(tmp_path).load_daily_bars(
        symbols=["XLK"],
        start=date(2024, 1, 3),
        end=date(2024, 1, 5),
        feed=DataFeed.IEX,
    )

    assert [bar.symbol for bar in read_back] == ["SPY", "SPY", "SPY"]
    assert all(bar.ingested_at == bars[0].ingested_at for bar in read_back)
    assert [bar.trading_date for bar in read_back] == [
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]
    assert [bar.symbol for bar in duckdb_bars] == ["XLK", "XLK", "XLK"]


def test_parquet_store_merges_new_bars_without_erasing_history(tmp_path) -> None:
    store = ParquetBarStore(tmp_path)
    early_bars = FixtureHistoricalBarFetcher().fetch_daily_bars(
        symbols=["SPY"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 5),
        feed=DataFeed.IEX,
    )
    later_bars = FixtureHistoricalBarFetcher().fetch_daily_bars(
        symbols=["SPY"],
        start=date(2024, 1, 8),
        end=date(2024, 1, 10),
        feed=DataFeed.IEX,
    )

    store.write_bars(early_bars)
    store.write_bars(later_bars)
    read_back = store.read_bars(
        symbols=["SPY"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 10),
        feed=DataFeed.IEX,
    )

    assert [bar.trading_date for bar in read_back] == [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
        date(2024, 1, 10),
    ]


def test_duckdb_query_empty_range_and_missing_symbol_returns_empty(tmp_path) -> None:
    bars = FixtureHistoricalBarFetcher().fetch_daily_bars(
        symbols=["SPY"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 5),
        feed=DataFeed.IEX,
    )
    ParquetBarStore(tmp_path).write_bars(bars)

    query = DuckDBBarQuery(tmp_path)

    assert query.load_daily_bars(["QQQ"], date(2024, 1, 1), date(2024, 1, 5)) == ()
    assert query.load_daily_bars(["SPY"], date(2024, 2, 1), date(2024, 2, 5)) == ()
