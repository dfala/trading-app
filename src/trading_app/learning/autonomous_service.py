"""Long-running scheduler for autonomous research learning."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator

from trading_app.learning.autonomous import (
    DEFAULT_AUTONOMOUS_STRATEGY_IDS,
    DEFAULT_AUTONOMOUS_UNIVERSES,
    DEFAULT_LEARNING_STATUS_DIR,
    DEFAULT_RESEARCH_OUTPUT_DIR,
    AutonomousLearningCandidate,
    AutonomousLearningCycleConfig,
    AutonomousLearningCycleMode,
    AutonomousLearningCycleRun,
    AutonomousLearningCycleRunner,
    research_experiment_fingerprint,
)
from trading_app.market_data.storage import DEFAULT_BAR_ROOT
from trading_app.research.run_replay_discovery import (
    DEFAULT_WARMUP_CALENDAR_DAYS,
    DEFAULT_WARMUP_TRADING_DAYS,
    DISCOVERY_UNIVERSES,
    _load_env_file,
)
from trading_app.schemas import DataFeed, TradingModel, validate_symbol

MARKET_TIMEZONE = "America/New_York"
MARKET_OPEN_TIME = dt_time(hour=9, minute=30)
MARKET_CLOSE_TIME = dt_time(hour=16)
DEFAULT_AFTER_CLOSE_LEARNING_TIME = dt_time(hour=16, minute=15)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class AutonomousLearningServiceStatus(StrEnum):
    RUNNING = "running"
    IDLE = "idle"
    RUNNING_CYCLE = "running_cycle"
    FAILED = "failed"
    STOPPED = "stopped"


class AutonomousLearningServiceTask(StrEnum):
    HISTORICAL_EXPERIMENT = "historical_experiment"
    FRESH_MARKET_DATA = "fresh_market_data_learning"


class HistoricalHypothesisProfile(TradingModel):
    profile_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    mode: AutonomousLearningCycleMode
    universes: tuple[str, ...] = Field(min_length=1)
    strategy_ids: tuple[str, ...] = Field(min_length=1)
    max_strategies: int = Field(default=0, ge=0)
    start_date: date | None = None

    @field_validator("universes", "strategy_ids")
    @classmethod
    def _validate_non_empty_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("value cannot be empty")
        if any(not value.strip() for value in values):
            raise ValueError("tuple values must be non-empty strings")
        return values


@dataclass(frozen=True)
class _GeneratedStrategyBundle:
    bundle_id: str
    name: str
    summary: str
    strategy_ids: tuple[str, ...]
    max_strategies: int


@dataclass(frozen=True)
class _GeneratedUniverseGroup:
    group_id: str
    name: str
    universes: tuple[str, ...]


@dataclass(frozen=True)
class _GeneratedStartCohort:
    cohort_id: str
    name: str
    start_date: date | None


@dataclass(frozen=True)
class _GeneratedSearchDepth:
    depth_id: str
    name: str
    max_strategies: int


@dataclass(frozen=True)
class _PriorityTuningTarget:
    model_key: str
    name: str
    summary: str
    universe_id: str
    strategy_ids: tuple[str, ...]
    max_strategies: int


DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES = (
    HistoricalHypothesisProfile(
        profile_id="semiconductor-risk-overlays",
        name="Semiconductor Risk Overlays",
        summary=(
            "Stress the current semiconductor alpha sleeve with trend, "
            "volatility, and drawdown controls."
        ),
        mode=AutonomousLearningCycleMode.SMOKE,
        universes=("semiconductor-champions",),
        strategy_ids=(
            "market_drawdown_circuit_breaker",
            "risk_managed_semiconductor",
        ),
        max_strategies=24,
    ),
    HistoricalHypothesisProfile(
        profile_id="champion-breaker-sensitivity-expanded",
        name="Expanded Champion Breaker Sensitivity",
        summary=(
            "Stress the current champion family with wider QQQ/SPY drawdown "
            "threshold and partial-risk exposure grids."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("semiconductor-champions",),
        strategy_ids=("market_drawdown_circuit_breaker",),
        max_strategies=72,
    ),
    HistoricalHypothesisProfile(
        profile_id="semiconductor-alpha-blends",
        name="Semiconductor Alpha Blends",
        summary=(
            "Search whether semiconductor alpha can be blended with broader "
            "growth or tech sleeves while preserving drawdown controls."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("semiconductor-champions", "growth-industries"),
        strategy_ids=(
            "risk_managed_semiconductor",
            "market_drawdown_circuit_breaker",
            "volatility_aware_etf",
            "cash_rotation_model",
        ),
        max_strategies=72,
    ),
    HistoricalHypothesisProfile(
        profile_id="shadow-arena-finalists",
        name="Shadow Arena Finalists",
        summary=(
            "Populate the shadow arena with the strongest diverse candidates "
            "from semiconductor, broad-core, and growth universes."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=(
            "semiconductor-champions",
            "broad-core",
            "growth-industries",
        ),
        strategy_ids=(
            "monthly_sector_momentum",
            "benchmark_relative_strength_etf",
            "risk_managed_semiconductor",
            "market_drawdown_circuit_breaker",
            "volatility_aware_etf",
            "cash_rotation_model",
        ),
        max_strategies=72,
    ),
    HistoricalHypothesisProfile(
        profile_id="sector-etf-momentum-grid",
        name="Sector ETF Momentum Grid",
        summary=(
            "Search sector-rotation variants across trend, relative strength, "
            "volatility, cash, and defensive regime controls."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("sector-spdr",),
        strategy_ids=(
            "monthly_sector_momentum",
            "trend_following_etf",
            "benchmark_relative_strength_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
            "defensive_regime_switch",
        ),
        max_strategies=36,
    ),
    HistoricalHypothesisProfile(
        profile_id="defensive-macro-regime",
        name="Defensive Macro Regime",
        summary=(
            "Test whether macro and defensive assets improve drawdown control "
            "without giving up too much upside."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("macro-defensive",),
        strategy_ids=(
            "trend_following_etf",
            "cash_rotation_model",
            "defensive_regime_switch",
            "volatility_aware_etf",
        ),
        max_strategies=32,
    ),
    HistoricalHypothesisProfile(
        profile_id="growth-industry-rotation",
        name="Growth Industry Rotation",
        summary=(
            "Compare semiconductor concentration against broader growth and "
            "industry-ETF rotation candidates."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("growth-industries",),
        strategy_ids=(
            "monthly_sector_momentum",
            "benchmark_relative_strength_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
            "trend_following_etf",
        ),
        max_strategies=36,
    ),
    HistoricalHypothesisProfile(
        profile_id="broad-core-allocation",
        name="Broad Core Allocation",
        summary=(
            "Search broad, liquid ETF allocation variants as a sanity check "
            "against narrower sector or industry themes."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("broad-core",),
        strategy_ids=(
            "monthly_sector_momentum",
            "trend_following_etf",
            "mean_reversion_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
        ),
        max_strategies=36,
    ),
    HistoricalHypothesisProfile(
        profile_id="liquid-risk-on-rotation",
        name="Liquid Risk-On Rotation",
        summary=(
            "Test whether highly liquid risk-on ETFs can produce a cleaner "
            "rotation signal than the narrower semiconductor sleeve."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("liquid-risk-on",),
        strategy_ids=(
            "monthly_sector_momentum",
            "benchmark_relative_strength_etf",
            "volatility_aware_etf",
            "trend_following_etf",
            "cash_rotation_model",
        ),
        max_strategies=36,
    ),
    HistoricalHypothesisProfile(
        profile_id="semis-vs-growth-relative-strength",
        name="Semis vs Growth Relative Strength",
        summary=(
            "Compare semiconductor leadership against broader growth "
            "industries using relative strength and risk controls."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("semiconductor-champions", "growth-industries"),
        strategy_ids=(
            "risk_managed_semiconductor",
            "market_drawdown_circuit_breaker",
            "benchmark_relative_strength_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
        ),
        max_strategies=36,
    ),
    HistoricalHypothesisProfile(
        profile_id="defensive-sector-cash-controls",
        name="Defensive Sector Cash Controls",
        summary=(
            "Search whether defensive regime and cash overlays improve "
            "sector momentum drawdowns without overfitting to semiconductors."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("sector-spdr", "macro-defensive"),
        strategy_ids=(
            "defensive_regime_switch",
            "cash_rotation_model",
            "volatility_aware_etf",
            "trend_following_etf",
        ),
        max_strategies=36,
    ),
    HistoricalHypothesisProfile(
        profile_id="broad-vs-risk-on-crosscheck",
        name="Broad vs Risk-On Crosscheck",
        summary=(
            "Cross-check broad-core and liquid risk-on universes for "
            "signals that persist outside a single sector theme."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("broad-core", "liquid-risk-on"),
        strategy_ids=(
            "monthly_sector_momentum",
            "benchmark_relative_strength_etf",
            "mean_reversion_etf",
            "trend_following_etf",
            "volatility_aware_etf",
        ),
        max_strategies=36,
    ),
    HistoricalHypothesisProfile(
        profile_id="all-weather-growth-barbell",
        name="All-Weather Growth Barbell",
        summary=(
            "Test whether combining growth exposure with macro-defensive "
            "assets creates a sturdier challenger than pure sector momentum."
        ),
        mode=AutonomousLearningCycleMode.WEEKLY,
        universes=("growth-industries", "macro-defensive"),
        strategy_ids=(
            "monthly_sector_momentum",
            "defensive_regime_switch",
            "cash_rotation_model",
            "volatility_aware_etf",
            "trend_following_etf",
        ),
        max_strategies=36,
    ),
)

GENERATED_START_COHORTS = (
    _GeneratedStartCohort("full", "Full 2016-forward window", None),
    _GeneratedStartCohort(
        "post-election-2017",
        "Post-2016 election 2017-forward window",
        date(2017, 1, 3),
    ),
    _GeneratedStartCohort(
        "late-cycle-2018",
        "Late-cycle 2018-forward window",
        date(2018, 1, 2),
    ),
    _GeneratedStartCohort(
        "pre-covid-2019",
        "Pre-COVID 2019-forward window",
        date(2019, 1, 2),
    ),
    _GeneratedStartCohort("covid-2020", "Post-2020 regime window", date(2020, 1, 2)),
    _GeneratedStartCohort(
        "reopening-2021",
        "Reopening 2021-forward window",
        date(2021, 1, 4),
    ),
    _GeneratedStartCohort(
        "rate-reset-2022",
        "Rate-reset 2022-forward window",
        date(2022, 1, 3),
    ),
    _GeneratedStartCohort(
        "ai-boom-2023",
        "AI-boom 2023-forward window",
        date(2023, 1, 3),
    ),
    _GeneratedStartCohort(
        "recent-2024",
        "Recent 2024-forward window",
        date(2024, 1, 2),
    ),
)

GENERATED_SEARCH_DEPTHS = (
    _GeneratedSearchDepth("d12", "Fast top-12 catalog scan", 12),
    _GeneratedSearchDepth("d24", "Medium top-24 catalog scan", 24),
    _GeneratedSearchDepth("d36", "Broad top-36 catalog scan", 36),
    _GeneratedSearchDepth("d72", "Deep top-72 catalog scan", 72),
    _GeneratedSearchDepth("d144", "Deep top-144 catalog scan", 144),
)

PRIORITY_TUNING_TARGETS = (
    _PriorityTuningTarget(
        model_key="benchmark_relative_strength_etf:grid-l126-t63-n1",
        name="Benchmark Relative Strength Leader",
        summary=(
            "Tune the current semiconductor relative-strength leader and nearby "
            "benchmark-relative parameter variants."
        ),
        universe_id="semiconductor-champions",
        strategy_ids=("benchmark_relative_strength_etf",),
        max_strategies=36,
    ),
    _PriorityTuningTarget(
        model_key="cash_rotation_model:grid-l63-n3-b040",
        name="Cash Rotation Lower-Drawdown Challenger",
        summary=(
            "Tune the lower-drawdown cash-rotation challenger and adjacent "
            "breadth/top-N variants."
        ),
        universe_id="semiconductor-champions",
        strategy_ids=("cash_rotation_model",),
        max_strategies=36,
    ),
    _PriorityTuningTarget(
        model_key="cash_rotation_model:grid-l63-n2-b040",
        name="Cash Rotation Balanced Challenger",
        summary=(
            "Tune the balanced cash-rotation challenger and nearby breadth/top-N "
            "variants."
        ),
        universe_id="semiconductor-champions",
        strategy_ids=("cash_rotation_model",),
        max_strategies=36,
    ),
    _PriorityTuningTarget(
        model_key=(
            "market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk025-cash"
        ),
        name="Market Drawdown Circuit Breaker Challenger",
        summary=(
            "Tune the semiconductor drawdown circuit-breaker challenger and "
            "nearby drawdown/exposure settings."
        ),
        universe_id="semiconductor-champions",
        strategy_ids=("market_drawdown_circuit_breaker",),
        max_strategies=36,
    ),
)

GENERATED_UNIVERSE_GROUPS = (
    _GeneratedUniverseGroup(
        "semis",
        "Semiconductor champions",
        ("semiconductor-champions",),
    ),
    _GeneratedUniverseGroup("growth", "Growth industries", ("growth-industries",)),
    _GeneratedUniverseGroup("risk-on", "Liquid risk-on ETFs", ("liquid-risk-on",)),
    _GeneratedUniverseGroup("broad", "Broad core ETFs", ("broad-core",)),
    _GeneratedUniverseGroup("sectors", "Sector SPDRs", ("sector-spdr",)),
    _GeneratedUniverseGroup("defensive", "Macro defensive ETFs", ("macro-defensive",)),
    _GeneratedUniverseGroup(
        "semis-growth",
        "Semiconductors versus growth industries",
        ("semiconductor-champions", "growth-industries"),
    ),
    _GeneratedUniverseGroup(
        "semis-risk-on",
        "Semiconductors versus liquid risk-on ETFs",
        ("semiconductor-champions", "liquid-risk-on"),
    ),
    _GeneratedUniverseGroup(
        "growth-defensive",
        "Growth plus macro defensive ETFs",
        ("growth-industries", "macro-defensive"),
    ),
    _GeneratedUniverseGroup(
        "broad-risk-on",
        "Broad core versus liquid risk-on ETFs",
        ("broad-core", "liquid-risk-on"),
    ),
    _GeneratedUniverseGroup(
        "sectors-defensive",
        "Sector SPDRs plus defensive controls",
        ("sector-spdr", "macro-defensive"),
    ),
    _GeneratedUniverseGroup(
        "multi-risk",
        "Broad, growth, and semiconductor cross-check",
        ("broad-core", "growth-industries", "semiconductor-champions"),
    ),
)

GENERATED_STRATEGY_BUNDLES = (
    _GeneratedStrategyBundle(
        "relative-momentum",
        "Relative Momentum",
        (
            "Search relative-strength, monthly momentum, trend, volatility, "
            "and cash rotation signals."
        ),
        (
            "monthly_sector_momentum",
            "benchmark_relative_strength_etf",
            "trend_following_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
        ),
        36,
    ),
    _GeneratedStrategyBundle(
        "drawdown-risk-controls",
        "Drawdown Risk Controls",
        (
            "Stress drawdown circuit breakers, semiconductor sleeves, "
            "volatility controls, and cash rotation."
        ),
        (
            "market_drawdown_circuit_breaker",
            "risk_managed_semiconductor",
            "volatility_aware_etf",
            "cash_rotation_model",
        ),
        72,
    ),
    _GeneratedStrategyBundle(
        "defensive-cash",
        "Defensive Cash Controls",
        "Test defensive regime, cash rotation, trend, and volatility-aware variants.",
        (
            "defensive_regime_switch",
            "cash_rotation_model",
            "trend_following_etf",
            "volatility_aware_etf",
        ),
        36,
    ),
    _GeneratedStrategyBundle(
        "mean-reversion-control",
        "Mean Reversion Control",
        (
            "Check whether mean reversion adds useful contrast to trend "
            "and volatility controls."
        ),
        (
            "mean_reversion_etf",
            "trend_following_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
        ),
        36,
    ),
    _GeneratedStrategyBundle(
        "cash-volatility",
        "Cash and Volatility",
        "Focus on weak-opportunity cash rotation and volatility sizing controls.",
        (
            "cash_rotation_model",
            "volatility_aware_etf",
            "benchmark_relative_strength_etf",
        ),
        36,
    ),
    _GeneratedStrategyBundle(
        "semiconductor-polish",
        "Semiconductor Polish",
        (
            "Polish the strongest semiconductor risk-managed families without "
            "static hold controls."
        ),
        (
            "market_drawdown_circuit_breaker",
            "risk_managed_semiconductor",
        ),
        72,
    ),
)


class AutonomousLearningPromotionStatus(StrEnum):
    WAITING = "waiting_for_evidence"
    READY_FOR_MANUAL_REVIEW = "ready_for_manual_review"
    BLOCKED = "blocked"


class AutonomousLearningPromotionObservation(TradingModel):
    observed_at: AwareDatetime
    trading_day: date
    run_id: str = Field(min_length=1)
    candidate_model_key: str = Field(min_length=1)
    full_delta: float
    stress_delta: float | None = None
    min_fold_delta: float
    worst_drawdown: float
    gate_status: str = Field(min_length=1)
    candidate_status: str = Field(min_length=1)
    manual_approval_required: bool = True
    active_model_unchanged: bool = True


class AutonomousLearningPromotionGate(TradingModel):
    status: AutonomousLearningPromotionStatus
    candidate_model_key: str | None = None
    observation_count: int = Field(ge=0)
    distinct_observation_dates: int = Field(ge=0)
    first_seen_at: AwareDatetime | None = None
    last_seen_at: AwareDatetime | None = None
    evidence_run_ids: tuple[str, ...] = ()
    manual_approval_required: bool = True
    summary: str = Field(min_length=1)


class AutonomousLearningServiceState(TradingModel):
    generated_at: AwareDatetime
    heartbeat_at: AwareDatetime
    service_status: AutonomousLearningServiceStatus
    started_at: AwareDatetime | None = None
    stopped_at: AwareDatetime | None = None
    current_task: AutonomousLearningServiceTask | None = None
    active_run_id: str | None = None
    current_historical_hypothesis_id: str | None = None
    current_historical_fingerprint: str | None = None
    current_historical_lane: str | None = None
    last_historical_hypothesis_id: str | None = None
    last_historical_fingerprint: str | None = None
    last_historical_lane: str | None = None
    next_historical_hypothesis_id: str | None = None
    next_historical_fingerprint: str | None = None
    next_historical_lane: str | None = None
    historical_hypothesis_counts: dict[str, int] = Field(default_factory=dict)
    historical_fingerprint_counts: dict[str, int] = Field(default_factory=dict)
    historical_lane_counts: dict[str, int] = Field(default_factory=dict)
    dynamic_historical_backlog_enabled: bool = False
    dynamic_historical_profile_count: int = Field(default=0, ge=0)
    last_completed_task: AutonomousLearningServiceTask | None = None
    last_historical_experiment_at: AwareDatetime | None = None
    last_historical_experiment_attempt_at: AwareDatetime | None = None
    last_fresh_market_data_at: AwareDatetime | None = None
    last_fresh_market_data_attempt_at: AwareDatetime | None = None
    last_fresh_market_data_trading_day: date | None = None
    last_cycle_run_id: str | None = None
    last_cycle_status: str | None = None
    latest_recommended_challenger_model_key: str | None = None
    completed_cycle_count: int = Field(default=0, ge=0)
    failed_cycle_count: int = Field(default=0, ge=0)
    skipped_cycle_count: int = Field(default=0, ge=0)
    next_historical_experiment_due_at: AwareDatetime | None = None
    next_fresh_market_data_due_at: AwareDatetime | None = None
    last_error: str | None = None
    policy_summary: str = Field(min_length=1)
    promotion_gate: AutonomousLearningPromotionGate


class MarketLearningWindow(TradingModel):
    checked_at: AwareDatetime
    checked_at_market: AwareDatetime
    trading_day: date
    is_weekday: bool
    is_market_open: bool
    is_after_close_learning_window: bool


class AutonomousLearningServiceConfig(TradingModel):
    start_date: date = date(2016, 1, 4)
    benchmark: str = "SPY"
    universes: tuple[str, ...] = DEFAULT_AUTONOMOUS_UNIVERSES
    extra_symbols: tuple[str, ...] = ()
    strategy_ids: tuple[str, ...] = DEFAULT_AUTONOMOUS_STRATEGY_IDS
    feed: DataFeed = DataFeed.SIP
    root: Path = DEFAULT_BAR_ROOT
    output_dir: Path = DEFAULT_RESEARCH_OUTPUT_DIR
    status_dir: Path = DEFAULT_LEARNING_STATUS_DIR
    poll_seconds: int = Field(default=60, ge=1)
    historical_interval_hours: int = Field(default=0, ge=0)
    historical_cooldown_minutes: int = Field(default=1, ge=0)
    failed_retry_minutes: int = Field(default=60, ge=1)
    after_close_learning_time: dt_time = DEFAULT_AFTER_CLOSE_LEARNING_TIME
    market_timezone: str = MARKET_TIMEZONE
    max_strategies_historical: int = Field(default=36, ge=0)
    max_strategies_fresh: int = Field(default=24, ge=0)
    historical_hypotheses: tuple[HistoricalHypothesisProfile, ...] = (
        DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES
    )
    dynamic_historical_backlog: bool = True
    dynamic_historical_backlog_size: int = Field(default=5000, ge=0)
    leader_tuning_profile_count: int = Field(default=6, ge=0)
    repeat_historical_sweeps: bool = False
    tuning_mode: bool = False
    fetch_missing_after_close: bool = True
    refresh_data_after_close: bool = False
    run_historical_on_start: bool = True
    promotion_min_observations: int = Field(default=3, ge=1)
    promotion_min_distinct_days: int = Field(default=2, ge=1)
    promotion_min_span_days: int = Field(default=2, ge=0)
    champion_model_key: str = (
        "market_drawdown_circuit_breaker:top-semi-l126-any-dd12-risk0-cash"
    )

    @field_validator("benchmark")
    @classmethod
    def _validate_benchmark(cls, benchmark: str) -> str:
        return validate_symbol(benchmark)

    @field_validator("universes", "strategy_ids")
    @classmethod
    def _validate_non_empty_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("value cannot be empty")
        if any(not value.strip() for value in values):
            raise ValueError("tuple values must be non-empty strings")
        return values

    @field_validator("historical_hypotheses")
    @classmethod
    def _validate_historical_hypotheses(
        cls,
        values: tuple[HistoricalHypothesisProfile, ...],
    ) -> tuple[HistoricalHypothesisProfile, ...]:
        if not values:
            raise ValueError("historical_hypotheses cannot be empty")
        profile_ids = [profile.profile_id for profile in values]
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("historical_hypotheses profile_id values must be unique")
        return values

    @field_validator("extra_symbols")
    @classmethod
    def _validate_extra_symbols(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_symbol(symbol) for symbol in symbols)

    @field_validator("market_timezone")
    @classmethod
    def _validate_market_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class AutonomousLearningService:
    """Run self-feeding research cycles without granting trading authority."""

    def __init__(
        self,
        *,
        config: AutonomousLearningServiceConfig | None = None,
        runner: AutonomousLearningCycleRunner | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or AutonomousLearningServiceConfig()
        self.runner = runner or AutonomousLearningCycleRunner()
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self.sleeper = sleeper or time.sleep
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run_forever(
        self, *, max_loops: int | None = None
    ) -> AutonomousLearningServiceState:
        service_lock = self.config.status_dir / "autonomous-learning-service.lock"
        try:
            with _ServiceLock(service_lock):
                return self._run_loop(max_loops=max_loops)
        except RuntimeError as error:
            now = _aware(self.clock())
            state = self._read_state() or _initial_state(now, self.config)
            return self._write_state(
                _with_due_times(
                    state.model_copy(
                        update={
                            "service_status": AutonomousLearningServiceStatus.FAILED,
                            "heartbeat_at": now,
                            "current_task": None,
                            "active_run_id": None,
                            "failed_cycle_count": state.failed_cycle_count + 1,
                            "last_error": str(error),
                        }
                    ),
                    now=now,
                    config=self.config,
                )
            )

    def _run_loop(
        self, *, max_loops: int | None = None
    ) -> AutonomousLearningServiceState:
        state = self._read_state() or _initial_state(self.clock(), self.config)
        state = self._write_state(
            _with_due_times(
                state.model_copy(
                    update={
                        "service_status": AutonomousLearningServiceStatus.RUNNING,
                        "started_at": state.started_at or self.clock(),
                        "stopped_at": None,
                        "last_error": None,
                    }
                ),
                now=self.clock(),
                config=self.config,
            )
        )
        loops = 0
        while not self._stop_requested and (max_loops is None or loops < max_loops):
            state = self.run_once()
            loops += 1
            if self._stop_requested or (max_loops is not None and loops >= max_loops):
                break
            self.sleeper(self.config.poll_seconds)
        if self._stop_requested:
            state = self._write_state(
                state.model_copy(
                    update={
                        "service_status": AutonomousLearningServiceStatus.STOPPED,
                        "stopped_at": self.clock(),
                        "current_task": None,
                        "active_run_id": None,
                    }
                )
            )
        return state

    def run_once(
        self, *, now: datetime | None = None
    ) -> AutonomousLearningServiceState:
        checked_at = _aware(now or self.clock())
        state = self._read_state() or _initial_state(checked_at, self.config)
        task = next_due_task(state=state, now=checked_at, config=self.config)
        if task is None:
            return self._write_state(
                _with_due_times(
                    state.model_copy(
                        update={
                            "service_status": AutonomousLearningServiceStatus.IDLE,
                            "heartbeat_at": checked_at,
                            "current_task": None,
                            "active_run_id": None,
                            "current_historical_hypothesis_id": None,
                            "current_historical_fingerprint": None,
                            "current_historical_lane": None,
                        }
                    ),
                    now=checked_at,
                    config=self.config,
                )
            )
        return self._run_task(task, state=state, now=checked_at)

    def _run_task(
        self,
        task: AutonomousLearningServiceTask,
        *,
        state: AutonomousLearningServiceState,
        now: datetime,
    ) -> AutonomousLearningServiceState:
        hypothesis_profile = (
            _next_historical_hypothesis_profile(state, self.config, now=now)
            if task == AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT
            else None
        )
        historical_fingerprint = (
            _historical_fingerprint(hypothesis_profile, self.config, now=now)
            if hypothesis_profile is not None
            else None
        )
        if (
            task == AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT
            and hypothesis_profile is None
        ):
            return self._write_state(
                _with_due_times(
                    state.model_copy(
                        update={
                            "service_status": AutonomousLearningServiceStatus.IDLE,
                            "heartbeat_at": now,
                            "current_task": None,
                            "active_run_id": None,
                            "current_historical_hypothesis_id": None,
                            "current_historical_fingerprint": None,
                            "current_historical_lane": None,
                            "last_error": (
                                "No untried historical hypotheses remain in "
                                "the current sweep."
                            ),
                        }
                    ),
                    now=now,
                    config=self.config,
                )
            )
        run_id = _run_id(task, now, hypothesis_profile=hypothesis_profile)
        attempt_update: dict[str, object] = {
            "service_status": AutonomousLearningServiceStatus.RUNNING_CYCLE,
            "heartbeat_at": now,
            "current_task": task,
            "active_run_id": run_id,
            "last_error": None,
        }
        if task == AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT:
            attempt_update["last_historical_experiment_attempt_at"] = now
            attempt_update["current_historical_hypothesis_id"] = (
                hypothesis_profile.profile_id if hypothesis_profile else None
            )
            attempt_update["current_historical_fingerprint"] = historical_fingerprint
            attempt_update["current_historical_lane"] = (
                _historical_profile_lane(hypothesis_profile)
                if hypothesis_profile
                else None
            )
        else:
            attempt_update["last_fresh_market_data_attempt_at"] = now
        self._write_state(
            _with_due_times(
                state.model_copy(update=attempt_update),
                now=now,
                config=self.config,
            )
        )

        try:
            lock_path = self.config.status_dir / "autonomous-learning-cycle.lock"
            with _ServiceLock(lock_path):
                run = self.runner.run(
                    _cycle_config(
                        task,
                        run_id,
                        now,
                        self.config,
                        hypothesis_profile=hypothesis_profile,
                    ),
                    generated_at=now,
                )
        except Exception as error:
            failure_update = {
                **attempt_update,
                "service_status": AutonomousLearningServiceStatus.FAILED,
                "current_task": None,
                "active_run_id": None,
                "failed_cycle_count": state.failed_cycle_count + 1,
                "last_error": str(error),
            }
            if task == AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT:
                failure_update["current_historical_hypothesis_id"] = None
                failure_update["current_historical_fingerprint"] = None
                failure_update["current_historical_lane"] = None
            failed = state.model_copy(update=failure_update)
            return self._write_state(
                _with_due_times(failed, now=now, config=self.config)
            )

        observations = _load_promotion_observations(self.config.status_dir)
        observation = _promotion_observation(run, now=now, config=self.config)
        if observation is not None:
            observations = _append_promotion_observation(
                self.config.status_dir,
                observation,
                existing=observations,
            )
        promotion_gate = _promotion_gate(observations, config=self.config)
        completed_update: dict[str, object] = {
            "service_status": AutonomousLearningServiceStatus.IDLE,
            "heartbeat_at": now,
            "current_task": None,
            "active_run_id": None,
            "last_completed_task": task,
            "last_cycle_run_id": run.run_id,
            "last_cycle_status": run.status.value,
            "latest_recommended_challenger_model_key": (
                run.recommended_challenger_model_key
            ),
            "completed_cycle_count": state.completed_cycle_count + 1,
            "promotion_gate": promotion_gate,
            "last_error": None,
        }
        if task == AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT:
            hypothesis_counts = dict(state.historical_hypothesis_counts)
            fingerprint_counts = dict(state.historical_fingerprint_counts)
            lane_counts = dict(state.historical_lane_counts)
            if hypothesis_profile is not None:
                lane = _historical_profile_lane(hypothesis_profile)
                hypothesis_counts[hypothesis_profile.profile_id] = (
                    hypothesis_counts.get(hypothesis_profile.profile_id, 0) + 1
                )
                lane_counts[lane] = lane_counts.get(lane, 0) + 1
                completed_update["last_historical_hypothesis_id"] = (
                    hypothesis_profile.profile_id
                )
                completed_update["last_historical_lane"] = lane
            if historical_fingerprint is not None:
                fingerprint_counts[historical_fingerprint] = (
                    fingerprint_counts.get(historical_fingerprint, 0) + 1
                )
                completed_update["last_historical_fingerprint"] = historical_fingerprint
            completed_update["current_historical_hypothesis_id"] = None
            completed_update["current_historical_fingerprint"] = None
            completed_update["current_historical_lane"] = None
            completed_update["historical_hypothesis_counts"] = hypothesis_counts
            completed_update["historical_fingerprint_counts"] = fingerprint_counts
            completed_update["historical_lane_counts"] = lane_counts
            completed_update["last_historical_experiment_at"] = now
            completed_update["last_historical_experiment_attempt_at"] = now
        else:
            completed_update["last_fresh_market_data_at"] = now
            completed_update["last_fresh_market_data_attempt_at"] = now
            completed_update["last_fresh_market_data_trading_day"] = (
                market_learning_window(now, self.config).trading_day
            )
        completed = state.model_copy(update=completed_update)
        return self._write_state(
            _with_due_times(completed, now=now, config=self.config)
        )

    def _read_state(self) -> AutonomousLearningServiceState | None:
        return read_autonomous_learning_service_state(self.config.status_dir)

    def _write_state(
        self, state: AutonomousLearningServiceState
    ) -> AutonomousLearningServiceState:
        write_autonomous_learning_service_state(state, self.config.status_dir)
        return state


def next_due_task(
    *,
    state: AutonomousLearningServiceState,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> AutonomousLearningServiceTask | None:
    checked_at = _aware(now)
    if _fresh_learning_due(state=state, now=checked_at, config=config):
        return AutonomousLearningServiceTask.FRESH_MARKET_DATA
    if _historical_experiment_due(state=state, now=checked_at, config=config):
        return AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT
    return None


def market_learning_window(
    now: datetime, config: AutonomousLearningServiceConfig
) -> MarketLearningWindow:
    checked_at = _aware(now)
    local = checked_at.astimezone(ZoneInfo(config.market_timezone))
    is_weekday = local.weekday() < 5
    is_market_open = is_weekday and MARKET_OPEN_TIME <= local.time() < MARKET_CLOSE_TIME
    return MarketLearningWindow(
        checked_at=checked_at,
        checked_at_market=local,
        trading_day=local.date(),
        is_weekday=is_weekday,
        is_market_open=is_market_open,
        is_after_close_learning_window=(
            is_weekday and local.time() >= config.after_close_learning_time
        ),
    )


def read_autonomous_learning_service_state(
    status_dir: Path | str = DEFAULT_LEARNING_STATUS_DIR,
) -> AutonomousLearningServiceState | None:
    path = Path(status_dir) / "latest-autonomous-service-state.json"
    if not path.exists():
        return None
    return AutonomousLearningServiceState.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def write_autonomous_learning_service_state(
    state: AutonomousLearningServiceState,
    status_dir: Path | str = DEFAULT_LEARNING_STATUS_DIR,
) -> Path:
    directory = Path(status_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "latest-autonomous-service-state.json"
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.no_env_file:
        _load_env_file(args.env_file)
    config = AutonomousLearningServiceConfig(
        start_date=date.fromisoformat(args.start),
        benchmark=args.benchmark,
        universes=_csv_tuple(args.universes),
        extra_symbols=_csv_tuple(args.extra_symbols),
        strategy_ids=_csv_tuple(args.strategies),
        feed=DataFeed(args.feed),
        root=Path(args.root),
        output_dir=Path(args.output_dir),
        status_dir=Path(args.status_dir),
        poll_seconds=args.poll_seconds,
        historical_interval_hours=args.historical_interval_hours,
        historical_cooldown_minutes=args.historical_cooldown_minutes,
        failed_retry_minutes=args.failed_retry_minutes,
        max_strategies_historical=args.max_strategies_historical,
        max_strategies_fresh=args.max_strategies_fresh,
        dynamic_historical_backlog=not args.no_dynamic_historical_backlog,
        dynamic_historical_backlog_size=args.dynamic_historical_backlog_size,
        leader_tuning_profile_count=args.leader_tuning_profile_count,
        fetch_missing_after_close=not args.no_fetch_missing_after_close,
        refresh_data_after_close=args.refresh_data_after_close,
        run_historical_on_start=not args.no_historical_on_start,
        repeat_historical_sweeps=args.repeat_historical_sweeps,
        tuning_mode=args.tuning_mode,
        promotion_min_observations=args.promotion_min_observations,
        promotion_min_distinct_days=args.promotion_min_distinct_days,
        promotion_min_span_days=args.promotion_min_span_days,
        champion_model_key=args.champion_model_key,
    )
    service = AutonomousLearningService(config=config)
    state = service.run_forever(max_loops=1 if args.once else args.max_loops)
    print(f"autonomous_service_status={state.service_status.value}")
    print(f"autonomous_service_heartbeat={state.heartbeat_at.isoformat()}")
    current_task = state.current_task.value if state.current_task else "none"
    print(f"autonomous_service_current_task={current_task}")
    print(f"autonomous_service_last_cycle={state.last_cycle_run_id or 'none'}")
    print(
        "autonomous_service_next_hypothesis="
        f"{state.next_historical_hypothesis_id or 'none'}"
    )
    print(f"autonomous_service_last_error={state.last_error or 'none'}")
    state_path = Path(config.status_dir) / "latest-autonomous-service-state.json"
    print(f"autonomous_service_state={state_path}")
    return 1 if state.service_status == AutonomousLearningServiceStatus.FAILED else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the autonomous self-feeding learning service."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-loops", type=int, default=None)
    parser.add_argument("--start", default="2016-01-04")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument(
        "--universes",
        default=",".join(DEFAULT_AUTONOMOUS_UNIVERSES),
    )
    parser.add_argument("--extra-symbols", default="")
    parser.add_argument(
        "--strategies",
        default=",".join(DEFAULT_AUTONOMOUS_STRATEGY_IDS),
    )
    parser.add_argument(
        "--feed",
        default=DataFeed.SIP.value,
        choices=[DataFeed.IEX.value, DataFeed.SIP.value],
    )
    parser.add_argument("--root", default=str(DEFAULT_BAR_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_RESEARCH_OUTPUT_DIR))
    parser.add_argument("--status-dir", default=str(DEFAULT_LEARNING_STATUS_DIR))
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--historical-interval-hours", type=int, default=0)
    parser.add_argument("--historical-cooldown-minutes", type=int, default=1)
    parser.add_argument("--failed-retry-minutes", type=int, default=60)
    parser.add_argument("--max-strategies-historical", type=int, default=36)
    parser.add_argument("--max-strategies-fresh", type=int, default=24)
    parser.add_argument("--no-dynamic-historical-backlog", action="store_true")
    parser.add_argument("--dynamic-historical-backlog-size", type=int, default=5000)
    parser.add_argument("--leader-tuning-profile-count", type=int, default=6)
    parser.add_argument("--no-fetch-missing-after-close", action="store_true")
    parser.add_argument("--refresh-data-after-close", action="store_true")
    parser.add_argument("--no-historical-on-start", action="store_true")
    parser.add_argument("--repeat-historical-sweeps", action="store_true")
    parser.add_argument("--tuning-mode", action="store_true")
    parser.add_argument("--promotion-min-observations", type=int, default=3)
    parser.add_argument("--promotion-min-distinct-days", type=int, default=2)
    parser.add_argument("--promotion-min-span-days", type=int, default=2)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-env-file", action="store_true")
    parser.add_argument(
        "--champion-model-key",
        default=("market_drawdown_circuit_breaker:top-semi-l126-any-dd12-risk0-cash"),
    )
    return parser


def _cycle_config(
    task: AutonomousLearningServiceTask,
    run_id: str,
    now: datetime,
    config: AutonomousLearningServiceConfig,
    *,
    hypothesis_profile: HistoricalHypothesisProfile | None = None,
) -> AutonomousLearningCycleConfig:
    window = market_learning_window(now, config)
    if task == AutonomousLearningServiceTask.FRESH_MARKET_DATA:
        return AutonomousLearningCycleConfig(
            mode=AutonomousLearningCycleMode.NIGHTLY,
            hypothesis_id="fresh-market-data-learning",
            run_id=run_id,
            start_date=config.start_date,
            end_date=window.trading_day,
            benchmark=config.benchmark,
            universes=config.universes,
            extra_symbols=config.extra_symbols,
            strategy_ids=config.strategy_ids,
            feed=config.feed,
            root=config.root,
            output_dir=config.output_dir,
            status_dir=config.status_dir,
            warmup_calendar_days=DEFAULT_WARMUP_CALENDAR_DAYS,
            warmup_trading_days=DEFAULT_WARMUP_TRADING_DAYS,
            max_strategies=config.max_strategies_fresh,
            fetch_missing=config.fetch_missing_after_close,
            refresh_data=config.refresh_data_after_close,
            champion_model_key=config.champion_model_key,
            tuning_mode=config.tuning_mode,
        )
    profile = hypothesis_profile or config.historical_hypotheses[0]
    return AutonomousLearningCycleConfig(
        mode=profile.mode,
        hypothesis_id=profile.profile_id,
        run_id=run_id,
        start_date=profile.start_date or config.start_date,
        end_date=None,
        benchmark=config.benchmark,
        universes=profile.universes,
        extra_symbols=config.extra_symbols,
        strategy_ids=profile.strategy_ids,
        feed=config.feed,
        root=config.root,
        output_dir=config.output_dir,
        status_dir=config.status_dir,
        warmup_calendar_days=DEFAULT_WARMUP_CALENDAR_DAYS,
        warmup_trading_days=DEFAULT_WARMUP_TRADING_DAYS,
        max_strategies=_historical_max_strategies(profile, config),
        fetch_missing=False,
        refresh_data=False,
        champion_model_key=config.champion_model_key,
        tuning_mode=config.tuning_mode or config.repeat_historical_sweeps,
    )


def _fresh_learning_due(
    *,
    state: AutonomousLearningServiceState,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> bool:
    window = market_learning_window(now, config)
    if not window.is_after_close_learning_window:
        return False
    if state.last_fresh_market_data_trading_day == window.trading_day:
        return False
    return _retry_allowed(
        state.last_fresh_market_data_attempt_at,
        now=now,
        config=config,
    )


def _historical_experiment_due(
    *,
    state: AutonomousLearningServiceState,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> bool:
    if _next_historical_hypothesis_profile(state, config, now=now) is None:
        return False
    if (
        config.run_historical_on_start
        and state.last_historical_experiment_attempt_at is None
    ):
        return True
    if state.last_historical_experiment_at is None:
        return _retry_allowed(
            state.last_historical_experiment_attempt_at,
            now=now,
            config=config,
        )
    pending_retry_at = _pending_historical_attempt_retry_at(state, config)
    if pending_retry_at is not None and now < pending_retry_at:
        return False
    return now >= _next_successful_historical_due_at(state, config)


def _retry_allowed(
    last_attempt_at: datetime | None,
    *,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> bool:
    if last_attempt_at is None:
        return True
    return now - last_attempt_at >= timedelta(minutes=config.failed_retry_minutes)


def _with_due_times(
    state: AutonomousLearningServiceState,
    *,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> AutonomousLearningServiceState:
    state = _with_historical_hypothesis_migration(state, config)
    generated_profile_count = len(_generated_historical_backlog_profiles(config))
    next_profile = _next_historical_hypothesis_profile(state, config, now=now)
    next_fingerprint = (
        _historical_fingerprint(next_profile, config, now=now)
        if next_profile is not None
        else None
    )
    return state.model_copy(
        update={
            "next_historical_experiment_due_at": _next_historical_due_at(
                state, now=now, config=config
            ),
            "next_fresh_market_data_due_at": _next_fresh_due_at(
                state, now=now, config=config
            ),
            "next_historical_hypothesis_id": (
                next_profile.profile_id if next_profile is not None else None
            ),
            "next_historical_fingerprint": next_fingerprint,
            "next_historical_lane": (
                _historical_profile_lane(next_profile)
                if next_profile is not None
                else None
            ),
            "dynamic_historical_backlog_enabled": config.dynamic_historical_backlog,
            "dynamic_historical_profile_count": generated_profile_count,
            "policy_summary": _policy_summary(config),
        }
    )


def _with_historical_hypothesis_migration(
    state: AutonomousLearningServiceState,
    config: AutonomousLearningServiceConfig,
) -> AutonomousLearningServiceState:
    if state.historical_hypothesis_counts or state.last_historical_hypothesis_id:
        return state
    if state.last_historical_experiment_at is None:
        return state
    first_profile = config.historical_hypotheses[0]
    fingerprint = _historical_fingerprint(
        first_profile,
        config,
        now=state.last_historical_experiment_at,
    )
    return state.model_copy(
        update={
            "last_historical_hypothesis_id": first_profile.profile_id,
            "last_historical_fingerprint": fingerprint,
            "historical_hypothesis_counts": {first_profile.profile_id: 1},
            "historical_fingerprint_counts": {fingerprint: 1},
        }
    )


def _next_historical_hypothesis_profile(
    state: AutonomousLearningServiceState,
    config: AutonomousLearningServiceConfig,
    *,
    now: datetime,
) -> HistoricalHypothesisProfile | None:
    profiles = _historical_profiles_for_state(state, config, now=now)
    for profile in profiles:
        if _profile_experiment_count(state, profile, config, now=now) == 0:
            return profile
    if not (config.repeat_historical_sweeps or config.tuning_mode):
        return None
    profile_count = len(profiles)
    completed_count = sum(
        state.historical_hypothesis_counts.get(profile.profile_id, 0)
        for profile in profiles
    )
    return profiles[completed_count % profile_count]


def _historical_profiles_for_state(
    state: AutonomousLearningServiceState,
    config: AutonomousLearningServiceConfig,
    *,
    now: datetime,
) -> tuple[HistoricalHypothesisProfile, ...]:
    base_profiles = tuple(config.historical_hypotheses)
    generated_profiles = _rank_generated_profiles(
        _generated_historical_backlog_profiles(config),
        state=state,
        config=config,
        now=now,
    )
    return _dedupe_profiles((*base_profiles, *generated_profiles))


def _generated_historical_backlog_profiles(
    config: AutonomousLearningServiceConfig,
) -> tuple[HistoricalHypothesisProfile, ...]:
    if (
        not config.dynamic_historical_backlog
        or config.dynamic_historical_backlog_size == 0
    ):
        return ()
    generated: list[HistoricalHypothesisProfile] = []
    generated.extend(_priority_tuning_profiles(config))
    generated.extend(_leader_tuning_profiles(config))
    generated.extend(_exploration_backlog_profiles(config))
    return _dedupe_profiles(tuple(generated))[: config.dynamic_historical_backlog_size]


def _priority_tuning_profiles(
    config: AutonomousLearningServiceConfig,
) -> tuple[HistoricalHypothesisProfile, ...]:
    profiles: list[HistoricalHypothesisProfile] = []
    for target in PRIORITY_TUNING_TARGETS:
        if target.universe_id not in DISCOVERY_UNIVERSES:
            continue
        target_hash = sha256(target.model_key.encode()).hexdigest()[:8]
        for cohort in GENERATED_START_COHORTS:
            for depth in _search_depths_for_max(target.max_strategies, config):
                profile_id = "-".join(
                    (
                        "priority-tune",
                        cohort.cohort_id,
                        depth.depth_id,
                        _slug(target.model_key),
                        target_hash,
                    )
                )
                profiles.append(
                    HistoricalHypothesisProfile(
                        profile_id=profile_id,
                        name=f"Priority tune {target.name}",
                        summary=(
                            f"{target.summary} Target model: "
                            f"`{target.model_key}`. Validation cohort: "
                            f"{cohort.name}. Search depth: {depth.name}."
                        ),
                        mode=AutonomousLearningCycleMode.WEEKLY,
                        universes=(target.universe_id,),
                        strategy_ids=target.strategy_ids,
                        max_strategies=depth.max_strategies,
                        start_date=cohort.start_date or config.start_date,
                    )
                )
    return tuple(profiles)


def _leader_tuning_profiles(
    config: AutonomousLearningServiceConfig,
) -> tuple[HistoricalHypothesisProfile, ...]:
    entries = _read_leaderboard_entries(config.status_dir)
    if not entries or config.leader_tuning_profile_count == 0:
        return ()
    profiles: list[HistoricalHypothesisProfile] = []
    cohorts = GENERATED_START_COHORTS[:6]
    for entry in entries[: config.leader_tuning_profile_count]:
        universe_id = str(entry.get("universe_id") or "")
        model_key = str(entry.get("model_key") or "")
        strategy_id = model_key.split(":", 1)[0]
        if universe_id not in DISCOVERY_UNIVERSES or not strategy_id:
            continue
        strategy_ids = _leader_tuning_strategy_ids(strategy_id)
        leader_hash = sha256(f"{universe_id}:{model_key}".encode()).hexdigest()[:8]
        for cohort in cohorts:
            for depth in _search_depths_for_max(
                _leader_tuning_max_strategies(strategy_id),
                config,
            ):
                profile_id = "-".join(
                    (
                        "auto-tune",
                        cohort.cohort_id,
                        depth.depth_id,
                        _slug(strategy_id),
                        _slug(universe_id),
                        leader_hash,
                    )
                )
                profiles.append(
                    HistoricalHypothesisProfile(
                        profile_id=profile_id,
                        name=f"Tune {strategy_id} leader in {universe_id}",
                        summary=(
                            f"Polish leaderboard candidate `{model_key}` in the "
                            f"{cohort.name.lower()} using adjacent strategy families "
                            f"with a {depth.name.lower()} and the same manual "
                            "promotion gates."
                        ),
                        mode=AutonomousLearningCycleMode.WEEKLY,
                        universes=(universe_id,),
                        strategy_ids=strategy_ids,
                        max_strategies=depth.max_strategies,
                        start_date=cohort.start_date,
                    ),
                )
    return tuple(profiles)


def _exploration_backlog_profiles(
    config: AutonomousLearningServiceConfig,
) -> tuple[HistoricalHypothesisProfile, ...]:
    profiles: list[HistoricalHypothesisProfile] = []
    for cohort in GENERATED_START_COHORTS:
        for universe_group in GENERATED_UNIVERSE_GROUPS:
            if not _universe_group_available(universe_group):
                continue
            for bundle in GENERATED_STRATEGY_BUNDLES:
                if not _bundle_compatible_with_universe(bundle, universe_group):
                    continue
                for depth in _search_depths_for_max(bundle.max_strategies, config):
                    profile_id = "-".join(
                        (
                            "auto-explore",
                            cohort.cohort_id,
                            depth.depth_id,
                            bundle.bundle_id,
                            universe_group.group_id,
                        )
                    )
                    profiles.append(
                        HistoricalHypothesisProfile(
                            profile_id=profile_id,
                            name=f"{bundle.name} - {universe_group.name}",
                            summary=(
                                f"{bundle.summary} Universe group: "
                                f"{universe_group.name}. Validation cohort: "
                                f"{cohort.name}. Search depth: {depth.name}."
                            ),
                            mode=AutonomousLearningCycleMode.WEEKLY,
                            universes=universe_group.universes,
                            strategy_ids=bundle.strategy_ids,
                            max_strategies=depth.max_strategies,
                            start_date=cohort.start_date or config.start_date,
                        )
                    )
    return tuple(profiles)


def _rank_generated_profiles(
    profiles: tuple[HistoricalHypothesisProfile, ...],
    *,
    state: AutonomousLearningServiceState,
    config: AutonomousLearningServiceConfig,
    now: datetime,
) -> tuple[HistoricalHypothesisProfile, ...]:
    if not profiles:
        return ()
    lane_counts = state.historical_lane_counts
    total_lane_runs = sum(lane_counts.values())

    def sort_key(profile: HistoricalHypothesisProfile) -> tuple[float, int, int, str]:
        lane = _historical_profile_lane(profile)
        target_share = _historical_lane_target_share(lane)
        current_share = (
            lane_counts.get(lane, 0) / total_lane_runs if total_lane_runs else 0.0
        )
        lane_deficit = target_share - current_share
        experiment_count = _profile_experiment_count(
            state,
            profile,
            config,
            now=now,
        )
        depth = profile.max_strategies
        return (lane_deficit, -experiment_count, -depth, profile.profile_id)

    return tuple(sorted(profiles, key=sort_key, reverse=True))


def _search_depths_for_max(
    max_strategies: int,
    config: AutonomousLearningServiceConfig,
) -> tuple[_GeneratedSearchDepth, ...]:
    cap = max_strategies
    if config.max_strategies_historical > 0:
        cap = min(cap, config.max_strategies_historical)
    depths = tuple(
        depth for depth in GENERATED_SEARCH_DEPTHS if depth.max_strategies <= cap
    )
    if depths:
        return depths
    return (
        _GeneratedSearchDepth(
            f"d{cap}",
            f"Top-{cap} catalog scan",
            max(cap, 1),
        ),
    )


def _historical_profile_lane(profile: HistoricalHypothesisProfile) -> str:
    profile_id = profile.profile_id
    if profile_id.startswith("priority-tune-"):
        return "priority_tuning"
    if profile_id.startswith("auto-tune-"):
        return "finalist_tuning"
    if (
        "semiconductor-polish" in profile_id
        or "drawdown-risk-controls" in profile_id
        or "risk-overlays" in profile_id
    ):
        return "finalist_tuning"
    if any(
        marker in profile_id
        for marker in (
            "late-cycle",
            "covid",
            "rate-reset",
            "ai-boom",
            "recent",
            "pre-covid",
            "reopening",
        )
    ):
        return "stress_validation"
    if profile_id in {
        "shadow-arena-finalists",
        "champion-breaker-sensitivity-expanded",
    }:
        return "finalist_tuning"
    return "new_exploration"


def _historical_lane_target_share(lane: str) -> float:
    if lane == "new_exploration":
        return 0.45
    if lane == "priority_tuning":
        return 0.25
    if lane == "finalist_tuning":
        return 0.10
    if lane == "stress_validation":
        return 0.15
    return 0.05


def _leader_tuning_strategy_ids(strategy_id: str) -> tuple[str, ...]:
    if strategy_id in {
        "market_drawdown_circuit_breaker",
        "risk_managed_semiconductor",
    }:
        return (
            "market_drawdown_circuit_breaker",
            "risk_managed_semiconductor",
            "volatility_aware_etf",
            "cash_rotation_model",
        )
    if strategy_id in {
        "monthly_sector_momentum",
        "benchmark_relative_strength_etf",
        "trend_following_etf",
        "volatility_aware_etf",
    }:
        return (
            "monthly_sector_momentum",
            "benchmark_relative_strength_etf",
            "trend_following_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
        )
    if strategy_id in {"defensive_regime_switch", "cash_rotation_model"}:
        return (
            "defensive_regime_switch",
            "cash_rotation_model",
            "trend_following_etf",
            "volatility_aware_etf",
        )
    if strategy_id == "mean_reversion_etf":
        return (
            "mean_reversion_etf",
            "trend_following_etf",
            "volatility_aware_etf",
            "cash_rotation_model",
        )
    return (strategy_id,)


def _leader_tuning_max_strategies(strategy_id: str) -> int:
    if strategy_id in {
        "market_drawdown_circuit_breaker",
        "risk_managed_semiconductor",
    }:
        return 72
    return 36


def _read_leaderboard_entries(status_dir: Path | str) -> tuple[dict[str, object], ...]:
    path = Path(status_dir) / "learning-leaderboard.json"
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ()
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return ()
    return tuple(entry for entry in entries if isinstance(entry, dict))


def _universe_group_available(group: _GeneratedUniverseGroup) -> bool:
    return all(universe_id in DISCOVERY_UNIVERSES for universe_id in group.universes)


def _bundle_compatible_with_universe(
    bundle: _GeneratedStrategyBundle,
    group: _GeneratedUniverseGroup,
) -> bool:
    if bundle.bundle_id == "semiconductor-polish":
        return any(
            universe == "semiconductor-champions" for universe in group.universes
        )
    if bundle.bundle_id == "drawdown-risk-controls":
        return any(
            universe
            in {"semiconductor-champions", "growth-industries", "liquid-risk-on"}
            for universe in group.universes
        )
    if bundle.bundle_id == "defensive-cash":
        return any(
            universe in {"sector-spdr", "macro-defensive", "broad-core"}
            for universe in group.universes
        )
    return True


def _dedupe_profiles(
    profiles: tuple[HistoricalHypothesisProfile, ...],
) -> tuple[HistoricalHypothesisProfile, ...]:
    seen: set[str] = set()
    deduped: list[HistoricalHypothesisProfile] = []
    for profile in profiles:
        if profile.profile_id in seen:
            continue
        seen.add(profile.profile_id)
        deduped.append(profile)
    return tuple(deduped)


def _slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "unknown"


def _profile_experiment_count(
    state: AutonomousLearningServiceState,
    profile: HistoricalHypothesisProfile,
    config: AutonomousLearningServiceConfig,
    *,
    now: datetime,
) -> int:
    fingerprint = _historical_fingerprint(profile, config, now=now)
    if fingerprint in state.historical_fingerprint_counts:
        return state.historical_fingerprint_counts[fingerprint]
    return state.historical_hypothesis_counts.get(profile.profile_id, 0)


def _historical_fingerprint(
    profile: HistoricalHypothesisProfile,
    config: AutonomousLearningServiceConfig,
    *,
    now: datetime | None = None,
) -> str:
    checked_at = _aware(now or datetime.now(tz=UTC))
    cycle_config = _cycle_config(
        AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT,
        "fingerprint",
        checked_at,
        config,
        hypothesis_profile=profile,
    )
    return research_experiment_fingerprint(
        cycle_config,
        end_date=_historical_research_end_date(checked_at),
    )


def _historical_research_end_date(now: datetime) -> date:
    candidate = _aware(now).date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _historical_max_strategies(
    profile: HistoricalHypothesisProfile,
    config: AutonomousLearningServiceConfig,
) -> int:
    if config.max_strategies_historical == 0:
        return profile.max_strategies
    if profile.max_strategies == 0:
        return config.max_strategies_historical
    return min(profile.max_strategies, config.max_strategies_historical)


def _next_historical_due_at(
    state: AutonomousLearningServiceState,
    *,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> datetime | None:
    if _next_historical_hypothesis_profile(state, config, now=now) is None:
        return None
    if (
        config.run_historical_on_start
        and state.last_historical_experiment_attempt_at is None
    ):
        return now
    if state.last_historical_experiment_at is None:
        if state.last_historical_experiment_attempt_at is None:
            return now
        return state.last_historical_experiment_attempt_at + timedelta(
            minutes=config.failed_retry_minutes
        )
    due_at = _next_successful_historical_due_at(state, config)
    if (
        state.last_historical_experiment_attempt_at is not None
        and state.last_historical_experiment_attempt_at
        > state.last_historical_experiment_at
    ):
        retry_at = _pending_historical_attempt_retry_at(state, config)
        if retry_at is None:
            return due_at
        return max(due_at, retry_at)
    return due_at


def _pending_historical_attempt_retry_at(
    state: AutonomousLearningServiceState,
    config: AutonomousLearningServiceConfig,
) -> datetime | None:
    if (
        state.last_historical_experiment_at is None
        or state.last_historical_experiment_attempt_at is None
        or state.last_historical_experiment_attempt_at
        <= state.last_historical_experiment_at
    ):
        return None
    retry_minutes = (
        config.failed_retry_minutes
        if state.last_error
        else config.historical_cooldown_minutes
    )
    return state.last_historical_experiment_attempt_at + timedelta(
        minutes=retry_minutes
    )


def _next_successful_historical_due_at(
    state: AutonomousLearningServiceState,
    config: AutonomousLearningServiceConfig,
) -> datetime:
    if state.last_historical_experiment_at is None:
        raise ValueError("last_historical_experiment_at is required")
    return state.last_historical_experiment_at + timedelta(
        hours=config.historical_interval_hours,
        minutes=config.historical_cooldown_minutes,
    )


def _next_fresh_due_at(
    state: AutonomousLearningServiceState,
    *,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> datetime:
    tz = ZoneInfo(config.market_timezone)
    local = now.astimezone(tz)
    current_day = local.date()
    completed_current_market_day = (
        state.last_fresh_market_data_trading_day == current_day
    )
    candidate = datetime.combine(
        current_day,
        config.after_close_learning_time,
        tzinfo=tz,
    )
    if (
        completed_current_market_day
        or not _is_weekday(current_day)
        or local >= candidate
    ):
        current_day = _next_weekday(current_day)
        candidate = datetime.combine(
            current_day,
            config.after_close_learning_time,
            tzinfo=tz,
        )
    if state.last_fresh_market_data_attempt_at is not None:
        retry_at = state.last_fresh_market_data_attempt_at + timedelta(
            minutes=config.failed_retry_minutes
        )
        if retry_at > now and not completed_current_market_day:
            return retry_at
    return candidate.astimezone(UTC)


def _promotion_observation(
    run: AutonomousLearningCycleRun,
    *,
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> AutonomousLearningPromotionObservation | None:
    model_key = run.recommended_challenger_model_key
    if model_key is None:
        return None
    candidate = _candidate_by_key(run.top_candidates, model_key)
    if candidate is None:
        return None
    return AutonomousLearningPromotionObservation(
        observed_at=now,
        trading_day=market_learning_window(now, config).trading_day,
        run_id=run.run_id,
        candidate_model_key=model_key,
        full_delta=candidate.full_delta,
        stress_delta=candidate.stress_delta,
        min_fold_delta=candidate.min_fold_delta,
        worst_drawdown=candidate.worst_drawdown,
        gate_status=candidate.gate_status,
        candidate_status=candidate.status,
        manual_approval_required=run.manual_approval_required,
        active_model_unchanged=run.active_model_unchanged,
    )


def _promotion_gate(
    observations: tuple[AutonomousLearningPromotionObservation, ...],
    *,
    config: AutonomousLearningServiceConfig,
) -> AutonomousLearningPromotionGate:
    if not observations:
        return AutonomousLearningPromotionGate(
            status=AutonomousLearningPromotionStatus.WAITING,
            observation_count=0,
            distinct_observation_dates=0,
            summary=(
                "No gate-qualified challenger has repeated enough times for "
                "manual promotion review."
            ),
        )
    latest_key = observations[-1].candidate_model_key
    candidate_observations = tuple(
        observation
        for observation in observations
        if observation.candidate_model_key == latest_key
    )
    dates = {observation.trading_day for observation in candidate_observations}
    first = candidate_observations[0]
    last = candidate_observations[-1]
    span_days = (last.trading_day - first.trading_day).days
    evidence_ok = (
        len(candidate_observations) >= config.promotion_min_observations
        and len(dates) >= config.promotion_min_distinct_days
        and span_days >= config.promotion_min_span_days
        and all(
            observation.manual_approval_required and observation.active_model_unchanged
            for observation in candidate_observations
        )
    )
    if evidence_ok:
        status = AutonomousLearningPromotionStatus.READY_FOR_MANUAL_REVIEW
        summary = (
            f"{latest_key} has repeated across {len(dates)} day(s) and "
            f"{len(candidate_observations)} observation(s). Manual review is "
            "eligible, but authority still cannot change automatically."
        )
    else:
        status = AutonomousLearningPromotionStatus.WAITING
        summary = (
            f"{latest_key} has {len(candidate_observations)} observation(s) "
            f"across {len(dates)} day(s); promotion review waits for repeated "
            "cross-day evidence."
        )
    return AutonomousLearningPromotionGate(
        status=status,
        candidate_model_key=latest_key,
        observation_count=len(candidate_observations),
        distinct_observation_dates=len(dates),
        first_seen_at=first.observed_at,
        last_seen_at=last.observed_at,
        evidence_run_ids=tuple(
            observation.run_id for observation in candidate_observations[-10:]
        ),
        summary=summary,
    )


def _append_promotion_observation(
    status_dir: Path,
    observation: AutonomousLearningPromotionObservation,
    *,
    existing: tuple[AutonomousLearningPromotionObservation, ...],
) -> tuple[AutonomousLearningPromotionObservation, ...]:
    if any(item.run_id == observation.run_id for item in existing):
        return existing
    directory = Path(status_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "promotion-observations.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(observation.model_dump_json())
        handle.write("\n")
    return (*existing, observation)


def _load_promotion_observations(
    status_dir: Path | str,
) -> tuple[AutonomousLearningPromotionObservation, ...]:
    path = Path(status_dir) / "promotion-observations.jsonl"
    if not path.exists():
        return ()
    observations = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            observations.append(
                AutonomousLearningPromotionObservation.model_validate_json(line)
            )
    return tuple(observations)


def _initial_state(
    now: datetime,
    config: AutonomousLearningServiceConfig,
) -> AutonomousLearningServiceState:
    checked_at = _aware(now)
    return _with_due_times(
        AutonomousLearningServiceState(
            generated_at=checked_at,
            heartbeat_at=checked_at,
            service_status=AutonomousLearningServiceStatus.IDLE,
            policy_summary=_policy_summary(config),
            promotion_gate=_promotion_gate((), config=config),
        ),
        now=checked_at,
        config=config,
    )


def _candidate_by_key(
    candidates: tuple[AutonomousLearningCandidate, ...], model_key: str
) -> AutonomousLearningCandidate | None:
    for candidate in candidates:
        if candidate.model_key == model_key:
            return candidate
    return None


def _run_id(
    task: AutonomousLearningServiceTask,
    now: datetime,
    *,
    hypothesis_profile: HistoricalHypothesisProfile | None = None,
) -> str:
    if task == AutonomousLearningServiceTask.FRESH_MARKET_DATA:
        label = "after-close"
    elif hypothesis_profile is not None:
        label = f"historical-{hypothesis_profile.profile_id}"
    else:
        label = "historical"
    return f"learning-cycle-{label}-{now:%Y%m%dT%H%M%SZ}"


def _policy_summary(config: AutonomousLearningServiceConfig) -> str:
    profile_ids = ", ".join(
        profile.profile_id for profile in config.historical_hypotheses
    )
    generated_count = len(_generated_historical_backlog_profiles(config))
    backlog_text = (
        f" plus up to {generated_count} generated exploration/tuning profiles"
        if config.dynamic_historical_backlog
        else ""
    )
    sweep_policy = (
        "repeat completed sweeps in explicit tuning mode"
        if config.repeat_historical_sweeps or config.tuning_mode
        else "advance to the next unseen fingerprint"
    )
    return (
        "Historical experiments run as a fingerprinted novelty queue with a "
        f"{config.historical_cooldown_minutes} minute cooldown"
        f"{_legacy_interval_suffix(config)} and {sweep_policy}; queued "
        "profiles: "
        f"{len(config.historical_hypotheses)} base hypothesis families"
        f"{backlog_text} "
        f"({profile_ids}); lane targets are 45% new exploration, 25% priority "
        "tuning, 10% other finalist tuning, 15% stress validation, and 5% "
        "runtime health; fresh "
        "market-data learning runs after "
        f"{config.after_close_learning_time.isoformat()} "
        f"{config.market_timezone}; promotion remains manual and requires "
        "repeated cross-day evidence."
    )


def _legacy_interval_suffix(config: AutonomousLearningServiceConfig) -> str:
    if config.historical_interval_hours == 0:
        return ""
    return f" plus {config.historical_interval_hours} hour coarse interval"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _is_weekday(value: date) -> bool:
    return value.weekday() < 5


def _next_weekday(value: date) -> date:
    candidate = value + timedelta(days=1)
    while not _is_weekday(candidate):
        candidate += timedelta(days=1)
    return candidate


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


class _ServiceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "autonomous learning service is already running"
            ) from error
        self._handle.write(f"pid={os.getpid()}\n")
        self._handle.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


if __name__ == "__main__":
    raise SystemExit(main())
