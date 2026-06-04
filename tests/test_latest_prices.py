from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from trading_app.market_data import (
    AlpacaLatestPriceFetcher,
    FixtureLatestPriceFetcher,
    LatestPriceStatus,
)
from trading_app.schemas import DataFeed

NOW = datetime(2026, 5, 29, 20, 5, tzinfo=UTC)


def test_alpaca_latest_price_fetcher_maps_latest_trade_response() -> None:
    client = FakeLatestTradeClient(
        {
            "SPY": SimpleNamespace(price="501.25", timestamp=NOW),
            "XLK": SimpleNamespace(price=Decimal("232.10"), timestamp=NOW),
        }
    )
    fetcher = AlpacaLatestPriceFetcher(client=client)

    snapshot = fetcher.fetch_latest_prices(
        ("SPY", "XLK"),
        as_of=NOW + timedelta(minutes=1),
        feed=DataFeed.IEX,
    )

    assert client.last_request.symbol_or_symbols == ["SPY", "XLK"]
    assert client.last_request.feed.value == "iex"
    assert snapshot.status == LatestPriceStatus.FRESH
    assert snapshot.price_map == {
        "SPY": Decimal("501.25"),
        "XLK": Decimal("232.10"),
    }
    assert snapshot.warning is not None


def test_alpaca_latest_price_fetcher_rejects_blank_credentials() -> None:
    with pytest.raises(ValueError, match="ALPACA_API_KEY"):
        AlpacaLatestPriceFetcher(api_key=" ", secret_key="\t")


def test_latest_price_snapshot_marks_missing_and_stale_symbols() -> None:
    fetcher = FixtureLatestPriceFetcher(
        {"SPY": Decimal("500")},
        observed_at=NOW - timedelta(hours=1),
        missing_symbols=("XLK",),
    )

    snapshot = fetcher.fetch_latest_prices(
        ("SPY", "XLK"),
        as_of=NOW,
        max_age=timedelta(minutes=15),
    )

    assert snapshot.status == LatestPriceStatus.MISSING
    assert snapshot.missing_symbols == ("XLK",)
    assert snapshot.stale_symbols == ("SPY",)
    assert snapshot.freshness_evidence == (
        "missing",
        "stale_symbols=SPY",
        "missing_symbols=XLK",
    )
    assert snapshot.prices[0].status == LatestPriceStatus.STALE
    assert not snapshot.all_fresh


class FakeLatestTradeClient:
    def __init__(self, response) -> None:
        self.response = response
        self.last_request = None

    def get_stock_latest_trade(self, request_params):
        self.last_request = request_params
        return self.response
