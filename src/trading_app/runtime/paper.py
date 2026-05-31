"""Always-on Alpaca paper runtime."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from trading_app.broker import AlpacaPaperBrokerAdapter
from trading_app.dashboard.models import DashboardMetric, DashboardModelCard
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
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime.health import RuntimeHealthEngine
from trading_app.runtime.models import (
    OperatorControlAction,
    OperatorControlRequest,
    OperatorControlResult,
    RuntimeCycleResult,
    RuntimeEvent,
    RuntimeEventSeverity,
    RuntimeSnapshot,
    RuntimeStatus,
)
from trading_app.runtime.operator import RuntimeAlertEngine, RuntimeControlCenter
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, Order, OrderSide, OrderStatus, OrderType
from trading_app.strategies.catalog import (
    StrategyAuthority,
    strategy_definition_metadata,
)
from trading_app.strategies.sector_momentum import (
    DEFAULT_SECTOR_ETFS,
    MonthlySectorMomentumStrategy,
)

MARKET_TZ = ZoneInfo("America/New_York")
QUANTITY_INCREMENT = Decimal("0.000001")


@dataclass(frozen=True)
class AlwaysOnPaperRuntimeConfig:
    symbols: tuple[str, ...] = (*DEFAULT_SECTOR_ETFS, "SPY")
    starting_cash: Decimal = Decimal("100000")
    feed: DataFeed = DataFeed.IEX
    output_dir: Path = Path("data/runtime")
    latest_price_max_age: timedelta = timedelta(minutes=15)
    market_poll_interval_seconds: int = 60
    off_hours_poll_interval_seconds: int = 900
    trade_after_close_time: dt_time = dt_time(hour=16, minute=5)
    nightly_learning_time: dt_time = dt_time(hour=20)
    strategy_cash_buffer: Decimal = Decimal("0.01")


class AlwaysOnPaperRuntime:
    """Coordinate Alpaca paper monitoring, trading, reports, and learning."""

    def __init__(
        self,
        *,
        service: PaperTradingService,
        latest_price_fetcher: LatestPriceFetcher,
        historical_bar_fetcher: HistoricalBarFetcher,
        strategy: MonthlySectorMomentumStrategy | None = None,
        risk_engine: RiskEngine | None = None,
        config: AlwaysOnPaperRuntimeConfig | None = None,
        persistence_store: RuntimePersistenceStore | None = None,
        control_center: RuntimeControlCenter | None = None,
        alert_engine: RuntimeAlertEngine | None = None,
        health_engine: RuntimeHealthEngine | None = None,
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
        self.strategy = strategy or MonthlySectorMomentumStrategy()
        self.risk_engine = risk_engine or service.risk_engine
        self.control_center = control_center or RuntimeControlCenter()
        self.alert_engine = alert_engine or RuntimeAlertEngine()
        self.health_engine = health_engine or RuntimeHealthEngine()
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
        self._last_trade_date: date | None = None
        self._last_rebalance_month: tuple[int, int] | None = None
        self._last_report_date: date | None = None
        self._last_learning_date: date | None = None
        self._restore_from_persistence()

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
        if not paper_report.reconciliation.reconciled:
            events.append(
                self._event(
                    now,
                    RuntimeEventSeverity.WARNING,
                    "reconciliation",
                    "Broker reconciliation is not clean; new paper orders are blocked.",
                )
            )

        if self._should_evaluate_strategy(now):
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
                    submitted = self._evaluate_strategy(now, paper_report, events)
                    orders_submitted = submitted
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
        self.persistence_store.persist_dashboard_snapshot(
            self.dashboard_snapshot(as_of=now)
        )
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
        daily_report = self._last_report or DailyReportGenerator().build(
            paper_report,
            generated_at=now,
            data_quality_report=self._latest_data_quality_report(now),
            active_strategy_definition=self.strategy.definition(
                authority=StrategyAuthority.PAPER
            ),
        )
        return RuntimeSnapshot(
            as_of=now,
            status=self._last_cycle.status
            if self._last_cycle
            else RuntimeStatus.RUNNING,
            mode="Alpaca Paper",
            latest_prices=self._last_prices,
            paper_report=paper_report,
            daily_report=daily_report,
            nightly_learning=self._last_learning_run,
            active_model_key=(
                f"{self.strategy.strategy_id}:{self.strategy.strategy_version}"
            ),
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
        )

    def dashboard_snapshot(self, *, as_of: datetime | None = None):
        from trading_app.dashboard.models import OperatorDashboardSnapshot

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
        metrics = (
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
            open_orders=open_orders,
            recent_fills=self.service.fills,
            paper_report=paper_report,
            daily_report=daily_report,
            nightly_learning=runtime_snapshot.nightly_learning,
            metrics=metrics,
            model_cards=(
                DashboardModelCard(
                    label="Active Paper Model",
                    strategy_id=self.strategy.strategy_id,
                    version=self.strategy.strategy_version,
                    state="paper",
                    score=0.0,
                    detail="Daily-close authority only",
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

    def _restore_from_persistence(self) -> None:
        recovered = self.persistence_store.restore_service(self.service)
        self._last_prices = recovered.latest_prices
        self._last_cycle = recovered.last_cycle
        self._last_report = recovered.daily_report
        self._last_report_path = recovered.daily_report_path
        self._last_learning_run = recovered.nightly_learning
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
        if recovered.last_cycle and recovered.last_cycle.strategy_evaluated:
            local_date = recovered.last_cycle.as_of.astimezone(MARKET_TZ).date()
            self._last_trade_date = local_date
        if recovered.last_cycle and recovered.last_cycle.orders_submitted:
            local_date = recovered.last_cycle.as_of.astimezone(MARKET_TZ).date()
            self._last_rebalance_month = (local_date.year, local_date.month)
        if recovered.daily_report:
            self._last_report_date = recovered.daily_report.trading_day
        if recovered.nightly_learning:
            self._last_learning_date = recovered.nightly_learning.as_of.astimezone(
                MARKET_TZ
            ).date()

    def _portfolio_report(
        self,
        as_of: datetime,
        *,
        events: list[RuntimeEvent] | None = None,
    ):
        try:
            paper_report = self.service.portfolio_report(as_of=as_of)
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
            client_order_id = broker_order.client_order_id
            if (
                not client_order_id
                or self.service.ledger.get_order(client_order_id) is None
            ):
                continue
            _, fill = self.service.sync_broker_order_state(broker_order, as_of=as_of)
            if fill is not None:
                self.persistence_store.persist_fill(fill)
                fills_applied += 1
        return fills_applied

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
        month_key = (local_date.year, local_date.month)
        portfolio_empty = not paper_report.ledger_snapshot.positions
        if self._last_rebalance_month == month_key and not portfolio_empty:
            return 0

        bars = self.historical_bar_fetcher.fetch_daily_bars(
            list(self.strategy.universe),
            local_date - timedelta(days=260),
            local_date,
            self.config.feed,
        )
        targets = self.strategy.generate_targets(bars, local_date)
        if not targets:
            return 0

        submitted = self._submit_rebalance_orders(
            as_of=as_of,
            targets=targets,
            latest_prices=self._last_prices.price_map,
            events=events,
        )
        if submitted:
            self._last_rebalance_month = month_key
        return submitted

    def _submit_rebalance_orders(
        self,
        *,
        as_of: datetime,
        targets: dict[str, Decimal],
        latest_prices: dict[str, Decimal],
        events: list[RuntimeEvent],
    ) -> int:
        snapshot = self.service.ledger.snapshot(as_of)
        equity = snapshot.cash + sum(
            position.quantity
            * latest_prices.get(position.symbol, position.average_cost)
            for position in snapshot.positions
        )
        submitted = 0
        current_positions = {
            position.symbol: position for position in snapshot.positions
        }
        target_values = {symbol: equity * weight for symbol, weight in targets.items()}

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
                    quantity=_round_quantity_down(min(quantity, position.quantity)),
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
        )
        self.persistence_store.persist_submission(submission)
        for status in self.service.order_statuses:
            if status.order_id == order.id:
                self.persistence_store.persist_order_status(status)
        return 1 if submission.accepted and submission.broker_submitted else 0

    def _should_evaluate_strategy(self, as_of: datetime) -> bool:
        local = as_of.astimezone(MARKET_TZ)
        if local.weekday() >= 5:
            return False
        if local.time() < self.config.trade_after_close_time:
            return False
        return self._last_trade_date != local.date()

    def _should_write_daily_report(self, as_of: datetime) -> bool:
        local = as_of.astimezone(MARKET_TZ)
        if local.weekday() >= 5 or local.time() < self.config.trade_after_close_time:
            return False
        return self._last_report_date != local.date()

    def _should_run_nightly_learning(self, as_of: datetime) -> bool:
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


def _is_market_hours(as_of: datetime) -> bool:
    local = as_of.astimezone(MARKET_TZ)
    return local.weekday() < 5 and dt_time(hour=9, minute=30) <= local.time() < dt_time(
        hour=16
    )


def _round_quantity_down(quantity: Decimal) -> Decimal:
    return quantity.quantize(QUANTITY_INCREMENT, rounding=ROUND_DOWN)


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
