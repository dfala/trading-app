"""Always-on Alpaca paper runtime."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from enum import StrEnum
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

from trading_app.broker import AlpacaPaperBrokerAdapter
from trading_app.dashboard.models import (
    DashboardMetric,
    DashboardModelCard,
    DashboardModelEvidence,
)
from trading_app.learning.autonomous import (
    AutonomousLearningCycleRun,
    AutonomousLearningLeaderboard,
    AutonomousLearningLeaderboardEntry,
)
from trading_app.live import (
    EnvironmentMode,
    LiveReadinessGate,
    LiveRiskLimits,
    LiveTradingConfig,
)
from trading_app.market_data import (
    AlpacaHistoricalBarFetcher,
    AlpacaLatestPriceFetcher,
    HistoricalBarFetcher,
    LatestPriceFetcher,
    LatestPriceSnapshot,
    MarketDataQualityChecker,
)
from trading_app.paper import PaperTradingService
from trading_app.reporting import DailyReportGenerator, write_markdown_report
from trading_app.research.run_replay_discovery import DISCOVERY_UNIVERSES
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime.health import RuntimeHealthEngine
from trading_app.runtime.live_sandbox import (
    LiveSandboxControlAction,
    LiveSandboxControlRequest,
    LiveSandboxRuntime,
)
from trading_app.runtime.models import (
    OperatorControlAction,
    OperatorControlRequest,
    OperatorControlResult,
    RuntimeCycleResult,
    RuntimeEvent,
    RuntimeEventSeverity,
    RuntimeSnapshot,
    RuntimeStatus,
    ShadowChallengerObservation,
    ShadowOrderIntent,
)
from trading_app.runtime.operator import RuntimeAlertEngine, RuntimeControlCenter
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import (
    DataFeed,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioSnapshot,
    Position,
)
from trading_app.strategies.benchmark_relative import (
    BenchmarkRelativeStrengthETFStrategy,
)
from trading_app.strategies.cash_rotation import CashRotationETFStrategy
from trading_app.strategies.catalog import (
    StrategyAuthority,
    strategy_definition_metadata,
)
from trading_app.strategies.market_drawdown_circuit_breaker import (
    MarketDrawdownCircuitBreakerStrategy,
)
from trading_app.strategies.risk_managed_semiconductor import (
    RiskManagedSemiconductorStrategy,
)
from trading_app.strategies.sector_momentum import (
    DEFAULT_SECTOR_ETFS,
    MonthlySectorMomentumStrategy,
)

MARKET_TZ = ZoneInfo("America/New_York")
QUANTITY_INCREMENT = Decimal("0.000001")
DEFAULT_PAPER_MODEL_KEY = "monthly_sector_momentum:1.0.0"
PROMOTED_MARKET_DRAWDOWN_CIRCUIT_BREAKER_KEY = (
    "market_drawdown_circuit_breaker:top-semi-l126-qqq-dd10-risk025-cash"
)
SHADOW_MARKET_DRAWDOWN_CIRCUIT_BREAKER_KEY = (
    "market_drawdown_circuit_breaker:top-semi-l126-qqq-dd10-risk0-cash"
)
RESEARCH_BENCHMARK_RELATIVE_STRENGTH_KEY = (
    "benchmark_relative_strength_etf:grid-l126-t63-n1"
)
RESEARCH_CASH_ROTATION_KEY = "cash_rotation_model:grid-l63-n1-b040"
RESEARCH_MARKET_DRAWDOWN_RISK025_KEY = (
    "market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk025-cash"
)
RESEARCH_RISK_MANAGED_SEMICONDUCTOR_KEY = (
    "risk_managed_semiconductor:vol-smh-v63-t020-off-cash"
)
RESEARCH_SEMICONDUCTOR_CHAMPIONS_UNIVERSE = ("QQQ", "XLK", "SMH", "SOXX")
PROMOTED_MACRO_DEFENSIVE_BENCHMARK_RELATIVE_KEY = (
    "benchmark_relative_strength_etf:grid-l252-t21-n2"
)
PROMOTED_MACRO_DEFENSIVE_UNIVERSE_ID = "macro-defensive"
PAPER_SEMICONDUCTOR_SYMBOLS = ("SOXX", "SMH")
DEFAULT_MAX_PAPER_SYMBOL_ALLOCATION = Decimal("0.35")
DEFAULT_MAX_PAPER_SEMICONDUCTOR_ALLOCATION = Decimal("0.50")
DEFAULT_INITIAL_PAPER_DEPLOYMENT_ALLOCATION = Decimal("0.25")
DEFAULT_AUTO_LEADERBOARD_SHADOW_COUNT = 3

_MARKET_DRAWDOWN_MODEL_RE = re.compile(
    r"^market_drawdown_circuit_breaker:"
    r"top-semi-l(?P<lookback>\d+)-(?P<trigger>any|qqq)-"
    r"dd(?P<drawdown>\d+)-risk(?P<risk>\d+)-cash$"
)
_BENCHMARK_RELATIVE_MODEL_RE = re.compile(
    r"^benchmark_relative_strength_etf:"
    r"grid-l(?P<lookback>\d+)-t(?P<tracking>\d+)-n(?P<top_n>\d+)$"
)
_CASH_ROTATION_MODEL_RE = re.compile(
    r"^cash_rotation_model:"
    r"grid-l(?P<lookback>\d+)-n(?P<top_n>\d+)-b(?P<breadth>\d+)$"
)
_RISK_MANAGED_SEMICONDUCTOR_MODEL_RE = re.compile(
    r"^risk_managed_semiconductor:"
    r"vol-(?P<sleeve>smh|soxx)-v(?P<volatility>\d+)-t(?P<target>\d+)-off-cash$"
)


class StrategySchedule(StrEnum):
    DAILY_CLOSE = "daily_close"
    MARKET_OPEN = "market_open"


@dataclass(frozen=True)
class _FullComparisonIndex:
    rows_by_model: dict[str, tuple[tuple[dict[str, object], Path], ...]]
    rows_by_path_and_model: dict[tuple[Path, str], dict[str, object]]


@dataclass(frozen=True)
class AlwaysOnPaperRuntimeConfig:
    symbols: tuple[str, ...] = (*DEFAULT_SECTOR_ETFS, "SPY")
    starting_cash: Decimal = Decimal("100000")
    managed_capital: Decimal | None = None
    paper_epoch_started_at: datetime | None = None
    feed: DataFeed = DataFeed.IEX
    output_dir: Path = Path("data/runtime")
    active_model_key: str = DEFAULT_PAPER_MODEL_KEY
    active_model_universe_id: str | None = None
    shadow_challenger_model_key: str | None = None
    shadow_challenger_model_keys: tuple[str, ...] = ()
    auto_shadow_leaderboard_candidates: bool = True
    leaderboard_shadow_candidate_count: int = DEFAULT_AUTO_LEADERBOARD_SHADOW_COUNT
    strategy_schedule: StrategySchedule = StrategySchedule.DAILY_CLOSE
    latest_price_max_age: timedelta = timedelta(minutes=15)
    market_poll_interval_seconds: int = 60
    off_hours_poll_interval_seconds: int = 900
    market_open_time: dt_time = dt_time(hour=9, minute=30)
    trade_after_close_time: dt_time = dt_time(hour=16, minute=5)
    nightly_learning_time: dt_time = dt_time(hour=20)
    strategy_cash_buffer: Decimal = Decimal("0.01")
    max_paper_symbol_allocation: Decimal | None = DEFAULT_MAX_PAPER_SYMBOL_ALLOCATION
    max_paper_semiconductor_allocation: Decimal | None = (
        DEFAULT_MAX_PAPER_SEMICONDUCTOR_ALLOCATION
    )
    initial_paper_deployment_allocation: Decimal | None = (
        DEFAULT_INITIAL_PAPER_DEPLOYMENT_ALLOCATION
    )


class AlwaysOnPaperRuntime:
    """Coordinate Alpaca paper monitoring, trading, reports, and learning."""

    def __init__(
        self,
        *,
        service: PaperTradingService,
        latest_price_fetcher: LatestPriceFetcher,
        historical_bar_fetcher: HistoricalBarFetcher,
        strategy: object | None = None,
        risk_engine: RiskEngine | None = None,
        config: AlwaysOnPaperRuntimeConfig | None = None,
        persistence_store: RuntimePersistenceStore | None = None,
        control_center: RuntimeControlCenter | None = None,
        alert_engine: RuntimeAlertEngine | None = None,
        health_engine: RuntimeHealthEngine | None = None,
        live_sandbox: LiveSandboxRuntime | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or AlwaysOnPaperRuntimeConfig()
        self.persistence_store = persistence_store or RuntimePersistenceStore(
            self.config.output_dir
        )
        self.service = service
        self.latest_price_fetcher = latest_price_fetcher
        self.historical_bar_fetcher = historical_bar_fetcher
        self.strategy = strategy or build_paper_strategy(
            self.config.active_model_key,
            universe_id=self.config.active_model_universe_id,
        )
        self.shadow_challenger_model_keys = (
            self._resolved_shadow_challenger_model_keys()
        )
        self.shadow_challenger_strategies = tuple(
            (model_key, build_paper_strategy(model_key))
            for model_key in self.shadow_challenger_model_keys
        )
        self.shadow_challenger_strategy = (
            self.shadow_challenger_strategies[0][1]
            if self.shadow_challenger_strategies
            else None
        )
        self.risk_engine = risk_engine or service.risk_engine
        self.control_center = control_center or RuntimeControlCenter()
        self.alert_engine = alert_engine or RuntimeAlertEngine()
        self.health_engine = health_engine or RuntimeHealthEngine()
        self.live_sandbox = live_sandbox or LiveSandboxRuntime.disabled()
        self._external_control_center = control_center is not None
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self.sleeper = sleeper or time.sleep
        self._events: list[RuntimeEvent] = []
        self._alerts = ()
        self._health_report = None
        self._last_cycle: RuntimeCycleResult | None = None
        self._last_control_result: OperatorControlResult | None = (
            self.control_center.last_result
        )
        self._last_prices: LatestPriceSnapshot | None = None
        self._last_paper_report = None
        self._last_report = None
        self._last_report_path: Path | None = None
        self._last_learning_run = None
        self._last_shadow_challenger_observation: ShadowChallengerObservation | None = (
            None
        )
        self._last_shadow_challenger_observations: dict[
            str,
            ShadowChallengerObservation,
        ] = {}
        self._last_trade_date: date | None = None
        self._last_shadow_challenger_date: date | None = None
        self._last_shadow_challenger_dates: dict[str, date] = {}
        self._last_rebalance_month: tuple[int, int] | None = None
        self._last_report_date: date | None = None
        self._last_learning_date: date | None = None
        self._dashboard_snapshot_cache: tuple[float, object] | None = None
        self._dashboard_snapshot_cache_lock = RLock()
        self._full_comparison_index_cache: tuple[float, _FullComparisonIndex] | None = (
            None
        )
        self._full_comparison_index_lock = RLock()
        self._restore_from_persistence()

    def _resolved_shadow_challenger_model_keys(self) -> tuple[str, ...]:
        configured = _configured_shadow_challenger_model_keys(self.config)
        if not self.config.auto_shadow_leaderboard_candidates:
            return configured
        leaderboard = self.persistence_store.read_autonomous_learning_leaderboard()
        if leaderboard is None:
            return configured
        automatic = leaderboard_shadow_challenger_model_keys(
            leaderboard,
            active_model_key=self.config.active_model_key,
            limit=self.config.leaderboard_shadow_candidate_count,
            excluded_model_keys=configured,
        )
        return _dedupe_model_keys(*configured, *automatic)

    @classmethod
    def from_alpaca_env(
        cls,
        *,
        config: AlwaysOnPaperRuntimeConfig | None = None,
        risk_engine: RiskEngine | None = None,
    ) -> AlwaysOnPaperRuntime:
        resolved_config = config or AlwaysOnPaperRuntimeConfig()
        broker = AlpacaPaperBrokerAdapter()
        active_risk = risk_engine or RiskEngine(
            RiskConfig(
                enforce_market_hours=False,
                us_tradable_universe=frozenset(resolved_config.symbols),
                tradable_symbols=frozenset(resolved_config.symbols),
                max_symbol_allocation=resolved_config.max_paper_symbol_allocation,
                max_sector_allocation=(
                    resolved_config.max_paper_semiconductor_allocation
                ),
                symbol_to_sector={
                    symbol: _paper_symbol_sector(symbol)
                    for symbol in resolved_config.symbols
                },
            )
        )
        service = PaperTradingService(
            broker=broker,
            starting_cash=resolved_config.starting_cash,
            risk_engine=active_risk,
        )
        return cls(
            service=service,
            latest_price_fetcher=AlpacaLatestPriceFetcher(),
            historical_bar_fetcher=AlpacaHistoricalBarFetcher(),
            risk_engine=active_risk,
            config=resolved_config,
            persistence_store=RuntimePersistenceStore(resolved_config.output_dir),
            live_sandbox=LiveSandboxRuntime.from_env(),
        )

    def run_forever(self, *, max_cycles: int | None = None) -> None:
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            as_of = self.clock()
            self.run_once(as_of=as_of)
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            self.sleeper(self._sleep_seconds(as_of))

    def run_once(self, *, as_of: datetime | None = None) -> RuntimeCycleResult:
        now = as_of or self.clock()
        events: list[RuntimeEvent] = []
        prices_refreshed = False
        broker_synced = False
        strategy_evaluated = False
        shadow_challenger_observed = False
        orders_submitted = 0
        fills_applied = 0
        report_written = False
        nightly_learning_ran = False

        try:
            self._last_prices = self.latest_price_fetcher.fetch_latest_prices(
                tuple(self.config.symbols),
                as_of=now,
                feed=self.config.feed,
                max_age=self.config.latest_price_max_age,
            )
            prices_refreshed = True
            self.persistence_store.persist_latest_prices(self._last_prices)
            if not self._last_prices.all_fresh:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.WARNING,
                        "market_data",
                        "Latest prices are missing or stale; paper orders are blocked.",
                        self._last_prices.missing_symbols,
                    )
                )
        except Exception as error:
            self._last_prices = None
            events.append(
                self._event(
                    now,
                    RuntimeEventSeverity.ERROR,
                    "market_data",
                    str(error),
                )
            )

        try:
            fills_applied = self._sync_broker_orders(as_of=now)
            broker_synced = True
        except Exception as error:
            events.append(
                self._event(
                    now,
                    RuntimeEventSeverity.ERROR,
                    "broker_sync",
                    str(error),
                )
            )

        paper_report = self._portfolio_report(now, events=events)
        self.persistence_store.persist_reconciliation(paper_report.reconciliation)

        try:
            live_cycle = self.live_sandbox.run_once(
                as_of=now,
                latest_prices=self._last_prices,
                historical_bar_fetcher=self.historical_bar_fetcher,
            )
            self.persistence_store.persist_live_sandbox_cycle(live_cycle)
            self.persistence_store.persist_live_sandbox_service_state(
                self.live_sandbox.service
            )
        except Exception as error:
            events.append(
                self._event(
                    now,
                    RuntimeEventSeverity.ERROR,
                    "live_sandbox",
                    f"Live sandbox cycle failed: {error}",
                )
            )
        if not paper_report.reconciliation.reconciled:
            events.append(
                self._event(
                    now,
                    RuntimeEventSeverity.WARNING,
                    "reconciliation",
                    "Broker reconciliation is not clean; new paper orders are blocked.",
                )
            )

        repair_reason = self._paper_rebalance_repair_reason(
            now,
            paper_report=paper_report,
        )
        if self._should_evaluate_strategy(now) or repair_reason:
            if repair_reason == "rollout_limits":
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.INFO,
                        "paper_rollout_limits",
                        (
                            "Paper portfolio exceeds rollout concentration "
                            "limits; evaluating a de-risking rebalance."
                        ),
                    )
                )
            elif repair_reason == "managed_capital_deployment_gap":
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.INFO,
                        "managed_capital",
                        (
                            "Paper portfolio is materially below the managed "
                            "capital target; evaluating a rebalance."
                        ),
                    )
                )
            if not prices_refreshed:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.ERROR,
                        "strategy",
                        (
                            "Scheduled paper strategy evaluation was skipped because "
                            "latest prices did not refresh in the current cycle."
                        ),
                    )
                )
            elif not broker_synced:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.ERROR,
                        "strategy",
                        (
                            "Scheduled paper strategy evaluation was skipped because "
                            "broker state did not sync in the current cycle."
                        ),
                    )
                )
            elif self.control_center.state.paused:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.INFO,
                        "operator_control",
                        (
                            "Runtime is paused; scheduled paper strategy evaluation "
                            "was skipped."
                        ),
                    )
                )
            elif self.control_center.state.paper_kill_switch_enabled:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.WARNING,
                        "operator_control",
                        (
                            "Paper kill switch is enabled; scheduled paper orders "
                            "are blocked."
                        ),
                    )
                )
            else:
                strategy_evaluated = True
                try:
                    had_execution_inputs = (
                        self._last_prices is not None
                        and self._last_prices.all_fresh
                        and paper_report.reconciliation.reconciled
                    )
                    submitted = self._evaluate_strategy(now, paper_report, events)
                    orders_submitted = submitted
                    if had_execution_inputs:
                        self._last_trade_date = now.astimezone(MARKET_TZ).date()
                except Exception as error:
                    events.append(
                        self._event(
                            now,
                            RuntimeEventSeverity.ERROR,
                            "strategy",
                            f"Scheduled paper strategy evaluation failed: {error}",
                        )
                    )

        due_shadow_challengers = self._due_shadow_challengers(now)
        if due_shadow_challengers:
            if self._last_prices is None or not self._last_prices.all_fresh:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.WARNING,
                        "shadow_challenger",
                        (
                            "Shadow challenger observation was skipped because "
                            "latest prices are missing or stale."
                        ),
                    )
                )
            else:
                for model_key, strategy in due_shadow_challengers:
                    try:
                        observation = self._evaluate_shadow_challenger(
                            now,
                            events,
                            model_key=model_key,
                            strategy=strategy,
                        )
                        if observation is not None:
                            self._last_shadow_challenger_observations[model_key] = (
                                observation
                            )
                            self._last_shadow_challenger_observation = (
                                self._primary_shadow_challenger_observation()
                            )
                            self.persistence_store.persist_shadow_challenger_observation(
                                observation
                            )
                            self._last_shadow_challenger_dates[model_key] = (
                                now.astimezone(MARKET_TZ).date()
                            )
                            self._last_shadow_challenger_date = (
                                self._primary_shadow_challenger_date()
                            )
                            shadow_challenger_observed = True
                    except Exception as error:
                        events.append(
                            self._event(
                                now,
                                RuntimeEventSeverity.ERROR,
                                "shadow_challenger",
                                (
                                    "Shadow challenger observation failed for "
                                    f"{model_key}: {error}"
                                ),
                                (model_key,),
                            )
                        )
                if shadow_challenger_observed:
                    self.persistence_store.persist_shadow_challenger_observations(
                        self._ordered_shadow_challenger_observations()
                    )

        # Mark every known shadow challenger to market each cycle so the
        # journal accumulates a dense equity time series. This is a no-op on
        # decision ticks (skipped via prior.as_of == as_of) and when prices
        # are stale.
        self._refresh_shadow_challenger_equity(now)

        if self._should_write_daily_report(now):
            try:
                self._write_daily_report(now)
                report_written = True
            except Exception as error:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.ERROR,
                        "daily_report",
                        str(error),
                    )
                )

        if self._should_run_nightly_learning(now):
            try:
                self._last_learning_run = self._run_nightly_learning(now)
                self.persistence_store.persist_learning_run(self._last_learning_run)
                self._last_learning_date = now.astimezone(MARKET_TZ).date()
                nightly_learning_ran = True
            except Exception as error:
                events.append(
                    self._event(
                        now,
                        RuntimeEventSeverity.ERROR,
                        "nightly_learning",
                        str(error),
                    )
                )

        status = self._status(events)
        cycle = RuntimeCycleResult(
            as_of=now,
            status=status,
            prices_refreshed=prices_refreshed,
            broker_synced=broker_synced,
            strategy_evaluated=strategy_evaluated,
            shadow_challenger_observed=shadow_challenger_observed,
            orders_submitted=orders_submitted,
            fills_applied=fills_applied,
            report_written=report_written,
            nightly_learning_ran=nightly_learning_ran,
            events=tuple(events),
        )
        self._events.extend(events)
        self._last_cycle = cycle
        self._alerts = self.alert_engine.evaluate(
            self.snapshot(as_of=now),
            control_state=self.control_center.state,
        )
        cycle = cycle.model_copy(update={"alerts": self._alerts})
        self._last_cycle = cycle
        self._health_report = self.health_engine.evaluate(self.snapshot(as_of=now))
        self.persistence_store.persist_cycle(cycle)
        self.persistence_store.persist_events(tuple(events))
        self.persistence_store.persist_alerts(self._alerts)
        self.persistence_store.persist_health_report(self._health_report)
        self.persistence_store.persist_control_state(self.control_center.state)
        self.persistence_store.persist_service_state(self.service)
        runtime_snapshot = self.snapshot(as_of=now)
        self.persistence_store.persist_runtime_snapshot(runtime_snapshot)
        self.persistence_store.persist_live_sandbox_snapshot(
            runtime_snapshot.live_sandbox
        )
        self.persistence_store.persist_dashboard_snapshot(
            self.dashboard_snapshot(as_of=now)
        )
        self._invalidate_dashboard_snapshot_cache()
        return cycle

    def apply_control(
        self,
        request: OperatorControlRequest | OperatorControlAction | str,
        *,
        requested_by: str = "local-operator",
        reason: str = "",
        requested_at: datetime | None = None,
    ) -> OperatorControlResult:
        """Apply a local operator control action to the paper runtime."""

        if not isinstance(request, OperatorControlRequest):
            request = OperatorControlRequest(
                action=OperatorControlAction(request),
                requested_at=requested_at or self.clock(),
                requested_by=requested_by,
                reason=reason,
            )
        result = self.control_center.apply(request)
        self._last_control_result = result

        if request.action == OperatorControlAction.FORCE_RECONCILIATION:
            paper_report = self._portfolio_report(request.requested_at)
            self.persistence_store.persist_reconciliation(paper_report.reconciliation)
        elif request.action == OperatorControlAction.GENERATE_REPORT:
            self._write_daily_report(request.requested_at)

        event = self._event(
            request.requested_at,
            RuntimeEventSeverity.INFO,
            "operator_control",
            result.message,
            (request.action.value,),
        )
        self._events.append(event)
        self.persistence_store.persist_control_result(result)
        self.persistence_store.persist_events((event,))
        self._alerts = self.alert_engine.evaluate(
            self.snapshot(as_of=request.requested_at),
            control_state=self.control_center.state,
        )
        self.persistence_store.persist_alerts(self._alerts)
        self._health_report = self.health_engine.evaluate(
            self.snapshot(as_of=request.requested_at)
        )
        self.persistence_store.persist_health_report(self._health_report)
        self._invalidate_dashboard_snapshot_cache()
        return result

    def apply_live_sandbox_control(
        self,
        request: LiveSandboxControlRequest | LiveSandboxControlAction | str,
        *,
        requested_by: str = "local-operator",
        reason: str = "",
        requested_at: datetime | None = None,
    ):
        """Apply a local operator control action to the live sandbox."""

        result = self.live_sandbox.apply_control(
            request,
            requested_by=requested_by,
            reason=reason,
            requested_at=requested_at,
        )
        self.persistence_store.persist_live_sandbox_control_result(result)
        self.persistence_store.persist_live_sandbox_service_state(
            self.live_sandbox.service
        )
        self.persistence_store.persist_live_sandbox_snapshot(
            self.live_sandbox.snapshot(
                as_of=result.request.requested_at,
                latest_prices=self._last_prices,
            )
        )
        self._invalidate_dashboard_snapshot_cache()
        return result

    def health_report(self, *, as_of: datetime | None = None):
        """Return the latest runtime health report."""

        now = as_of or self.clock()
        if self._health_report is None or self._health_report.as_of != now:
            self._health_report = self.health_engine.evaluate(self.snapshot(as_of=now))
        return self._health_report

    def snapshot(self, *, as_of: datetime | None = None) -> RuntimeSnapshot:
        now = as_of or self.clock()
        paper_report = self._portfolio_report(now)
        daily_report = self._current_daily_report(now, paper_report)
        return RuntimeSnapshot(
            as_of=now,
            status=self._last_cycle.status
            if self._last_cycle
            else RuntimeStatus.RUNNING,
            mode="Alpaca Paper",
            latest_prices=self._last_prices,
            paper_report=paper_report,
            daily_report=daily_report,
            shadow_challenger=self._primary_shadow_challenger_observation(),
            shadow_challengers=self._ordered_shadow_challenger_observations(),
            nightly_learning=self._last_learning_run,
            active_model_key=self._active_model_key(),
            last_cycle=self._last_cycle,
            daily_report_path=(
                str(self._last_report_path) if self._last_report_path else None
            ),
            nightly_learning_path=(
                str(self.persistence_store.read_learning_report_path())
                if self.persistence_store.read_learning_report_path() is not None
                else None
            ),
            events=tuple(self._events[-50:]),
            control_state=self.control_center.state,
            last_control_result=self._last_control_result,
            alerts=self._alerts,
            health_report=self._health_report,
            live_sandbox=self.live_sandbox.snapshot(
                as_of=now,
                latest_prices=self._last_prices,
            ),
        )

    def dashboard_snapshot(self, *, as_of: datetime | None = None):
        if as_of is None:
            with self._dashboard_snapshot_cache_lock:
                cached = self._dashboard_snapshot_cache
                now_monotonic = time.monotonic()
                if cached is not None and cached[0] > now_monotonic:
                    return cached[1]
                snapshot = self._build_dashboard_snapshot(as_of=None)
                self._dashboard_snapshot_cache = (now_monotonic + 5, snapshot)
                return snapshot
        return self._build_dashboard_snapshot(as_of=as_of)

    def _invalidate_dashboard_snapshot_cache(self) -> None:
        with self._dashboard_snapshot_cache_lock:
            self._dashboard_snapshot_cache = None

    def _build_dashboard_snapshot(self, *, as_of: datetime | None = None):
        from trading_app.dashboard.models import (
            DashboardPortfolioHistoryPoint,
            OperatorDashboardSnapshot,
        )

        runtime_snapshot = self.snapshot(as_of=as_of)
        paper_report = runtime_snapshot.paper_report
        daily_report = runtime_snapshot.daily_report
        latest_prices = runtime_snapshot.latest_prices
        health_report = runtime_snapshot.health_report or self.health_report(
            as_of=runtime_snapshot.as_of
        )
        price_status = latest_prices.status.value if latest_prices else "unavailable"
        open_orders = sum(
            1
            for status in paper_report.order_statuses
            if status.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
        )
        health_report_path = self.persistence_store.read_health_report_path()
        learning_report_path = self.persistence_store.read_learning_report_path()
        statement_reconciliation = (
            self.persistence_store.read_statement_reconciliation_report()
        )
        statement_reconciliation_path = (
            self.persistence_store.read_statement_reconciliation_path()
        )
        estimated_equity = daily_report.pnl_report.estimated_equity
        latest_price_map = latest_prices.price_map if latest_prices else {}
        managed_target_equity = (
            _managed_target_equity(
                paper_report.ledger_snapshot,
                latest_price_map,
                self.config,
            )
            if self.config.managed_capital is not None
            else None
        )
        # Return the full multi-day journal so the dashboard can render any
        # period (1D / 1W / 1M / ALL). The client filters by the selected
        # window. The limit covers roughly two weeks of 1-minute ticks; if we
        # ever need longer ranges we'll downsample server-side rather than
        # ship millions of points to the browser.
        portfolio_history = _dashboard_history_with_current(
            self.persistence_store.read_dashboard_portfolio_history(limit=5000),
            DashboardPortfolioHistoryPoint(
                as_of=runtime_snapshot.as_of,
                estimated_equity=estimated_equity,
                cash=daily_report.pnl_report.ending_cash,
                realized_pnl=daily_report.pnl_report.realized_pnl,
            ),
        )
        managed_metrics = (
            (
                DashboardMetric(
                    label="Managed capital",
                    value=_money(self.config.managed_capital),
                    detail=(
                        "Capital slice used for model sizing; broker cash "
                        "outside this slice is not target capital"
                    ),
                    tone="info",
                ),
                DashboardMetric(
                    label="Target equity",
                    value=_money(managed_target_equity or Decimal("0")),
                    detail="Effective daily model sizing equity",
                    tone="info",
                ),
            )
            if self.config.managed_capital is not None
            else ()
        )
        metrics = (
            *managed_metrics,
            DashboardMetric(
                label="Paper cash",
                value=_money(daily_report.pnl_report.ending_cash),
                detail="Alpaca paper plus internal ledger",
                tone="good",
            ),
            DashboardMetric(
                label="Estimated equity",
                value=_money(estimated_equity),
                detail="Latest paper valuation",
                tone="good",
            ),
            DashboardMetric(
                label="Price freshness",
                value=price_status,
                detail="Alpaca latest trade feed",
                tone="good" if price_status == "fresh" else "warn",
            ),
            DashboardMetric(
                label="Runtime",
                value=runtime_snapshot.status.value,
                detail="Always-on paper loop",
                tone=(
                    "danger"
                    if runtime_snapshot.status == RuntimeStatus.BLOCKED
                    else "warn"
                    if runtime_snapshot.status == RuntimeStatus.DEGRADED
                    else "info"
                ),
            ),
            DashboardMetric(
                label="Alerts",
                value=str(len(runtime_snapshot.alerts)),
                detail="Active operator alerts",
                tone="danger"
                if any(
                    alert.severity == RuntimeEventSeverity.ERROR
                    for alert in runtime_snapshot.alerts
                )
                else "warn"
                if runtime_snapshot.alerts
                else "good",
            ),
            DashboardMetric(
                label="Health",
                value=health_report.status.value,
                detail=health_report.next_action,
                tone=_health_tone(health_report.status.value),
            ),
        )
        full_comparison_index = self._full_comparison_index()
        model_evidence_by_key = self._model_card_evidence_by_key(
            comparison_index=full_comparison_index,
        )
        active_model_key = self._active_model_key()
        active_model_evidence = model_evidence_by_key.get(active_model_key)
        active_model_label = _active_model_card_label(active_model_evidence)
        return OperatorDashboardSnapshot(
            generated_at=runtime_snapshot.as_of,
            mode="Alpaca Paper",
            broker=self.service.broker.provider,
            data_feed_status=(
                latest_prices.warning
                if latest_prices and latest_prices.warning
                else "Alpaca latest trade feed"
            ),
            kill_switch_enabled=(
                self.risk_engine.config.kill_switch_enabled
                or self.control_center.state.paper_kill_switch_enabled
            ),
            cash=daily_report.pnl_report.ending_cash,
            estimated_equity=estimated_equity,
            realized_pnl=daily_report.pnl_report.realized_pnl,
            managed_capital=self.config.managed_capital,
            managed_target_equity=managed_target_equity,
            portfolio_history=portfolio_history,
            open_orders=open_orders,
            recent_fills=self.service.fills,
            paper_report=paper_report,
            daily_report=daily_report,
            shadow_challenger=runtime_snapshot.shadow_challenger,
            shadow_challengers=runtime_snapshot.shadow_challengers,
            nightly_learning=runtime_snapshot.nightly_learning,
            latest_prices=latest_prices,
            autonomous_learning=self._autonomous_learning_cycle_for_dashboard(
                comparison_index=full_comparison_index,
            ),
            autonomous_learning_service=(
                self.persistence_store.read_autonomous_learning_service_state()
            ),
            metrics=metrics,
            model_cards=(
                DashboardModelCard(
                    label=active_model_label,
                    strategy_id=self.strategy.strategy_id,
                    version=self.strategy.strategy_version,
                    state="paper",
                    score=(
                        active_model_evidence.risk_adjusted_score
                        if active_model_evidence is not None
                        and active_model_evidence.risk_adjusted_score is not None
                        else 0.0
                    ),
                    detail=_active_model_card_detail(
                        self.config.strategy_schedule,
                        active_model_evidence,
                    ),
                    evidence=active_model_evidence,
                ),
                *self._shadow_challenger_model_cards(
                    evidence_by_key=model_evidence_by_key
                ),
            ),
            runtime_state=runtime_snapshot,
            control_state=self.control_center.state,
            last_control_result=self._last_control_result,
            alerts=runtime_snapshot.alerts,
            health_report=health_report,
            health_report_path=(
                str(health_report_path) if health_report_path is not None else None
            ),
            nightly_learning_path=(
                str(learning_report_path) if learning_report_path is not None else None
            ),
            live_readiness=self._live_readiness_report(
                runtime_snapshot=runtime_snapshot,
                paper_report=paper_report,
            ),
            live_sandbox=runtime_snapshot.live_sandbox,
            completion_audit=self.persistence_store.read_completion_audit_report(),
            final_acceptance=self.persistence_store.read_final_acceptance_report(),
            statement_reconciliation=statement_reconciliation,
            statement_reconciliation_path=(
                str(statement_reconciliation_path)
                if statement_reconciliation_path is not None
                else None
            ),
            active_strategy_definition=self.strategy.definition(
                authority=StrategyAuthority.PAPER
            ),
        )

    def dashboard_snapshot_for_api(self):
        """Return the latest persisted dashboard snapshot for browser polling."""

        try:
            snapshot = self.persistence_store.read_dashboard_snapshot()
        except Exception:
            snapshot = None
        if snapshot is not None:
            updates = {
                "kill_switch_enabled": (
                    self.risk_engine.config.kill_switch_enabled
                    or self.control_center.state.paper_kill_switch_enabled
                ),
                "control_state": self.control_center.state,
                "last_control_result": self._last_control_result,
                "alerts": self._alerts,
                "live_sandbox": self.live_sandbox.snapshot(
                    as_of=self.clock(),
                    latest_prices=self._last_prices,
                ),
            }
            if self._health_report is not None:
                updates["health_report"] = self._health_report
            return snapshot.model_copy(update=updates)
        return self.dashboard_snapshot()

    def _restore_from_persistence(self) -> None:
        recovered = self.persistence_store.restore_service(self.service)
        self._last_prices = recovered.latest_prices
        self._last_cycle = recovered.last_cycle
        self._last_report = recovered.daily_report
        self._last_report_path = recovered.daily_report_path
        self._last_learning_run = recovered.nightly_learning
        self._last_shadow_challenger_observations = {
            observation.model_key: observation
            for observation in recovered.shadow_challengers
        }
        if (
            recovered.shadow_challenger is not None
            and recovered.shadow_challenger.model_key
            not in self._last_shadow_challenger_observations
        ):
            self._last_shadow_challenger_observations[
                recovered.shadow_challenger.model_key
            ] = recovered.shadow_challenger
        self._last_shadow_challenger_observation = (
            self._primary_shadow_challenger_observation() or recovered.shadow_challenger
        )
        self._events = list(recovered.events[-50:])
        self._alerts = recovered.alerts
        self._health_report = recovered.health_report
        if not self._external_control_center and (
            recovered.control_state is not None or recovered.control_results
        ):
            self.control_center = RuntimeControlCenter(
                state=recovered.control_state,
                history=recovered.control_results,
            )
        self._last_control_result = self.control_center.last_result
        self.live_sandbox.restore_state(
            control_state=self.persistence_store.read_live_sandbox_control_state(),
            submissions=self.persistence_store.read_live_sandbox_submissions(),
            order_statuses=self.persistence_store.read_live_sandbox_order_statuses(),
            fills=self.persistence_store.read_live_sandbox_fills(),
            latest_cycle=self.persistence_store.read_live_sandbox_latest_cycle(),
        )
        if recovered.last_cycle and _cycle_consumed_trade_date(recovered.last_cycle):
            local_date = recovered.last_cycle.as_of.astimezone(MARKET_TZ).date()
            self._last_trade_date = local_date
        if recovered.last_cycle and recovered.last_cycle.orders_submitted:
            local_date = recovered.last_cycle.as_of.astimezone(MARKET_TZ).date()
            self._last_rebalance_month = (local_date.year, local_date.month)
        latest_runtime_submission = _latest_runtime_submission(recovered.submissions)
        if latest_runtime_submission is not None:
            local_date = latest_runtime_submission.submitted_at.astimezone(
                MARKET_TZ
            ).date()
            self._last_trade_date = local_date
            self._last_rebalance_month = (local_date.year, local_date.month)
        if recovered.daily_report:
            self._last_report_date = recovered.daily_report.trading_day
        if recovered.nightly_learning:
            self._last_learning_date = recovered.nightly_learning.as_of.astimezone(
                MARKET_TZ
            ).date()
        self._last_shadow_challenger_dates = {
            model_key: observation.as_of.astimezone(MARKET_TZ).date()
            for model_key, observation in (
                self._last_shadow_challenger_observations.items()
            )
        }
        if self._last_shadow_challenger_observation:
            self._last_shadow_challenger_date = (
                self._last_shadow_challenger_observation.as_of.astimezone(
                    MARKET_TZ
                ).date()
            )

    def _active_model_key(self) -> str:
        return f"{self.strategy.strategy_id}:{self.strategy.strategy_version}"

    def _current_daily_report(self, now: datetime, paper_report):
        cached_report = self._last_report
        if (
            self._daily_report_matches_active_strategy(cached_report)
            and cached_report.trading_day == paper_report.as_of.date()
            and not _is_market_hours(now)
        ):
            return cached_report
        return DailyReportGenerator().build(
            paper_report,
            generated_at=now,
            data_quality_report=self._latest_data_quality_report(now),
            active_strategy_definition=self.strategy.definition(
                authority=StrategyAuthority.PAPER
            ),
        )

    def _daily_report_matches_active_strategy(self, report) -> bool:
        if report is None or report.active_strategy_definition is None:
            return False
        definition = report.active_strategy_definition
        return (
            definition.strategy_id == self.strategy.strategy_id
            and definition.version == self.strategy.strategy_version
        )

    def _model_card_evidence_by_key(
        self,
        *,
        comparison_index: _FullComparisonIndex | None = None,
    ) -> dict[str, DashboardModelEvidence]:
        model_keys = {
            self._active_model_key(),
            *self.shadow_challenger_model_keys,
        }
        leaderboard = self.persistence_store.read_autonomous_learning_leaderboard()
        active_model_key = self._active_model_key()
        active_universe_id = self.config.active_model_universe_id
        leaderboard_entries: dict[str, AutonomousLearningLeaderboardEntry] = {}
        leaderboard_entries_by_model_universe: dict[
            tuple[str, str],
            AutonomousLearningLeaderboardEntry,
        ] = {}
        if leaderboard is not None:
            for entry in leaderboard.entries:
                previous = leaderboard_entries.get(entry.model_key)
                if previous is None or entry.rank < previous.rank:
                    leaderboard_entries[entry.model_key] = entry
                universe_key = (entry.model_key, entry.universe_id)
                previous_universe = leaderboard_entries_by_model_universe.get(
                    universe_key,
                )
                if previous_universe is None or entry.rank < previous_universe.rank:
                    leaderboard_entries_by_model_universe[universe_key] = entry

        evidence_by_key: dict[str, DashboardModelEvidence] = {}
        for model_key in sorted(model_keys):
            target_universe_id = (
                active_universe_id if model_key == active_model_key else None
            )
            entry = (
                leaderboard_entries_by_model_universe.get(
                    (model_key, target_universe_id),
                )
                if target_universe_id
                else leaderboard_entries.get(model_key)
            )
            needs_comparison_row = (
                entry is None
                or entry.net_total_return is None
                or entry.benchmark_total_return is None
            )
            comparison_row = None
            comparison_path = None
            if needs_comparison_row:
                comparison_row, comparison_path = self._latest_full_comparison_row(
                    model_key=model_key,
                    universe_id=(
                        entry.universe_id
                        if entry is not None
                        else target_universe_id
                    ),
                    latest_run_id=entry.latest_run_id if entry is not None else None,
                    prefer_longest_window=target_universe_id is not None,
                    comparison_index=comparison_index,
                )
            comparison_universe_id = _comparison_path_universe_id(comparison_path)
            source = (
                "leaderboard+full_comparison"
                if entry is not None and comparison_row is not None
                else "leaderboard"
                if entry is not None
                else "full_comparison_only"
                if comparison_row is not None
                else "missing"
            )
            note = None
            if source == "full_comparison_only":
                note = (
                    "This exact model is not in the consolidated leaderboard yet; "
                    "showing its latest full-period comparison row."
                )
            elif source == "missing":
                note = "No leaderboard or full-period comparison evidence found."
            evidence = DashboardModelEvidence(
                model_key=model_key,
                source=source,
                source_report=str(comparison_path) if comparison_path else None,
                benchmark=_optional_string(comparison_row, "comparison_benchmark")
                or "SPY",
                comparison_start_date=_optional_string(
                    comparison_row,
                    "comparison_start_date",
                ),
                comparison_end_date=_optional_string(
                    comparison_row,
                    "comparison_end_date",
                ),
                comparison_generated_at=_optional_string(
                    comparison_row,
                    "comparison_generated_at",
                ),
                rank=entry.rank if entry is not None else None,
                comparison_rank=_optional_int(comparison_row, "rank"),
                universe_id=(
                    entry.universe_id
                    if entry is not None
                    else comparison_universe_id or target_universe_id
                ),
                strategy_name=(
                    entry.strategy_name
                    if entry is not None
                    else _optional_string(comparison_row, "strategy_name")
                ),
                net_total_return=(
                    entry.net_total_return
                    if entry is not None and entry.net_total_return is not None
                    else _optional_float(comparison_row, "net_total_return")
                ),
                benchmark_total_return=(
                    entry.benchmark_total_return
                    if entry is not None and entry.benchmark_total_return is not None
                    else _optional_float(comparison_row, "benchmark_total_return")
                ),
                excess_return=_optional_float(
                    comparison_row,
                    "excess_return",
                    fallback=entry.full_delta if entry is not None else None,
                ),
                full_delta=entry.full_delta
                if entry is not None
                else _optional_float(comparison_row, "excess_return"),
                stress_delta=entry.stress_delta if entry is not None else None,
                annualized_return=_optional_float(
                    comparison_row,
                    "annualized_return",
                ),
                annualized_volatility=_optional_float(
                    comparison_row,
                    "annualized_volatility",
                ),
                worst_drawdown=(
                    entry.worst_drawdown
                    if entry is not None
                    else _optional_float(comparison_row, "max_drawdown")
                ),
                risk_adjusted_score=(
                    entry.risk_adjusted_score
                    if entry is not None
                    else _optional_float(comparison_row, "research_score")
                ),
                positive_folds=entry.positive_folds if entry is not None else None,
                fold_count=entry.fold_count if entry is not None else None,
                min_fold_delta=entry.min_fold_delta if entry is not None else None,
                average_fold_delta=(
                    entry.average_fold_delta if entry is not None else None
                ),
                turnover=_optional_float(comparison_row, "turnover"),
                trade_count=_optional_int(comparison_row, "trade_count"),
                decision_count=_optional_int(comparison_row, "decision_count"),
                seen_count=entry.seen_count if entry is not None else None,
                gate_status=entry.gate_status if entry is not None else None,
                status=entry.status if entry is not None else None,
                latest_run_id=entry.latest_run_id if entry is not None else None,
                late_entry_risk=(
                    entry.late_entry_risk
                    if entry is not None
                    else _optional_bool(comparison_row, "late_entry_risk")
                ),
                late_entry_risk_reason=(
                    entry.late_entry_risk_reason
                    if entry is not None
                    else _optional_string(comparison_row, "late_entry_risk_reason")
                ),
                portfolio_governance_classification=(
                    entry.portfolio_governance_classification
                    if entry is not None
                    else _optional_string(
                        comparison_row,
                        "portfolio_governance_classification",
                    )
                ),
                champion_eligible=(
                    entry.champion_eligible
                    if entry is not None
                    else _optional_bool(comparison_row, "champion_eligible")
                ),
                average_semiconductor_exposure=(
                    entry.average_semiconductor_exposure
                    if entry is not None
                    else _optional_float(
                        comparison_row,
                        "average_semiconductor_exposure",
                    )
                ),
                peak_semiconductor_exposure=(
                    entry.peak_semiconductor_exposure
                    if entry is not None
                    else _optional_float(comparison_row, "peak_semiconductor_exposure")
                ),
                material_semiconductor_exposure_ratio=(
                    entry.material_semiconductor_exposure_ratio
                    if entry is not None
                    else _optional_float(
                        comparison_row,
                        "material_semiconductor_exposure_ratio",
                    )
                ),
                portfolio_governance_notes=(
                    entry.portfolio_governance_notes
                    if entry is not None
                    else _optional_string_tuple(
                        comparison_row,
                        "portfolio_governance_notes",
                    )
                ),
                note=note,
            )
            evidence_by_key[model_key] = _normalized_dashboard_evidence(evidence)
        return evidence_by_key

    def _autonomous_learning_cycle_for_dashboard(
        self,
        *,
        comparison_index: _FullComparisonIndex | None = None,
    ) -> AutonomousLearningCycleRun | None:
        cycle = self.persistence_store.read_autonomous_learning_cycle()
        if cycle is None:
            return None
        leaderboard = self.persistence_store.read_autonomous_learning_leaderboard()
        if leaderboard is None:
            return cycle

        enriched_entries = []
        for entry in leaderboard.entries:
            if (
                entry.net_total_return is not None
                and entry.benchmark_total_return is not None
            ):
                enriched_entries.append(entry)
                continue
            comparison_row, _ = self._latest_full_comparison_row(
                model_key=entry.model_key,
                universe_id=entry.universe_id,
                latest_run_id=entry.latest_run_id,
                expected_excess_return=entry.full_delta,
                comparison_index=comparison_index,
            )
            updates = {
                key: value
                for key, value in {
                    "net_total_return": _optional_float(
                        comparison_row,
                        "net_total_return",
                    ),
                    "benchmark_total_return": _optional_float(
                        comparison_row,
                        "benchmark_total_return",
                    ),
                }.items()
                if value is not None
            }
            enriched_entries.append(
                entry.model_copy(update=updates) if updates else entry
            )
        return cycle.model_copy(
            update={
                "leaderboard": leaderboard.model_copy(
                    update={"entries": tuple(enriched_entries)}
                )
            }
        )

    def _latest_full_comparison_row(
        self,
        *,
        model_key: str,
        universe_id: str | None,
        latest_run_id: str | None,
        expected_excess_return: float | None = None,
        prefer_longest_window: bool = False,
        comparison_index: _FullComparisonIndex | None = None,
    ) -> tuple[dict[str, object] | None, Path | None]:
        index = comparison_index or self._full_comparison_index()
        if not index.rows_by_model:
            return None, None
        if latest_run_id and universe_id and not prefer_longest_window:
            candidate_path = (
                self._research_replay_dir()
                / f"{latest_run_id}-{universe_id}-full-base-comparison.json"
            )
            row = index.rows_by_path_and_model.get((candidate_path, model_key))
            if row is not None and _comparison_row_matches_excess(
                row,
                expected_excess_return,
            ):
                return row, candidate_path
        candidates: list[tuple[dict[str, object], Path]] = []
        for row, path in index.rows_by_model.get(model_key, ()):
            if universe_id and _comparison_path_universe_id(path) != universe_id:
                continue
            if _comparison_row_matches_excess(
                row,
                expected_excess_return,
            ):
                if prefer_longest_window:
                    candidates.append((row, path))
                    continue
                return row, path
        if candidates:
            return max(candidates, key=_comparison_window_sort_key)
        return None, None

    def _full_comparison_index(self) -> _FullComparisonIndex:
        now_monotonic = time.monotonic()
        with self._full_comparison_index_lock:
            cached = self._full_comparison_index_cache
            if cached is not None and cached[0] > now_monotonic:
                return cached[1]

        index = _build_full_comparison_index(self._research_replay_dir())

        with self._full_comparison_index_lock:
            self._full_comparison_index_cache = (
                time.monotonic() + 60,
                index,
            )
        return index

    def _research_replay_dir(self) -> Path:
        return self.config.output_dir.parent / "research" / "replay"

    def _shadow_challenger_model_cards(
        self,
        *,
        evidence_by_key: dict[str, DashboardModelEvidence] | None = None,
    ) -> tuple[DashboardModelCard, ...]:
        if not self.shadow_challenger_strategies:
            return ()
        detail = "Virtual ledger only; no Alpaca broker orders"
        cards: list[DashboardModelCard] = []
        evidence_by_key = evidence_by_key or {}
        for index, (model_key, strategy) in enumerate(
            self.shadow_challenger_strategies,
            start=1,
        ):
            observation = self._last_shadow_challenger_observations.get(model_key)
            evidence = evidence_by_key.get(model_key)
            score = (
                evidence.risk_adjusted_score
                if evidence is not None and evidence.risk_adjusted_score is not None
                else float(observation.estimated_equity / self.config.starting_cash - 1)
                if observation is not None and self.config.starting_cash > 0
                else 0.0
            )
            cards.append(
                DashboardModelCard(
                    label=(
                        "Shadow Challenger"
                        if len(self.shadow_challenger_strategies) == 1
                        else f"Shadow Challenger {index}"
                    ),
                    strategy_id=strategy.strategy_id,
                    version=strategy.strategy_version,
                    state="shadow",
                    score=score,
                    detail=detail,
                    evidence=evidence,
                )
            )
        return tuple(cards)

    def _portfolio_report(
        self,
        as_of: datetime,
        *,
        events: list[RuntimeEvent] | None = None,
    ):
        try:
            paper_report = self.service.portfolio_report(
                as_of=as_of,
                broker_orders=self._broker_orders_for_paper_epoch(),
            )
        except Exception as error:
            message = f"Broker portfolio report unavailable: {error}"
            if events is not None:
                events.append(
                    self._event(
                        as_of,
                        RuntimeEventSeverity.ERROR,
                        "broker_sync",
                        message,
                    )
                )
            paper_report = self.service.degraded_portfolio_report(
                as_of=as_of,
                message=message,
            )
        self._last_paper_report = paper_report
        return paper_report

    def _broker_orders_for_paper_epoch(self) -> tuple:
        epoch = self.config.paper_epoch_started_at
        if epoch is None:
            return self.service.broker.list_orders()
        return tuple(
            broker_order
            for broker_order in self.service.broker.list_orders()
            if not self._broker_order_before_paper_epoch(broker_order)
        )

    def _live_readiness_report(
        self, *, runtime_snapshot: RuntimeSnapshot, paper_report
    ):
        latest_prices = runtime_snapshot.latest_prices
        symbols = tuple(sorted(self.config.symbols))
        gate = LiveReadinessGate(
            config=LiveTradingConfig(
                mode=EnvironmentMode.LIVE_READINESS,
                paper_account_id=f"{self.service.broker.provider}-paper-runtime",
                live_account_id="live-trading-disabled",
                live_trading_enabled=False,
            ),
            limits=LiveRiskLimits(
                allowed_symbols=symbols,
                kill_switch_enabled=(
                    self.risk_engine.config.kill_switch_enabled
                    or self.control_center.state.paper_kill_switch_enabled
                ),
            ),
        )
        return gate.build_report(
            as_of=runtime_snapshot.as_of,
            paper_trading_days=0,
            candidate_model_key=runtime_snapshot.active_model_key,
            candidate_model_state="paper",
            risk_engine_active=self.risk_engine is not None,
            kill_switch_tested=self.control_center.state.paper_kill_switch_enabled,
            broker_reconciled=paper_report.reconciliation.reconciled,
            data_feed_fresh=bool(latest_prices and latest_prices.all_fresh),
            limits_configured=bool(symbols),
            user_reviewed_assumptions=False,
            explicit_user_approval=False,
        )

    def _sync_broker_orders(self, *, as_of: datetime) -> int:
        fills_applied = 0
        for broker_order in self.service.broker.list_orders():
            if self._broker_order_before_paper_epoch(broker_order):
                continue
            client_order_id = broker_order.client_order_id
            if (
                not client_order_id
                or self.service.ledger.get_order(client_order_id) is None
            ):
                if not _is_runtime_client_order_id(client_order_id):
                    continue
                submission = self.service.recover_broker_order(
                    broker_order,
                    strategy_id=self.strategy.strategy_id,
                    as_of=as_of,
                )
                self.persistence_store.persist_submission(submission)
                local_date = broker_order.submitted_at.astimezone(MARKET_TZ).date()
                self._last_trade_date = local_date
                self._last_rebalance_month = (local_date.year, local_date.month)
            _, fill = self.service.sync_broker_order_state(broker_order, as_of=as_of)
            if fill is not None:
                self.persistence_store.persist_fill(fill)
                fills_applied += 1
        return fills_applied

    def _broker_order_before_paper_epoch(self, broker_order) -> bool:
        epoch = self.config.paper_epoch_started_at
        if epoch is None:
            return False
        return broker_order.submitted_at < epoch

    def _write_daily_report(self, as_of: datetime) -> None:
        reports_dir = self.config.output_dir / "reports"
        markdown_path = reports_dir / f"daily-report-{as_of.date().isoformat()}.md"
        self._last_report = DailyReportGenerator().build(
            self._portfolio_report(as_of),
            generated_at=as_of,
            data_quality_report=self._latest_data_quality_report(as_of),
            operator_actions=self.control_center.history,
            runtime_events=tuple(self._events[-50:]),
            nightly_learning=self._last_learning_run,
            active_strategy_definition=self.strategy.definition(
                authority=StrategyAuthority.PAPER
            ),
            markdown_path=str(markdown_path),
        )
        self._last_report_path = write_markdown_report(
            self._last_report,
            reports_dir,
        )
        self.persistence_store.persist_daily_report(
            self._last_report,
            markdown_path=self._last_report_path,
        )
        self._last_report_date = as_of.astimezone(MARKET_TZ).date()

    def _evaluate_strategy(
        self,
        as_of: datetime,
        paper_report,
        events: list[RuntimeEvent],
    ) -> int:
        if self.control_center.state.paused:
            return 0
        if self.control_center.state.paper_kill_switch_enabled:
            return 0
        if self._last_prices is None or not self._last_prices.all_fresh:
            return 0
        if not paper_report.reconciliation.reconciled:
            return 0

        local_date = as_of.astimezone(MARKET_TZ).date()
        symbols = _strategy_required_symbols(self.strategy)
        history_days = _strategy_history_calendar_days(self.strategy)
        bars = self.historical_bar_fetcher.fetch_daily_bars(
            list(symbols),
            local_date - timedelta(days=history_days),
            local_date,
            self.config.feed,
        )
        targets = self.strategy.generate_targets(bars, local_date)
        if not targets and not paper_report.ledger_snapshot.positions:
            return 0
        targets = self._paper_rollout_limited_targets(
            targets,
            snapshot=paper_report.ledger_snapshot,
            latest_prices=self._last_prices.price_map,
            events=events,
            as_of=as_of,
        )

        return self._submit_rebalance_orders(
            as_of=as_of,
            targets=targets,
            latest_prices=self._last_prices.price_map,
            events=events,
        )

    def _evaluate_shadow_challenger(
        self,
        as_of: datetime,
        events: list[RuntimeEvent],
        *,
        model_key: str,
        strategy,
    ) -> ShadowChallengerObservation | None:
        if self._last_prices is None:
            return None
        if not self._last_prices.all_fresh:
            return None

        local_date = as_of.astimezone(MARKET_TZ).date()
        symbols = _strategy_required_symbols(strategy)
        history_days = _strategy_history_calendar_days(strategy)
        bars = self.historical_bar_fetcher.fetch_daily_bars(
            list(symbols),
            local_date - timedelta(days=history_days),
            local_date,
            self.config.feed,
        )
        targets, explanation, metadata = _strategy_targets_with_metadata(
            strategy,
            bars,
            local_date,
        )
        previous_snapshot = self._shadow_challenger_snapshot(model_key, as_of)
        next_snapshot, orders, previous_equity, estimated_equity = (
            self._apply_shadow_rebalance(
                as_of=as_of,
                snapshot=previous_snapshot,
                targets=targets,
                latest_prices=self._last_prices.price_map,
            )
        )
        if not targets:
            events.append(
                self._event(
                    as_of,
                    RuntimeEventSeverity.WARNING,
                    "shadow_challenger",
                    "Shadow challenger produced no targets.",
                    (model_key,),
                )
            )
        return ShadowChallengerObservation(
            as_of=as_of,
            model_key=model_key,
            strategy_id=strategy.strategy_id,
            version=strategy.strategy_version,
            latest_prices_fresh=self._last_prices.all_fresh,
            broker_orders_submitted=False,
            targets=targets,
            explanation=explanation,
            metadata=metadata,
            orders=orders,
            ledger_snapshot=next_snapshot,
            estimated_equity=estimated_equity,
            previous_estimated_equity=previous_equity,
        )

    def _shadow_challenger_snapshot(
        self,
        model_key: str,
        as_of: datetime,
    ) -> PortfolioSnapshot:
        observation = self._last_shadow_challenger_observations.get(model_key)
        if observation is not None:
            return observation.ledger_snapshot.model_copy(update={"as_of": as_of})
        return PortfolioSnapshot(
            cash=self.config.starting_cash,
            positions=(),
            realized_pnl=Decimal("0"),
            total_fees=Decimal("0"),
            as_of=as_of,
        )

    def _apply_shadow_rebalance(
        self,
        *,
        as_of: datetime,
        snapshot: PortfolioSnapshot,
        targets: dict[str, Decimal],
        latest_prices: dict[str, Decimal],
    ) -> tuple[PortfolioSnapshot, tuple[ShadowOrderIntent, ...], Decimal, Decimal]:
        cash = snapshot.cash
        realized_pnl = snapshot.realized_pnl
        total_fees = snapshot.total_fees
        positions = {position.symbol: position for position in snapshot.positions}
        previous_equity = _estimated_equity(snapshot, latest_prices)
        target_values = {
            symbol: previous_equity * weight for symbol, weight in targets.items()
        }
        orders: list[ShadowOrderIntent] = []

        for symbol in sorted(set(positions) | set(targets)):
            if symbol not in latest_prices:
                continue
            position = positions.get(symbol)
            if position is None:
                continue
            price = latest_prices[symbol]
            current_value = position.quantity * price
            target_value = target_values.get(symbol, Decimal("0"))
            if current_value <= target_value:
                continue
            quantity = (
                position.quantity
                if target_value == 0
                else (current_value - target_value) / price
            )
            quantity = _round_quantity_down(min(quantity, position.quantity))
            if quantity <= 0:
                continue
            orders.append(
                ShadowOrderIntent(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=quantity,
                    estimated_price=price,
                    estimated_notional=quantity * price,
                    current_value=current_value,
                    target_value=target_value,
                )
            )
            cash += quantity * price
            realized = (price - position.average_cost) * quantity
            realized_pnl += realized
            next_quantity = position.quantity - quantity
            if next_quantity <= 0:
                del positions[symbol]
            else:
                positions[symbol] = position.model_copy(
                    update={
                        "quantity": next_quantity,
                        "realized_pnl": position.realized_pnl + realized,
                    }
                )

        for symbol in sorted(targets):
            if symbol not in latest_prices:
                continue
            price = latest_prices[symbol]
            position = positions.get(symbol)
            current_quantity = position.quantity if position else Decimal("0")
            current_value = current_quantity * price
            target_value = target_values[symbol]
            if current_value >= target_value:
                continue
            available_cash = cash * (Decimal("1") - self.config.strategy_cash_buffer)
            quantity = min(
                (target_value - current_value) / price,
                available_cash / price,
            )
            quantity = _round_quantity_down(quantity)
            if quantity <= 0:
                continue
            orders.append(
                ShadowOrderIntent(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    quantity=quantity,
                    estimated_price=price,
                    estimated_notional=quantity * price,
                    current_value=current_value,
                    target_value=target_value,
                )
            )
            cash -= quantity * price
            if position is None:
                positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    average_cost=price,
                    realized_pnl=Decimal("0"),
                )
            else:
                existing_cost = position.quantity * position.average_cost
                next_quantity = position.quantity + quantity
                next_average_cost = (existing_cost + quantity * price) / next_quantity
                positions[symbol] = position.model_copy(
                    update={
                        "quantity": next_quantity,
                        "average_cost": next_average_cost,
                    }
                )

        next_snapshot = PortfolioSnapshot(
            cash=max(cash, Decimal("0")),
            positions=tuple(sorted(positions.values(), key=lambda item: item.symbol)),
            realized_pnl=realized_pnl,
            total_fees=total_fees,
            as_of=as_of,
        )
        estimated_equity = _estimated_equity(next_snapshot, latest_prices)
        return next_snapshot, tuple(orders), previous_equity, estimated_equity

    def _submit_rebalance_orders(
        self,
        *,
        as_of: datetime,
        targets: dict[str, Decimal],
        latest_prices: dict[str, Decimal],
        events: list[RuntimeEvent],
    ) -> int:
        snapshot = self.service.ledger.snapshot(as_of)
        target_equity = _managed_target_equity(
            snapshot,
            latest_prices,
            self.config,
        )
        submitted = 0
        current_positions = {
            position.symbol: position for position in snapshot.positions
        }
        target_values = {
            symbol: target_equity * weight for symbol, weight in targets.items()
        }

        for symbol in sorted(set(current_positions) | set(targets)):
            if symbol not in latest_prices:
                continue
            position = current_positions.get(symbol)
            if position is None:
                continue
            current_value = position.quantity * latest_prices[symbol]
            target_value = target_values.get(symbol, Decimal("0"))
            if current_value <= target_value:
                continue
            quantity = (
                position.quantity
                if target_value == 0
                else (current_value - target_value) / latest_prices[symbol]
            )
            try:
                submitted += self._submit_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=_round_quantity_up(min(quantity, position.quantity)),
                    estimated_price=latest_prices[symbol],
                    as_of=as_of,
                    latest_prices=latest_prices,
                )
            except Exception as error:
                events.append(
                    self._broker_submission_event(
                        as_of=as_of,
                        symbol=symbol,
                        side=OrderSide.SELL,
                        error=error,
                    )
                )
                return submitted

        for symbol in sorted(targets):
            if symbol not in latest_prices:
                continue
            position = self.service.ledger.get_position(symbol)
            current_quantity = position.quantity if position else Decimal("0")
            current_value = current_quantity * latest_prices[symbol]
            target_value = target_values[symbol]
            if current_value >= target_value:
                continue
            cash = self.service.ledger.cash * (
                Decimal("1") - self.config.strategy_cash_buffer
            )
            quantity = min(
                (target_value - current_value) / latest_prices[symbol],
                cash / latest_prices[symbol],
            )
            try:
                submitted += self._submit_order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    quantity=_round_quantity_down(quantity),
                    estimated_price=latest_prices[symbol],
                    as_of=as_of,
                    latest_prices=latest_prices,
                )
            except Exception as error:
                events.append(
                    self._broker_submission_event(
                        as_of=as_of,
                        symbol=symbol,
                        side=OrderSide.BUY,
                        error=error,
                    )
                )
                return submitted
        return submitted

    def _broker_submission_event(
        self,
        *,
        as_of: datetime,
        symbol: str,
        side: OrderSide,
        error: Exception,
    ) -> RuntimeEvent:
        return self._event(
            as_of,
            RuntimeEventSeverity.ERROR,
            "broker_order_submission",
            f"Paper order submission failed for {symbol} {side.value}: {error}",
            (symbol, side.value),
        )

    def _submit_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        estimated_price: Decimal,
        as_of: datetime,
        latest_prices: dict[str, Decimal],
    ) -> int:
        if quantity <= 0:
            return 0
        if self.control_center.state.paused:
            return 0
        if self.control_center.state.paper_kill_switch_enabled:
            return 0
        order = Order(
            id=(
                f"runtime-{as_of.astimezone(MARKET_TZ).date().isoformat()}-"
                f"{symbol}-{side.value.lower()}-{len(self.service.submissions) + 1}"
            ),
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            created_at=as_of,
        )
        submission = self.service.submit_order(
            order,
            strategy_id=self.strategy.strategy_id,
            estimated_price=estimated_price,
            as_of=as_of,
            latest_prices=latest_prices,
            sector=_paper_symbol_sector(symbol),
        )
        self.persistence_store.persist_submission(submission)
        for status in self.service.order_statuses:
            if status.order_id == order.id:
                self.persistence_store.persist_order_status(status)
        return 1 if submission.accepted and submission.broker_submitted else 0

    def _paper_rollout_limited_targets(
        self,
        targets: dict[str, Decimal],
        *,
        snapshot: PortfolioSnapshot,
        latest_prices: dict[str, Decimal],
        events: list[RuntimeEvent],
        as_of: datetime,
    ) -> dict[str, Decimal]:
        limited = {
            symbol: max(weight, Decimal("0"))
            for symbol, weight in targets.items()
            if weight > 0
        }
        if not limited:
            return limited

        original = dict(limited)
        symbol_cap = self.config.max_paper_symbol_allocation
        if symbol_cap is not None:
            limited = {
                symbol: min(weight, symbol_cap) for symbol, weight in limited.items()
            }

        semiconductor_cap = self.config.max_paper_semiconductor_allocation
        if semiconductor_cap is not None:
            semiconductor_symbols = set(PAPER_SEMICONDUCTOR_SYMBOLS)
            semiconductor_weight = sum(
                weight
                for symbol, weight in limited.items()
                if symbol in semiconductor_symbols
            )
            if semiconductor_weight > semiconductor_cap and semiconductor_weight > 0:
                scale = semiconductor_cap / semiconductor_weight
                limited = {
                    symbol: (
                        weight * scale if symbol in semiconductor_symbols else weight
                    )
                    for symbol, weight in limited.items()
                }

        initial_cap = self.config.initial_paper_deployment_allocation
        if (
            initial_cap is not None
            and self.config.managed_capital is None
            and not self._has_broker_submitted_order()
        ):
            gross_target = sum(limited.values(), Decimal("0"))
            if gross_target > initial_cap and gross_target > 0:
                scale = initial_cap / gross_target
                limited = {symbol: weight * scale for symbol, weight in limited.items()}

        changed = any(
            limited.get(symbol, Decimal("0")) != original.get(symbol, Decimal("0"))
            for symbol in set(limited) | set(original)
        )
        if changed:
            events.append(
                self._event(
                    as_of,
                    RuntimeEventSeverity.INFO,
                    "paper_rollout_limits",
                    (
                        "Paper strategy targets were capped by rollout "
                        "concentration limits."
                    ),
                    tuple(
                        f"{symbol}:{original.get(symbol, Decimal('0'))}"
                        f"->{limited.get(symbol, Decimal('0'))}"
                        for symbol in sorted(set(limited) | set(original))
                    ),
                )
            )
        return limited

    def _paper_rebalance_repair_reason(
        self,
        as_of: datetime,
        *,
        paper_report,
    ) -> str | None:
        if self._last_prices is None or not self._last_prices.all_fresh:
            return None
        if not paper_report.reconciliation.reconciled:
            return None
        if self.control_center.state.paused:
            return None
        if self.control_center.state.paper_kill_switch_enabled:
            return None
        if any(
            status.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
            for status in paper_report.order_statuses
        ):
            return None
        local = as_of.astimezone(MARKET_TZ)
        if local.weekday() >= 5:
            return None
        if self.config.strategy_schedule == StrategySchedule.MARKET_OPEN:
            if local.time() < self.config.market_open_time:
                return None
            if local.time() >= dt_time(hour=16):
                return None
        elif local.time() < self.config.trade_after_close_time:
            return None
        if self._paper_rollout_limits_breached(
            paper_report.ledger_snapshot,
            self._last_prices.price_map,
        ):
            return "rollout_limits"
        if self._paper_managed_capital_deployment_gap(
            as_of,
            paper_report=paper_report,
        ):
            return "managed_capital_deployment_gap"
        return None

    def _paper_rollout_limits_breached(
        self,
        snapshot: PortfolioSnapshot,
        latest_prices: dict[str, Decimal],
    ) -> bool:
        equity = _managed_target_equity(snapshot, latest_prices, self.config)
        if equity <= 0:
            return False
        symbol_cap = self.config.max_paper_symbol_allocation
        if symbol_cap is not None:
            for position in snapshot.positions:
                value = position.quantity * latest_prices.get(
                    position.symbol,
                    position.average_cost,
                )
                if _allocation(value, equity) > symbol_cap:
                    return True
        semiconductor_cap = self.config.max_paper_semiconductor_allocation
        if semiconductor_cap is not None:
            semiconductor_value = sum(
                position.quantity
                * latest_prices.get(position.symbol, position.average_cost)
                for position in snapshot.positions
                if position.symbol in PAPER_SEMICONDUCTOR_SYMBOLS
            )
            if _allocation(semiconductor_value, equity) > semiconductor_cap:
                return True
        return False

    def _paper_managed_capital_deployment_gap(
        self,
        as_of: datetime,
        *,
        paper_report,
    ) -> bool:
        if self.config.managed_capital is None or self._last_prices is None:
            return False
        latest_prices = self._last_prices.price_map
        snapshot = paper_report.ledger_snapshot
        target_equity = _managed_target_equity(snapshot, latest_prices, self.config)
        if target_equity <= 0:
            return False

        gross_position_value = sum(
            position.quantity
            * latest_prices.get(position.symbol, position.average_cost)
            for position in snapshot.positions
        )
        threshold = max(Decimal("25"), target_equity * Decimal("0.02"))
        if gross_position_value >= target_equity - threshold:
            return False

        local_date = as_of.astimezone(MARKET_TZ).date()
        try:
            bars = self.historical_bar_fetcher.fetch_daily_bars(
                list(_strategy_required_symbols(self.strategy)),
                local_date
                - timedelta(days=_strategy_history_calendar_days(self.strategy)),
                local_date,
                self.config.feed,
            )
            targets = self.strategy.generate_targets(bars, local_date)
        except Exception:
            return False
        if not targets:
            return False
        targets = self._paper_rollout_limited_targets(
            targets,
            snapshot=snapshot,
            latest_prices=latest_prices,
            events=[],
            as_of=as_of,
        )
        for symbol, weight in targets.items():
            if symbol not in latest_prices:
                continue
            position = self.service.ledger.get_position(symbol)
            current_value = (
                position.quantity * latest_prices[symbol]
                if position is not None
                else Decimal("0")
            )
            target_value = target_equity * weight
            if target_value - current_value > threshold:
                return True
        return False

    def _has_broker_submitted_order(self) -> bool:
        return any(
            submission.broker_submitted for submission in self.service.submissions
        )

    def _should_evaluate_strategy(self, as_of: datetime) -> bool:
        local = as_of.astimezone(MARKET_TZ)
        if local.weekday() >= 5:
            return False
        if self.config.strategy_schedule == StrategySchedule.MARKET_OPEN:
            if local.time() < self.config.market_open_time:
                return False
            if local.time() >= dt_time(hour=16):
                return False
            return self._last_trade_date != local.date()
        if local.time() < self.config.trade_after_close_time:
            return False
        return self._last_trade_date != local.date()

    def _due_shadow_challengers(
        self, as_of: datetime
    ) -> tuple[tuple[str, object], ...]:
        if not self.shadow_challenger_strategies:
            return ()
        local = as_of.astimezone(MARKET_TZ)
        if local.weekday() >= 5:
            return ()
        if self.config.strategy_schedule == StrategySchedule.MARKET_OPEN:
            if local.time() < self.config.market_open_time:
                return ()
            if local.time() >= dt_time(hour=16):
                return ()
        elif local.time() < self.config.trade_after_close_time:
            return ()
        return tuple(
            (model_key, strategy)
            for model_key, strategy in self.shadow_challenger_strategies
            if self._last_shadow_challenger_dates.get(model_key) != local.date()
        )

    def _should_evaluate_shadow_challenger(self, as_of: datetime) -> bool:
        return bool(self._due_shadow_challengers(as_of))

    def _refresh_shadow_challenger_equity(
        self,
        as_of: datetime,
    ) -> tuple[ShadowChallengerObservation, ...]:
        """Mark each known shadow challenger to market and journal a new
        observation per model.

        Decision-time observations (targets, orders, explanation) are written
        by ``_evaluate_shadow_challenger`` once per business day. This refresh
        runs every cycle so the per-model equity time series stays dense and
        the dashboard chart can render real curves instead of single dots.

        Positions don't change here — only ``as_of`` and ``estimated_equity``
        move. ``orders`` are cleared because no new orders are submitted at
        a mark-to-market tick.
        """

        if self._last_prices is None or not self._last_prices.all_fresh:
            return ()
        if not self._last_shadow_challenger_observations:
            return ()

        prices = self._last_prices.price_map
        refreshed: list[ShadowChallengerObservation] = []
        for model_key, prior in list(self._last_shadow_challenger_observations.items()):
            snapshot = prior.ledger_snapshot
            if snapshot is None:
                continue
            # Skip a duplicate write when the decision-time observation
            # already happened in this same cycle.
            if prior.as_of == as_of:
                continue
            new_equity = _estimated_equity(snapshot, prices)
            # Only equity-related fields move on a mark-to-market tick.
            # Targets, explanation, orders, and metadata describe the most
            # recent rebalance decision and remain useful between decisions.
            observation = prior.model_copy(
                update={
                    "as_of": as_of,
                    "estimated_equity": new_equity,
                    "previous_estimated_equity": prior.estimated_equity,
                    "latest_prices_fresh": True,
                }
            )
            self._last_shadow_challenger_observations[model_key] = observation
            self.persistence_store.persist_shadow_challenger_observation(observation)
            refreshed.append(observation)

        if refreshed:
            self.persistence_store.persist_shadow_challenger_observations(
                self._ordered_shadow_challenger_observations()
            )
            self._last_shadow_challenger_observation = (
                self._primary_shadow_challenger_observation()
            )
        return tuple(refreshed)

    def _ordered_shadow_challenger_observations(
        self,
    ) -> tuple[ShadowChallengerObservation, ...]:
        ordered = [
            self._last_shadow_challenger_observations[model_key]
            for model_key in self.shadow_challenger_model_keys
            if model_key in self._last_shadow_challenger_observations
        ]
        configured = {observation.model_key for observation in ordered}
        ordered.extend(
            observation
            for model_key, observation in sorted(
                self._last_shadow_challenger_observations.items()
            )
            if model_key not in configured
        )
        return tuple(ordered)

    def _primary_shadow_challenger_observation(
        self,
    ) -> ShadowChallengerObservation | None:
        observations = self._ordered_shadow_challenger_observations()
        return observations[0] if observations else None

    def _primary_shadow_challenger_date(self) -> date | None:
        observation = self._primary_shadow_challenger_observation()
        if observation is None:
            return None
        return observation.as_of.astimezone(MARKET_TZ).date()

    def _should_write_daily_report(self, as_of: datetime) -> bool:
        local = as_of.astimezone(MARKET_TZ)
        if local.weekday() >= 5 or local.time() < self.config.trade_after_close_time:
            return False
        return self._last_report_date != local.date()

    def _should_run_nightly_learning(self, as_of: datetime) -> bool:
        if not isinstance(self.strategy, MonthlySectorMomentumStrategy):
            return False
        local = as_of.astimezone(MARKET_TZ)
        if self._last_report_date != local.date():
            return False
        if local.time() < self.config.nightly_learning_time:
            return False
        return self._last_learning_date != local.date()

    def _run_nightly_learning(self, as_of: datetime):
        from trading_app.learning import (
            CandidateSpec,
            ModelRegistry,
            ModelRegistryState,
            ModelVersionRecord,
            NightlyLearningConfig,
            NightlyLearningLoop,
        )

        local_date = as_of.astimezone(MARKET_TZ).date()
        bars = self.historical_bar_fetcher.fetch_daily_bars(
            list(self.strategy.universe),
            local_date - timedelta(days=260),
            local_date,
            self.config.feed,
        )
        benchmark_bars = self.historical_bar_fetcher.fetch_daily_bars(
            ["SPY"],
            local_date - timedelta(days=260),
            local_date,
            self.config.feed,
        )
        registry = ModelRegistry()
        champion = registry.register(
            ModelVersionRecord(
                strategy_id=self.strategy.strategy_id,
                version=self.strategy.strategy_version,
                state=ModelRegistryState.PAPER,
                parameters={
                    "universe": self.strategy.universe,
                    "lookback_days": self.strategy.lookback_days,
                    "top_n": self.strategy.top_n,
                },
                hypothesis="Active Alpaca paper sector momentum model.",
                created_at=as_of,
                is_active=True,
                metadata=strategy_definition_metadata(
                    self.strategy.definition(authority=StrategyAuthority.PAPER)
                ),
            )
        )
        candidate_strategy = MonthlySectorMomentumStrategy(
            universe=self.strategy.universe,
            lookback_days=max(21, self.strategy.lookback_days // 2),
            top_n=self.strategy.top_n,
        )
        return NightlyLearningLoop(registry=registry).run(
            as_of=as_of,
            champion=champion,
            candidate_specs=(
                CandidateSpec(
                    strategy_id=self.strategy.strategy_id,
                    version=f"{self.strategy.strategy_version}-candidate",
                    parameters={
                        "universe": self.strategy.universe,
                        "lookback_days": candidate_strategy.lookback_days,
                        "top_n": self.strategy.top_n,
                    },
                    hypothesis="Shorter lookback challenger for recommendation only.",
                    parent_version=self.strategy.strategy_version,
                    metadata=strategy_definition_metadata(
                        candidate_strategy.definition(
                            authority=StrategyAuthority.RESEARCH_ONLY
                        )
                    ),
                ),
            ),
            strategy_factory=lambda params: MonthlySectorMomentumStrategy(**params),
            bars=bars,
            benchmark_bars=benchmark_bars,
            config=NightlyLearningConfig(
                auto_shadow_approved_candidates=False,
                min_score_delta_for_shadow=-1.0,
                min_average_excess_return=-1.0,
            ),
        )

    def _latest_data_quality_report(self, as_of: datetime):
        return MarketDataQualityChecker().assess_latest_prices(
            self._last_prices,
            symbols=self.config.symbols,
            generated_at=as_of,
        )

    def _sleep_seconds(self, as_of: datetime) -> int:
        return (
            self.config.market_poll_interval_seconds
            if _is_market_hours(as_of)
            else self.config.off_hours_poll_interval_seconds
        )

    def _status(self, events: list[RuntimeEvent]) -> RuntimeStatus:
        if any(event.severity == RuntimeEventSeverity.ERROR for event in events):
            return RuntimeStatus.BLOCKED
        if any(event.severity == RuntimeEventSeverity.WARNING for event in events):
            return RuntimeStatus.DEGRADED
        return RuntimeStatus.RUNNING

    @staticmethod
    def _event(
        timestamp: datetime,
        severity: RuntimeEventSeverity,
        category: str,
        message: str,
        evidence=(),
    ) -> RuntimeEvent:
        return RuntimeEvent(
            timestamp=timestamp,
            severity=severity,
            category=category,
            message=message,
            evidence=tuple(str(item) for item in evidence),
        )


def build_paper_strategy(model_key: str, *, universe_id: str | None = None):
    """Build an explicitly approved paper strategy by model key."""

    if model_key == DEFAULT_PAPER_MODEL_KEY:
        return MonthlySectorMomentumStrategy()
    benchmark_relative_match = _BENCHMARK_RELATIVE_MODEL_RE.match(model_key)
    if benchmark_relative_match:
        universe = _paper_strategy_universe(universe_id)
        strategy = BenchmarkRelativeStrengthETFStrategy(
            universe=universe,
            benchmark="SPY",
            lookback_days=int(benchmark_relative_match.group("lookback")),
            tracking_window_days=int(benchmark_relative_match.group("tracking")),
            top_n=int(benchmark_relative_match.group("top_n")),
        )
        strategy.strategy_version = model_key.removeprefix(
            "benchmark_relative_strength_etf:"
        )
        return strategy
    cash_rotation_match = _CASH_ROTATION_MODEL_RE.match(model_key)
    if cash_rotation_match:
        strategy = CashRotationETFStrategy(
            universe=RESEARCH_SEMICONDUCTOR_CHAMPIONS_UNIVERSE,
            lookback_days=int(cash_rotation_match.group("lookback")),
            top_n=int(cash_rotation_match.group("top_n")),
            min_breadth=_coded_decimal_percent(cash_rotation_match.group("breadth")),
        )
        strategy.strategy_version = model_key.removeprefix("cash_rotation_model:")
        return strategy
    market_drawdown_match = _MARKET_DRAWDOWN_MODEL_RE.match(model_key)
    if market_drawdown_match:
        trigger = market_drawdown_match.group("trigger")
        drawdown_symbols = ("QQQ",) if trigger == "qqq" else ("SPY", "QQQ")
        version = model_key.removeprefix("market_drawdown_circuit_breaker:")
        return MarketDrawdownCircuitBreakerStrategy(
            version=version,
            risk_symbols=("SOXX", "SMH"),
            risk_off_weights={},
            benchmark="SPY",
            momentum_lookback_days=int(market_drawdown_match.group("lookback")),
            drawdown_symbols=drawdown_symbols,
            drawdown_lookback_days=252,
            drawdown_threshold=_coded_decimal_percent(
                market_drawdown_match.group("drawdown")
            ),
            triggered_risk_exposure=_coded_decimal_percent(
                market_drawdown_match.group("risk")
            ),
            trigger_mode="any",
        )
    risk_managed_match = _RISK_MANAGED_SEMICONDUCTOR_MODEL_RE.match(model_key)
    if risk_managed_match:
        sleeve_symbol = risk_managed_match.group("sleeve").upper()
        strategy = RiskManagedSemiconductorStrategy(
            sleeve_weights={sleeve_symbol: Decimal("1")},
            risk_off_weights={},
            benchmark="SPY",
            trend_window_days=None,
            volatility_window_days=int(risk_managed_match.group("volatility")),
            target_volatility=_coded_decimal_percent(
                risk_managed_match.group("target")
            ),
        )
        strategy.strategy_version = model_key.removeprefix(
            "risk_managed_semiconductor:"
        )
        return strategy
    raise ValueError(f"unknown paper model key: {model_key}")


def default_symbols_for_paper_model(
    model_key: str,
    *,
    active_model_universe_id: str | None = None,
    shadow_challenger_model_key: str | None = None,
    shadow_challenger_model_keys: tuple[str, ...] = (),
    leaderboard_path: Path | str | None = None,
    auto_shadow_leaderboard_candidates: bool = True,
    leaderboard_shadow_candidate_count: int = DEFAULT_AUTO_LEADERBOARD_SHADOW_COUNT,
) -> tuple[str, ...]:
    shadow_keys = _dedupe_model_keys(
        shadow_challenger_model_key,
        *shadow_challenger_model_keys,
    )
    if auto_shadow_leaderboard_candidates and leaderboard_path is not None:
        leaderboard = _read_autonomous_learning_leaderboard_path(Path(leaderboard_path))
        if leaderboard is not None:
            shadow_keys = _dedupe_model_keys(
                *shadow_keys,
                *leaderboard_shadow_challenger_model_keys(
                    leaderboard,
                    active_model_key=model_key,
                    limit=leaderboard_shadow_candidate_count,
                    excluded_model_keys=shadow_keys,
                ),
            )
    symbols = set(
        _strategy_required_symbols(
            build_paper_strategy(model_key, universe_id=active_model_universe_id),
        ),
    )
    for shadow_model_key in shadow_keys:
        symbols.update(
            _strategy_required_symbols(build_paper_strategy(shadow_model_key))
        )
    return tuple(sorted(symbols))


def _paper_strategy_universe(universe_id: str | None) -> tuple[str, ...]:
    if not universe_id:
        return RESEARCH_SEMICONDUCTOR_CHAMPIONS_UNIVERSE
    try:
        return DISCOVERY_UNIVERSES[universe_id]
    except KeyError as error:
        raise ValueError(f"unknown paper model universe id: {universe_id}") from error


def leaderboard_shadow_challenger_model_keys(
    leaderboard: AutonomousLearningLeaderboard,
    *,
    active_model_key: str,
    limit: int = DEFAULT_AUTO_LEADERBOARD_SHADOW_COUNT,
    excluded_model_keys: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return top buildable leaderboard models for fast paper-phase shadowing."""

    if limit <= 0:
        return ()
    excluded = {active_model_key, *excluded_model_keys}
    selected: list[str] = []
    for entry in leaderboard.entries:
        if len(selected) >= limit:
            break
        if entry.model_key in excluded or entry.model_key in selected:
            continue
        if not _leaderboard_entry_shadow_eligible(entry):
            continue
        try:
            build_paper_strategy(entry.model_key)
        except ValueError:
            continue
        selected.append(entry.model_key)
    return tuple(selected)


def _leaderboard_entry_shadow_eligible(
    entry: AutonomousLearningLeaderboardEntry,
) -> bool:
    stress_positive = entry.stress_delta is None or entry.stress_delta > 0
    folds_positive = entry.fold_count == 0 or entry.positive_folds == entry.fold_count
    return (
        folds_positive
        and entry.full_delta > 0
        and stress_positive
        and not entry.late_entry_risk
        and entry.worst_drawdown >= -0.35
    )


def _read_autonomous_learning_leaderboard_path(
    path: Path,
) -> AutonomousLearningLeaderboard | None:
    if not path.exists():
        return None
    try:
        return AutonomousLearningLeaderboard.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return None


def _coded_decimal_percent(code: str) -> Decimal:
    return Decimal(int(code)) / Decimal("100")


def _configured_shadow_challenger_model_keys(
    config: AlwaysOnPaperRuntimeConfig,
) -> tuple[str, ...]:
    return _dedupe_model_keys(
        config.shadow_challenger_model_key,
        *config.shadow_challenger_model_keys,
    )


def _dedupe_model_keys(*model_keys: str | None) -> tuple[str, ...]:
    deduped: list[str] = []
    for model_key in model_keys:
        if model_key and model_key not in deduped:
            deduped.append(model_key)
    return tuple(deduped)


def _strategy_required_symbols(strategy) -> tuple[str, ...]:
    required_symbols = getattr(strategy, "required_symbols", None)
    if required_symbols is not None:
        return tuple(required_symbols)
    symbols = set(getattr(strategy, "universe", ()))
    benchmark = getattr(strategy, "benchmark", None)
    if benchmark:
        symbols.add(benchmark)
    return tuple(sorted(symbols))


def _strategy_history_calendar_days(strategy) -> int:
    lookbacks = (
        getattr(strategy, "lookback_days", 0),
        getattr(strategy, "tracking_window_days", 0),
        getattr(strategy, "momentum_lookback_days", 0),
        getattr(strategy, "drawdown_lookback_days", 0),
        getattr(strategy, "trend_window_days", 0) or 0,
        getattr(strategy, "relative_momentum_days", 0) or 0,
        getattr(strategy, "volatility_window_days", 0) or 0,
    )
    return max(260, max(lookbacks) * 3)


def _strategy_model_key(strategy) -> str:
    return f"{strategy.strategy_id}:{strategy.strategy_version}"


def _strategy_targets_with_metadata(strategy, bars, as_of):
    if hasattr(strategy, "generate_targets_with_metadata"):
        return strategy.generate_targets_with_metadata(bars, as_of)
    targets = strategy.generate_targets(bars, as_of)
    return (
        targets,
        f"Generated shadow targets for {_strategy_model_key(strategy)}.",
        {"adapter": "runtime_shadow", "reason": "targets_generated"},
    )


def _estimated_equity(
    snapshot: PortfolioSnapshot,
    latest_prices: dict[str, Decimal],
) -> Decimal:
    return snapshot.cash + sum(
        position.quantity * latest_prices.get(position.symbol, position.average_cost)
        for position in snapshot.positions
    )


def _managed_target_equity(
    snapshot: PortfolioSnapshot,
    latest_prices: dict[str, Decimal],
    config: AlwaysOnPaperRuntimeConfig,
) -> Decimal:
    equity = _estimated_equity(snapshot, latest_prices)
    if config.managed_capital is None:
        return equity
    if config.managed_capital <= 0:
        return Decimal("0")
    return min(config.managed_capital, equity)


def _dashboard_history_with_current(history, current):
    if history and history[-1].as_of == current.as_of:
        return history
    # Cap matches read_dashboard_portfolio_history's default to keep payloads
    # bounded while still covering multi-day windows.
    return (*history, current)[-5000:]


def _comparison_row_for_model(
    path: Path,
    model_key: str,
) -> dict[str, object] | None:
    return _comparison_rows_for_path(path).get(model_key)


def _comparison_path_universe_id(path: Path | None) -> str | None:
    if path is None:
        return None
    name = path.name.lower()
    for universe_id in sorted(DISCOVERY_UNIVERSES, key=len, reverse=True):
        if f"-{universe_id}-" in name or f"-{universe_id}." in name:
            return universe_id
    return None


def _comparison_window_sort_key(
    candidate: tuple[dict[str, object], Path],
) -> tuple[int, int, int, str]:
    row, path = candidate
    start = _optional_date(row, "comparison_start_date")
    end = _optional_date(row, "comparison_end_date")
    duration_days = (end - start).days if start is not None and end is not None else -1
    end_ordinal = end.toordinal() if end is not None else -1
    start_ordinal = start.toordinal() if start is not None else 9999999
    return (duration_days, end_ordinal, -start_ordinal, str(path))


def _build_full_comparison_index(replay_dir: Path) -> _FullComparisonIndex:
    if not replay_dir.exists():
        return _FullComparisonIndex({}, {})
    try:
        paths = sorted(
            replay_dir.glob("*-full-base-comparison.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return _FullComparisonIndex({}, {})

    rows_by_model: dict[str, list[tuple[dict[str, object], Path]]] = {}
    rows_by_path_and_model: dict[tuple[Path, str], dict[str, object]] = {}
    for path in paths:
        for model_key, row in _comparison_rows_for_path(path).items():
            rows_by_model.setdefault(model_key, []).append((row, path))
            rows_by_path_and_model[(path, model_key)] = row
    return _FullComparisonIndex(
        rows_by_model={
            model_key: tuple(rows) for model_key, rows in rows_by_model.items()
        },
        rows_by_path_and_model=rows_by_path_and_model,
    )


def _comparison_rows_for_path(path: Path) -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return {}
    comparison_metadata = {
        target_key: payload[source_key]
        for source_key, target_key in (
            ("start_date", "comparison_start_date"),
            ("end_date", "comparison_end_date"),
            ("generated_at", "comparison_generated_at"),
            ("benchmark", "comparison_benchmark"),
        )
        if source_key in payload
    }
    rows_by_model: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_key = row.get("model_key")
        if not isinstance(model_key, str) or not model_key:
            continue
        result = {str(key): value for key, value in row.items()}
        result.update(comparison_metadata)
        rows_by_model.setdefault(model_key, result)
    return rows_by_model


def _comparison_row_matches_excess(
    row: dict[str, object],
    expected_excess_return: float | None,
) -> bool:
    if expected_excess_return is None:
        return True
    actual = _optional_float(row, "excess_return")
    if actual is None:
        return False
    return abs(actual - expected_excess_return) <= 0.000001


def _optional_float(
    row: dict[str, object] | None,
    key: str,
    *,
    fallback: float | None = None,
) -> float | None:
    if row is None:
        return fallback
    value = row.get(key)
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _optional_int(row: dict[str, object] | None, key: str) -> int | None:
    if row is None:
        return None
    value = row.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(row: dict[str, object] | None, key: str) -> bool | None:
    if row is None:
        return None
    value = row.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _optional_string(row: dict[str, object] | None, key: str) -> str | None:
    if row is None:
        return None
    value = row.get(key)
    return str(value) if value not in (None, "") else None


def _optional_string_tuple(row: dict[str, object] | None, key: str) -> tuple[str, ...]:
    if row is None:
        return ()
    value = row.get(key)
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if item not in (None, ""))
    return ()


def _optional_date(row: dict[str, object] | None, key: str) -> date | None:
    value = _optional_string(row, key)
    if value is None:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _cycle_consumed_trade_date(cycle: RuntimeCycleResult) -> bool:
    if not cycle.strategy_evaluated:
        return False
    if cycle.orders_submitted:
        return True
    return cycle.status == RuntimeStatus.RUNNING


def _is_runtime_client_order_id(client_order_id: str) -> bool:
    return client_order_id.startswith("runtime-")


def _latest_runtime_submission(submissions):
    runtime_submissions = [
        submission
        for submission in submissions
        if submission.broker_submitted
        and _is_runtime_client_order_id(submission.order.id)
    ]
    if not runtime_submissions:
        return None
    return max(runtime_submissions, key=lambda submission: submission.submitted_at)


def _strategy_schedule_detail(schedule: StrategySchedule) -> str:
    if schedule == StrategySchedule.MARKET_OPEN:
        return "Market-open paper authority only"
    return "Daily-close authority only"


def _active_model_card_label(evidence: DashboardModelEvidence | None) -> str:
    if _evidence_blocks_champion_label(evidence):
        return "Paper Authority"
    return "Champion"


def _active_model_card_detail(
    schedule: StrategySchedule,
    evidence: DashboardModelEvidence | None,
) -> str:
    detail = _strategy_schedule_detail(schedule)
    if not _evidence_blocks_champion_label(evidence):
        return detail
    reason = _paper_authority_not_champion_reason(evidence)
    return f"{detail}; {reason}"


def _normalized_dashboard_evidence(
    evidence: DashboardModelEvidence,
) -> DashboardModelEvidence:
    classification = evidence.portfolio_governance_classification
    notes = evidence.portfolio_governance_notes
    if _evidence_is_semiconductor_sleeve(evidence):
        classification = "sector_sleeve"
    elif _evidence_is_inferred_portfolio_candidate(evidence):
        classification = "portfolio_candidate"
        if not notes:
            notes = ("Broad ETF universe; champion-eligible replay evidence.",)
    candidate = evidence.model_copy(
        update={
            "portfolio_governance_classification": classification,
            "portfolio_governance_notes": notes,
        }
    )
    if not _evidence_blocks_champion_label(candidate):
        return candidate
    reason = _paper_authority_not_champion_reason(evidence)
    if reason and reason not in notes:
        notes = (*notes, reason)
    return candidate.model_copy(
        update={
            "champion_eligible": False,
            "portfolio_governance_notes": notes,
        }
    )


def _evidence_blocks_champion_label(evidence: DashboardModelEvidence | None) -> bool:
    if evidence is None:
        return False
    if evidence.late_entry_risk:
        return True
    if evidence.champion_eligible is False:
        return True
    classification = (evidence.portfolio_governance_classification or "").lower()
    if classification == "unknown":
        return True
    if classification and classification not in {
        "portfolio_candidate",
        "portfolio_core",
    }:
        return True
    return _evidence_is_semiconductor_sleeve(evidence)


def _evidence_is_semiconductor_sleeve(evidence: DashboardModelEvidence) -> bool:
    universe_id = (evidence.universe_id or "").lower()
    strategy_name = (evidence.strategy_name or "").lower()
    model_key = evidence.model_key.lower()
    return (
        universe_id == "semiconductor-champions"
        or "semiconductor sleeve" in strategy_name
        or "top-semi" in model_key
        or model_key.startswith("risk_managed_semiconductor:")
    )


def _evidence_is_inferred_portfolio_candidate(
    evidence: DashboardModelEvidence,
) -> bool:
    classification = (evidence.portfolio_governance_classification or "").lower()
    universe_id = (evidence.universe_id or "").lower()
    return (
        evidence.champion_eligible is True
        and classification in {"", "unknown"}
        and not evidence.late_entry_risk
        and not _evidence_is_semiconductor_sleeve(evidence)
        and universe_id in {"macro-defensive", "broad-core", "sector-spdr"}
    )


def _paper_authority_not_champion_reason(
    evidence: DashboardModelEvidence | None,
) -> str:
    if evidence is None:
        return "champion eligibility evidence missing"
    if evidence.late_entry_risk:
        return "late-entry review blocks champion status"
    if evidence.portfolio_governance_notes:
        return evidence.portfolio_governance_notes[0]
    if _evidence_is_semiconductor_sleeve(evidence):
        return "semiconductor sleeve is not whole-portfolio champion eligible"
    classification = (evidence.portfolio_governance_classification or "").replace(
        "_",
        " ",
    )
    if classification and classification not in {
        "portfolio candidate",
        "portfolio core",
    }:
        return f"{classification} is not whole-portfolio champion eligible"
    return "not whole-portfolio champion eligible"


def _is_market_hours(as_of: datetime) -> bool:
    local = as_of.astimezone(MARKET_TZ)
    return local.weekday() < 5 and dt_time(hour=9, minute=30) <= local.time() < dt_time(
        hour=16
    )


def _round_quantity_down(quantity: Decimal) -> Decimal:
    return quantity.quantize(QUANTITY_INCREMENT, rounding=ROUND_DOWN)


def _round_quantity_up(quantity: Decimal) -> Decimal:
    return quantity.quantize(QUANTITY_INCREMENT, rounding=ROUND_UP)


def _allocation(value: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        return Decimal("Infinity")
    return value / equity


def _paper_symbol_sector(symbol: str) -> str:
    if symbol in PAPER_SEMICONDUCTOR_SYMBOLS:
        return "semiconductors"
    return symbol.lower()


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _health_tone(status: str) -> str:
    if status == "critical":
        return "danger"
    if status == "degraded":
        return "warn"
    if status == "watch":
        return "info"
    return "good"
