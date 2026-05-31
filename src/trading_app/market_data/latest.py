"""Latest-price fetchers for live paper monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from pydantic import AwareDatetime, Field, field_validator

from trading_app.alpaca_credentials import resolve_alpaca_credentials
from trading_app.schemas import DataFeed, Price, TradingModel, validate_symbol


class LatestPriceStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"


class LatestPriceRecord(TradingModel):
    symbol: str
    price: Price
    observed_at: AwareDatetime
    fetched_at: AwareDatetime
    feed: DataFeed
    source: str = Field(min_length=1)
    status: LatestPriceStatus = LatestPriceStatus.FRESH

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class LatestPriceSnapshot(TradingModel):
    as_of: AwareDatetime
    feed: DataFeed
    source: str = Field(min_length=1)
    prices: tuple[LatestPriceRecord, ...]
    missing_symbols: tuple[str, ...] = ()
    status: LatestPriceStatus
    warning: str | None = None

    @property
    def price_map(self) -> dict[str, Decimal]:
        return {record.symbol: record.price for record in self.prices}

    @property
    def all_fresh(self) -> bool:
        return self.status == LatestPriceStatus.FRESH and not self.missing_symbols


class LatestPriceFetcher(Protocol):
    def fetch_latest_prices(
        self,
        symbols: tuple[str, ...],
        *,
        as_of: datetime,
        feed: DataFeed = DataFeed.IEX,
        max_age: timedelta = timedelta(minutes=15),
    ) -> LatestPriceSnapshot: ...


class AlpacaLatestPriceFetcher:
    """Fetch latest U.S. equity trade prices from Alpaca market data."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        client: Any | None = None,
        source: str = "alpaca",
    ) -> None:
        self.source = source
        if client is not None:
            self._client = client
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

    def fetch_latest_prices(
        self,
        symbols: tuple[str, ...],
        *,
        as_of: datetime,
        feed: DataFeed = DataFeed.IEX,
        max_age: timedelta = timedelta(minutes=15),
    ) -> LatestPriceSnapshot:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        normalized_symbols = tuple(
            sorted(validate_symbol(symbol) for symbol in symbols)
        )
        if not normalized_symbols:
            return LatestPriceSnapshot(
                as_of=as_of,
                feed=feed,
                source=self.source,
                prices=(),
                missing_symbols=(),
                status=LatestPriceStatus.MISSING,
                warning=_feed_warning(feed),
            )

        request = _latest_trade_request(normalized_symbols, feed)
        response = self._client.get_stock_latest_trade(request_params=request)
        records: list[LatestPriceRecord] = []
        missing: list[str] = []
        for symbol in normalized_symbols:
            trade = _response_item(response, symbol)
            if trade is None:
                missing.append(symbol)
                continue
            observed_at = _aware_datetime(_value(trade, "timestamp"))
            price = Decimal(str(_value(trade, "price")))
            status = (
                LatestPriceStatus.STALE
                if as_of - observed_at > max_age
                else LatestPriceStatus.FRESH
            )
            records.append(
                LatestPriceRecord(
                    symbol=symbol,
                    price=price,
                    observed_at=observed_at,
                    fetched_at=as_of,
                    feed=feed,
                    source=self.source,
                    status=status,
                )
            )

        snapshot_status = LatestPriceStatus.FRESH
        if missing:
            snapshot_status = LatestPriceStatus.MISSING
        elif any(record.status == LatestPriceStatus.STALE for record in records):
            snapshot_status = LatestPriceStatus.STALE

        return LatestPriceSnapshot(
            as_of=as_of,
            feed=feed,
            source=self.source,
            prices=tuple(records),
            missing_symbols=tuple(missing),
            status=snapshot_status,
            warning=_feed_warning(feed),
        )


class FixtureLatestPriceFetcher:
    """Deterministic latest-price fetcher for tests."""

    def __init__(
        self,
        prices: dict[str, Decimal],
        *,
        observed_at: datetime,
        source: str = "latest-fixture",
        missing_symbols: tuple[str, ...] = (),
    ) -> None:
        self.prices = {
            validate_symbol(symbol): price for symbol, price in prices.items()
        }
        self.observed_at = observed_at
        self.source = source
        self.missing_symbols = tuple(
            validate_symbol(symbol) for symbol in missing_symbols
        )

    def fetch_latest_prices(
        self,
        symbols: tuple[str, ...],
        *,
        as_of: datetime,
        feed: DataFeed = DataFeed.IEX,
        max_age: timedelta = timedelta(minutes=15),
    ) -> LatestPriceSnapshot:
        records = []
        missing = []
        for symbol in tuple(sorted(validate_symbol(symbol) for symbol in symbols)):
            if symbol in self.missing_symbols or symbol not in self.prices:
                missing.append(symbol)
                continue
            status = (
                LatestPriceStatus.STALE
                if as_of - self.observed_at > max_age
                else LatestPriceStatus.FRESH
            )
            records.append(
                LatestPriceRecord(
                    symbol=symbol,
                    price=self.prices[symbol],
                    observed_at=self.observed_at,
                    fetched_at=as_of,
                    feed=feed,
                    source=self.source,
                    status=status,
                )
            )
        snapshot_status = LatestPriceStatus.FRESH
        if missing:
            snapshot_status = LatestPriceStatus.MISSING
        elif any(record.status == LatestPriceStatus.STALE for record in records):
            snapshot_status = LatestPriceStatus.STALE
        return LatestPriceSnapshot(
            as_of=as_of,
            feed=feed,
            source=self.source,
            prices=tuple(records),
            missing_symbols=tuple(missing),
            status=snapshot_status,
            warning=_feed_warning(feed),
        )


def _latest_trade_request(symbols: tuple[str, ...], feed: DataFeed):
    from alpaca.data.enums import DataFeed as AlpacaDataFeed
    from alpaca.data.requests import StockLatestTradeRequest

    if feed not in {DataFeed.IEX, DataFeed.SIP}:
        raise ValueError("Alpaca latest trades support IEX or SIP feed")
    return StockLatestTradeRequest(
        symbol_or_symbols=list(symbols),
        feed=getattr(AlpacaDataFeed, feed.value),
    )


def _response_item(response: Any, symbol: str) -> Any | None:
    if isinstance(response, dict):
        return response.get(symbol)
    try:
        return response[symbol]
    except (KeyError, TypeError):
        return None


def _value(raw: Any, name: str) -> Any:
    value = raw.get(name) if isinstance(raw, dict) else getattr(raw, name, None)
    if value is None:
        raise ValueError(f"missing latest trade field: {name}")
    return value


def _aware_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value


def _feed_warning(feed: DataFeed) -> str | None:
    if feed == DataFeed.IEX:
        return (
            "IEX/free data is development-grade and should not drive final "
            "funding decisions."
        )
    return None
