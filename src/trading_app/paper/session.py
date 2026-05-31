"""Paper session runner and market-refresh state."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, Field

from trading_app.alpaca_credentials import resolve_alpaca_credentials
from trading_app.broker import AlpacaPaperBrokerAdapter
from trading_app.market_data.historical import (
    AlpacaHistoricalBarFetcher,
    FixtureHistoricalBarFetcher,
    HistoricalBarFetcher,
)
from trading_app.paper.models import PaperPortfolioReport
from trading_app.paper.trading import PaperTradingService
from trading_app.risk import RiskEngine
from trading_app.schemas import DataFeed, OrderStatus, TradingModel, validate_symbol


class PaperSessionMode(StrEnum):
    DEMO = "demo"
    ALPACA_PAPER = "alpaca_paper"


class SessionConnectionStatus(StrEnum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


class MarketDataRefreshStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class MarketDataRefresh(TradingModel):
    as_of: AwareDatetime
    symbols: tuple[str, ...]
    feed: DataFeed
    source: str = Field(min_length=1)
    prices: dict[str, Decimal]
    status: MarketDataRefreshStatus
    warning: str | None = None
    errors: tuple[str, ...] = ()


class PaperSessionEvent(TradingModel):
    as_of: AwareDatetime
    event_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class PaperSessionState(TradingModel):
    as_of: AwareDatetime
    mode: PaperSessionMode
    provider: str = Field(min_length=1)
    connection_status: SessionConnectionStatus
    market_data: MarketDataRefresh
    portfolio_report: PaperPortfolioReport
    open_order_count: int = Field(ge=0)
    events: tuple[PaperSessionEvent, ...] = ()


class PaperSessionRunner:
    """Poll paper broker state and refresh latest market data for operations."""

    def __init__(
        self,
        *,
        service: PaperTradingService,
        symbols: tuple[str, ...],
        mode: PaperSessionMode = PaperSessionMode.DEMO,
        market_data_fetcher: HistoricalBarFetcher | None = None,
        feed: DataFeed = DataFeed.IEX,
        refresh_lookback_days: int = 7,
    ) -> None:
        self.service = service
        self.symbols = tuple(sorted(validate_symbol(symbol) for symbol in symbols))
        self.mode = mode
        self.market_data_fetcher = market_data_fetcher or FixtureHistoricalBarFetcher(
            source="session-demo"
        )
        self.feed = feed
        self.refresh_lookback_days = refresh_lookback_days

    def poll_once(self, *, as_of: datetime) -> PaperSessionState:
        """Synchronize broker state once and return dashboard-ready state."""

        events: list[PaperSessionEvent] = []
        connection_status = SessionConnectionStatus.CONNECTED

        try:
            self._sync_open_orders(as_of=as_of)
        except Exception as error:  # pragma: no cover - exercised by integration use
            connection_status = SessionConnectionStatus.DEGRADED
            events.append(
                PaperSessionEvent(
                    as_of=as_of,
                    event_type="order_sync_error",
                    message=str(error),
                )
            )

        market_data = self.refresh_market_data(as_of=as_of)
        if market_data.status != MarketDataRefreshStatus.FRESH:
            connection_status = SessionConnectionStatus.DEGRADED
            events.extend(
                PaperSessionEvent(
                    as_of=as_of,
                    event_type="market_data_error",
                    message=message,
                )
                for message in market_data.errors
            )

        portfolio_report = self.service.portfolio_report(as_of=as_of)
        if not portfolio_report.reconciliation.reconciled:
            connection_status = SessionConnectionStatus.DEGRADED
            events.append(
                PaperSessionEvent(
                    as_of=as_of,
                    event_type="reconciliation_issue",
                    message=(
                        f"{len(portfolio_report.reconciliation.issues)} "
                        "broker reconciliation issue(s) detected."
                    ),
                )
            )

        open_order_count = sum(
            1
            for status in portfolio_report.order_statuses
            if status.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
        )
        return PaperSessionState(
            as_of=as_of,
            mode=self.mode,
            provider=self.service.broker.provider,
            connection_status=connection_status,
            market_data=market_data,
            portfolio_report=portfolio_report,
            open_order_count=open_order_count,
            events=tuple(events),
        )

    def refresh_market_data(self, *, as_of: datetime) -> MarketDataRefresh:
        """Fetch recent bars and expose latest closes with provenance."""

        symbols = self._symbols_to_refresh(as_of=as_of)
        if not symbols:
            return MarketDataRefresh(
                as_of=as_of,
                symbols=(),
                feed=self.feed,
                source="none",
                prices={},
                status=MarketDataRefreshStatus.UNAVAILABLE,
                errors=("No symbols configured for market refresh.",),
            )

        start = as_of.date() - timedelta(days=self.refresh_lookback_days)
        try:
            bars = self.market_data_fetcher.fetch_daily_bars(
                list(symbols), start, as_of.date(), self.feed
            )
        except Exception as error:
            return MarketDataRefresh(
                as_of=as_of,
                symbols=symbols,
                feed=self.feed,
                source="unavailable",
                prices={},
                status=MarketDataRefreshStatus.UNAVAILABLE,
                errors=(str(error),),
                warning=_feed_warning(self.feed),
            )

        latest = {}
        for symbol in symbols:
            symbol_bars = [bar for bar in bars if bar.symbol == symbol]
            if symbol_bars:
                latest[symbol] = sorted(symbol_bars, key=lambda bar: bar.trading_date)[
                    -1
                ]

        prices = {symbol: bar.close_price for symbol, bar in latest.items()}
        missing = tuple(symbol for symbol in symbols if symbol not in prices)
        status = (
            MarketDataRefreshStatus.FRESH
            if not missing
            else MarketDataRefreshStatus.STALE
            if prices
            else MarketDataRefreshStatus.UNAVAILABLE
        )
        sources = tuple(sorted({bar.source for bar in latest.values()}))
        return MarketDataRefresh(
            as_of=as_of,
            symbols=symbols,
            feed=self.feed,
            source=", ".join(sources) if sources else "unavailable",
            prices=prices,
            status=status,
            errors=tuple(f"Missing latest price for {symbol}." for symbol in missing),
            warning=_feed_warning(self.feed),
        )

    def _sync_open_orders(self, *, as_of: datetime) -> None:
        if not hasattr(self.service.broker, "list_orders"):
            return
        for broker_order in self.service.broker.list_orders():
            client_order_id = broker_order.client_order_id
            if client_order_id and self.service.ledger.get_order(client_order_id):
                self.service.ingest_order_state(broker_order, as_of=as_of)

    def _symbols_to_refresh(self, *, as_of: datetime) -> tuple[str, ...]:
        position_symbols = tuple(
            position.symbol
            for position in self.service.ledger.snapshot(as_of).positions
        )
        return tuple(sorted(set(self.symbols) | set(position_symbols)))


def build_alpaca_paper_session_from_env(
    *,
    symbols: tuple[str, ...],
    starting_cash: Decimal = Decimal("100000"),
    risk_engine: RiskEngine | None = None,
    feed: DataFeed = DataFeed.IEX,
) -> PaperSessionRunner:
    """Create a real Alpaca paper session runner from environment variables."""

    resolve_alpaca_credentials()
    service = PaperTradingService(
        broker=AlpacaPaperBrokerAdapter(),
        starting_cash=starting_cash,
        risk_engine=risk_engine,
    )
    return PaperSessionRunner(
        service=service,
        symbols=symbols,
        mode=PaperSessionMode.ALPACA_PAPER,
        market_data_fetcher=AlpacaHistoricalBarFetcher(),
        feed=feed,
    )


def _feed_warning(feed: DataFeed) -> str | None:
    if feed == DataFeed.IEX:
        return (
            "IEX/free data is development-grade and should not drive final "
            "funding decisions."
        )
    return None
