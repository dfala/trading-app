from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime import (
    AlwaysOnPaperRuntime,
    AlwaysOnPaperRuntimeConfig,
    RuntimeCompletionAuditor,
)
from trading_app.runtime.models import RuntimeStatus
from trading_app.schemas import DataFeed, Order, OrderSide, OrderType
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
NIGHT = datetime(2026, 5, 30, 1, 0, tzinfo=UTC)


class FailingLatestPriceFetcher:
    def fetch_latest_prices(self, *_args, **_kwargs):
        raise RuntimeError("latest price feed unavailable")


class FailingHistoricalBarFetcher:
    def fetch_daily_bars(self, *_args, **_kwargs):
        raise RuntimeError("historical bars unavailable")


def make_runtime(
    *,
    latest_observed_at: datetime = AFTER_CLOSE,
    output_dir=None,
) -> AlwaysOnPaperRuntime:
    symbols = ("AAA", "BBB", "SPY")
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(symbols),
            tradable_symbols=frozenset(symbols),
        )
    )
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    service = PaperTradingService(
        broker=broker,
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
            observed_at=latest_observed_at,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="runtime-test"),
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"),
            lookback_days=5,
            top_n=1,
        ),
        risk_engine=risk_engine,
        config=AlwaysOnPaperRuntimeConfig(
            symbols=symbols,
            output_dir=output_dir or AlwaysOnPaperRuntimeConfig().output_dir,
            feed=DataFeed.IEX,
        ),
    )


def test_daily_close_runtime_submits_paper_orders_once_per_day(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)

    first = runtime.run_once(as_of=AFTER_CLOSE)
    second = runtime.run_once(as_of=AFTER_CLOSE + timedelta(minutes=5))

    assert first.strategy_evaluated
    assert first.orders_submitted == 1
    assert first.report_written
    assert second.orders_submitted == 0
    assert len(runtime.service.submissions) == 1
    assert runtime.service.submissions[0].broker_submitted


def test_runtime_blocks_paper_orders_when_latest_prices_are_stale(tmp_path) -> None:
    runtime = make_runtime(
        latest_observed_at=AFTER_CLOSE - timedelta(hours=2),
        output_dir=tmp_path,
    )

    result = runtime.run_once(as_of=AFTER_CLOSE)

    assert result.status == RuntimeStatus.DEGRADED
    assert result.strategy_evaluated
    assert result.orders_submitted == 0
    assert "stale" in result.events[0].message


def test_runtime_blocks_orders_when_current_price_refresh_fails(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.run_once(as_of=AFTER_CLOSE - timedelta(hours=1))
    runtime.latest_price_fetcher = FailingLatestPriceFetcher()

    result = runtime.run_once(as_of=AFTER_CLOSE)
    snapshot = runtime.snapshot(as_of=AFTER_CLOSE)

    assert result.status == RuntimeStatus.BLOCKED
    assert not result.prices_refreshed
    assert not result.strategy_evaluated
    assert result.orders_submitted == 0
    assert snapshot.latest_prices is None
    assert any(event.category == "strategy" for event in result.events)


def test_runtime_syncs_incremental_broker_fill_exactly_once(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    order = Order(
        id="manual-paper-order",
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
    runtime.service.broker.fill_order(
        "manual-paper-order",
        price=Decimal("100"),
        quantity=Decimal("1"),
        filled_at=AFTER_CLOSE,
    )

    first = runtime.run_once(as_of=AFTER_CLOSE - timedelta(hours=1))
    second = runtime.run_once(as_of=AFTER_CLOSE - timedelta(minutes=30))

    assert first.fills_applied == 1
    assert second.fills_applied == 0
    assert runtime.service.ledger.filled_quantity("manual-paper-order") == Decimal("1")
    assert runtime.service.ledger.get_position("AAA").quantity == Decimal("1")
    fill_lines = (
        (tmp_path / "journal" / "fills.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(fill_lines) == 1


def test_runtime_blocks_orders_when_broker_reports_unknown_fill(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    external_order = Order(
        id="external-broker-order",
        symbol="AAA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=AFTER_CLOSE,
    )
    runtime.service.broker.submit_order(external_order)
    runtime.service.broker.fill_order(
        "external-broker-order",
        price=Decimal("100"),
        filled_at=AFTER_CLOSE,
    )

    result = runtime.run_once(as_of=AFTER_CLOSE)
    report = runtime.service.portfolio_report(as_of=AFTER_CLOSE)

    assert result.status == RuntimeStatus.DEGRADED
    assert result.strategy_evaluated
    assert result.orders_submitted == 0
    assert not report.reconciliation.reconciled
    assert any(
        issue.issue_type.value == "UNKNOWN_BROKER_ORDER"
        for issue in report.reconciliation.issues
    )


def test_runtime_blocks_orders_when_broker_sync_fails(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)

    def fail_list_orders():
        raise RuntimeError("paper broker unavailable")

    runtime.service.broker.list_orders = fail_list_orders

    result = runtime.run_once(as_of=AFTER_CLOSE)

    assert result.status == RuntimeStatus.BLOCKED
    assert not result.broker_synced
    assert not result.strategy_evaluated
    assert result.orders_submitted == 0
    assert any(event.category == "strategy" for event in result.events)


def test_runtime_contains_strategy_failure_and_retries_later(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.historical_bar_fetcher = FailingHistoricalBarFetcher()

    failed = runtime.run_once(as_of=AFTER_CLOSE)
    runtime.historical_bar_fetcher = FixtureHistoricalBarFetcher(source="runtime-test")
    recovered = runtime.run_once(as_of=AFTER_CLOSE + timedelta(minutes=5))

    assert failed.status == RuntimeStatus.BLOCKED
    assert failed.strategy_evaluated
    assert failed.orders_submitted == 0
    assert any(
        "historical bars unavailable" in event.message for event in failed.events
    )
    assert recovered.strategy_evaluated
    assert recovered.orders_submitted == 1


def test_runtime_reports_partial_order_submission_failure(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.strategy = MonthlySectorMomentumStrategy(
        universe=("AAA", "BBB"),
        lookback_days=5,
        top_n=2,
    )
    original_submit_order = runtime.service.broker.submit_order
    calls = 0

    def submit_first_then_fail(order):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("paper broker submission unavailable")
        return original_submit_order(order)

    runtime.service.broker.submit_order = submit_first_then_fail

    result = runtime.run_once(as_of=AFTER_CLOSE)

    assert result.status == RuntimeStatus.BLOCKED
    assert result.strategy_evaluated
    assert result.orders_submitted == 1
    assert len(runtime.service.submissions) == 1
    assert any(event.category == "broker_order_submission" for event in result.events)


def test_runtime_writes_report_and_runs_learning_without_active_mutation(
    tmp_path,
) -> None:
    runtime = make_runtime(output_dir=tmp_path)

    result = runtime.run_once(as_of=NIGHT)
    snapshot = runtime.snapshot(as_of=NIGHT)

    assert result.report_written
    assert result.nightly_learning_ran
    assert snapshot.daily_report_path is not None
    assert snapshot.daily_report is not None
    assert snapshot.daily_report.active_strategy_definition is not None
    assert snapshot.daily_report.active_strategy_definition.strategy_id == (
        "monthly_sector_momentum"
    )
    assert snapshot.nightly_learning_path is not None
    assert snapshot.nightly_learning is not None
    assert snapshot.nightly_learning.active_model_unchanged
    assert not snapshot.nightly_learning.registry_after.records[1].is_active


def test_runtime_dashboard_snapshot_uses_alpaca_paper_mode(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.run_once(as_of=AFTER_CLOSE)
    RuntimeCompletionAuditor(output_dir=tmp_path).audit(as_of=AFTER_CLOSE)

    snapshot = runtime.dashboard_snapshot()

    assert snapshot.mode == "Alpaca Paper"
    assert snapshot.runtime_state is not None
    assert snapshot.completion_audit is not None
    assert snapshot.metrics[2].label == "Price freshness"
    assert snapshot.model_cards[0].detail == "Daily-close authority only"
    assert snapshot.live_readiness.status.value == "blocked"
    assert snapshot.live_readiness.config.paper_account_id == (
        "memory-paper-paper-runtime"
    )
    assert snapshot.live_readiness.config.live_account_id == "live-trading-disabled"
    assert "demo" not in snapshot.live_readiness.model_dump_json()
    assert snapshot.health_report_path is not None
    assert "health-report-" in snapshot.health_report_path


def test_runtime_loop_uses_fake_clock_and_does_not_sleep_after_last_cycle(
    tmp_path,
) -> None:
    sleeps = []
    runtime = make_runtime(output_dir=tmp_path)
    runtime.clock = lambda: AFTER_CLOSE
    runtime.sleeper = sleeps.append

    runtime.run_forever(max_cycles=1)

    assert sleeps == []


def test_alpaca_runtime_factory_rejects_live_trading_flag_before_client_creation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret")
    monkeypatch.setenv("ALPACA_LIVE_TRADING_ENABLED", "true")

    with pytest.raises(ValueError, match="ALPACA_LIVE_TRADING_ENABLED"):
        AlwaysOnPaperRuntime.from_alpaca_env(
            config=AlwaysOnPaperRuntimeConfig(output_dir=tmp_path)
        )
