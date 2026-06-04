"""Autonomous research-cycle orchestration for self-feeding learning."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, Field, field_validator

from trading_app.market_data.storage import DEFAULT_BAR_ROOT, DuckDBBarQuery
from trading_app.research.replay_suite import (
    ReplayStrategyComparisonRunner,
    build_etf_parameter_grid_replay_catalog,
    build_market_drawdown_circuit_breaker_replay_catalog,
)
from trading_app.research.run_replay_discovery import (
    DEFAULT_WARMUP_CALENDAR_DAYS,
    DEFAULT_WARMUP_TRADING_DAYS,
    DiscoveryRun,
    _config,
    _discovery_periods,
    _fetch_and_store,
    _fetch_missing_symbols,
    _limited_catalog,
    _missing_symbols,
    _required_symbols,
    _risk_managed_semiconductor_definitions,
    _run_catalog,
    _selected_universes,
    _with_extra_symbols,
    score_discovery_candidates,
)
from trading_app.schemas import DataFeed, TradingModel, validate_symbol
from trading_app.strategies import StrategyCatalog

DEFAULT_RESEARCH_OUTPUT_DIR = Path("data/research/replay")
DEFAULT_LEARNING_STATUS_DIR = Path("data/runtime/learning")
DEFAULT_CHAMPION_MODEL_KEY = (
    "market_drawdown_circuit_breaker:top-semi-l126-qqq-dd10-risk025-cash"
)
DEFAULT_AUTONOMOUS_STRATEGY_IDS = (
    "market_drawdown_circuit_breaker",
    "risk_managed_semiconductor",
)
DEFAULT_AUTONOMOUS_UNIVERSES = ("semiconductor-champions",)
DEFAULT_SHADOW_ARENA_SIZE = 12
DEFAULT_LEADERBOARD_SIZE = 100


class AutonomousLearningCycleMode(StrEnum):
    NIGHTLY = "nightly"
    WEEKLY = "weekly"
    SMOKE = "smoke"


class AutonomousLearningCycleStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class AutonomousLearningCandidate(TradingModel):
    rank: int = Field(ge=1)
    universe_id: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    full_delta: float
    stress_delta: float | None = None
    net_total_return: float | None = None
    benchmark_total_return: float | None = None
    annualized_return: float | None = None
    annualized_volatility: float | None = None
    turnover: float | None = None
    trade_count: int = Field(default=0, ge=0)
    decision_count: int = Field(default=0, ge=0)
    positive_folds: int = Field(ge=0)
    fold_count: int = Field(ge=0)
    min_fold_delta: float
    average_fold_delta: float
    worst_drawdown: float
    risk_adjusted_score: float
    gate_status: str = Field(min_length=1)
    status: str = Field(min_length=1)
    benchmark_ladder: dict[str, float] = Field(default_factory=dict)
    manual_approval_required: bool = True


class AutonomousResearchFingerprint(TradingModel):
    fingerprint: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    mode: AutonomousLearningCycleMode
    universe_ids: tuple[str, ...]
    strategy_ids: tuple[str, ...]
    start_date: date
    end_date: date
    benchmark: str = Field(min_length=1)
    feed: DataFeed
    max_strategies: int = Field(ge=0)
    tuning_mode: bool = False
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    run_count: int = Field(ge=1)
    run_ids: tuple[str, ...]


class AutonomousShadowArenaCandidate(TradingModel):
    rank: int = Field(ge=1)
    universe_id: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    authority: str = "shadow"
    broker_orders_submitted: bool = False
    virtual_starting_cash: Decimal
    historical_virtual_equity: Decimal | None = None
    historical_virtual_pnl: Decimal | None = None
    full_delta: float
    stress_delta: float | None = None
    min_fold_delta: float
    worst_drawdown: float
    risk_adjusted_score: float
    gate_status: str = Field(min_length=1)
    status: str = Field(min_length=1)
    next_review_action: str = Field(min_length=1)


class AutonomousShadowArenaReport(TradingModel):
    run_id: str = Field(min_length=1)
    generated_at: AwareDatetime
    arena_size: int = Field(ge=0)
    broker_orders_submitted: bool = False
    candidates: tuple[AutonomousShadowArenaCandidate, ...]
    summary: str = Field(min_length=1)


class AutonomousLearningLeaderboardEntry(TradingModel):
    rank: int = Field(ge=1)
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    seen_count: int = Field(ge=1)
    latest_run_id: str = Field(min_length=1)
    hypothesis_ids: tuple[str, ...]
    universe_id: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    full_delta: float
    net_total_return: float | None = None
    benchmark_total_return: float | None = None
    stress_delta: float | None = None
    min_fold_delta: float
    average_fold_delta: float
    worst_drawdown: float
    risk_adjusted_score: float
    positive_folds: int = Field(ge=0)
    fold_count: int = Field(ge=0)
    gate_status: str = Field(min_length=1)
    status: str = Field(min_length=1)
    benchmark_ladder: dict[str, float] = Field(default_factory=dict)
    manual_approval_required: bool = True


class AutonomousLearningLeaderboard(TradingModel):
    generated_at: AwareDatetime
    entry_count: int = Field(ge=0)
    entries: tuple[AutonomousLearningLeaderboardEntry, ...]
    summary: str = Field(min_length=1)


class AutonomousCandidateReadinessReport(TradingModel):
    run_id: str = Field(min_length=1)
    generated_at: AwareDatetime
    pilot_status: str = Field(min_length=1)
    pilot_candidate_model_key: str | None = None
    promotion_qualified: tuple[AutonomousLearningCandidate, ...] = ()
    raw_alpha_watchlist: tuple[AutonomousLearningCandidate, ...] = ()
    low_drawdown_watchlist: tuple[AutonomousLearningCandidate, ...] = ()
    fragile_watchlist: tuple[AutonomousLearningCandidate, ...] = ()
    gate_rules: tuple[str, ...] = ()
    summary: str = Field(min_length=1)


class AutonomousLearningCycleConfig(TradingModel):
    mode: AutonomousLearningCycleMode = AutonomousLearningCycleMode.NIGHTLY
    hypothesis_id: str = "default"
    run_id: str = ""
    start_date: date = date(2016, 1, 4)
    end_date: date | None = None
    benchmark: str = "SPY"
    universes: tuple[str, ...] = DEFAULT_AUTONOMOUS_UNIVERSES
    extra_symbols: tuple[str, ...] = ()
    strategy_ids: tuple[str, ...] = DEFAULT_AUTONOMOUS_STRATEGY_IDS
    feed: DataFeed = DataFeed.SIP
    root: Path = DEFAULT_BAR_ROOT
    output_dir: Path = DEFAULT_RESEARCH_OUTPUT_DIR
    status_dir: Path = DEFAULT_LEARNING_STATUS_DIR
    starting_cash: Decimal = Decimal("100000")
    slippage_bps: Decimal = Decimal("5")
    stress_slippage_bps: Decimal = Decimal("25")
    warmup_calendar_days: int = DEFAULT_WARMUP_CALENDAR_DAYS
    warmup_trading_days: int = DEFAULT_WARMUP_TRADING_DAYS
    max_strategies: int = Field(default=0, ge=0)
    shadow_arena_size: int = Field(default=DEFAULT_SHADOW_ARENA_SIZE, ge=0)
    leaderboard_size: int = Field(default=DEFAULT_LEADERBOARD_SIZE, ge=1)
    tuning_mode: bool = False
    fetch_missing: bool = False
    refresh_data: bool = False
    champion_model_key: str = DEFAULT_CHAMPION_MODEL_KEY

    @field_validator("hypothesis_id")
    @classmethod
    def _validate_hypothesis_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("hypothesis_id cannot be empty")
        return value

    @field_validator("benchmark")
    @classmethod
    def _validate_benchmark(cls, benchmark: str) -> str:
        return validate_symbol(benchmark)

    @field_validator("universes", "strategy_ids")
    @classmethod
    def _require_non_empty(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("value cannot be empty")
        if any(not value.strip() for value in values):
            raise ValueError("tuple values must be non-empty strings")
        return values

    @field_validator("extra_symbols")
    @classmethod
    def _validate_extra_symbols(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_symbol(symbol) for symbol in symbols)


class AutonomousLearningCycleRun(TradingModel):
    run_id: str = Field(min_length=1)
    generated_at: AwareDatetime
    mode: AutonomousLearningCycleMode
    hypothesis_id: str = "default"
    status: AutonomousLearningCycleStatus
    start_date: date
    end_date: date
    benchmark: str
    feed: DataFeed
    universe_ids: tuple[str, ...]
    strategy_ids: tuple[str, ...]
    candidate_count: int = Field(ge=0)
    completed_report_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    blocked_reasons: tuple[str, ...] = ()
    skipped_reasons: tuple[str, ...] = ()
    current_champion_model_key: str = Field(min_length=1)
    recommended_challenger_model_key: str | None = None
    top_candidates: tuple[AutonomousLearningCandidate, ...] = ()
    research_fingerprint: str | None = None
    tuning_mode: bool = False
    shadow_arena: AutonomousShadowArenaReport | None = None
    leaderboard: AutonomousLearningLeaderboard | None = None
    candidate_readiness: AutonomousCandidateReadinessReport | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    manual_approval_required: bool = True
    active_model_unchanged: bool = True
    summary: str = Field(min_length=1)
    next_actions: tuple[str, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AutonomousLearningCycleRunner:
    """Run bounded, reproducible champion/challenger research automatically."""

    def run(
        self,
        config: AutonomousLearningCycleConfig | None = None,
        *,
        generated_at: datetime | None = None,
    ) -> AutonomousLearningCycleRun:
        resolved = config or AutonomousLearningCycleConfig()
        generated = _aware_generated_at(generated_at)
        end_date = resolved.end_date or _default_end_date(generated.date())
        run_id = resolved.run_id or _run_id(resolved.mode, generated)
        fingerprint = research_experiment_fingerprint(resolved, end_date=end_date)
        universes = _resolve_universes(resolved)
        periods = _discovery_periods(resolved.start_date, end_date)
        required_symbols = _required_symbols(universes, resolved.benchmark)
        data_start = resolved.start_date - timedelta(days=resolved.warmup_calendar_days)

        if resolved.refresh_data:
            _fetch_and_store(
                root=resolved.root,
                symbols=required_symbols,
                start=data_start,
                end=end_date,
                feed=resolved.feed,
            )
        elif resolved.fetch_missing:
            _fetch_missing_symbols(
                root=resolved.root,
                symbols=required_symbols,
                start=data_start,
                end=end_date,
                feed=resolved.feed,
            )

        runs: list[DiscoveryRun] = []
        skipped: list[str] = []
        for universe_id, symbols in universes.items():
            universe_runs, universe_skipped = self._run_universe(
                config=resolved,
                universe_id=universe_id,
                symbols=symbols,
                periods=periods,
                run_id=run_id,
                generated_at=generated,
                end_date=end_date,
            )
            runs.extend(universe_runs)
            skipped.extend(universe_skipped)

        fold_ids = tuple(
            period.period_id for period in periods if period.period_id != "full"
        )
        scores = score_discovery_candidates(runs, fold_ids=fold_ids)
        top_candidates = tuple(
            _candidate_summary(rank, score)
            for rank, score in enumerate(scores[:25], start=1)
        )
        recommended_candidate = _recommended_candidate(top_candidates)
        shadow_arena = _shadow_arena_report(
            run_id=run_id,
            generated_at=generated,
            candidates=top_candidates,
            starting_cash=resolved.starting_cash,
            arena_size=resolved.shadow_arena_size,
        )
        status = (
            AutonomousLearningCycleStatus.COMPLETED
            if runs and scores
            else AutonomousLearningCycleStatus.BLOCKED
        )
        blocked_reasons = _blocked_reasons(
            status=status,
            skipped=tuple(skipped),
            runs=runs,
            scores=scores,
        )
        run = AutonomousLearningCycleRun(
            run_id=run_id,
            generated_at=generated,
            mode=resolved.mode,
            hypothesis_id=resolved.hypothesis_id,
            status=status,
            start_date=resolved.start_date,
            end_date=end_date,
            benchmark=resolved.benchmark,
            feed=resolved.feed,
            universe_ids=tuple(universes),
            strategy_ids=resolved.strategy_ids,
            candidate_count=len(scores),
            completed_report_count=len(runs),
            skipped_count=len(skipped),
            blocked_reasons=blocked_reasons,
            skipped_reasons=tuple(skipped),
            current_champion_model_key=resolved.champion_model_key,
            recommended_challenger_model_key=(
                recommended_candidate.model_key if recommended_candidate else None
            ),
            top_candidates=top_candidates,
            research_fingerprint=fingerprint,
            tuning_mode=resolved.tuning_mode,
            shadow_arena=shadow_arena,
            manual_approval_required=True,
            active_model_unchanged=True,
            summary=_summary(status=status, scores=top_candidates, skipped=skipped),
            next_actions=_next_actions(
                status=status,
                scores=top_candidates,
                recommended=recommended_candidate,
            ),
            metadata={
                "period_count": len(periods),
                "fold_ids": fold_ids,
                "required_symbols": required_symbols,
                "refresh_data": resolved.refresh_data,
                "fetch_missing": resolved.fetch_missing,
                "hypothesis_id": resolved.hypothesis_id,
                "max_strategies": resolved.max_strategies,
                "research_fingerprint": fingerprint,
                "tuning_mode": resolved.tuning_mode,
                "shadow_arena_size": resolved.shadow_arena_size,
                "leaderboard_size": resolved.leaderboard_size,
            },
        )
        readiness = _candidate_readiness_report(run)
        run = run.model_copy(update={"candidate_readiness": readiness})
        artifact_paths = write_autonomous_learning_cycle_artifacts(
            run,
            output_dir=resolved.output_dir,
            status_dir=resolved.status_dir,
        )
        leaderboard = _read_leaderboard(Path(artifact_paths["leaderboard_json"]))
        return run.model_copy(
            update={"artifact_paths": artifact_paths, "leaderboard": leaderboard}
        )

    def _run_universe(
        self,
        *,
        config: AutonomousLearningCycleConfig,
        universe_id: str,
        symbols: tuple[str, ...],
        periods,
        run_id: str,
        generated_at: datetime,
        end_date: date,
    ) -> tuple[list[DiscoveryRun], list[str]]:
        query = DuckDBBarQuery(config.root)
        runner = ReplayStrategyComparisonRunner()
        runs: list[DiscoveryRun] = []
        skipped: list[str] = []
        catalog = _limited_catalog(
            _filtered_catalog(
                _autonomous_catalog(
                    symbols=symbols,
                    benchmark=config.benchmark,
                    mode=config.mode,
                ),
                config.strategy_ids,
            ),
            config.max_strategies,
        )
        required_symbols = tuple(sorted(set(symbols) | {config.benchmark}))

        for period in periods:
            data_start = period.start - timedelta(days=config.warmup_calendar_days)
            bars = query.load_daily_bars(
                list(symbols),
                data_start,
                period.end,
                config.feed,
            )
            benchmark_bars = query.load_daily_bars(
                [config.benchmark],
                data_start,
                period.end,
                config.feed,
            )
            missing = _missing_symbols(required_symbols, (*bars, *benchmark_bars))
            if missing:
                skipped.append(
                    f"{universe_id}:{period.period_id} missing bars for "
                    f"{','.join(missing)}"
                )
                continue

            runs.append(
                _run_catalog(
                    runner=runner,
                    catalog=catalog,
                    universe_id=universe_id,
                    period_id=period.period_id,
                    cost_label="base",
                    bars=bars,
                    benchmark_bars=benchmark_bars,
                    config=_config(
                        run_id=f"{run_id}-{universe_id}-{period.period_id}-base",
                        start=period.start,
                        end=period.end,
                        symbols=symbols,
                        benchmark=config.benchmark,
                        feed=config.feed,
                        starting_cash=config.starting_cash,
                        slippage_bps=config.slippage_bps,
                        warmup_trading_days=config.warmup_trading_days,
                    ),
                    output_dir=config.output_dir,
                    generated_at=generated_at,
                    strategy_ids=(),
                )
            )
            if period.period_id == "full":
                runs.append(
                    _run_catalog(
                        runner=runner,
                        catalog=catalog,
                        universe_id=universe_id,
                        period_id=period.period_id,
                        cost_label="stress",
                        bars=bars,
                        benchmark_bars=benchmark_bars,
                        config=_config(
                            run_id=(
                                f"{run_id}-{universe_id}-{period.period_id}-stress-cost"
                            ),
                            start=period.start,
                            end=end_date,
                            symbols=symbols,
                            benchmark=config.benchmark,
                            feed=config.feed,
                            starting_cash=config.starting_cash,
                            slippage_bps=config.stress_slippage_bps,
                            warmup_trading_days=config.warmup_trading_days,
                        ),
                        output_dir=config.output_dir,
                        generated_at=generated_at,
                        strategy_ids=(),
                    )
                )
        return runs, skipped


def _filtered_catalog(
    catalog: StrategyCatalog,
    strategy_ids: tuple[str, ...],
) -> StrategyCatalog:
    if not strategy_ids:
        return catalog
    allowed = set(strategy_ids)
    return StrategyCatalog(
        tuple(
            definition
            for definition in catalog.all()
            if definition.strategy_id in allowed
        )
    )


def write_autonomous_learning_cycle_artifacts(
    run: AutonomousLearningCycleRun,
    *,
    output_dir: Path | str = DEFAULT_RESEARCH_OUTPUT_DIR,
    status_dir: Path | str = DEFAULT_LEARNING_STATUS_DIR,
) -> dict[str, str]:
    research_dir = Path(output_dir)
    state_dir = Path(status_dir)
    research_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = research_dir / f"{run.run_id}.md"
    json_path = research_dir / f"{run.run_id}.json"
    latest_json_path = state_dir / "latest-learning-cycle.json"
    latest_markdown_path = state_dir / "latest-learning-cycle.md"
    fingerprint_path = state_dir / "research-fingerprints.json"
    leaderboard_json_path = state_dir / "learning-leaderboard.json"
    leaderboard_markdown_path = state_dir / "learning-leaderboard.md"
    shadow_arena_json_path = state_dir / "shadow-arena.json"
    shadow_arena_markdown_path = state_dir / "shadow-arena.md"
    readiness_json_path = state_dir / "candidate-readiness.json"
    readiness_markdown_path = state_dir / "candidate-readiness.md"
    raw_alpha_json_path = state_dir / "raw-alpha-watchlist.json"
    raw_alpha_markdown_path = state_dir / "raw-alpha-watchlist.md"
    low_drawdown_json_path = state_dir / "low-drawdown-watchlist.json"
    low_drawdown_markdown_path = state_dir / "low-drawdown-watchlist.md"
    promotion_qualified_json_path = state_dir / "promotion-qualified.json"
    promotion_qualified_markdown_path = state_dir / "promotion-qualified.md"
    experiment_queue_markdown_path = state_dir / "experiment-queue.md"
    run_readiness_json_path = research_dir / f"{run.run_id}-candidate-readiness.json"
    run_readiness_markdown_path = research_dir / f"{run.run_id}-candidate-readiness.md"
    run_raw_alpha_markdown_path = research_dir / f"{run.run_id}-raw-alpha-watchlist.md"
    run_low_drawdown_markdown_path = (
        research_dir / f"{run.run_id}-low-drawdown-watchlist.md"
    )
    run_promotion_qualified_markdown_path = (
        research_dir / f"{run.run_id}-promotion-qualified.md"
    )
    run_experiment_queue_markdown_path = (
        research_dir / f"{run.run_id}-experiment-queue.md"
    )
    artifact_paths = {
        "markdown": str(markdown_path),
        "json": str(json_path),
        "latest_json": str(latest_json_path),
        "latest_markdown": str(latest_markdown_path),
        "fingerprints": str(fingerprint_path),
        "leaderboard_json": str(leaderboard_json_path),
        "leaderboard_markdown": str(leaderboard_markdown_path),
        "candidate_readiness_json": str(run_readiness_json_path),
        "candidate_readiness_markdown": str(run_readiness_markdown_path),
        "latest_candidate_readiness_json": str(readiness_json_path),
        "latest_candidate_readiness_markdown": str(readiness_markdown_path),
        "raw_alpha_watchlist_markdown": str(run_raw_alpha_markdown_path),
        "latest_raw_alpha_watchlist_markdown": str(raw_alpha_markdown_path),
        "low_drawdown_watchlist_markdown": str(run_low_drawdown_markdown_path),
        "latest_low_drawdown_watchlist_markdown": str(low_drawdown_markdown_path),
        "promotion_qualified_markdown": str(run_promotion_qualified_markdown_path),
        "latest_promotion_qualified_markdown": str(promotion_qualified_markdown_path),
        "experiment_queue_markdown": str(run_experiment_queue_markdown_path),
        "latest_experiment_queue_markdown": str(experiment_queue_markdown_path),
    }
    if run.shadow_arena is not None:
        artifact_paths.update(
            {
                "shadow_arena_json": str(shadow_arena_json_path),
                "shadow_arena_markdown": str(shadow_arena_markdown_path),
            }
        )
    run_with_artifacts = run.model_copy(update={"artifact_paths": artifact_paths})
    if run_with_artifacts.candidate_readiness is None:
        run_with_artifacts = run_with_artifacts.model_copy(
            update={
                "candidate_readiness": _candidate_readiness_report(run_with_artifacts)
            }
        )
    write_research_fingerprint_record(run_with_artifacts, path=fingerprint_path)
    leaderboard = update_autonomous_learning_leaderboard(
        run_with_artifacts,
        path=leaderboard_json_path,
        markdown_path=leaderboard_markdown_path,
    )
    run_with_artifacts = run_with_artifacts.model_copy(
        update={"leaderboard": leaderboard}
    )
    if run_with_artifacts.shadow_arena is not None:
        shadow_arena_json_path.write_text(
            run_with_artifacts.shadow_arena.model_dump_json(indent=2),
            encoding="utf-8",
        )
        shadow_arena_markdown_path.write_text(
            render_shadow_arena_markdown(run_with_artifacts.shadow_arena),
            encoding="utf-8",
        )

    if run_with_artifacts.candidate_readiness is not None:
        readiness = run_with_artifacts.candidate_readiness
        readiness_json = readiness.model_dump_json(indent=2)
        readiness_json_path.write_text(readiness_json, encoding="utf-8")
        run_readiness_json_path.write_text(readiness_json, encoding="utf-8")
        readiness_markdown = render_candidate_readiness_markdown(readiness)
        readiness_markdown_path.write_text(readiness_markdown, encoding="utf-8")
        run_readiness_markdown_path.write_text(readiness_markdown, encoding="utf-8")

        _write_candidate_group_artifacts(
            title="Promotion Qualified Candidates",
            run=run_with_artifacts,
            candidates=readiness.promotion_qualified,
            json_path=promotion_qualified_json_path,
            latest_markdown_path=promotion_qualified_markdown_path,
            run_markdown_path=run_promotion_qualified_markdown_path,
            empty_message=(
                "No candidate currently clears the strict promotion-quality thresholds."
            ),
        )
        _write_candidate_group_artifacts(
            title="Raw Alpha Watchlist",
            run=run_with_artifacts,
            candidates=readiness.raw_alpha_watchlist,
            json_path=raw_alpha_json_path,
            latest_markdown_path=raw_alpha_markdown_path,
            run_markdown_path=run_raw_alpha_markdown_path,
            empty_message="No high-return fragile candidate was found in this cycle.",
        )
        _write_candidate_group_artifacts(
            title="Low Drawdown Watchlist",
            run=run_with_artifacts,
            candidates=readiness.low_drawdown_watchlist,
            json_path=low_drawdown_json_path,
            latest_markdown_path=low_drawdown_markdown_path,
            run_markdown_path=run_low_drawdown_markdown_path,
            empty_message=(
                "No candidate currently clears the low-drawdown watchlist thresholds."
            ),
        )
        experiment_queue_markdown = render_experiment_queue_markdown(run_with_artifacts)
        experiment_queue_markdown_path.write_text(
            experiment_queue_markdown, encoding="utf-8"
        )
        run_experiment_queue_markdown_path.write_text(
            experiment_queue_markdown, encoding="utf-8"
        )

    markdown = render_autonomous_learning_cycle_markdown(run_with_artifacts)
    markdown_path.write_text(markdown, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    json_payload = run_with_artifacts.model_dump_json(indent=2)
    json_path.write_text(json_payload, encoding="utf-8")
    latest_json_path.write_text(json_payload, encoding="utf-8")

    return artifact_paths


def research_experiment_fingerprint(
    config: AutonomousLearningCycleConfig,
    *,
    end_date: date,
) -> str:
    payload = _research_fingerprint_payload(config, end_date=end_date)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()[:16]


def write_research_fingerprint_record(
    run: AutonomousLearningCycleRun,
    *,
    path: Path,
) -> AutonomousResearchFingerprint | None:
    if run.research_fingerprint is None:
        return None
    records = _read_fingerprint_records(path)
    existing = records.get(run.research_fingerprint)
    run_ids = tuple(existing.run_ids) if existing is not None else ()
    if run.run_id not in run_ids:
        run_ids = (*run_ids, run.run_id)
    record = AutonomousResearchFingerprint(
        fingerprint=run.research_fingerprint,
        hypothesis_id=run.hypothesis_id,
        mode=run.mode,
        universe_ids=run.universe_ids,
        strategy_ids=run.strategy_ids,
        start_date=run.start_date,
        end_date=run.end_date,
        benchmark=run.benchmark,
        feed=run.feed,
        max_strategies=int(run.metadata.get("max_strategies", 0)),
        tuning_mode=run.tuning_mode,
        first_seen_at=existing.first_seen_at if existing else run.generated_at,
        last_seen_at=run.generated_at,
        run_count=len(run_ids),
        run_ids=run_ids[-25:],
    )
    records[run.research_fingerprint] = record
    path.write_text(
        json.dumps(
            {
                key: value.model_dump(mode="json")
                for key, value in sorted(records.items())
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return record


def update_autonomous_learning_leaderboard(
    run: AutonomousLearningCycleRun,
    *,
    path: Path,
    markdown_path: Path,
) -> AutonomousLearningLeaderboard:
    existing = _read_leaderboard(path)
    entries_by_key = {
        (entry.universe_id, entry.model_key): entry
        for entry in (existing.entries if existing else ())
        if not _is_baseline_or_control_candidate(entry.model_key)
    }
    for candidate in run.top_candidates:
        if _is_baseline_or_control_candidate(candidate.model_key):
            continue
        key = (candidate.universe_id, candidate.model_key)
        previous = entries_by_key.get(key)
        hypotheses = tuple(
            sorted({*(previous.hypothesis_ids if previous else ()), run.hypothesis_id})
        )
        better_than_previous = previous is None or _candidate_sort_key(
            candidate
        ) > _leaderboard_entry_sort_key(previous)
        source = candidate if better_than_previous else previous
        entries_by_key[key] = AutonomousLearningLeaderboardEntry(
            rank=previous.rank if previous else 1,
            first_seen_at=previous.first_seen_at if previous else run.generated_at,
            last_seen_at=run.generated_at,
            seen_count=(previous.seen_count if previous else 0) + 1,
            latest_run_id=run.run_id,
            hypothesis_ids=hypotheses,
            universe_id=candidate.universe_id,
            model_key=candidate.model_key,
            strategy_name=source.strategy_name,
            full_delta=source.full_delta,
            net_total_return=source.net_total_return,
            benchmark_total_return=source.benchmark_total_return,
            stress_delta=source.stress_delta,
            min_fold_delta=source.min_fold_delta,
            average_fold_delta=source.average_fold_delta,
            worst_drawdown=source.worst_drawdown,
            risk_adjusted_score=source.risk_adjusted_score,
            positive_folds=source.positive_folds,
            fold_count=source.fold_count,
            gate_status=source.gate_status,
            status=source.status,
            benchmark_ladder=source.benchmark_ladder,
            manual_approval_required=True,
        )
    limit = int(run.metadata.get("leaderboard_size", DEFAULT_LEADERBOARD_SIZE))
    ranked = tuple(
        entry.model_copy(update={"rank": index})
        for index, entry in enumerate(
            sorted(
                entries_by_key.values(),
                key=_leaderboard_entry_sort_key,
                reverse=True,
            )[:limit],
            start=1,
        )
    )
    leaderboard = AutonomousLearningLeaderboard(
        generated_at=run.generated_at,
        entry_count=len(ranked),
        entries=ranked,
        summary=_leaderboard_summary(ranked),
    )
    path.write_text(leaderboard.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_autonomous_learning_leaderboard_markdown(leaderboard),
        encoding="utf-8",
    )
    return leaderboard


def render_autonomous_learning_leaderboard_markdown(
    leaderboard: AutonomousLearningLeaderboard,
) -> str:
    lines = [
        "# Autonomous Learning Leaderboard",
        "",
        "> Research and shadow evidence only. This leaderboard cannot promote "
        "paper or live trading authority.",
        "",
        "## Summary",
        "",
        f"- Generated at: `{leaderboard.generated_at.isoformat()}`",
        f"- Entries: `{leaderboard.entry_count}`",
        "",
        leaderboard.summary,
        "",
        "## Leaders",
        "",
        "| Rank | Candidate | Hypotheses | Seen | Net Return | Benchmark | "
        "Full Delta | Stress Delta | Positive Folds | Min Fold | Worst DD | "
        "Risk Score | Gate | Status |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | --- | --- |",
    ]
    for entry in leaderboard.entries[:50]:
        lines.append(
            f"| {entry.rank} | `{entry.universe_id}:{entry.model_key}` | "
            f"`{', '.join(entry.hypothesis_ids)}` | "
            f"{entry.seen_count} | "
            f"{_format_optional_pct(entry.net_total_return)} | "
            f"{_format_optional_pct(entry.benchmark_total_return)} | "
            f"{entry.full_delta:+.2%} | "
            f"{_format_optional_pct(entry.stress_delta)} | "
            f"{entry.positive_folds}/{entry.fold_count} | "
            f"{entry.min_fold_delta:+.2%} | "
            f"{entry.worst_drawdown:.2%} | "
            f"{entry.risk_adjusted_score:.2f} | "
            f"{_table_text(entry.gate_status)} | "
            f"{_table_text(entry.status)} |"
        )
    lines.extend(
        [
            "",
            "## Rules",
            "",
            "- Static buy-and-hold benchmarks are excluded from candidate rankings.",
            "- Repeated sightings count as evidence only when the underlying "
            "hypothesis fingerprint is distinct or tuning mode is explicit.",
            "- Very recent spikes do not make a winner promotion-ready. Champion "
            "reviews must check whether the last 21/63 trading days explain too "
            "much of the edge and must prefer 3/6/12-month consistency over "
            "late-window acceleration.",
            "- Manual approval is required before any paper or live authority changes.",
            "",
        ]
    )
    return "\n".join(lines)


def render_shadow_arena_markdown(report: AutonomousShadowArenaReport) -> str:
    lines = [
        "# Autonomous Shadow Arena",
        "",
        "> Virtual-only candidate tracking. No Alpaca broker orders are submitted "
        "by this arena.",
        "",
        "## Summary",
        "",
        f"- Run id: `{report.run_id}`",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Arena size: `{report.arena_size}`",
        f"- Broker orders submitted: `{_yes_no(report.broker_orders_submitted)}`",
        "",
        report.summary,
        "",
        "## Candidates",
        "",
        "| Rank | Candidate | Virtual Equity | Virtual PnL | Full Delta | "
        "Stress Delta | Min Fold | Worst DD | Risk Score | Gate | Action |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for candidate in report.candidates:
        lines.append(
            f"| {candidate.rank} | `{candidate.universe_id}:{candidate.model_key}` | "
            f"{_format_optional_money(candidate.historical_virtual_equity)} | "
            f"{_format_optional_money(candidate.historical_virtual_pnl)} | "
            f"{candidate.full_delta:+.2%} | "
            f"{_format_optional_pct(candidate.stress_delta)} | "
            f"{candidate.min_fold_delta:+.2%} | "
            f"{candidate.worst_drawdown:.2%} | "
            f"{candidate.risk_adjusted_score:.2f} | "
            f"{_table_text(candidate.gate_status)} | "
            f"{_table_text(candidate.next_review_action)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_candidate_readiness_markdown(
    report: AutonomousCandidateReadinessReport,
) -> str:
    lines = [
        "# Candidate Readiness Report",
        "",
        "> Research evidence only. This report decides whether candidates are "
        "ready for manual review, not whether they may trade live capital.",
        "",
        "## Summary",
        "",
        f"- Run id: `{report.run_id}`",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Pilot status: `{report.pilot_status}`",
        f"- Pilot candidate: `{report.pilot_candidate_model_key or 'none'}`",
        f"- Promotion-qualified candidates: `{len(report.promotion_qualified)}`",
        f"- Raw-alpha watchlist candidates: `{len(report.raw_alpha_watchlist)}`",
        f"- Low-drawdown watchlist candidates: `{len(report.low_drawdown_watchlist)}`",
        f"- Fragile watchlist candidates: `{len(report.fragile_watchlist)}`",
        "",
        report.summary,
        "",
        "## Gate Rules",
        "",
    ]
    lines.extend(f"- {rule}" for rule in report.gate_rules)
    lines.extend(["", "## Promotion Qualified", ""])
    lines.extend(
        _candidate_table(
            report.promotion_qualified,
            empty_message=(
                "No candidate clears the strict promotion-quality thresholds."
            ),
        )
    )
    lines.extend(["", "## Raw Alpha Watchlist", ""])
    lines.extend(
        _candidate_table(
            report.raw_alpha_watchlist,
            empty_message="No high-return fragile candidate was found.",
        )
    )
    lines.extend(["", "## Low Drawdown Watchlist", ""])
    lines.extend(
        _candidate_table(
            report.low_drawdown_watchlist,
            empty_message="No low-drawdown candidate was found.",
        )
    )
    lines.extend(["", "## Fragile But Interesting", ""])
    lines.extend(
        _candidate_table(
            report.fragile_watchlist,
            empty_message="No fragile positive-return candidate was found.",
        )
    )
    lines.extend(
        [
            "",
            "## Decision Boundary",
            "",
            "- A candidate can be interesting without being promotion-quality.",
            "- Small live-money pilots remain disabled until separate manual "
            "approval, clean paper evidence, and kill-switch gates pass.",
            "- Static buy-and-hold ETFs are benchmarks only, not candidate models.",
            "",
        ]
    )
    return "\n".join(lines)


def render_experiment_queue_markdown(run: AutonomousLearningCycleRun) -> str:
    readiness = run.candidate_readiness
    pilot_key = readiness.pilot_candidate_model_key if readiness else None
    leader_key = run.top_candidates[0].model_key if run.top_candidates else "none"
    lines = [
        "# Experiment Queue",
        "",
        "> This queue keeps the autonomous loop learning. Exact repeat runs are "
        "not useful unless they are explicit finalist retests or the data window "
        "has changed.",
        "",
        "## Summary",
        "",
        f"- Run id: `{run.run_id}`",
        f"- Generated at: `{run.generated_at.isoformat()}`",
        f"- Last hypothesis: `{run.hypothesis_id}`",
        f"- Research fingerprint: `{run.research_fingerprint or 'none'}`",
        f"- Current leader: `{leader_key}`",
        f"- Pilot candidate: `{pilot_key or 'none'}`",
        "",
        "The next cycles should keep four lanes active: new exploration, finalist "
        "tuning, regime/stress validation, and runtime health checks.",
        "",
        "## Lane Priorities",
        "",
        "| Lane | Target share | What to do next |",
        "| --- | ---: | --- |",
        "| New exploration | 50% | Test unseen fingerprints across universes, "
        "cohorts, depths, and bundles. |",
        "| Finalist tuning | 25% | Tune leaderboard leaders and adjacent "
        "semiconductor or cash-rotation parameters. |",
        "| Stress validation | 20% | Re-run finalists through crash, rate-reset, "
        "AI-boom, and stress-cost windows. |",
        "| Runtime health | 5% | Verify persistence, novelty, shadow evidence, "
        "and data-quality gates. |",
        "",
        "## Immediate Actions",
        "",
    ]
    lines.extend(f"- {action}" for action in run.next_actions)
    if readiness and readiness.raw_alpha_watchlist:
        lines.append(
            "- Fine-tune raw-alpha candidates only after checking fold cushion and "
            "drawdown; do not promote them on raw return alone."
        )
    if readiness and readiness.low_drawdown_watchlist:
        lines.append(
            "- Keep low-drawdown candidates in the arena as defensive challengers "
            "even when their raw return trails the alpha leader."
        )
    lines.extend(
        [
            "",
            "## Anti-Repeat Rule",
            "",
            "- Prefer an unseen fingerprint over any repeated fingerprint.",
            "- Repeat a completed fingerprint only when it is marked as finalist "
            "tuning, fresh-data retest, or explicit stress validation.",
            "- Repeated sightings count as evidence only when the fingerprint, "
            "data window, or tuning mode is distinct.",
            "",
        ]
    )
    return "\n".join(lines)


def render_autonomous_learning_cycle_markdown(
    run: AutonomousLearningCycleRun,
) -> str:
    lines = [
        "# Autonomous Learning Cycle Report",
        "",
        "> Research evidence only. This self-feeding loop may generate, test, "
        "rank, and recommend candidates, but it cannot grant paper or live "
        "trading authority.",
        "",
        "## Summary",
        "",
        f"- Run id: `{run.run_id}`",
        f"- Status: `{run.status.value}`",
        f"- Mode: `{run.mode.value}`",
        f"- Hypothesis: `{run.hypothesis_id}`",
        f"- Generated at: `{run.generated_at.isoformat()}`",
        f"- Range: `{run.start_date.isoformat()}` to `{run.end_date.isoformat()}`",
        f"- Benchmark: `{run.benchmark}`",
        f"- Feed: `{run.feed.value}`",
        f"- Universes: `{', '.join(run.universe_ids)}`",
        f"- Strategies searched: `{', '.join(run.strategy_ids)}`",
        f"- Candidate rows scored: `{run.candidate_count}`",
        f"- Completed replay reports: `{run.completed_report_count}`",
        f"- Skipped replay checks: `{run.skipped_count}`",
        f"- Current champion: `{run.current_champion_model_key}`",
        f"- Recommended challenger: `{run.recommended_challenger_model_key or 'none'}`",
        f"- Research fingerprint: `{run.research_fingerprint or 'none'}`",
        f"- Tuning mode: `{_yes_no(run.tuning_mode)}`",
        f"- Manual approval required: `{_yes_no(run.manual_approval_required)}`",
        f"- Active model unchanged: `{_yes_no(run.active_model_unchanged)}`",
        "",
        run.summary,
        "",
    ]

    if run.blocked_reasons:
        lines.extend(["## Blockers", "", "| Reason |", "| --- |"])
        lines.extend(f"| {_table_text(reason)} |" for reason in run.blocked_reasons)
        lines.append("")

    lines.extend(
        [
            "## Candidate Scoreboard",
            "",
            "| Rank | Universe | Candidate | Full Delta | Stress Delta | "
            "Positive Folds | Min Fold Delta | Avg Fold Delta | Worst DD | "
            "Risk Score | Gate Status | Status |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | --- | --- |",
        ]
    )
    if run.top_candidates:
        for candidate in run.top_candidates:
            lines.append(
                f"| {candidate.rank} | `{candidate.universe_id}` | "
                f"{_table_text(candidate.strategy_name)} "
                f"(`{candidate.model_key}`) | "
                f"{candidate.full_delta:+.2%} | "
                f"{_format_optional_pct(candidate.stress_delta)} | "
                f"{candidate.positive_folds}/{candidate.fold_count} | "
                f"{candidate.min_fold_delta:+.2%} | "
                f"{candidate.average_fold_delta:+.2%} | "
                f"{candidate.worst_drawdown:.2%} | "
                f"{candidate.risk_adjusted_score:.2f} | "
                f"{_table_text(candidate.gate_status)} | "
                f"{_table_text(candidate.status)} |"
            )
    else:
        lines.append(
            "| 0 | `none` | No candidates completed | - | - | 0/0 | - | - | "
            "- | - | blocked | blocked |"
        )

    lines.extend(
        [
            "",
            "## Benchmark Ladder For Leaders",
            "",
            "| Rank | Candidate | vs SPY | vs QQQ | vs XLK | vs SOXX | vs SMH | "
            "vs Semis Basket |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for candidate in run.top_candidates[:10]:
        ladder = candidate.benchmark_ladder
        lines.append(
            f"| {candidate.rank} | `{candidate.model_key}` | "
            f"{_format_optional_pct(ladder.get('SPY'))} | "
            f"{_format_optional_pct(ladder.get('QQQ'))} | "
            f"{_format_optional_pct(ladder.get('XLK'))} | "
            f"{_format_optional_pct(ladder.get('SOXX'))} | "
            f"{_format_optional_pct(ladder.get('SMH'))} | "
            f"{_format_optional_pct(ladder.get('Semis Basket'))} |"
        )

    if run.shadow_arena is not None:
        lines.extend(
            [
                "",
                "## Shadow Arena",
                "",
                f"- Broker orders submitted: "
                f"`{_yes_no(run.shadow_arena.broker_orders_submitted)}`",
                f"- Candidates tracked: `{len(run.shadow_arena.candidates)}`",
                f"- Artifact: "
                f"`{run.artifact_paths.get('shadow_arena_markdown', 'not written')}`",
                "",
                run.shadow_arena.summary,
                "",
            ]
        )

    if run.leaderboard is not None:
        leader = run.leaderboard.entries[0] if run.leaderboard.entries else None
        leader_key = f"{leader.universe_id}:{leader.model_key}" if leader else "none"
        lines.extend(
            [
                "",
                "## Consolidated Leaderboard",
                "",
                f"- Entries: `{run.leaderboard.entry_count}`",
                f"- Current leader: `{leader_key}`",
                f"- Artifact: "
                f"`{run.artifact_paths.get('leaderboard_markdown', 'not written')}`",
                "",
                run.leaderboard.summary,
                "",
            ]
        )

    if run.candidate_readiness is not None:
        readiness = run.candidate_readiness
        lines.extend(
            [
                "",
                "## Candidate Readiness",
                "",
                f"- Pilot status: `{readiness.pilot_status}`",
                f"- Pilot candidate: `{readiness.pilot_candidate_model_key or 'none'}`",
                f"- Promotion-qualified: `{len(readiness.promotion_qualified)}`",
                f"- Raw-alpha watchlist: `{len(readiness.raw_alpha_watchlist)}`",
                f"- Low-drawdown watchlist: `{len(readiness.low_drawdown_watchlist)}`",
                f"- Artifact: `{_artifact_path(run, 'candidate_readiness_markdown')}`",
                "",
                readiness.summary,
                "",
            ]
        )

    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {action}" for action in run.next_actions)
    if run.skipped_reasons:
        lines.extend(["", "## Skipped Detail", "", "| Reason |", "| --- |"])
        lines.extend(
            f"| {_table_text(reason)} |" for reason in run.skipped_reasons[:80]
        )
    lines.extend(
        [
            "",
            "## Governance",
            "",
            "- The loop can self-feed research by adding fresh evidence and rankings.",
            "- The loop cannot self-promote any model into higher paper or live "
            "authority.",
            "- Live-money trading remains disabled until separate readiness, "
            "operator signoff, and kill-switch gates pass.",
            "",
        ]
    )
    return "\n".join(lines)


def _candidate_readiness_report(
    run: AutonomousLearningCycleRun,
) -> AutonomousCandidateReadinessReport:
    candidates = tuple(run.top_candidates)
    promotion_qualified = tuple(
        candidates[index]
        for index in _top_candidate_indexes(
            candidates,
            predicate=_candidate_is_promotion_qualified,
            limit=25,
        )
    )
    raw_alpha = tuple(
        candidates[index]
        for index in _top_candidate_indexes(
            candidates,
            predicate=lambda candidate: (
                _candidate_is_raw_alpha_watchlist(candidate)
                and not _candidate_is_promotion_qualified(candidate)
            ),
            limit=25,
            sort_key=lambda candidate: (
                candidate.full_delta,
                candidate.stress_delta if candidate.stress_delta is not None else -99,
                candidate.min_fold_delta,
                candidate.worst_drawdown,
            ),
        )
    )
    low_drawdown = tuple(
        candidates[index]
        for index in _top_candidate_indexes(
            candidates,
            predicate=_candidate_is_low_drawdown_watchlist,
            limit=25,
            sort_key=lambda candidate: (
                candidate.full_delta,
                candidate.min_fold_delta,
                candidate.worst_drawdown,
            ),
        )
    )
    fragile = tuple(
        candidates[index]
        for index in _top_candidate_indexes(
            candidates,
            predicate=_candidate_is_fragile_watchlist,
            limit=25,
            sort_key=lambda candidate: (
                candidate.full_delta,
                candidate.stress_delta if candidate.stress_delta is not None else -99,
                candidate.risk_adjusted_score,
            ),
        )
    )
    pilot_candidate = next(
        (
            candidate
            for candidate in candidates
            if _candidate_is_pilot_eligible(candidate)
        ),
        None,
    )
    pilot_status = (
        "manual_pilot_review_eligible"
        if pilot_candidate is not None
        else "research_only"
    )
    if pilot_candidate is None:
        summary = (
            "No candidate currently clears the Friday pilot-readiness gates. "
            "Keep researching and shadow-tracking; do not promote live authority."
        )
    else:
        summary = (
            f"{pilot_candidate.model_key} clears the minimum research gates for "
            "manual pilot review, but live-money trading still requires separate "
            "operator approval, clean paper evidence, and kill switches."
        )
    return AutonomousCandidateReadinessReport(
        run_id=run.run_id,
        generated_at=run.generated_at,
        pilot_status=pilot_status,
        pilot_candidate_model_key=(
            pilot_candidate.model_key if pilot_candidate is not None else None
        ),
        promotion_qualified=promotion_qualified,
        raw_alpha_watchlist=raw_alpha,
        low_drawdown_watchlist=low_drawdown,
        fragile_watchlist=fragile,
        gate_rules=(
            "Promotion-quality: all validation folds positive, stress-cost delta "
            "positive, worst fold cushion at least +10%, and max drawdown no worse "
            "than -30%, while also beating QQQ or XLK.",
            "Pilot-eligible minimum: all validation folds positive, stress-cost "
            "delta positive, worst fold cushion at least +5%, and max drawdown no "
            "worse than -35%.",
            "Raw-alpha watchlist: strong full-period alpha but not yet robust "
            "enough for promotion.",
            "Low-drawdown watchlist: all-fold-positive candidates with max "
            "drawdown no worse than -25%.",
            "Recent-spike discipline: do not promote a model because the last "
            "21 or 63 trading days exploded upward; require 3/6/12-month "
            "consistency and a late-entry risk review.",
            "Static buy-and-hold instruments remain benchmarks only.",
        ),
        summary=summary,
    )


def _top_candidate_indexes(
    candidates: tuple[AutonomousLearningCandidate, ...],
    *,
    predicate,
    limit: int,
    sort_key=None,
) -> tuple[int, ...]:
    sortable = [
        (index, candidate)
        for index, candidate in enumerate(candidates)
        if predicate(candidate)
    ]
    if sort_key is None:
        sort_key = _candidate_sort_key
    return tuple(
        index
        for index, _ in sorted(
            sortable,
            key=lambda item: sort_key(item[1]),
            reverse=True,
        )[:limit]
    )


def _candidate_is_promotion_qualified(
    candidate: AutonomousLearningCandidate,
) -> bool:
    stress_positive = candidate.stress_delta is None or candidate.stress_delta > 0
    beats_tech = (candidate.benchmark_ladder.get("QQQ", -99.0) > 0) or (
        candidate.benchmark_ladder.get("XLK", -99.0) > 0
    )
    return (
        candidate.status == "all folds positive"
        and candidate.positive_folds == candidate.fold_count
        and candidate.full_delta > 0
        and stress_positive
        and beats_tech
        and candidate.min_fold_delta >= 0.10
        and candidate.worst_drawdown >= -0.30
    )


def _candidate_is_pilot_eligible(candidate: AutonomousLearningCandidate) -> bool:
    stress_positive = candidate.stress_delta is None or candidate.stress_delta > 0
    return (
        candidate.status == "all folds positive"
        and candidate.positive_folds == candidate.fold_count
        and candidate.full_delta > 0
        and stress_positive
        and candidate.min_fold_delta >= 0.05
        and candidate.worst_drawdown >= -0.35
    )


def _candidate_is_raw_alpha_watchlist(
    candidate: AutonomousLearningCandidate,
) -> bool:
    stress_delta = candidate.stress_delta if candidate.stress_delta is not None else 0
    return candidate.full_delta >= 0.50 or stress_delta >= 0.50


def _candidate_is_low_drawdown_watchlist(
    candidate: AutonomousLearningCandidate,
) -> bool:
    return (
        candidate.status == "all folds positive"
        and candidate.positive_folds == candidate.fold_count
        and candidate.full_delta > 0
        and candidate.worst_drawdown >= -0.25
    )


def _candidate_is_fragile_watchlist(
    candidate: AutonomousLearningCandidate,
) -> bool:
    if candidate.full_delta <= 0:
        return False
    return (
        candidate.positive_folds < candidate.fold_count
        or candidate.min_fold_delta < 0.05
        or candidate.worst_drawdown < -0.35
    )


def _write_candidate_group_artifacts(
    *,
    title: str,
    run: AutonomousLearningCycleRun,
    candidates: tuple[AutonomousLearningCandidate, ...],
    json_path: Path,
    latest_markdown_path: Path,
    run_markdown_path: Path,
    empty_message: str,
) -> None:
    payload = {
        "run_id": run.run_id,
        "generated_at": run.generated_at.isoformat(),
        "title": title,
        "candidate_count": len(candidates),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown = render_candidate_group_markdown(
        title=title,
        run=run,
        candidates=candidates,
        empty_message=empty_message,
    )
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    run_markdown_path.write_text(markdown, encoding="utf-8")


def render_candidate_group_markdown(
    *,
    title: str,
    run: AutonomousLearningCycleRun,
    candidates: tuple[AutonomousLearningCandidate, ...],
    empty_message: str,
) -> str:
    lines = [
        f"# {title}",
        "",
        "> Research evidence only. Candidates listed here still require manual "
        "review before any authority change.",
        "",
        "## Summary",
        "",
        f"- Run id: `{run.run_id}`",
        f"- Generated at: `{run.generated_at.isoformat()}`",
        f"- Hypothesis: `{run.hypothesis_id}`",
        f"- Candidates: `{len(candidates)}`",
        "",
    ]
    lines.extend(_candidate_table(candidates, empty_message=empty_message))
    lines.append("")
    return "\n".join(lines)


def _candidate_table(
    candidates: tuple[AutonomousLearningCandidate, ...],
    *,
    empty_message: str,
) -> list[str]:
    lines = [
        "| Rank | Universe | Candidate | Full Delta | Stress Delta | Min Fold | "
        "Worst DD | Folds | Risk Score | Gate | Status |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    if not candidates:
        empty = _table_text(empty_message)
        lines.append(f"| 0 | `none` | {empty} | - | - | - | - | 0/0 | - | - | - |")
        return lines
    for candidate in candidates:
        lines.append(
            f"| {candidate.rank} | `{candidate.universe_id}` | "
            f"`{candidate.model_key}` | "
            f"{candidate.full_delta:+.2%} | "
            f"{_format_optional_pct(candidate.stress_delta)} | "
            f"{candidate.min_fold_delta:+.2%} | "
            f"{candidate.worst_drawdown:.2%} | "
            f"{candidate.positive_folds}/{candidate.fold_count} | "
            f"{candidate.risk_adjusted_score:.2f} | "
            f"{_table_text(candidate.gate_status)} | "
            f"{_table_text(candidate.status)} |"
        )
    return lines


def _research_fingerprint_payload(
    config: AutonomousLearningCycleConfig,
    *,
    end_date: date,
) -> dict[str, object]:
    return {
        "hypothesis_id": config.hypothesis_id,
        "mode": config.mode.value,
        "start_date": config.start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "benchmark": config.benchmark,
        "universes": config.universes,
        "extra_symbols": config.extra_symbols,
        "strategy_ids": config.strategy_ids,
        "feed": config.feed.value,
        "max_strategies": config.max_strategies,
        "starting_cash": str(config.starting_cash),
        "slippage_bps": str(config.slippage_bps),
        "stress_slippage_bps": str(config.stress_slippage_bps),
        "warmup_calendar_days": config.warmup_calendar_days,
        "warmup_trading_days": config.warmup_trading_days,
    }


def _read_fingerprint_records(
    path: Path,
) -> dict[str, AutonomousResearchFingerprint]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): AutonomousResearchFingerprint.model_validate_json(json.dumps(value))
        for key, value in payload.items()
        if isinstance(value, dict)
    }


def _read_leaderboard(path: Path) -> AutonomousLearningLeaderboard | None:
    if not path.exists():
        return None
    return AutonomousLearningLeaderboard.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _shadow_arena_report(
    *,
    run_id: str,
    generated_at: datetime,
    candidates: tuple[AutonomousLearningCandidate, ...],
    starting_cash: Decimal,
    arena_size: int,
) -> AutonomousShadowArenaReport:
    arena_candidates = tuple(
        _shadow_arena_candidate(
            candidate,
            rank=index,
            starting_cash=starting_cash,
        )
        for index, candidate in enumerate(candidates[:arena_size], start=1)
    )
    summary = (
        f"Shadow arena is tracking {len(arena_candidates)} research candidate(s) "
        "in virtual-only mode. It does not submit broker orders."
    )
    return AutonomousShadowArenaReport(
        run_id=run_id,
        generated_at=generated_at,
        arena_size=arena_size,
        broker_orders_submitted=False,
        candidates=arena_candidates,
        summary=summary,
    )


def _shadow_arena_candidate(
    candidate: AutonomousLearningCandidate,
    *,
    rank: int,
    starting_cash: Decimal,
) -> AutonomousShadowArenaCandidate:
    historical_equity = (
        starting_cash * (Decimal("1") + Decimal(str(candidate.net_total_return)))
        if candidate.net_total_return is not None
        else None
    )
    historical_pnl = (
        historical_equity - starting_cash if historical_equity is not None else None
    )
    action = (
        "Manual review eligible if forward evidence confirms."
        if _candidate_passes_shadow_gate(candidate)
        else "Track only; gates are incomplete."
    )
    return AutonomousShadowArenaCandidate(
        rank=rank,
        universe_id=candidate.universe_id,
        model_key=candidate.model_key,
        strategy_name=candidate.strategy_name,
        authority="shadow",
        broker_orders_submitted=False,
        virtual_starting_cash=starting_cash,
        historical_virtual_equity=historical_equity,
        historical_virtual_pnl=historical_pnl,
        full_delta=candidate.full_delta,
        stress_delta=candidate.stress_delta,
        min_fold_delta=candidate.min_fold_delta,
        worst_drawdown=candidate.worst_drawdown,
        risk_adjusted_score=candidate.risk_adjusted_score,
        gate_status=candidate.gate_status,
        status=candidate.status,
        next_review_action=action,
    )


def _candidate_passes_shadow_gate(candidate: AutonomousLearningCandidate) -> bool:
    stress_positive = candidate.stress_delta is None or candidate.stress_delta > 0
    return (
        candidate.status == "all folds positive"
        and candidate.min_fold_delta > 0
        and stress_positive
        and candidate.worst_drawdown >= -0.30
    )


def _candidate_sort_key(candidate: AutonomousLearningCandidate) -> tuple[float, ...]:
    stress_delta = candidate.stress_delta if candidate.stress_delta is not None else -99
    gate_bonus = 1.0 if _candidate_passes_shadow_gate(candidate) else 0.0
    return (
        gate_bonus,
        candidate.risk_adjusted_score,
        float(candidate.positive_folds),
        candidate.min_fold_delta,
        stress_delta,
        candidate.full_delta,
        candidate.worst_drawdown,
    )


def _is_baseline_or_control_candidate(model_key: str) -> bool:
    return model_key.startswith("static_etf_allocation:") or model_key.endswith(
        "-no-breaker"
    )


def _leaderboard_entry_sort_key(
    entry: AutonomousLearningLeaderboardEntry,
) -> tuple[float, ...]:
    stress_delta = entry.stress_delta if entry.stress_delta is not None else -99
    gate_bonus = (
        1.0
        if entry.status == "all folds positive"
        and entry.min_fold_delta > 0
        and stress_delta > 0
        and entry.worst_drawdown >= -0.30
        else 0.0
    )
    return (
        gate_bonus,
        entry.risk_adjusted_score,
        float(entry.positive_folds),
        entry.min_fold_delta,
        stress_delta,
        entry.full_delta,
        entry.worst_drawdown,
    )


def _leaderboard_summary(
    entries: tuple[AutonomousLearningLeaderboardEntry, ...],
) -> str:
    if not entries:
        return "No autonomous learning candidates have reached the leaderboard yet."
    leader = entries[0]
    gate_count = sum(
        1
        for entry in entries
        if entry.status == "all folds positive"
        and entry.min_fold_delta > 0
        and (entry.stress_delta is None or entry.stress_delta > 0)
        and entry.worst_drawdown >= -0.30
    )
    return (
        f"Current research leader is {leader.universe_id}:{leader.model_key}; "
        f"{gate_count} leaderboard candidate(s) pass the shadow review gates. "
        "Manual review remains required before authority changes."
    )


def _format_optional_money(value: Decimal | None) -> str:
    return "n/a" if value is None else f"${value:,.2f}"


def _resolve_universes(
    config: AutonomousLearningCycleConfig,
) -> dict[str, tuple[str, ...]]:
    universes = _selected_universes(",".join(config.universes), config.benchmark)
    if config.extra_symbols:
        universes = _with_extra_symbols(
            universes,
            ",".join(config.extra_symbols),
            config.benchmark,
        )
    return universes


def _autonomous_catalog(
    *,
    symbols: tuple[str, ...],
    benchmark: str,
    mode: AutonomousLearningCycleMode,
) -> StrategyCatalog:
    definitions = []
    if mode == AutonomousLearningCycleMode.WEEKLY:
        definitions.extend(
            build_etf_parameter_grid_replay_catalog(
                symbols=symbols,
                benchmark=benchmark,
            ).all()
        )
    definitions.extend(_risk_managed_semiconductor_definitions(symbols, benchmark))
    available = set(symbols) | {benchmark}
    if {"SOXX", "SMH", "QQQ"} <= available:
        definitions.extend(
            build_market_drawdown_circuit_breaker_replay_catalog(
                benchmark=benchmark,
            ).all()
        )
    return StrategyCatalog(tuple(definitions))


def _candidate_summary(rank: int, score) -> AutonomousLearningCandidate:
    return AutonomousLearningCandidate(
        rank=rank,
        universe_id=score.universe_id,
        model_key=score.model_key,
        strategy_name=score.strategy_name,
        full_delta=score.full_delta,
        stress_delta=score.stress_delta,
        net_total_return=score.full.net_total_return,
        benchmark_total_return=score.full.benchmark_total_return,
        annualized_return=score.full.annualized_return,
        annualized_volatility=score.full.annualized_volatility,
        turnover=score.full.turnover,
        trade_count=score.full.trade_count,
        decision_count=score.full.decision_count,
        positive_folds=score.positive_folds,
        fold_count=len(score.folds),
        min_fold_delta=score.min_fold_delta,
        average_fold_delta=score.average_fold_delta,
        worst_drawdown=score.worst_drawdown,
        risk_adjusted_score=score.risk_adjusted_score,
        gate_status=score.gate_status,
        status=score.status,
        benchmark_ladder=score.benchmark_ladder,
        manual_approval_required=True,
    )


def _blocked_reasons(
    *,
    status: AutonomousLearningCycleStatus,
    skipped: tuple[str, ...],
    runs: list[DiscoveryRun],
    scores: list,
) -> tuple[str, ...]:
    if status != AutonomousLearningCycleStatus.BLOCKED:
        return ()
    reasons = []
    if not runs:
        reasons.append("No replay reports completed.")
    if not scores:
        reasons.append("No candidate scores were produced.")
    reasons.extend(skipped[:10])
    return tuple(reasons or ("Autonomous cycle blocked before scoring.",))


def _recommended_candidate(
    scores: tuple[AutonomousLearningCandidate, ...],
) -> AutonomousLearningCandidate | None:
    for score in scores:
        stress_positive = score.stress_delta is None or score.stress_delta > 0
        if (
            score.status == "all folds positive"
            and score.min_fold_delta > 0
            and stress_positive
            and score.worst_drawdown >= -0.30
        ):
            return score
    return None


def _summary(
    *,
    status: AutonomousLearningCycleStatus,
    scores: tuple[AutonomousLearningCandidate, ...],
    skipped: list[str],
) -> str:
    if status == AutonomousLearningCycleStatus.BLOCKED:
        return (
            "Autonomous learning was blocked before it could produce a usable "
            "champion/challenger ranking."
        )
    leader = scores[0]
    recommendation = _recommended_candidate(scores)
    recommendation_sentence = (
        f" Gate-qualified challenger: {recommendation.model_key}."
        if recommendation is not None
        else " No gate-qualified challenger was found."
    )
    return (
        f"Autonomous learning completed and ranked {len(scores)} candidate(s). "
        f"Top scored candidate {leader.model_key} shows full-sample delta "
        f"{leader.full_delta:+.2%}, minimum fold delta "
        f"{leader.min_fold_delta:+.2%}, and max drawdown "
        f"{leader.worst_drawdown:.2%}.{recommendation_sentence} "
        f"{len(skipped)} replay check(s) were skipped or blocked by data "
        "availability."
    )


def _next_actions(
    *,
    status: AutonomousLearningCycleStatus,
    scores: tuple[AutonomousLearningCandidate, ...],
    recommended: AutonomousLearningCandidate | None,
) -> tuple[str, ...]:
    if status == AutonomousLearningCycleStatus.BLOCKED:
        return (
            "Refresh or backfill missing historical bars, then rerun the cycle.",
            "Do not change paper or live authority while evidence is blocked.",
        )
    leader = recommended or scores[0]
    actions = [
        f"Review {leader.model_key} against the current champion before any "
        "promotion request."
        if recommended is not None
        else (
            "Do not open a promotion request yet; no candidate passed the "
            "consistency, stress, and drawdown recommendation gates."
        ),
        "Keep the active model unchanged until forward shadow or paper evidence "
        "confirms the backtest signal.",
    ]
    if recommended is None or leader.gate_status != "risk gates passed":
        actions.append(
            "Treat the scored leaders as research-only until the next autonomous "
            "cycle or forward evidence closes the risk gaps."
        )
    else:
        actions.append(
            "Queue the leader for manual shadow-review; approval is still "
            "required before authority changes."
        )
    return tuple(actions)


def _default_end_date(today: date) -> date:
    candidate = today - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _aware_generated_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _run_id(mode: AutonomousLearningCycleMode, generated_at: datetime) -> str:
    return f"learning-cycle-{mode.value}-{generated_at:%Y%m%dT%H%M%SZ}"


def _format_optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2%}"


def _table_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _artifact_path(run: AutonomousLearningCycleRun, key: str) -> str:
    return run.artifact_paths.get(key, "not written")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
