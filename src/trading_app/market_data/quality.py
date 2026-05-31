"""Market-data quality and provenance checks."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from pydantic import AwareDatetime, Field

from trading_app.market_data.latest import LatestPriceSnapshot, LatestPriceStatus
from trading_app.schemas import (
    AdjustmentType,
    BarTimeframe,
    DailyBar,
    DataFeed,
    TradingModel,
    validate_symbol,
)


class DataQualityStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class DataQualityIssueCode(StrEnum):
    EMPTY_DATASET = "empty_dataset"
    INVALID_SYMBOL = "invalid_symbol"
    MISSING_BAR = "missing_bar"
    DUPLICATE_BAR = "duplicate_bar"
    OUT_OF_ORDER = "out_of_order"
    MIXED_FEEDS = "mixed_feeds"
    MIXED_TIMEFRAMES = "mixed_timeframes"
    MIXED_ADJUSTMENTS = "mixed_adjustments"
    UNEXPECTED_FEED = "unexpected_feed"
    IEX_DEVELOPMENT_GRADE = "iex_development_grade"
    LOOKAHEAD_BAR = "lookahead_bar"
    MISSING_LATEST_PRICE = "missing_latest_price"
    STALE_LATEST_PRICE = "stale_latest_price"
    ZERO_VOLUME = "zero_volume"


class MarketDataProvenance(TradingModel):
    dataset_type: str = Field(min_length=1)
    symbols: tuple[str, ...]
    start: date | None = None
    end: date | None = None
    ingested_at_min: AwareDatetime | None = None
    ingested_at_max: AwareDatetime | None = None
    feeds: tuple[DataFeed, ...]
    sources: tuple[str, ...]
    timeframes: tuple[BarTimeframe, ...] = ()
    adjustments: tuple[AdjustmentType, ...] = ()


class DataQualityIssue(TradingModel):
    code: DataQualityIssueCode
    status: DataQualityStatus
    message: str = Field(min_length=1)
    symbol: str | None = None
    trading_date: date | None = None
    evidence: tuple[str, ...] = ()


class MarketDataQualityReport(TradingModel):
    generated_at: AwareDatetime
    status: DataQualityStatus
    can_use_for_research: bool
    can_use_for_trading: bool
    provenance: MarketDataProvenance
    issues: tuple[DataQualityIssue, ...] = ()
    warnings: int = Field(ge=0)
    failures: int = Field(ge=0)
    summary: str = Field(min_length=1)


class MarketDataQualityChecker:
    """Produce timestamp-safe market-data quality reports."""

    def assess_daily_bars(
        self,
        bars: tuple[DailyBar, ...] | list[DailyBar],
        *,
        symbols: tuple[str, ...] | list[str],
        start: date,
        end: date,
        generated_at: datetime | None = None,
        expected_feed: DataFeed | None = None,
        as_of_date: date | None = None,
        require_all_symbols: bool = True,
    ) -> MarketDataQualityReport:
        checked_at = _aware_now(generated_at)
        normalized_symbols, invalid_symbol_issues = _normalize_symbols(symbols)
        bars_tuple = tuple(bars)
        issues = list(invalid_symbol_issues)

        if not bars_tuple:
            issues.append(
                _issue(
                    DataQualityIssueCode.EMPTY_DATASET,
                    DataQualityStatus.FAILED,
                    "No daily bars were supplied.",
                )
            )

        issues.extend(_daily_bar_structure_issues(bars_tuple, expected_feed))
        if bars_tuple != tuple(
            sorted(bars_tuple, key=lambda bar: (bar.trading_date, bar.symbol))
        ):
            issues.append(
                _issue(
                    DataQualityIssueCode.OUT_OF_ORDER,
                    DataQualityStatus.WARNING,
                    "Daily bars are not sorted by trading date and symbol.",
                )
            )

        duplicates = _duplicate_bars(bars_tuple)
        for symbol, trading_day in duplicates:
            issues.append(
                _issue(
                    DataQualityIssueCode.DUPLICATE_BAR,
                    DataQualityStatus.FAILED,
                    "Duplicate daily bar for symbol and trading date.",
                    symbol=symbol,
                    trading_date=trading_day,
                )
            )

        for bar in bars_tuple:
            if bar.volume == 0:
                issues.append(
                    _issue(
                        DataQualityIssueCode.ZERO_VOLUME,
                        DataQualityStatus.WARNING,
                        "Daily bar has zero volume.",
                        symbol=bar.symbol,
                        trading_date=bar.trading_date,
                    )
                )

        if require_all_symbols and normalized_symbols:
            available = {(bar.symbol, bar.trading_date) for bar in bars_tuple}
            for trading_day in _business_days(start, end):
                for symbol in normalized_symbols:
                    if (symbol, trading_day) not in available:
                        issues.append(
                            _issue(
                                DataQualityIssueCode.MISSING_BAR,
                                DataQualityStatus.WARNING,
                                "Expected daily bar is missing.",
                                symbol=symbol,
                                trading_date=trading_day,
                            )
                        )

        if as_of_date is not None:
            for bar in bars_tuple:
                if bar.trading_date > as_of_date:
                    issues.append(
                        _issue(
                            DataQualityIssueCode.LOOKAHEAD_BAR,
                            DataQualityStatus.FAILED,
                            "Daily bar is after the decision date.",
                            symbol=bar.symbol,
                            trading_date=bar.trading_date,
                            evidence=(f"as_of_date={as_of_date.isoformat()}",),
                        )
                    )

        provenance = MarketDataProvenance(
            dataset_type="daily_bars",
            symbols=tuple(
                sorted({*normalized_symbols, *(bar.symbol for bar in bars_tuple)})
            ),
            start=start,
            end=end,
            ingested_at_min=min((bar.ingested_at for bar in bars_tuple), default=None),
            ingested_at_max=max((bar.ingested_at for bar in bars_tuple), default=None),
            feeds=tuple(
                sorted(
                    {bar.data_feed for bar in bars_tuple}, key=lambda item: item.value
                )
            ),
            sources=tuple(sorted({bar.source for bar in bars_tuple})),
            timeframes=tuple(
                sorted(
                    {bar.timeframe for bar in bars_tuple}, key=lambda item: item.value
                )
            ),
            adjustments=tuple(
                sorted(
                    {bar.adjustment for bar in bars_tuple}, key=lambda item: item.value
                )
            ),
        )
        return _report(checked_at, provenance, tuple(issues))

    def assess_latest_prices(
        self,
        snapshot: LatestPriceSnapshot | None,
        *,
        symbols: tuple[str, ...] | list[str],
        generated_at: datetime | None = None,
    ) -> MarketDataQualityReport:
        checked_at = _aware_now(generated_at)
        normalized_symbols, symbol_issues = _normalize_symbols(symbols)
        issues = list(symbol_issues)
        if snapshot is None:
            issues.append(
                _issue(
                    DataQualityIssueCode.EMPTY_DATASET,
                    DataQualityStatus.FAILED,
                    "Latest-price snapshot is unavailable.",
                )
            )
            provenance = MarketDataProvenance(
                dataset_type="latest_prices",
                symbols=tuple(normalized_symbols),
                feeds=(),
                sources=(),
            )
            return _report(checked_at, provenance, tuple(issues))

        if snapshot.feed == DataFeed.IEX:
            issues.append(_iex_issue())

        for symbol in snapshot.missing_symbols:
            issues.append(
                _issue(
                    DataQualityIssueCode.MISSING_LATEST_PRICE,
                    DataQualityStatus.FAILED,
                    "Required latest price is missing.",
                    symbol=symbol,
                )
            )

        for record in snapshot.prices:
            if record.status == LatestPriceStatus.STALE:
                issues.append(
                    _issue(
                        DataQualityIssueCode.STALE_LATEST_PRICE,
                        DataQualityStatus.FAILED,
                        "Latest price is stale.",
                        symbol=record.symbol,
                        evidence=(f"observed_at={record.observed_at.isoformat()}",),
                    )
                )

        seen = {record.symbol for record in snapshot.prices}
        for symbol in normalized_symbols:
            if symbol not in seen and symbol not in snapshot.missing_symbols:
                issues.append(
                    _issue(
                        DataQualityIssueCode.MISSING_LATEST_PRICE,
                        DataQualityStatus.FAILED,
                        "Required latest price is absent from the snapshot.",
                        symbol=symbol,
                    )
                )

        provenance = MarketDataProvenance(
            dataset_type="latest_prices",
            symbols=tuple(
                sorted(
                    {
                        *normalized_symbols,
                        *(record.symbol for record in snapshot.prices),
                    }
                )
            ),
            feeds=(snapshot.feed,),
            sources=(snapshot.source,),
        )
        return _report(checked_at, provenance, tuple(issues))


def _daily_bar_structure_issues(
    bars: tuple[DailyBar, ...],
    expected_feed: DataFeed | None,
) -> tuple[DataQualityIssue, ...]:
    issues: list[DataQualityIssue] = []
    feeds = {bar.data_feed for bar in bars}
    timeframes = {bar.timeframe for bar in bars}
    adjustments = {bar.adjustment for bar in bars}
    if len(feeds) > 1:
        issues.append(
            _issue(
                DataQualityIssueCode.MIXED_FEEDS,
                DataQualityStatus.FAILED,
                "Daily bars contain multiple data feeds.",
                evidence=tuple(sorted(feed.value for feed in feeds)),
            )
        )
    if expected_feed is not None and feeds and feeds != {expected_feed}:
        issues.append(
            _issue(
                DataQualityIssueCode.UNEXPECTED_FEED,
                DataQualityStatus.FAILED,
                "Daily bars do not match the expected feed.",
                evidence=(expected_feed.value, *sorted(feed.value for feed in feeds)),
            )
        )
    if DataFeed.IEX in feeds:
        issues.append(_iex_issue())
    if len(timeframes) > 1:
        issues.append(
            _issue(
                DataQualityIssueCode.MIXED_TIMEFRAMES,
                DataQualityStatus.FAILED,
                "Daily bars contain multiple timeframes.",
                evidence=tuple(sorted(timeframe.value for timeframe in timeframes)),
            )
        )
    if len(adjustments) > 1:
        issues.append(
            _issue(
                DataQualityIssueCode.MIXED_ADJUSTMENTS,
                DataQualityStatus.FAILED,
                "Daily bars contain multiple adjustment modes.",
                evidence=tuple(sorted(adjustment.value for adjustment in adjustments)),
            )
        )
    return tuple(issues)


def _normalize_symbols(
    symbols: tuple[str, ...] | list[str],
) -> tuple[tuple[str, ...], tuple[DataQualityIssue, ...]]:
    normalized: list[str] = []
    issues: list[DataQualityIssue] = []
    for symbol in symbols:
        try:
            normalized.append(validate_symbol(symbol))
        except ValueError as error:
            issues.append(
                _issue(
                    DataQualityIssueCode.INVALID_SYMBOL,
                    DataQualityStatus.FAILED,
                    "Symbol is outside the supported U.S. stock/ETF format.",
                    evidence=(str(symbol), str(error)),
                )
            )
    return tuple(sorted(set(normalized))), tuple(issues)


def _duplicate_bars(bars: tuple[DailyBar, ...]) -> tuple[tuple[str, date], ...]:
    seen: set[tuple[str, date]] = set()
    duplicates: set[tuple[str, date]] = set()
    for bar in bars:
        key = (bar.symbol, bar.trading_date)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return tuple(sorted(duplicates, key=lambda item: (item[1], item[0])))


def _report(
    generated_at: datetime,
    provenance: MarketDataProvenance,
    issues: tuple[DataQualityIssue, ...],
) -> MarketDataQualityReport:
    failures = sum(1 for issue in issues if issue.status == DataQualityStatus.FAILED)
    warnings = sum(1 for issue in issues if issue.status == DataQualityStatus.WARNING)
    status = (
        DataQualityStatus.FAILED
        if failures
        else DataQualityStatus.WARNING
        if warnings
        else DataQualityStatus.PASSED
    )
    return MarketDataQualityReport(
        generated_at=generated_at,
        status=status,
        can_use_for_research=failures == 0,
        can_use_for_trading=failures == 0 and warnings == 0,
        provenance=provenance,
        issues=issues,
        warnings=warnings,
        failures=failures,
        summary=_summary(status, failures, warnings),
    )


def _issue(
    code: DataQualityIssueCode,
    status: DataQualityStatus,
    message: str,
    *,
    symbol: str | None = None,
    trading_date: date | None = None,
    evidence: tuple[str, ...] = (),
) -> DataQualityIssue:
    return DataQualityIssue(
        code=code,
        status=status,
        message=message,
        symbol=symbol,
        trading_date=trading_date,
        evidence=tuple(str(item) for item in evidence),
    )


def _iex_issue() -> DataQualityIssue:
    return _issue(
        DataQualityIssueCode.IEX_DEVELOPMENT_GRADE,
        DataQualityStatus.WARNING,
        (
            "IEX/free data is development-grade and should not drive final "
            "funding decisions."
        ),
    )


def _summary(status: DataQualityStatus, failures: int, warnings: int) -> str:
    if status == DataQualityStatus.PASSED:
        return "Market data quality checks passed."
    if status == DataQualityStatus.WARNING:
        return f"Market data quality checks passed with {warnings} warning(s)."
    return (
        f"Market data quality checks failed with {failures} failure(s) "
        f"and {warnings} warning(s)."
    )


def _business_days(start: date, end: date) -> tuple[date, ...]:
    current = start
    days: list[date] = []
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _aware_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value
