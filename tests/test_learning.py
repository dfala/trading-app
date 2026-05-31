from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from trading_app.learning import (
    CandidateSpec,
    FeatureUpdater,
    ModelRegistry,
    ModelRegistryError,
    ModelRegistryState,
    ModelVersionRecord,
    NightlyLearningConfig,
    NightlyLearningLoop,
    PromotionAction,
    WalkForwardEvaluator,
    build_walk_forward_folds,
    render_learning_markdown_report,
)
from trading_app.schemas import DailyBar, DataFeed
from trading_app.strategies import StrategyAuthority, strategy_definition_metadata
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

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
        source="learning-test",
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


def learning_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(business_days(date(2025, 1, 1), 80)):
        aaa_close = Decimal("100") + Decimal(index) * Decimal("0.25")
        bbb_close = Decimal("100") + Decimal(index) * Decimal("0.05")
        if index >= 40:
            bbb_close += Decimal(index - 39) * Decimal("0.70")
        spy_close = Decimal("100") + Decimal(index) * Decimal("0.10")
        bars.append(make_bar("AAA", trading_day, aaa_close))
        bars.append(make_bar("BBB", trading_day, bbb_close))
        benchmark.append(make_bar("SPY", trading_day, spy_close))
    return tuple(bars), tuple(benchmark)


def champion_record() -> ModelVersionRecord:
    return ModelVersionRecord(
        strategy_id="monthly_sector_momentum",
        version="1.0.0",
        state=ModelRegistryState.PAPER,
        parameters={
            "universe": ("AAA", "BBB"),
            "lookback_days": 5,
            "top_n": 1,
        },
        hypothesis="Baseline monthly sector momentum champion.",
        created_at=NOW,
        is_active=True,
    )


def candidate_spec() -> CandidateSpec:
    candidate_strategy = MonthlySectorMomentumStrategy(
        universe=("AAA", "BBB"),
        lookback_days=3,
        top_n=1,
    )
    return CandidateSpec(
        strategy_id="monthly_sector_momentum",
        version="1.1.0",
        parameters={
            "universe": ("AAA", "BBB"),
            "lookback_days": 3,
            "top_n": 1,
        },
        hypothesis="Shorter lookback may adapt faster after regime changes.",
        parent_version="1.0.0",
        metadata=strategy_definition_metadata(
            candidate_strategy.definition(authority=StrategyAuthority.RESEARCH_ONLY)
        ),
    )


def strategy_factory(parameters: dict):
    return MonthlySectorMomentumStrategy(**parameters)


class WarmupRequiredStrategy:
    strategy_id = "warmup_required"

    def generate_targets(self, bars: tuple[DailyBar, ...], as_of: date):
        prior_bars = [
            bar for bar in bars if bar.symbol == "AAA" and bar.trading_date < as_of
        ]
        if len(prior_bars) < 5:
            return {}
        return {"AAA": Decimal("1")}


def test_feature_update_summarizes_nightly_dataset() -> None:
    bars, _ = learning_bars()

    feature_update = FeatureUpdater().update(bars, as_of=NOW)

    assert feature_update.id == "features-2026-05-29"
    assert feature_update.symbols == ("AAA", "BBB")
    assert feature_update.feature_names == (
        "close_price",
        "daily_return",
        "rolling_momentum",
    )
    assert feature_update.observation_count == len(bars)
    assert len(feature_update.latest_observations) == 2
    assert feature_update.latest_observations[0].symbol == "AAA"
    assert set(feature_update.latest_observations[0].values) == {
        "close_price",
        "daily_return",
        "rolling_momentum",
    }


def test_registry_tracks_states_and_requires_manual_active_changes() -> None:
    registry = ModelRegistry()
    champion = registry.register(champion_record())
    candidate = registry.register(
        ModelVersionRecord(
            strategy_id="monthly_sector_momentum",
            version="1.1.0",
            state=ModelRegistryState.BACKTEST,
            parameters=candidate_spec().parameters,
            hypothesis=candidate_spec().hypothesis,
            parent_version="1.0.0",
            created_at=NOW,
        )
    )

    shadow = registry.transition_state(
        strategy_id=candidate.strategy_id,
        version=candidate.version,
        state=ModelRegistryState.SHADOW,
    )

    assert registry.active_model("monthly_sector_momentum") == champion
    assert shadow.state == ModelRegistryState.SHADOW
    with pytest.raises(ModelRegistryError):
        registry.set_active(
            strategy_id=candidate.strategy_id,
            version=candidate.version,
            approved_by="",
        )


def test_build_walk_forward_folds_uses_train_then_test_windows() -> None:
    dates = tuple(business_days(date(2025, 1, 1), 12))

    folds = build_walk_forward_folds(
        dates,
        train_window_days=4,
        test_window_days=3,
        max_folds=2,
    )

    assert len(folds) == 2
    assert folds[0].train_start == dates[0]
    assert folds[0].train_end == dates[3]
    assert folds[0].test_start == dates[4]
    assert folds[0].test_end == dates[6]
    assert folds[1].train_start == dates[3]


def test_nightly_learning_recommends_shadow_without_changing_active_model() -> None:
    bars, benchmark = learning_bars()
    registry = ModelRegistry()
    champion = registry.register(champion_record())

    result = NightlyLearningLoop(registry=registry).run(
        as_of=NOW,
        champion=champion,
        candidate_specs=(candidate_spec(),),
        strategy_factory=strategy_factory,
        bars=bars,
        benchmark_bars=benchmark,
        config=NightlyLearningConfig(
            train_window_days=20,
            test_window_days=15,
            max_folds=2,
            min_score_delta_for_shadow=-1.0,
            min_average_excess_return=-1.0,
            max_drawdown_floor=-0.99,
        ),
    )

    shadow_candidate = registry.get("monthly_sector_momentum", "1.1.0")

    assert result.feature_update.observation_count == len(bars)
    assert len(result.trained_candidates) == 1
    assert len(result.candidate_evaluations[0].fold_results) == 2
    assert result.recommendations[0].action == PromotionAction.PROMOTE_TO_SHADOW
    assert result.recommendations[0].manual_review_required
    assert 0 < result.recommendations[0].confidence <= 1
    recommendation_evidence = result.recommendations[0].evidence
    assert any(
        item.startswith("aggregate_max_drawdown:") for item in recommendation_evidence
    )
    assert any(item.startswith("average_turnover:") for item in recommendation_evidence)
    assert "fold_count:2" in recommendation_evidence
    assert "slippage_bps:5" in recommendation_evidence
    assert "data_caveat:IEX development-grade data" in recommendation_evidence
    assert (
        result.trained_candidates[0].candidate.metadata["strategy_definition"][
            "authority"
        ]
        == "research_only"
    )
    assert shadow_candidate.state == ModelRegistryState.BACKTEST
    assert registry.active_model("monthly_sector_momentum").version == "1.0.0"
    assert result.registry_before.active_keys == result.registry_after.active_keys
    assert result.active_model_unchanged
    assert "Active model unchanged: True" in result.research_memo


def test_nightly_learning_can_only_auto_shadow_when_explicitly_enabled() -> None:
    bars, benchmark = learning_bars()
    registry = ModelRegistry()
    champion = registry.register(champion_record())

    result = NightlyLearningLoop(registry=registry).run(
        as_of=NOW,
        champion=champion,
        candidate_specs=(candidate_spec(),),
        strategy_factory=strategy_factory,
        bars=bars,
        benchmark_bars=benchmark,
        config=NightlyLearningConfig(
            train_window_days=20,
            test_window_days=15,
            max_folds=2,
            min_score_delta_for_shadow=-1.0,
            min_average_excess_return=-1.0,
            max_drawdown_floor=-0.99,
            auto_shadow_approved_candidates=True,
        ),
    )

    shadow_candidate = registry.get("monthly_sector_momentum", "1.1.0")

    assert result.recommendations[0].manual_review_required
    assert shadow_candidate.state == ModelRegistryState.SHADOW
    assert result.active_model_unchanged


def test_learning_markdown_memo_separates_evidence_interpretation_and_action() -> None:
    bars, benchmark = learning_bars()
    registry = ModelRegistry()
    champion = registry.register(champion_record())

    result = NightlyLearningLoop(registry=registry).run(
        as_of=NOW,
        champion=champion,
        candidate_specs=(candidate_spec(),),
        strategy_factory=strategy_factory,
        bars=bars,
        benchmark_bars=benchmark,
        config=NightlyLearningConfig(
            train_window_days=20,
            test_window_days=15,
            max_folds=2,
            min_score_delta_for_shadow=-1.0,
            min_average_excess_return=-1.0,
            max_drawdown_floor=-0.99,
        ),
    )

    markdown = render_learning_markdown_report(result)

    assert "# Nightly Learning Recommendation Memo" in markdown
    assert "AI-assisted research is advisory only" in markdown
    assert "## Evidence" in markdown
    assert "## Interpretation" in markdown
    assert "## Proposed Action" in markdown
    assert "Confidence:" in markdown
    assert "data_caveat:IEX development-grade data" in markdown
    assert "Live-money trading remains disabled" in markdown


def test_walk_forward_folds_use_training_history_as_warmup() -> None:
    trading_dates = business_days(date(2025, 1, 1), 8)
    bars = tuple(
        make_bar("AAA", trading_day, Decimal("100") + Decimal(index))
        for index, trading_day in enumerate(trading_dates)
    )
    benchmark = tuple(
        make_bar("SPY", trading_day, Decimal("100")) for trading_day in trading_dates
    )
    model = ModelVersionRecord(
        strategy_id="warmup_required",
        version="0.1.0",
        state=ModelRegistryState.BACKTEST,
        parameters={},
        hypothesis="Requires prior fold history before it can trade.",
        created_at=NOW,
    )

    evaluation = WalkForwardEvaluator().evaluate(
        model=model,
        strategy=WarmupRequiredStrategy(),
        bars=bars,
        benchmark_bars=benchmark,
        config=NightlyLearningConfig(
            train_window_days=5,
            test_window_days=3,
            max_folds=1,
            min_average_excess_return=-1.0,
        ),
    )

    assert evaluation.fold_results[0].fold.test_start == trading_dates[5]
    assert evaluation.fold_results[0].metrics.trade_count == 1
