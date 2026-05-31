"""Deterministic nightly learning loop demo."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_app.learning import (
    CandidateSpec,
    ModelRegistry,
    ModelRegistryState,
    ModelVersionRecord,
    NightlyLearningConfig,
    NightlyLearningLoop,
)
from trading_app.schemas import DailyBar, DataFeed
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy


def main() -> None:
    as_of = datetime(2026, 5, 29, 23, tzinfo=UTC)
    bars, benchmark_bars = _demo_bars()
    registry = ModelRegistry()
    champion = ModelVersionRecord(
        strategy_id="monthly_sector_momentum",
        version="1.0.0",
        state=ModelRegistryState.PAPER,
        parameters={
            "universe": ("AAA", "BBB"),
            "lookback_days": 5,
            "top_n": 1,
        },
        hypothesis="Baseline sector momentum champion.",
        created_at=as_of,
        is_active=True,
    )
    registry.register(champion)
    result = NightlyLearningLoop(registry=registry).run(
        as_of=as_of,
        champion=champion,
        candidate_specs=(
            CandidateSpec(
                strategy_id="monthly_sector_momentum",
                version="1.1.0-shadow-candidate",
                parameters={
                    "universe": ("AAA", "BBB"),
                    "lookback_days": 3,
                    "top_n": 1,
                },
                hypothesis="Shorter momentum lookback may react faster.",
                parent_version="1.0.0",
            ),
        ),
        strategy_factory=lambda params: MonthlySectorMomentumStrategy(**params),
        bars=bars,
        benchmark_bars=benchmark_bars,
        config=NightlyLearningConfig(
            train_window_days=20,
            test_window_days=15,
            max_folds=2,
            min_score_delta_for_shadow=-1.0,
            min_average_excess_return=-1.0,
        ),
    )

    print("Nightly Learning Demo")
    print(f"feature_update={result.feature_update.id}")
    print(f"trained_candidates={len(result.trained_candidates)}")
    print(f"comparisons={len(result.comparisons)}")
    for recommendation in result.recommendations:
        print(
            "recommendation="
            f"{recommendation.model.version}:{recommendation.action.value}"
            f":target={recommendation.target_state}"
        )
    print(f"active_model_unchanged={result.active_model_unchanged}")
    print(f"registry_active={','.join(result.registry_after.active_keys)}")
    print(f"memo={result.research_memo}")


def _demo_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(_business_days(date(2025, 1, 1), 90)):
        aaa_close = Decimal("100") + Decimal(index) * Decimal("0.30")
        bbb_close = Decimal("100") + Decimal(index) * Decimal("0.08")
        if index >= 45:
            bbb_close += Decimal(index - 44) * Decimal("0.80")
        spy_close = Decimal("100") + Decimal(index) * Decimal("0.12")
        bars.append(_bar("AAA", trading_day, aaa_close))
        bars.append(_bar("BBB", trading_day, bbb_close))
        benchmark.append(_bar("SPY", trading_day, spy_close))
    return tuple(bars), tuple(benchmark)


def _business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _bar(symbol: str, trading_date: date, close: Decimal) -> DailyBar:
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
        source="learning-demo",
        data_feed=DataFeed.IEX,
    )


if __name__ == "__main__":
    main()
