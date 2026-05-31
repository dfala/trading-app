from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_app.backtest import BacktestConfig
from trading_app.learning import ModelEvidenceType, PromotionAction
from trading_app.research import StrategyResearchEvaluationRunner
from trading_app.research.evaluation import default_strategy_factories
from trading_app.schemas import DailyBar, DataFeed
from trading_app.strategies import (
    StrategyAuthority,
    StrategyCadence,
    StrategyCatalog,
    StrategyDefinition,
    StrategyFamily,
    StrategyImplementationStatus,
    build_default_strategy_catalog,
    monthly_sector_momentum_definition,
    trend_following_etf_definition,
)

NOW = datetime(2026, 5, 29, 23, tzinfo=UTC)


def make_bar(symbol: str, trading_date: date, close: Decimal) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year, trading_date.month, trading_date.day, 21, tzinfo=UTC
        ),
        ingested_at=datetime(2026, 5, 29, 22, tzinfo=UTC),
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=Decimal("1000000"),
        source="research-test",
        data_feed=DataFeed.IEX,
    )


def business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def research_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(business_days(date(2025, 1, 1), 70)):
        aaa_close = Decimal("100") + Decimal(index) * Decimal("0.20")
        bbb_close = Decimal("100") + Decimal(index) * Decimal("0.05")
        if index >= 35:
            bbb_close += Decimal(index - 34) * Decimal("0.80")
        spy_close = Decimal("100") + Decimal(index) * Decimal("0.10")
        bars.append(make_bar("AAA", trading_day, aaa_close))
        bars.append(make_bar("BBB", trading_day, bbb_close))
        benchmark.append(make_bar("SPY", trading_day, spy_close))
    return tuple(bars), tuple(benchmark)


def research_catalog() -> StrategyCatalog:
    return StrategyCatalog(
        (
            monthly_sector_momentum_definition(
                universe=("AAA", "BBB"),
                lookback_days=5,
                top_n=1,
            ),
            trend_following_etf_definition(
                universe=("AAA", "BBB"),
                trend_window_days=5,
                top_n=1,
            ),
            StrategyDefinition(
                strategy_id="cash_rotation_model",
                version="0.1.0",
                name="Cash Rotation Model",
                family=StrategyFamily.CASH_ROTATION,
                implementation_status=StrategyImplementationStatus.RESEARCH_IDEA,
                authority=StrategyAuthority.RESEARCH_ONLY,
                hypothesis="Cash can be useful when opportunity sets are weak.",
                universe=("AAA", "BBB"),
                benchmark="SPY",
                data_requirements=("Adjusted daily bars.",),
                feature_names=("opportunity_score",),
                trading_cadence=StrategyCadence.MONTHLY,
                holding_period="Research-defined.",
                signal_logic="Research idea only.",
                sizing_logic="Research idea only.",
                exit_logic="Research idea only.",
                risk_assumptions=("Long-only if implemented.",),
                failure_modes=("Cash drag in bull markets.",),
                constraints=("No trading authority.",),
                ai_role=("Draft hypothesis reviews.",),
            ),
        )
    )


def test_research_runner_creates_evidence_and_comparisons() -> None:
    bars, benchmark = research_bars()

    report = StrategyResearchEvaluationRunner().run(
        catalog=research_catalog(),
        champion_strategy_id="monthly_sector_momentum",
        champion_version="1.0.0",
        bars=bars,
        benchmark_bars=benchmark,
        as_of=NOW,
        config=BacktestConfig(
            commission_per_trade=Decimal("1"),
            slippage_bps=Decimal("5"),
            short_term_tax_rate=Decimal("0.30"),
            long_term_tax_rate=Decimal("0.15"),
        ),
    )

    assert report.champion_key == "monthly_sector_momentum:1.0.0"
    assert report.evaluated_model_keys == (
        "monthly_sector_momentum:1.0.0",
        "trend_following_etf:0.1.0",
    )
    assert len(report.evidence) == 2
    assert all(
        item.evidence_type == ModelEvidenceType.BACKTEST for item in report.evidence
    )
    assert len(report.comparisons) == 1
    assert report.comparisons[0].challenger.strategy_id == "trend_following_etf"
    assert report.comparisons[0].recommendation == PromotionAction.WATCH
    assert report.active_model_unchanged
    assert "Active model unchanged" in report.summary


def test_research_runner_skips_unimplemented_strategy_cards() -> None:
    bars, benchmark = research_bars()

    report = StrategyResearchEvaluationRunner().run(
        catalog=research_catalog(),
        champion_strategy_id="monthly_sector_momentum",
        champion_version="1.0.0",
        bars=bars,
        benchmark_bars=benchmark,
        as_of=NOW,
    )

    assert len(report.skipped_definitions) == 1
    assert report.skipped_definitions[0].strategy_id == "cash_rotation_model"
    assert "not implemented" in report.skipped_definitions[0].reason


def test_research_report_is_json_serializable_and_contains_strategy_metadata() -> None:
    bars, benchmark = research_bars()

    report = StrategyResearchEvaluationRunner().run(
        catalog=research_catalog(),
        champion_strategy_id="monthly_sector_momentum",
        champion_version="1.0.0",
        bars=bars,
        benchmark_bars=benchmark,
        as_of=NOW,
    )
    payload = report.model_dump_json()

    assert "trend_following_etf" in payload
    assert report.evidence[0].metrics.trade_count >= 0
    assert report.evidence[0].cost_assumptions["starting_cash"] == "100000"
    assert (
        report.evidence[1].risk_settings["constraints"][0]
        == "Research-only by default."
    )
    assert (
        report.comparisons[0].challenger.metadata["strategy_definition"]["authority"]
        == "research_only"
    )


def test_default_research_factories_cover_implemented_default_catalog() -> None:
    implemented_strategy_ids = {
        definition.strategy_id
        for definition in build_default_strategy_catalog().implemented()
    }

    assert implemented_strategy_ids <= set(default_strategy_factories())
