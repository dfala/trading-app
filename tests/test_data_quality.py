from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_app.market_data import (
    DataQualityIssueCode,
    DataQualityStatus,
    FixtureLatestPriceFetcher,
    MarketDataQualityChecker,
)
from trading_app.schemas import DailyBar, DataFeed

NOW = datetime(2026, 5, 29, 20, tzinfo=UTC)


def make_bar(
    symbol: str,
    trading_date: date,
    *,
    feed: DataFeed = DataFeed.SIP,
    volume: Decimal = Decimal("1000000"),
) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            21,
            tzinfo=UTC,
        ),
        ingested_at=NOW,
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100"),
        volume=volume,
        source="quality-test",
        data_feed=feed,
    )


def test_daily_bar_quality_passes_clean_sip_dataset() -> None:
    bars = (
        make_bar("AAA", date(2026, 5, 28)),
        make_bar("AAA", date(2026, 5, 29)),
    )

    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 28),
        end=date(2026, 5, 29),
        generated_at=NOW,
        expected_feed=DataFeed.SIP,
        as_of_date=date(2026, 5, 29),
    )

    assert report.status == DataQualityStatus.PASSED
    assert report.can_use_for_research
    assert report.can_use_for_trading
    assert report.provenance.feeds == (DataFeed.SIP,)
    assert report.provenance.ingested_at_min == NOW
    assert report.provenance.ingested_at_max == NOW


def test_daily_bar_quality_warns_for_iex_and_missing_bars() -> None:
    bars = (make_bar("AAA", date(2026, 5, 28), feed=DataFeed.IEX),)

    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 28),
        end=date(2026, 5, 29),
        generated_at=NOW,
        expected_feed=DataFeed.IEX,
        as_of_date=date(2026, 5, 29),
    )
    codes = {issue.code for issue in report.issues}

    assert report.status == DataQualityStatus.WARNING
    assert report.can_use_for_research
    assert not report.can_use_for_trading
    assert DataQualityIssueCode.IEX_DEVELOPMENT_GRADE in codes
    assert DataQualityIssueCode.MISSING_BAR in codes


def test_daily_bar_quality_fails_duplicates_mixed_feeds_and_lookahead() -> None:
    bars = (
        make_bar("AAA", date(2026, 5, 29), feed=DataFeed.SIP),
        make_bar("AAA", date(2026, 5, 29), feed=DataFeed.IEX),
        make_bar("AAA", date(2026, 6, 1), feed=DataFeed.SIP),
    )

    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 29),
        end=date(2026, 6, 1),
        generated_at=NOW,
        expected_feed=DataFeed.SIP,
        as_of_date=date(2026, 5, 29),
    )
    codes = {issue.code for issue in report.issues}

    assert report.status == DataQualityStatus.FAILED
    assert not report.can_use_for_research
    assert DataQualityIssueCode.DUPLICATE_BAR in codes
    assert DataQualityIssueCode.MIXED_FEEDS in codes
    assert DataQualityIssueCode.UNEXPECTED_FEED in codes
    assert DataQualityIssueCode.LOOKAHEAD_BAR in codes


def test_daily_bar_quality_warns_on_out_of_order_input() -> None:
    bars = (
        make_bar("AAA", date(2026, 5, 29)),
        make_bar("AAA", date(2026, 5, 28)),
    )

    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 28),
        end=date(2026, 5, 29),
        generated_at=NOW,
        expected_feed=DataFeed.SIP,
    )

    assert report.status == DataQualityStatus.WARNING
    assert any(
        issue.code == DataQualityIssueCode.OUT_OF_ORDER for issue in report.issues
    )


def test_daily_bar_quality_warns_on_zero_volume_bars() -> None:
    bars = (
        make_bar("AAA", date(2026, 5, 28), volume=Decimal("0")),
        make_bar("AAA", date(2026, 5, 29)),
    )

    report = MarketDataQualityChecker().assess_daily_bars(
        bars,
        symbols=("AAA",),
        start=date(2026, 5, 28),
        end=date(2026, 5, 29),
        generated_at=NOW,
        expected_feed=DataFeed.SIP,
    )

    assert report.status == DataQualityStatus.WARNING
    assert report.can_use_for_research
    assert not report.can_use_for_trading
    assert any(
        issue.code == DataQualityIssueCode.ZERO_VOLUME for issue in report.issues
    )


def test_latest_price_quality_fails_missing_and_stale_prices() -> None:
    snapshot = FixtureLatestPriceFetcher(
        {"AAA": Decimal("100")},
        observed_at=NOW - timedelta(hours=1),
        missing_symbols=("BBB",),
    ).fetch_latest_prices(
        ("AAA", "BBB"),
        as_of=NOW,
        feed=DataFeed.IEX,
        max_age=timedelta(minutes=15),
    )

    report = MarketDataQualityChecker().assess_latest_prices(
        snapshot,
        symbols=("AAA", "BBB"),
        generated_at=NOW,
    )
    codes = {issue.code for issue in report.issues}

    assert report.status == DataQualityStatus.FAILED
    assert not report.can_use_for_trading
    assert DataQualityIssueCode.MISSING_LATEST_PRICE in codes
    assert DataQualityIssueCode.STALE_LATEST_PRICE in codes
    assert DataQualityIssueCode.IEX_DEVELOPMENT_GRADE in codes
