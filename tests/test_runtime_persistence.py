from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime import AlwaysOnPaperRuntime, AlwaysOnPaperRuntimeConfig
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, Order, OrderSide, OrderType
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
NIGHT = datetime(2026, 5, 30, 1, 0, tzinfo=UTC)


def make_runtime(output_dir) -> AlwaysOnPaperRuntime:
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
        ),
        persistence_store=RuntimePersistenceStore(output_dir),
    )


def test_runtime_persists_cycle_prices_reconciliation_and_service_state(
    tmp_path,
) -> None:
    runtime = make_runtime(tmp_path)

    result = runtime.run_once(as_of=AFTER_CLOSE)
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert result.orders_submitted == 1
    assert recovered.latest_prices is not None
    assert recovered.last_cycle == result
    assert recovered.daily_report is not None
    assert recovered.dashboard_snapshot is not None
    assert recovered.dashboard_snapshot.mode == "Alpaca Paper"
    assert recovered.submissions[0].order.symbol in {"AAA", "BBB"}
    assert recovered.order_statuses[0].order_id == recovered.submissions[0].order.id
    assert (tmp_path / "state" / "latest-reconciliation.json").exists()
    assert (tmp_path / "state" / "latest-runtime-snapshot.json").exists()
    assert (tmp_path / "state" / "latest-dashboard-snapshot.json").exists()
    assert (tmp_path / "journal" / "dashboard-snapshots.jsonl").exists()
    assert (tmp_path / "journal" / "submissions.jsonl").exists()


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
