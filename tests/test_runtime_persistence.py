from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime import (
    AlwaysOnPaperRuntime,
    AlwaysOnPaperRuntimeConfig,
    OperatorControlAction,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, Order, OrderSide, OrderType
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
NIGHT = datetime(2026, 5, 30, 1, 0, tzinfo=UTC)


def make_runtime(
    output_dir,
    *,
    managed_capital: Decimal | None = None,
) -> AlwaysOnPaperRuntime:
    symbols = ("AAA", "BBB", "SPY")
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(symbols),
            tradable_symbols=frozenset(symbols),
        )
    )
    service = PaperTradingService(
        broker=InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000")),
        starting_cash=Decimal("10000"),
        risk_engine=risk_engine,
    )
    return AlwaysOnPaperRuntime(
        service=service,
        latest_price_fetcher=FixtureLatestPriceFetcher(
            {
                "AAA": Decimal("100"),
                "BBB": Decimal("120"),
                "SPY": Decimal("500"),
            },
            observed_at=AFTER_CLOSE,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="persistence-test"),
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"),
            lookback_days=5,
            top_n=1,
        ),
        risk_engine=risk_engine,
        config=AlwaysOnPaperRuntimeConfig(
            symbols=symbols,
            output_dir=output_dir,
            feed=DataFeed.IEX,
            managed_capital=managed_capital,
        ),
        persistence_store=RuntimePersistenceStore(output_dir),
    )


def test_runtime_persists_cycle_prices_reconciliation_and_service_state(
    tmp_path,
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.persistence_store.persist_dashboard_snapshot(
        runtime.dashboard_snapshot(as_of=AFTER_CLOSE - timedelta(days=1))
    )

    result = runtime.run_once(as_of=AFTER_CLOSE)
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert result.orders_submitted == 1
    assert recovered.latest_prices is not None
    assert recovered.last_cycle == result
    assert recovered.daily_report is not None
    assert recovered.dashboard_snapshot is not None
    assert recovered.dashboard_snapshot.mode == "Alpaca Paper"
    assert recovered.dashboard_snapshot.portfolio_history
    assert recovered.dashboard_snapshot.portfolio_history[-1].estimated_equity == (
        recovered.dashboard_snapshot.estimated_equity
    )
    # portfolio_history now returns the full multi-day journal so the
    # dashboard can render any selected period. This single-cycle test only
    # produced one trading day's worth of data, but the dashboard chart is
    # no longer responsible for the trim.
    assert AFTER_CLOSE.date() in {
        point.as_of.date() for point in recovered.dashboard_snapshot.portfolio_history
    }
    assert RuntimePersistenceStore(tmp_path).read_dashboard_portfolio_history()
    assert recovered.submissions[0].order.symbol in {"AAA", "BBB"}
    assert recovered.order_statuses[0].order_id == recovered.submissions[0].order.id
    assert (tmp_path / "state" / "latest-reconciliation.json").exists()
    assert (tmp_path / "state" / "latest-runtime-snapshot.json").exists()
    assert (tmp_path / "state" / "latest-dashboard-snapshot.json").exists()
    assert (tmp_path / "journal" / "dashboard-portfolio-history.jsonl").exists()
    assert (tmp_path / "journal" / "submissions.jsonl").exists()


def test_runtime_dashboard_snapshot_for_api_uses_persisted_snapshot(tmp_path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.apply_control(
        OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
        requested_at=AFTER_CLOSE - timedelta(days=2),
    )
    persisted = runtime.dashboard_snapshot(as_of=AFTER_CLOSE - timedelta(days=1))
    runtime.persistence_store.persist_dashboard_snapshot(persisted)
    runtime.apply_control(
        OperatorControlAction.DISABLE_PAPER_KILL_SWITCH,
        requested_at=AFTER_CLOSE,
    )

    api_snapshot = runtime.dashboard_snapshot_for_api()

    assert api_snapshot.generated_at == persisted.generated_at
    assert api_snapshot.mode == "Alpaca Paper"
    assert not api_snapshot.kill_switch_enabled
    assert not api_snapshot.control_state.paper_kill_switch_enabled


def test_optional_autonomous_learning_files_fail_soft(tmp_path) -> None:
    store = RuntimePersistenceStore(tmp_path)
    store.ensure()
    (tmp_path / "learning" / "latest-learning-cycle.json").write_text(
        '{"candidate_readiness": {}}',
        encoding="utf-8",
    )
    (tmp_path / "learning" / "learning-leaderboard.json").write_text(
        '{"entries":"stale"}',
        encoding="utf-8",
    )
    (tmp_path / "learning" / "latest-autonomous-service-state.json").write_text(
        '{"service_status":"stale"}',
        encoding="utf-8",
    )

    assert store.read_autonomous_learning_cycle() is None
    assert store.read_autonomous_learning_leaderboard() is None
    assert store.read_autonomous_learning_service_state() is None
    recovered = store.recover()
    assert recovered.autonomous_learning is None
    assert recovered.autonomous_learning_service is None


def test_dashboard_snapshot_persistence_writes_compact_portfolio_history(
    tmp_path,
) -> None:
    store = RuntimePersistenceStore(tmp_path)
    snapshot = build_demo_dashboard_snapshot().model_copy(
        update={"generated_at": AFTER_CLOSE}
    )

    store.persist_dashboard_snapshot(snapshot)

    history = store.read_dashboard_portfolio_history()

    assert (tmp_path / "state" / "latest-dashboard-snapshot.json").exists()
    assert (tmp_path / "journal" / "dashboard-portfolio-history.jsonl").exists()
    assert not (tmp_path / "journal" / "dashboard-snapshots.jsonl").exists()
    assert len(history) == 1
    assert history[0].as_of == AFTER_CLOSE
    assert history[0].estimated_equity == snapshot.estimated_equity
    assert history[0].cash == snapshot.cash
    assert history[0].realized_pnl == snapshot.realized_pnl


def test_dashboard_portfolio_history_falls_back_to_legacy_snapshot_journal(
    tmp_path,
) -> None:
    store = RuntimePersistenceStore(tmp_path)
    store.ensure()
    snapshot = build_demo_dashboard_snapshot().model_copy(
        update={"generated_at": AFTER_CLOSE}
    )
    legacy_path = tmp_path / "journal" / "dashboard-snapshots.jsonl"
    legacy_path.write_text(
        "\n".join(("{not-json", snapshot.model_dump_json())),
        encoding="utf-8",
    )

    history = store.read_dashboard_portfolio_history(limit=10)

    assert len(history) == 1
    assert history[0].as_of == AFTER_CLOSE
    assert history[0].estimated_equity == snapshot.estimated_equity


def test_managed_capital_increase_triggers_same_day_rebalance(tmp_path) -> None:
    first_runtime = make_runtime(tmp_path, managed_capital=Decimal("100"))
    first_cycle = first_runtime.run_once(as_of=AFTER_CLOSE)
    assert first_cycle.orders_submitted == 1
    first_submission = first_runtime.service.submissions[0]
    fill = first_runtime.service.broker.fill_order(
        first_submission.order.id,
        price=Decimal("100"),
        filled_at=AFTER_CLOSE + timedelta(minutes=1),
    )
    first_runtime.service.ingest_fill_event(fill)
    first_runtime.persistence_store.persist_service_state(first_runtime.service)

    first_runtime.config = replace(
        first_runtime.config,
        managed_capital=Decimal("5000"),
    )
    larger_cycle = first_runtime.run_once(as_of=AFTER_CLOSE + timedelta(minutes=5))

    assert larger_cycle.strategy_evaluated
    assert larger_cycle.orders_submitted == 1


def test_paper_service_restores_ledger_from_persisted_orders_and_fills(
    tmp_path,
) -> None:
    runtime = make_runtime(tmp_path)
    order = Order(
        id="persisted-order",
        symbol="AAA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("2"),
        created_at=AFTER_CLOSE,
    )
    runtime.service.submit_order(
        order,
        strategy_id="manual",
        estimated_price=Decimal("100"),
        latest_prices={"AAA": Decimal("100")},
        as_of=AFTER_CLOSE,
    )
    event = runtime.service.broker.fill_order(
        "persisted-order",
        price=Decimal("100"),
        filled_at=AFTER_CLOSE,
    )
    runtime.service.ingest_fill_event(event)
    runtime.persistence_store.persist_service_state(runtime.service)

    fresh_service = PaperTradingService(
        broker=InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000")),
        starting_cash=Decimal("10000"),
    )
    store = RuntimePersistenceStore(tmp_path)
    first_recovery = store.restore_service(fresh_service)
    second_recovery = store.restore_service(fresh_service)

    assert len(first_recovery.fills) == 1
    assert len(second_recovery.fills) == 1
    assert fresh_service.ledger.cash == Decimal("9800")
    assert fresh_service.ledger.get_position("AAA").quantity == Decimal("2")
    assert fresh_service.ledger.filled_quantity("persisted-order") == Decimal("2")
    assert len(fresh_service.fills) == 1
    assert fresh_service.portfolio_report(as_of=AFTER_CLOSE).tax_summary.active_lots[
        0
    ].remaining_quantity == Decimal("2")


def test_restarted_runtime_recovers_and_does_not_double_trade_same_day(
    tmp_path,
) -> None:
    first_runtime = make_runtime(tmp_path)
    first_cycle = first_runtime.run_once(as_of=AFTER_CLOSE)

    restarted = make_runtime(tmp_path)
    second_cycle = restarted.run_once(as_of=AFTER_CLOSE)

    assert first_cycle.orders_submitted == 1
    assert restarted.service.ledger.get_order(
        first_runtime.service.submissions[0].order.id
    )
    assert second_cycle.strategy_evaluated is False
    assert second_cycle.orders_submitted == 0


def test_runtime_persists_report_and_learning_outputs(tmp_path) -> None:
    runtime = make_runtime(tmp_path)

    result = runtime.run_once(as_of=NIGHT)
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert result.report_written
    assert result.nightly_learning_ran
    assert recovered.daily_report is not None
    assert recovered.daily_report.active_strategy_definition is not None
    assert recovered.daily_report.active_strategy_definition.strategy_id == (
        "monthly_sector_momentum"
    )
    assert recovered.nightly_learning is not None
    assert recovered.daily_report_path is not None
    assert recovered.daily_report_path.exists()
    assert recovered.learning_report_path is not None
    assert recovered.learning_report_path.exists()
    assert recovered.learning_report_path.read_text(encoding="utf-8").startswith(
        "# Nightly Learning Recommendation Memo"
    )
    assert (tmp_path / "learning" / f"{recovered.nightly_learning.id}.json").exists()
    assert (tmp_path / "learning" / f"{recovered.nightly_learning.id}.md").exists()
