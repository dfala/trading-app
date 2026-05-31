"""Build deterministic operator dashboard data from the existing engine."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_app.broker import (
    BrokerPositionState,
    BrokerStatementSnapshot,
    InMemoryPaperBrokerAdapter,
)
from trading_app.dashboard.models import (
    DashboardMetric,
    DashboardModelCard,
    OperatorDashboardSnapshot,
)
from trading_app.learning import (
    CandidateSpec,
    ModelArena,
    ModelEvidenceRecord,
    ModelEvidenceType,
    ModelMetricSet,
    ModelRegistry,
    ModelRegistryState,
    ModelVersionRecord,
    NightlyLearningConfig,
    NightlyLearningLoop,
)
from trading_app.live import (
    EnvironmentMode,
    LiveReadinessGate,
    LiveRiskLimits,
    LiveTradingConfig,
)
from trading_app.market_data import FixtureLatestPriceFetcher, MarketDataQualityChecker
from trading_app.paper import (
    MarketDataRefresh,
    MarketDataRefreshStatus,
    PaperSessionMode,
    PaperSessionState,
    PaperTradingService,
    SessionConnectionStatus,
    reconcile_statement_snapshot,
)
from trading_app.reporting import DailyReportGenerator
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime.models import (
    OperatorControlState,
    RuntimeAlert,
    RuntimeAlertCode,
    RuntimeEventSeverity,
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimeIncident,
)
from trading_app.schemas import (
    DailyBar,
    DataFeed,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading_app.strategies import StrategyAuthority
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy


def build_demo_dashboard_snapshot() -> OperatorDashboardSnapshot:
    """Create a dashboard snapshot using local deterministic paper data."""

    as_of = datetime(2026, 5, 29, 16, tzinfo=UTC)
    active_strategy = MonthlySectorMomentumStrategy()
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    risk_engine = RiskEngine(
        RiskConfig(
            us_tradable_universe=frozenset({"SPY"}),
            tradable_symbols=frozenset({"SPY"}),
            max_orders_per_day=1,
        )
    )
    service = PaperTradingService(
        broker=broker,
        starting_cash=Decimal("10000"),
        risk_engine=risk_engine,
    )
    accepted_order = Order(
        id="daily-order-1",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("5"),
        created_at=as_of,
    )
    service.submit_order(
        accepted_order,
        strategy_id="sector_momentum",
        estimated_price=Decimal("500"),
        latest_prices={"SPY": Decimal("500")},
        as_of=as_of,
    )
    service.ingest_fill_event(
        broker.fill_order(
            accepted_order.id,
            price=Decimal("500"),
            filled_at=as_of,
        )
    )
    rejected_order = Order(
        id="daily-order-2",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=as_of,
    )
    service.submit_order(
        rejected_order,
        strategy_id="sector_momentum",
        estimated_price=Decimal("505"),
        latest_prices={"SPY": Decimal("505")},
        as_of=as_of,
    )

    paper_report = service.portfolio_report(as_of=as_of)
    statement_report = reconcile_statement_snapshot(
        paper_report.ledger_snapshot,
        BrokerStatementSnapshot(
            statement_id="statement-2026-05-29",
            as_of=as_of,
            provider=broker.provider,
            account_id="paper-demo",
            cash=paper_report.ledger_snapshot.cash,
            positions=tuple(
                BrokerPositionState(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    average_entry_price=position.average_cost,
                )
                for position in paper_report.ledger_snapshot.positions
            ),
            source="dashboard-demo-statement",
        ),
        as_of=as_of,
    )
    latest_snapshot = FixtureLatestPriceFetcher(
        {"SPY": Decimal("500")},
        observed_at=as_of,
        source="dashboard-demo",
    ).fetch_latest_prices(("SPY",), as_of=as_of, feed=DataFeed.IEX)
    data_quality_report = MarketDataQualityChecker().assess_latest_prices(
        latest_snapshot,
        symbols=("SPY",),
        generated_at=as_of,
    )
    daily_report = DailyReportGenerator().build(
        paper_report,
        generated_at=as_of,
        data_quality_report=data_quality_report,
        active_strategy_definition=active_strategy.definition(
            authority=StrategyAuthority.PAPER
        ),
    )
    nightly_learning = _nightly_learning(as_of=datetime(2026, 5, 29, 23, tzinfo=UTC))
    comparison = nightly_learning.comparisons[0]
    active_key = nightly_learning.registry_after.active_keys[0]
    open_orders = sum(
        1
        for status in paper_report.order_statuses
        if status.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
    )
    model_cards = (
        DashboardModelCard(
            label="Champion",
            strategy_id=comparison.champion.strategy_id,
            version=comparison.champion.version,
            state=comparison.champion.state.value,
            score=comparison.champion_score,
            detail=f"Active: {active_key}",
        ),
        DashboardModelCard(
            label="Challenger",
            strategy_id=comparison.challenger.strategy_id,
            version=comparison.challenger.version,
            state=nightly_learning.registry_after.records[1].state.value,
            score=comparison.challenger_score,
            detail=nightly_learning.recommendations[0].rationale,
        ),
    )
    metrics = (
        DashboardMetric(
            label="Paper cash",
            value=_money(daily_report.pnl_report.ending_cash),
            detail="Internal ledger balance",
            tone="good",
        ),
        DashboardMetric(
            label="Estimated equity",
            value=_money(daily_report.pnl_report.estimated_equity),
            detail="Cash plus paper positions",
            tone="good",
        ),
        DashboardMetric(
            label="Risk decisions",
            value=str(daily_report.risk_report.risk_decisions),
            detail=f"{daily_report.risk_report.rejection_count} rejection",
            tone="warn",
        ),
        DashboardMetric(
            label="Learning safety",
            value="Locked",
            detail="Active model unchanged",
            tone="info",
        ),
    )
    return OperatorDashboardSnapshot(
        generated_at=as_of,
        mode="Paper Trading",
        broker=broker.provider,
        data_feed_status="IEX development-grade demo feed",
        kill_switch_enabled=risk_engine.config.kill_switch_enabled,
        cash=daily_report.pnl_report.ending_cash,
        estimated_equity=daily_report.pnl_report.estimated_equity,
        realized_pnl=daily_report.pnl_report.realized_pnl,
        open_orders=open_orders,
        recent_fills=service.fills,
        paper_report=paper_report,
        daily_report=daily_report,
        nightly_learning=nightly_learning,
        metrics=metrics,
        model_cards=model_cards,
        session_state=PaperSessionState(
            as_of=as_of,
            mode=PaperSessionMode.DEMO,
            provider=broker.provider,
            connection_status=SessionConnectionStatus.CONNECTED,
            market_data=MarketDataRefresh(
                as_of=as_of,
                symbols=("SPY",),
                feed=DataFeed.IEX,
                source="dashboard-demo",
                prices={"SPY": Decimal("500")},
                status=MarketDataRefreshStatus.FRESH,
                warning=(
                    "IEX/free data is development-grade and should not drive "
                    "final funding decisions."
                ),
            ),
            portfolio_report=paper_report,
            open_order_count=open_orders,
        ),
        model_arena=_demo_model_arena(as_of),
        live_readiness=_demo_live_readiness(as_of),
        control_state=OperatorControlState(
            paused=False,
            paper_kill_switch_enabled=False,
            updated_at=as_of,
            updated_by="system",
            reason="demo snapshot",
        ),
        alerts=(
            RuntimeAlert(
                id="demo-risk-rejection",
                created_at=as_of,
                severity=RuntimeEventSeverity.WARNING,
                code=RuntimeAlertCode.RISK_REJECTION,
                title="Risk rejected an order",
                message="Demo max-orders rule rejected the second paper order.",
                evidence=("daily-order-2", "SPY", "MAX_ORDERS_PER_DAY"),
            ),
        ),
        health_report=_demo_health_report(as_of),
        statement_reconciliation=statement_report,
        statement_reconciliation_path=(
            "data/runtime/reports/statement-reconciliation-statement-2026-05-29.md"
        ),
        active_strategy_definition=active_strategy.definition(
            authority=StrategyAuthority.PAPER
        ),
    )


def _demo_health_report(as_of: datetime) -> RuntimeHealthReport:
    return RuntimeHealthReport(
        as_of=as_of,
        status=RuntimeHealthStatus.DEGRADED,
        summary="Demo paper runtime is healthy except for one risk rejection.",
        next_action="Review the rejected demo order before trusting the strategy.",
        checks=(
            RuntimeHealthCheck(
                name="runtime_loop",
                status=RuntimeHealthStatus.HEALTHY,
                message="Demo runtime heartbeat is fresh.",
                checked_at=as_of,
            ),
            RuntimeHealthCheck(
                name="reconciliation",
                status=RuntimeHealthStatus.HEALTHY,
                message="Broker and internal ledger reconciliation is clean.",
                checked_at=as_of,
            ),
            RuntimeHealthCheck(
                name="alerts",
                status=RuntimeHealthStatus.DEGRADED,
                message="One demo warning alert is active.",
                checked_at=as_of,
                evidence=("risk_rejection",),
            ),
        ),
        incidents=(
            RuntimeIncident(
                id="demo-risk-rejection",
                opened_at=as_of,
                status=RuntimeHealthStatus.DEGRADED,
                title="Risk rejected an order",
                summary="Demo max-orders rule rejected the second paper order.",
                suggested_action="Review the rejected order before changing strategy.",
                evidence=("daily-order-2", "SPY", "MAX_ORDERS_PER_DAY"),
            ),
        ),
    )


def _nightly_learning(*, as_of: datetime):
    bars, benchmark_bars = _learning_bars()
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
    return NightlyLearningLoop(registry=registry).run(
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


def _demo_model_arena(as_of: datetime):
    registry = ModelRegistry()
    champion = registry.register(
        ModelVersionRecord(
            strategy_id="monthly_sector_momentum",
            version="1.0.0",
            state=ModelRegistryState.PAPER,
            parameters={"lookback_days": 126, "top_n": 3},
            hypothesis="Baseline sector ETF momentum champion.",
            created_at=as_of,
            is_active=True,
        )
    )
    challenger = registry.register(
        ModelVersionRecord(
            strategy_id="monthly_sector_momentum",
            version="1.1.0",
            state=ModelRegistryState.VALIDATED,
            parameters={"lookback_days": 84, "top_n": 3},
            hypothesis="Faster sector momentum lookback after regime changes.",
            created_at=as_of,
            parent_version="1.0.0",
        )
    )
    arena = ModelArena(registry=registry)
    champion_evidence = arena.record_evidence(
        ModelEvidenceRecord(
            id="evidence-champion-paper",
            model_key=champion.key,
            evidence_type=ModelEvidenceType.PAPER,
            recorded_at=as_of,
            start_date=date(2026, 1, 1),
            end_date=as_of.date(),
            benchmark="SPY",
            data_source="paper-ledger-demo",
            metrics=ModelMetricSet(
                gross_total_return=0.042,
                net_total_return=0.039,
                benchmark_total_return=0.031,
                max_drawdown=-0.048,
                annualized_volatility=0.14,
                turnover=0.62,
                trade_count=18,
                average_holding_period_days=31,
                estimated_after_tax_total_return=0.028,
            ),
            cost_assumptions={"slippage_bps": 5, "commission_per_trade": 0},
            tax_assumptions={"status": "estimated"},
            risk_settings={"no_short_selling": True, "no_margin": True},
            notes="Champion paper evidence remains stable.",
        )
    )
    challenger_evidence = arena.record_evidence(
        ModelEvidenceRecord(
            id="evidence-challenger-walk-forward",
            model_key=challenger.key,
            evidence_type=ModelEvidenceType.WALK_FORWARD,
            recorded_at=as_of,
            start_date=date(2025, 1, 1),
            end_date=as_of.date(),
            benchmark="SPY",
            data_source="fixture-walk-forward",
            metrics=ModelMetricSet(
                gross_total_return=0.061,
                net_total_return=0.055,
                benchmark_total_return=0.031,
                max_drawdown=-0.044,
                annualized_volatility=0.15,
                turnover=0.74,
                trade_count=22,
                average_holding_period_days=24,
                estimated_after_tax_total_return=0.039,
            ),
            cost_assumptions={"slippage_bps": 5, "commission_per_trade": 0},
            tax_assumptions={"status": "estimated"},
            risk_settings={"no_short_selling": True, "no_margin": True},
            notes="Challenger cleared walk-forward evidence for shadow review.",
            failure_modes=("May overreact in sideways markets.",),
        )
    )
    comparison = arena.compare(
        champion=champion,
        challenger=challenger,
        champion_evidence_id=champion_evidence.id,
        challenger_evidence_id=challenger_evidence.id,
    )
    arena.request_promotion(
        request_id="promote-challenger-shadow",
        strategy_id=challenger.strategy_id,
        version=challenger.version,
        target_state=ModelRegistryState.SHADOW,
        evidence_ids=(challenger_evidence.id,),
        created_at=as_of,
        rationale=comparison.rationale,
        recommendation=comparison.recommendation,
    )
    return arena.snapshot(as_of=as_of)


def _demo_live_readiness(as_of: datetime):
    gate = LiveReadinessGate(
        config=LiveTradingConfig(
            mode=EnvironmentMode.LIVE_READINESS,
            paper_account_id="paper-demo-account",
            live_account_id="live-demo-account",
            live_trading_enabled=False,
        ),
        limits=LiveRiskLimits(
            max_live_allocation=Decimal("1000"),
            max_daily_loss=Decimal("50"),
            max_order_notional=Decimal("250"),
            max_orders_per_day=2,
            allowed_symbols=("SPY", "XLK"),
        ),
    )
    return gate.build_report(
        as_of=as_of,
        paper_trading_days=42,
        candidate_model_key="monthly_sector_momentum:1.1.0",
        candidate_model_state="candidate_live",
        risk_engine_active=True,
        kill_switch_tested=True,
        broker_reconciled=True,
        data_feed_fresh=True,
        limits_configured=True,
        user_reviewed_assumptions=True,
        explicit_user_approval=True,
    )


def _learning_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
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
        source="dashboard-demo",
        data_feed=DataFeed.IEX,
    )


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"
