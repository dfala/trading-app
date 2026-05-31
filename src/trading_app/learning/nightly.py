"""Nightly feature updates, candidate evaluation, and promotion recommendations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from statistics import mean

from trading_app.backtest.runner import BacktestConfig, BacktestResult, BacktestRunner
from trading_app.learning.models import (
    CandidateEvaluation,
    CandidateSpec,
    CandidateTrainingRecord,
    ChampionChallengerComparison,
    FeatureObservation,
    FeatureUpdateRecord,
    ModelRegistryState,
    ModelVersionRecord,
    NightlyLearningConfig,
    NightlyLearningRun,
    PromotionAction,
    PromotionRecommendation,
    WalkForwardFold,
    WalkForwardFoldResult,
    WalkForwardMetrics,
)
from trading_app.learning.registry import ModelRegistry, ModelRegistryError
from trading_app.schemas import DailyBar, DataFeed

StrategyFactory = Callable[[dict], object]


class FeatureUpdater:
    """Create a deterministic feature-update summary from daily bars."""

    def update(
        self, bars: list[DailyBar] | tuple[DailyBar, ...], *, as_of: datetime
    ) -> FeatureUpdateRecord:
        if not bars:
            raise ValueError("bars cannot be empty")
        sorted_bars = sorted(bars, key=lambda bar: (bar.trading_date, bar.symbol))
        symbols = tuple(sorted({bar.symbol for bar in sorted_bars}))
        latest_observations = tuple(
            _feature_observation(symbol=symbol, bars=sorted_bars) for symbol in symbols
        )
        return FeatureUpdateRecord(
            id=f"features-{as_of.date().isoformat()}",
            as_of=as_of,
            started_on=sorted_bars[0].trading_date,
            ended_on=sorted_bars[-1].trading_date,
            symbols=symbols,
            feature_names=("close_price", "daily_return", "rolling_momentum"),
            observation_count=len(sorted_bars),
            latest_observations=latest_observations,
            metadata={"source_count": len({bar.source for bar in sorted_bars})},
        )


class CandidateModelTrainer:
    """Version candidate configurations without touching active strategy code."""

    def train(
        self,
        specs: tuple[CandidateSpec, ...],
        *,
        feature_update: FeatureUpdateRecord,
        trained_at: datetime,
    ) -> tuple[CandidateTrainingRecord, ...]:
        return tuple(
            CandidateTrainingRecord(
                candidate=ModelVersionRecord(
                    strategy_id=spec.strategy_id,
                    version=spec.version,
                    state=ModelRegistryState.BACKTEST,
                    parameters=spec.parameters,
                    hypothesis=spec.hypothesis,
                    parent_version=spec.parent_version,
                    created_at=trained_at,
                    metadata=spec.metadata,
                ),
                trained_at=trained_at,
                feature_update_id=feature_update.id,
                training_notes=(
                    "Candidate configuration was generated from the nightly "
                    "feature update and queued for walk-forward validation."
                ),
            )
            for spec in specs
        )


class WalkForwardEvaluator:
    """Evaluate a model version over deterministic walk-forward folds."""

    def evaluate(
        self,
        *,
        model: ModelVersionRecord,
        strategy,
        bars: tuple[DailyBar, ...],
        benchmark_bars: tuple[DailyBar, ...],
        config: NightlyLearningConfig,
    ) -> CandidateEvaluation:
        folds = build_walk_forward_folds(
            tuple(sorted({bar.trading_date for bar in bars})),
            train_window_days=config.train_window_days,
            test_window_days=config.test_window_days,
            max_folds=config.max_folds,
        )
        if not folds:
            raise ValueError("not enough trading dates for walk-forward evaluation")

        fold_results = tuple(
            _evaluate_fold(
                fold=fold,
                strategy=strategy,
                bars=bars,
                benchmark_bars=benchmark_bars,
                config=config,
            )
            for fold in folds
        )
        scores = [result.metrics.score for result in fold_results]
        excess_returns = [result.metrics.excess_return for result in fold_results]
        max_drawdown = min(result.metrics.max_drawdown for result in fold_results)
        aggregate_score = mean(scores)
        aggregate_excess_return = mean(excess_returns)
        passed = (
            aggregate_excess_return >= config.min_average_excess_return
            and max_drawdown >= config.max_drawdown_floor
        )
        return CandidateEvaluation(
            model=model,
            fold_results=fold_results,
            aggregate_score=aggregate_score,
            aggregate_excess_return=aggregate_excess_return,
            aggregate_max_drawdown=max_drawdown,
            passed=passed,
        )


class NightlyLearningLoop:
    """Run the safe nightly learning workflow without mutating active models."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        feature_updater: FeatureUpdater | None = None,
        trainer: CandidateModelTrainer | None = None,
        evaluator: WalkForwardEvaluator | None = None,
    ) -> None:
        self.registry = registry
        self.feature_updater = feature_updater or FeatureUpdater()
        self.trainer = trainer or CandidateModelTrainer()
        self.evaluator = evaluator or WalkForwardEvaluator()

    def run(
        self,
        *,
        as_of: datetime,
        champion: ModelVersionRecord,
        candidate_specs: tuple[CandidateSpec, ...],
        strategy_factory: StrategyFactory,
        bars: tuple[DailyBar, ...],
        benchmark_bars: tuple[DailyBar, ...],
        config: NightlyLearningConfig | None = None,
    ) -> NightlyLearningRun:
        resolved_config = config or NightlyLearningConfig()
        registry_before = self.registry.snapshot(as_of)
        active_before = registry_before.active_keys
        feature_update = self.feature_updater.update(bars, as_of=as_of)
        trained_candidates = self.trainer.train(
            candidate_specs,
            feature_update=feature_update,
            trained_at=as_of,
        )

        for training_record in trained_candidates:
            candidate = training_record.candidate
            if not _registry_contains(self.registry, candidate):
                self.registry.register(candidate)

        champion_evaluation = self.evaluator.evaluate(
            model=champion,
            strategy=strategy_factory(champion.parameters),
            bars=bars,
            benchmark_bars=benchmark_bars,
            config=resolved_config,
        )
        candidate_evaluations = tuple(
            self.evaluator.evaluate(
                model=training_record.candidate,
                strategy=strategy_factory(training_record.candidate.parameters),
                bars=bars,
                benchmark_bars=benchmark_bars,
                config=resolved_config,
            )
            for training_record in trained_candidates
        )
        comparisons = tuple(
            _compare(
                champion=champion_evaluation,
                challenger=evaluation,
                config=resolved_config,
            )
            for evaluation in candidate_evaluations
        )
        data_caveats = _data_caveats(bars, benchmark_bars)
        recommendations = tuple(
            _recommend(
                comparison,
                evaluation=evaluation,
                config=resolved_config,
                data_caveats=data_caveats,
            )
            for comparison, evaluation in zip(
                comparisons, candidate_evaluations, strict=True
            )
        )
        if resolved_config.auto_shadow_approved_candidates:
            for recommendation in recommendations:
                if recommendation.action == PromotionAction.PROMOTE_TO_SHADOW:
                    self.registry.transition_state(
                        strategy_id=recommendation.model.strategy_id,
                        version=recommendation.model.version,
                        state=ModelRegistryState.SHADOW,
                    )

        registry_after = self.registry.snapshot(as_of)
        active_model_unchanged = active_before == registry_after.active_keys
        return NightlyLearningRun(
            id=f"nightly-{as_of.date().isoformat()}",
            as_of=as_of,
            feature_update=feature_update,
            trained_candidates=trained_candidates,
            champion_evaluation=champion_evaluation,
            candidate_evaluations=candidate_evaluations,
            comparisons=comparisons,
            recommendations=recommendations,
            registry_before=registry_before,
            registry_after=registry_after,
            active_model_unchanged=active_model_unchanged,
            research_memo=_research_memo(
                comparisons=comparisons,
                active_model_unchanged=active_model_unchanged,
            ),
        )


def build_walk_forward_folds(
    trading_dates: tuple,
    *,
    train_window_days: int,
    test_window_days: int,
    max_folds: int,
) -> tuple[WalkForwardFold, ...]:
    folds: list[WalkForwardFold] = []
    start = 0
    while len(
        folds
    ) < max_folds and start + train_window_days + test_window_days <= len(
        trading_dates
    ):
        train_dates = trading_dates[start : start + train_window_days]
        test_dates = trading_dates[
            start + train_window_days : start + train_window_days + test_window_days
        ]
        folds.append(
            WalkForwardFold(
                index=len(folds),
                train_start=train_dates[0],
                train_end=train_dates[-1],
                test_start=test_dates[0],
                test_end=test_dates[-1],
            )
        )
        start += test_window_days
    return tuple(folds)


def _feature_observation(*, symbol: str, bars: list[DailyBar]) -> FeatureObservation:
    symbol_bars = [bar for bar in bars if bar.symbol == symbol]
    first = symbol_bars[0]
    latest = symbol_bars[-1]
    previous = symbol_bars[-2] if len(symbol_bars) > 1 else latest
    daily_return = latest.close_price / previous.close_price - Decimal("1")
    rolling_momentum = latest.close_price / first.close_price - Decimal("1")
    return FeatureObservation(
        symbol=symbol,
        observed_on=latest.trading_date,
        values={
            "close_price": latest.close_price,
            "daily_return": daily_return,
            "rolling_momentum": rolling_momentum,
        },
    )


def _evaluate_fold(
    *,
    fold: WalkForwardFold,
    strategy,
    bars: tuple[DailyBar, ...],
    benchmark_bars: tuple[DailyBar, ...],
    config: NightlyLearningConfig,
) -> WalkForwardFoldResult:
    fold_input_bars = tuple(
        bar for bar in bars if fold.train_start <= bar.trading_date <= fold.test_end
    )
    fold_input_benchmark = tuple(
        bar
        for bar in benchmark_bars
        if fold.train_start <= bar.trading_date <= fold.test_end
    )
    result = BacktestRunner().run(
        strategy=strategy,
        bars=fold_input_bars,
        benchmark_bars=fold_input_benchmark,
        config=BacktestConfig(
            starting_cash=config.starting_cash,
            slippage_bps=config.slippage_bps,
        ),
        trading_start=fold.test_start,
    )
    return WalkForwardFoldResult(
        fold=fold,
        metrics=_metrics_from_backtest(result),
    )


def _metrics_from_backtest(result: BacktestResult) -> WalkForwardMetrics:
    excess_return = result.net_total_return - result.benchmark_total_return
    score = (
        excess_return
        + result.net_total_return
        - abs(result.max_drawdown) * 0.5
        - result.annualized_volatility * 0.1
        - result.turnover * 0.01
    )
    return WalkForwardMetrics(
        net_total_return=result.net_total_return,
        benchmark_total_return=result.benchmark_total_return,
        excess_return=excess_return,
        annualized_volatility=result.annualized_volatility,
        max_drawdown=result.max_drawdown,
        trade_count=result.trade_count,
        turnover=result.turnover,
        score=score,
    )


def _compare(
    *,
    champion: CandidateEvaluation,
    challenger: CandidateEvaluation,
    config: NightlyLearningConfig,
) -> ChampionChallengerComparison:
    delta = challenger.aggregate_score - champion.aggregate_score
    should_shadow = (
        challenger.passed
        and delta >= config.min_score_delta_for_shadow
        and challenger.aggregate_excess_return >= config.min_average_excess_return
    )
    recommendation = (
        PromotionAction.PROMOTE_TO_SHADOW if should_shadow else PromotionAction.WATCH
    )
    rationale = (
        "Challenger passed walk-forward thresholds and can enter shadow mode "
        "for live observation without changing the active champion."
        if should_shadow
        else "Challenger did not clear the shadow-mode threshold; keep watching."
    )
    return ChampionChallengerComparison(
        champion=champion.model,
        challenger=challenger.model,
        champion_score=champion.aggregate_score,
        challenger_score=challenger.aggregate_score,
        score_delta=delta,
        recommendation=recommendation,
        rationale=rationale,
    )


def _recommend(
    comparison: ChampionChallengerComparison,
    *,
    evaluation: CandidateEvaluation,
    config: NightlyLearningConfig,
    data_caveats: tuple[str, ...],
) -> PromotionRecommendation:
    target_state = (
        ModelRegistryState.SHADOW
        if comparison.recommendation == PromotionAction.PROMOTE_TO_SHADOW
        else None
    )
    average_turnover = _average_turnover(evaluation)
    return PromotionRecommendation(
        action=comparison.recommendation,
        model=comparison.challenger,
        target_state=target_state,
        manual_review_required=True,
        confidence=_recommendation_confidence(comparison, evaluation),
        rationale=comparison.rationale,
        evidence=(
            f"champion:{comparison.champion.key}",
            f"challenger:{comparison.challenger.key}",
            f"score_delta:{comparison.score_delta:.6f}",
            f"aggregate_excess_return:{evaluation.aggregate_excess_return:.6f}",
            f"aggregate_max_drawdown:{evaluation.aggregate_max_drawdown:.6f}",
            f"average_turnover:{average_turnover:.6f}",
            f"fold_count:{len(evaluation.fold_results)}",
            f"slippage_bps:{config.slippage_bps}",
            *data_caveats,
        ),
    )


def _research_memo(
    *,
    comparisons: tuple[ChampionChallengerComparison, ...],
    active_model_unchanged: bool,
) -> str:
    shadow_count = sum(
        1
        for comparison in comparisons
        if comparison.recommendation == PromotionAction.PROMOTE_TO_SHADOW
    )
    return (
        f"Nightly learning compared {len(comparisons)} challenger model(s). "
        f"{shadow_count} candidate(s) were recommended for shadow mode. "
        f"Active model unchanged: {active_model_unchanged}."
    )


def render_learning_markdown_report(run: NightlyLearningRun) -> str:
    """Render a reviewable nightly learning recommendation memo."""

    lines = [
        "# Nightly Learning Recommendation Memo",
        "",
        "> AI-assisted research is advisory only. It cannot trade, promote, or "
        "change the active paper model without explicit approval.",
        "",
        "## Summary",
        "",
        f"- Run id: `{run.id}`",
        f"- As of: `{run.as_of.isoformat()}`",
        f"- Active model unchanged: `{_yes_no(run.active_model_unchanged)}`",
        f"- Candidate count: `{len(run.candidate_evaluations)}`",
        f"- Recommendation count: `{len(run.recommendations)}`",
        "",
        run.research_memo,
        "",
        "## Evidence",
        "",
        f"- Feature update: `{run.feature_update.id}`",
        f"- Observation count: `{run.feature_update.observation_count}`",
        f"- Symbols: `{', '.join(run.feature_update.symbols)}`",
        f"- Champion: `{run.champion_evaluation.model.key}`",
        f"- Champion aggregate score: `{run.champion_evaluation.aggregate_score:.6f}`",
        "",
        "| Candidate | Folds | Excess Return | Max Drawdown | Score | Passed |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for evaluation in run.candidate_evaluations:
        lines.append(
            "| "
            f"{_table_text(evaluation.model.key)} | "
            f"{len(evaluation.fold_results)} | "
            f"{evaluation.aggregate_excess_return:.6f} | "
            f"{evaluation.aggregate_max_drawdown:.6f} | "
            f"{evaluation.aggregate_score:.6f} | "
            f"{_yes_no(evaluation.passed)} |"
        )

    lines.extend(["", "## Interpretation", ""])
    if run.comparisons:
        for comparison in run.comparisons:
            lines.append(
                "- "
                f"{comparison.challenger.key}: {comparison.rationale} "
                f"Score delta `{comparison.score_delta:.6f}`."
            )
    else:
        lines.append("No challenger comparisons were produced.")

    lines.extend(["", "## Proposed Action", ""])
    if run.recommendations:
        for recommendation in run.recommendations:
            target = (
                recommendation.target_state.value
                if recommendation.target_state is not None
                else "none"
            )
            lines.extend(
                [
                    f"### {recommendation.model.key}",
                    "",
                    f"- Action: `{recommendation.action.value}`",
                    f"- Target state: `{target}`",
                    f"- Confidence: `{recommendation.confidence:.2f}`",
                    "- Manual review required: "
                    f"`{_yes_no(recommendation.manual_review_required)}`",
                    f"- Rationale: {recommendation.rationale}",
                    "- Evidence:",
                    *[f"  - `{item}`" for item in recommendation.evidence],
                    "",
                ]
            )
    else:
        lines.append("No proposed model action.")

    lines.extend(
        [
            "## Governance Boundary",
            "",
            "- The active paper model remains locked unless explicitly approved.",
            "- Recommendation evidence must be reviewed before promotion.",
            "- Live-money trading remains disabled and out of scope.",
            "",
        ]
    )
    return "\n".join(lines)


def write_learning_markdown_report(
    run: NightlyLearningRun,
    output_dir: Path | str,
) -> Path:
    """Write a nightly learning recommendation memo and return its path."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run.id}.md"
    path.write_text(render_learning_markdown_report(run), encoding="utf-8")
    return path


def _registry_contains(registry: ModelRegistry, candidate: ModelVersionRecord) -> bool:
    try:
        registry.get(candidate.strategy_id, candidate.version)
    except ModelRegistryError:
        return False
    return True


def _recommendation_confidence(
    comparison: ChampionChallengerComparison,
    evaluation: CandidateEvaluation,
) -> float:
    fold_factor = min(1.0, len(evaluation.fold_results) / 3)
    score_factor = min(1.0, max(0.0, abs(comparison.score_delta)))
    pass_factor = 0.25 if evaluation.passed else 0.0
    return min(1.0, 0.25 + fold_factor * 0.35 + score_factor * 0.15 + pass_factor)


def _average_turnover(evaluation: CandidateEvaluation) -> float:
    if not evaluation.fold_results:
        return 0.0
    return mean(result.metrics.turnover for result in evaluation.fold_results)


def _data_caveats(
    bars: tuple[DailyBar, ...],
    benchmark_bars: tuple[DailyBar, ...],
) -> tuple[str, ...]:
    all_bars = tuple(bars) + tuple(benchmark_bars)
    feeds = tuple(
        sorted({bar.data_feed for bar in all_bars}, key=lambda feed: feed.value)
    )
    caveats = [f"data_feeds:{','.join(feed.value for feed in feeds) or 'none'}"]
    sources = tuple(sorted({bar.source for bar in all_bars}))
    caveats.append(f"data_sources:{','.join(sources) or 'none'}")
    if DataFeed.IEX in feeds:
        caveats.append("data_caveat:IEX development-grade data")
    if not all_bars:
        caveats.append("data_caveat:no bars supplied")
    return tuple(caveats)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _table_text(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
