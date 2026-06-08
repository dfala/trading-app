from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import trading_app.runtime.paper as paper_runtime
from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.learning.autonomous import (
    AutonomousLearningLeaderboard,
    AutonomousLearningLeaderboardEntry,
)
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
    StrategySchedule,
    build_paper_strategy,
    default_symbols_for_paper_model,
)
from trading_app.runtime.models import RuntimeStatus
from trading_app.schemas import DataFeed, Order, OrderSide, OrderType
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
NIGHT = datetime(2026, 5, 30, 1, 0, tzinfo=UTC)
PRE_OPEN = datetime(2026, 6, 2, 13, 29, tzinfo=UTC)
MARKET_OPEN = datetime(2026, 6, 2, 13, 31, tzinfo=UTC)
PROMOTED_MODEL_KEY = "market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk0-cash"
SHADOW_CHALLENGER_MODEL_KEY = (
    "market_drawdown_circuit_breaker:top-semi-l126-qqq-dd08-risk050-cash"
)
BENCHMARK_RELATIVE_MODEL_KEY = "benchmark_relative_strength_etf:grid-l126-t63-n1"
CASH_ROTATION_MODEL_KEY = "cash_rotation_model:grid-l63-n1-b040"
MARKET_DRAWDOWN_RISK025_MODEL_KEY = (
    "market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk025-cash"
)
LEADERBOARD_WINNER_MODEL_KEY = (
    "market_drawdown_circuit_breaker:top-semi-l126-qqq-dd10-risk025-cash"
)
CASH_ROTATION_GRID_MODEL_KEY = "cash_rotation_model:grid-l126-n1-b020"
BENCHMARK_RELATIVE_GRID_MODEL_KEY = "benchmark_relative_strength_etf:grid-l126-t21-n1"
MACRO_DEFENSIVE_BENCHMARK_RELATIVE_MODEL_KEY = (
    "benchmark_relative_strength_etf:grid-l252-t21-n2"
)
MACRO_DEFENSIVE_UNIVERSE_ID = "macro-defensive"
MACRO_DEFENSIVE_UNIVERSE = (
    "DIA",
    "QQQ",
    "IWM",
    "MDY",
    "TLT",
    "GLD",
    "XLP",
    "XLU",
    "XLV",
    "XLE",
)
RISK_MANAGED_SEMICONDUCTOR_MODEL_KEY = (
    "risk_managed_semiconductor:vol-smh-v63-t020-off-cash"
)
DEFAULT_RUNTIME_CONFIG = AlwaysOnPaperRuntimeConfig()


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


def make_promoted_runtime(
    *,
    latest_observed_at: datetime = MARKET_OPEN,
    output_dir=None,
    shadow_challenger_model_key: str | None = None,
    shadow_challenger_model_keys: tuple[str, ...] = (),
    starting_cash: Decimal = Decimal("10000"),
    managed_capital: Decimal | None = None,
    max_paper_symbol_allocation: Decimal | None = (
        DEFAULT_RUNTIME_CONFIG.max_paper_symbol_allocation
    ),
    max_paper_semiconductor_allocation: Decimal | None = (
        DEFAULT_RUNTIME_CONFIG.max_paper_semiconductor_allocation
    ),
    initial_paper_deployment_allocation: Decimal | None = (
        DEFAULT_RUNTIME_CONFIG.initial_paper_deployment_allocation
    ),
    paper_epoch_started_at: datetime | None = None,
) -> AlwaysOnPaperRuntime:
    symbols = ("SOXX", "SMH", "SPY", "QQQ", "XLK")
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(symbols),
            tradable_symbols=frozenset(symbols),
        )
    )
    broker = InMemoryPaperBrokerAdapter(starting_cash=starting_cash)
    service = PaperTradingService(
        broker=broker,
        starting_cash=starting_cash,
        risk_engine=risk_engine,
    )
    return AlwaysOnPaperRuntime(
        service=service,
        latest_price_fetcher=FixtureLatestPriceFetcher(
            {
                "SOXX": Decimal("210"),
                "SMH": Decimal("250"),
                "SPY": Decimal("530"),
                "QQQ": Decimal("470"),
                "XLK": Decimal("240"),
            },
            observed_at=latest_observed_at,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="runtime-test"),
        risk_engine=risk_engine,
        config=AlwaysOnPaperRuntimeConfig(
            symbols=symbols,
            starting_cash=starting_cash,
            paper_epoch_started_at=paper_epoch_started_at,
            output_dir=output_dir or AlwaysOnPaperRuntimeConfig().output_dir,
            feed=DataFeed.IEX,
            active_model_key=PROMOTED_MODEL_KEY,
            shadow_challenger_model_key=shadow_challenger_model_key,
            shadow_challenger_model_keys=shadow_challenger_model_keys,
            strategy_schedule=StrategySchedule.MARKET_OPEN,
            managed_capital=managed_capital,
            max_paper_symbol_allocation=max_paper_symbol_allocation,
            max_paper_semiconductor_allocation=max_paper_semiconductor_allocation,
            initial_paper_deployment_allocation=initial_paper_deployment_allocation,
        ),
    )


def make_macro_defensive_runtime(
    *,
    output_dir=None,
) -> AlwaysOnPaperRuntime:
    symbols = (*MACRO_DEFENSIVE_UNIVERSE, "SPY")
    prices = {symbol: Decimal("100") for symbol in symbols}
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
            prices,
            observed_at=MARKET_OPEN,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="runtime-test"),
        risk_engine=risk_engine,
        config=AlwaysOnPaperRuntimeConfig(
            symbols=symbols,
            output_dir=output_dir or AlwaysOnPaperRuntimeConfig().output_dir,
            feed=DataFeed.IEX,
            active_model_key=MACRO_DEFENSIVE_BENCHMARK_RELATIVE_MODEL_KEY,
            active_model_universe_id=MACRO_DEFENSIVE_UNIVERSE_ID,
            strategy_schedule=StrategySchedule.MARKET_OPEN,
        ),
    )


def write_runtime_leaderboard(
    output_dir,
    *model_keys: str,
) -> None:
    entries = []
    for index, model_key in enumerate(model_keys, start=1):
        entries.append(
            AutonomousLearningLeaderboardEntry(
                rank=index,
                first_seen_at=MARKET_OPEN,
                last_seen_at=MARKET_OPEN,
                seen_count=3,
                latest_run_id=f"leaderboard-run-{index}",
                hypothesis_ids=(f"hypothesis-{index}",),
                universe_id="semiconductor-champions",
                model_key=model_key,
                strategy_name="Runtime leaderboard test candidate",
                full_delta=12.0 - index,
                net_total_return=15.0 - index,
                benchmark_total_return=2.0,
                stress_delta=10.0 - index,
                min_fold_delta=0.15,
                average_fold_delta=1.0,
                worst_drawdown=-0.27,
                risk_adjusted_score=20.0 - index,
                positive_folds=3,
                fold_count=3,
                gate_status="return positive; risk gates incomplete",
                status="all folds positive",
            )
        )
    leaderboard = AutonomousLearningLeaderboard(
        generated_at=MARKET_OPEN,
        entry_count=len(entries),
        entries=tuple(entries),
        summary="test leaderboard",
    )
    learning_dir = output_dir / "learning"
    learning_dir.mkdir(parents=True, exist_ok=True)
    (learning_dir / "learning-leaderboard.json").write_text(
        leaderboard.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _write_comparison_report(
    path,
    *,
    universe_id: str,
    start_date: str = "2016-01-04",
    end_date: str = "2026-05-29",
    net_total_return: float,
    excess_return: float,
    max_drawdown: float,
    late_entry_risk: bool,
) -> None:
    path.write_text(
        json.dumps(
            {
                "start_date": start_date,
                "end_date": end_date,
                "generated_at": "2026-06-03T13:01:36Z",
                "benchmark": "SPY",
                "rows": [
                    {
                        "rank": 1,
                        "model_key": MACRO_DEFENSIVE_BENCHMARK_RELATIVE_MODEL_KEY,
                        "strategy_name": "Benchmark-relative ETF strength",
                        "universe_id": universe_id,
                        "net_total_return": net_total_return,
                        "benchmark_total_return": 3.409933543196922,
                        "excess_return": excess_return,
                        "max_drawdown": max_drawdown,
                        "research_score": 5.554364866742497,
                        "late_entry_risk": late_entry_risk,
                        "portfolio_governance_classification": (
                            "late_entry_review"
                            if late_entry_risk
                            else "portfolio_candidate"
                        ),
                        "champion_eligible": not late_entry_risk,
                    }
                ],
            },
        ),
        encoding="utf-8",
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


def test_market_open_promoted_model_submits_paper_orders_once_per_day(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(output_dir=tmp_path)

    pre_open = runtime.run_once(as_of=PRE_OPEN)
    opened = runtime.run_once(as_of=MARKET_OPEN)
    repeat = runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))
    snapshot = runtime.snapshot(as_of=MARKET_OPEN)

    assert not pre_open.strategy_evaluated
    assert opened.strategy_evaluated
    assert opened.orders_submitted == 1
    assert repeat.orders_submitted == 0
    assert snapshot.active_model_key == PROMOTED_MODEL_KEY
    assert runtime.service.submissions[0].broker_submitted


def test_market_open_promoted_model_starts_with_capped_paper_deployment(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(output_dir=tmp_path)

    opened = runtime.run_once(as_of=MARKET_OPEN)
    submission = runtime.service.submissions[0]

    assert opened.strategy_evaluated
    assert opened.orders_submitted == 1
    assert submission.broker_submitted
    assert submission.order.symbol == "SOXX"
    assert submission.order.side == OrderSide.BUY
    assert submission.estimated_notional <= Decimal("2500.00")
    assert any(
        event.category == "paper_rollout_limits" and "capped" in event.message
        for event in opened.events
    )


def test_market_open_promoted_model_can_size_to_managed_micro_pilot(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(
        output_dir=tmp_path,
        starting_cash=Decimal("10000"),
        managed_capital=Decimal("100"),
        max_paper_symbol_allocation=Decimal("1"),
        max_paper_semiconductor_allocation=Decimal("1"),
        initial_paper_deployment_allocation=None,
    )

    opened = runtime.run_once(as_of=MARKET_OPEN)
    submission = runtime.service.submissions[0]
    snapshot = runtime.dashboard_snapshot(as_of=MARKET_OPEN)

    assert opened.strategy_evaluated
    assert opened.orders_submitted == 1
    assert submission.order.symbol == "SOXX"
    assert submission.order.side == OrderSide.BUY
    assert Decimal("95") <= submission.estimated_notional <= Decimal("100")
    assert not any(
        event.category == "paper_rollout_limits" and "capped" in event.message
        for event in opened.events
    )
    assert snapshot.managed_capital == Decimal("100")
    assert snapshot.managed_target_equity == Decimal("100")


def test_market_open_promoted_model_rebalances_again_next_day(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(
        output_dir=tmp_path,
        starting_cash=Decimal("10000"),
        managed_capital=Decimal("100"),
        max_paper_symbol_allocation=Decimal("1"),
        max_paper_semiconductor_allocation=Decimal("1"),
        initial_paper_deployment_allocation=None,
    )

    opened = runtime.run_once(as_of=MARKET_OPEN)
    runtime.service.broker.fill_order(
        runtime.service.submissions[0].order.id,
        price=Decimal("210"),
        filled_at=MARKET_OPEN + timedelta(minutes=1),
    )
    runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=1))
    next_day = MARKET_OPEN + timedelta(days=1)
    runtime.latest_price_fetcher = FixtureLatestPriceFetcher(
        {
            "SOXX": Decimal("211"),
            "SMH": Decimal("250"),
            "SPY": Decimal("530"),
            "QQQ": Decimal("470"),
            "XLK": Decimal("240"),
        },
        observed_at=next_day,
    )

    next_cycle = runtime.run_once(as_of=next_day)

    assert opened.strategy_evaluated
    assert next_cycle.strategy_evaluated


def test_market_open_promoted_model_repairs_oversized_paper_position(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(output_dir=tmp_path)
    oversized_order = Order(
        id="manual-oversized-soxx",
        symbol="SOXX",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("40"),
        created_at=MARKET_OPEN - timedelta(minutes=1),
    )
    submission = runtime.service.submit_order(
        oversized_order,
        strategy_id="manual-test-setup",
        estimated_price=Decimal("210"),
        latest_prices={"SOXX": Decimal("210")},
        as_of=MARKET_OPEN - timedelta(minutes=1),
    )
    runtime.service.broker.fill_order(
        submission.order.id,
        price=Decimal("210"),
        filled_at=MARKET_OPEN - timedelta(minutes=1),
    )
    broker_order = runtime.service.broker.list_orders()[0]
    runtime.service.sync_broker_order_state(broker_order, as_of=MARKET_OPEN)
    runtime._last_trade_date = MARKET_OPEN.date()

    result = runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))
    repair_order = runtime.service.submissions[-1].order

    assert result.strategy_evaluated
    assert result.orders_submitted == 1
    assert repair_order.symbol == "SOXX"
    assert repair_order.side == OrderSide.SELL
    assert repair_order.quantity > 0
    assert any(
        event.category == "paper_rollout_limits" and "de-risking" in event.message
        for event in result.events
    )


def test_market_open_shadow_challenger_tracks_without_broker_orders(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(
        output_dir=tmp_path,
        shadow_challenger_model_key=SHADOW_CHALLENGER_MODEL_KEY,
    )

    opened = runtime.run_once(as_of=MARKET_OPEN)
    repeat = runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))
    snapshot = runtime.dashboard_snapshot(as_of=MARKET_OPEN + timedelta(minutes=5))

    assert opened.strategy_evaluated
    assert opened.shadow_challenger_observed
    assert repeat.orders_submitted == 0
    assert not repeat.shadow_challenger_observed
    assert len(runtime.service.submissions) == 1
    assert runtime.service.submissions[0].broker_submitted
    assert snapshot.shadow_challenger is not None
    assert snapshot.shadow_challenger.model_key == SHADOW_CHALLENGER_MODEL_KEY
    assert not snapshot.shadow_challenger.broker_orders_submitted
    assert snapshot.shadow_challenger.orders
    assert snapshot.model_cards[0].label == "Paper Authority"
    assert "not whole-portfolio champion eligible" in snapshot.model_cards[0].detail
    assert snapshot.model_cards[1].label == "Shadow Challenger"
    assert (tmp_path / "state" / "latest-shadow-challenger-observation.json").exists()
    assert (tmp_path / "journal" / "shadow-challenger-observations.jsonl").exists()


def test_shadow_challenger_journals_mark_to_market_each_cycle(tmp_path) -> None:
    """After the once-per-day decision, every subsequent cycle should append
    a mark-to-market observation per shadow model so the dashboard chart can
    plot a dense equity time series."""

    runtime = make_promoted_runtime(
        output_dir=tmp_path,
        shadow_challenger_model_key=SHADOW_CHALLENGER_MODEL_KEY,
    )

    decision = runtime.run_once(as_of=MARKET_OPEN)
    assert decision.shadow_challenger_observed

    journal_path = tmp_path / "journal" / "shadow-challenger-observations.jsonl"
    decision_rows = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(decision_rows) == 1

    # Two follow-up cycles in the same trading day should each add a MtM row
    # per shadow model — even though no new decision is "due" today.
    runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))
    runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=10))

    rows = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 3, (
        "Expected the decision-time row plus one MtM row per follow-up cycle, "
        f"got rows={rows}"
    )

    snapshot = runtime.dashboard_snapshot(
        as_of=MARKET_OPEN + timedelta(minutes=10),
    )
    assert snapshot.shadow_challenger is not None
    # The map tracks the latest MtM observation. Equity-related fields move
    # on each tick; orders/targets/metadata remain from the decision so the
    # dashboard still shows what the model rebalanced to.
    assert snapshot.shadow_challenger.as_of == MARKET_OPEN + timedelta(minutes=10)
    assert snapshot.shadow_challenger.orders, (
        "Orders from the daily decision should still be visible on MtM ticks"
    )
    assert snapshot.shadow_challenger.ledger_snapshot is not None


def test_market_open_tracks_multiple_shadow_challengers_with_separate_ledgers(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(
        output_dir=tmp_path,
        shadow_challenger_model_key=SHADOW_CHALLENGER_MODEL_KEY,
        shadow_challenger_model_keys=(
            BENCHMARK_RELATIVE_MODEL_KEY,
            CASH_ROTATION_MODEL_KEY,
        ),
    )

    opened = runtime.run_once(as_of=MARKET_OPEN)
    repeat = runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))
    snapshot = runtime.dashboard_snapshot(as_of=MARKET_OPEN + timedelta(minutes=5))

    assert opened.shadow_challenger_observed
    assert not repeat.shadow_challenger_observed
    assert [item.model_key for item in snapshot.shadow_challengers] == [
        SHADOW_CHALLENGER_MODEL_KEY,
        BENCHMARK_RELATIVE_MODEL_KEY,
        CASH_ROTATION_MODEL_KEY,
    ]
    assert all(not item.broker_orders_submitted for item in snapshot.shadow_challengers)
    assert len({id(item.ledger_snapshot) for item in snapshot.shadow_challengers}) == 3
    assert len(runtime.service.submissions) == 1
    assert len(snapshot.model_cards) == 4
    assert (tmp_path / "state" / "latest-shadow-challenger-observations.json").exists()

    restarted = make_promoted_runtime(
        output_dir=tmp_path,
        shadow_challenger_model_key=SHADOW_CHALLENGER_MODEL_KEY,
        shadow_challenger_model_keys=(
            BENCHMARK_RELATIVE_MODEL_KEY,
            CASH_ROTATION_MODEL_KEY,
        ),
    )

    assert [
        item.model_key
        for item in restarted.snapshot(as_of=MARKET_OPEN).shadow_challengers
    ] == [
        SHADOW_CHALLENGER_MODEL_KEY,
        BENCHMARK_RELATIVE_MODEL_KEY,
        CASH_ROTATION_MODEL_KEY,
    ]


def test_runtime_auto_shadows_top_buildable_leaderboard_candidates(tmp_path) -> None:
    write_runtime_leaderboard(
        tmp_path,
        LEADERBOARD_WINNER_MODEL_KEY,
        CASH_ROTATION_GRID_MODEL_KEY,
        BENCHMARK_RELATIVE_GRID_MODEL_KEY,
    )
    runtime = make_promoted_runtime(output_dir=tmp_path)

    opened = runtime.run_once(as_of=MARKET_OPEN)
    snapshot = runtime.dashboard_snapshot(as_of=MARKET_OPEN)

    assert opened.shadow_challenger_observed
    assert runtime.shadow_challenger_model_keys[:3] == (
        LEADERBOARD_WINNER_MODEL_KEY,
        CASH_ROTATION_GRID_MODEL_KEY,
        BENCHMARK_RELATIVE_GRID_MODEL_KEY,
    )
    assert [item.model_key for item in snapshot.shadow_challengers] == [
        LEADERBOARD_WINNER_MODEL_KEY,
        CASH_ROTATION_GRID_MODEL_KEY,
        BENCHMARK_RELATIVE_GRID_MODEL_KEY,
    ]
    assert all(not item.broker_orders_submitted for item in snapshot.shadow_challengers)


def test_shadow_challenger_key_uses_half_risk_exposure() -> None:
    strategy = build_paper_strategy(SHADOW_CHALLENGER_MODEL_KEY)

    assert strategy.strategy_version == "top-semi-l126-qqq-dd08-risk050-cash"
    assert strategy.triggered_risk_exposure == Decimal("0.50")
    assert strategy.drawdown_symbols == ("QQQ",)
    assert strategy.drawdown_threshold == Decimal("0.08")


def test_research_shadow_keys_build_with_backtested_parameters() -> None:
    benchmark_relative = build_paper_strategy(BENCHMARK_RELATIVE_MODEL_KEY)
    macro_relative = build_paper_strategy(
        MACRO_DEFENSIVE_BENCHMARK_RELATIVE_MODEL_KEY,
        universe_id=MACRO_DEFENSIVE_UNIVERSE_ID,
    )
    cash_rotation = build_paper_strategy(CASH_ROTATION_MODEL_KEY)
    risk025 = build_paper_strategy(MARKET_DRAWDOWN_RISK025_MODEL_KEY)
    risk_managed = build_paper_strategy(RISK_MANAGED_SEMICONDUCTOR_MODEL_KEY)

    assert benchmark_relative.strategy_version == "grid-l126-t63-n1"
    assert benchmark_relative.universe == ("QQQ", "XLK", "SMH", "SOXX")
    assert benchmark_relative.benchmark == "SPY"
    assert benchmark_relative.lookback_days == 126
    assert benchmark_relative.tracking_window_days == 63
    assert benchmark_relative.top_n == 1

    assert macro_relative.strategy_version == "grid-l252-t21-n2"
    assert macro_relative.universe == MACRO_DEFENSIVE_UNIVERSE
    assert macro_relative.benchmark == "SPY"
    assert macro_relative.lookback_days == 252
    assert macro_relative.tracking_window_days == 21
    assert macro_relative.top_n == 2

    assert cash_rotation.strategy_version == "grid-l63-n1-b040"
    assert cash_rotation.universe == ("QQQ", "XLK", "SMH", "SOXX")
    assert cash_rotation.lookback_days == 63
    assert cash_rotation.top_n == 1
    assert cash_rotation.min_breadth == Decimal("0.40")

    assert risk025.strategy_version == "top-semi-l126-any-dd08-risk025-cash"
    assert risk025.drawdown_symbols == ("SPY", "QQQ")
    assert risk025.triggered_risk_exposure == Decimal("0.25")

    assert risk_managed.strategy_version == "vol-smh-v63-t020-off-cash"
    assert risk_managed.sleeve_weights == {"SMH": Decimal("1")}
    assert risk_managed.volatility_window_days == 63
    assert risk_managed.target_volatility == Decimal("0.20")


def test_leaderboard_variant_keys_build_with_discovered_parameters() -> None:
    winner = build_paper_strategy(LEADERBOARD_WINNER_MODEL_KEY)
    cash_rotation = build_paper_strategy(CASH_ROTATION_GRID_MODEL_KEY)
    benchmark_relative = build_paper_strategy(BENCHMARK_RELATIVE_GRID_MODEL_KEY)

    assert winner.strategy_version == "top-semi-l126-qqq-dd10-risk025-cash"
    assert winner.momentum_lookback_days == 126
    assert winner.drawdown_symbols == ("QQQ",)
    assert winner.drawdown_threshold == Decimal("0.10")
    assert winner.triggered_risk_exposure == Decimal("0.25")

    assert cash_rotation.strategy_version == "grid-l126-n1-b020"
    assert cash_rotation.lookback_days == 126
    assert cash_rotation.top_n == 1
    assert cash_rotation.min_breadth == Decimal("0.20")

    assert benchmark_relative.strategy_version == "grid-l126-t21-n1"
    assert benchmark_relative.lookback_days == 126
    assert benchmark_relative.tracking_window_days == 21
    assert benchmark_relative.top_n == 1


def test_default_symbols_include_all_shadow_challenger_requirements() -> None:
    symbols = default_symbols_for_paper_model(
        PROMOTED_MODEL_KEY,
        shadow_challenger_model_key=SHADOW_CHALLENGER_MODEL_KEY,
        shadow_challenger_model_keys=(
            BENCHMARK_RELATIVE_MODEL_KEY,
            CASH_ROTATION_MODEL_KEY,
            RISK_MANAGED_SEMICONDUCTOR_MODEL_KEY,
        ),
    )

    assert symbols == ("QQQ", "SMH", "SOXX", "SPY", "XLK")


def test_default_symbols_use_active_model_universe() -> None:
    symbols = default_symbols_for_paper_model(
        MACRO_DEFENSIVE_BENCHMARK_RELATIVE_MODEL_KEY,
        active_model_universe_id=MACRO_DEFENSIVE_UNIVERSE_ID,
    )

    assert symbols == (
        "DIA",
        "GLD",
        "IWM",
        "MDY",
        "QQQ",
        "SPY",
        "TLT",
        "XLE",
        "XLP",
        "XLU",
        "XLV",
    )


def test_active_model_evidence_uses_configured_universe_for_reused_model_key(
    tmp_path,
) -> None:
    replay_dir = tmp_path / "research" / "replay"
    replay_dir.mkdir(parents=True)
    _write_comparison_report(
        replay_dir
        / (
            "learning-cycle-test-semiconductor-champions-"
            "full-base-comparison.json"
        ),
        universe_id="semiconductor-champions",
        net_total_return=6.148,
        excess_return=2.738,
        max_drawdown=-0.3377,
        late_entry_risk=True,
    )
    macro_path = replay_dir / (
        "learning-cycle-test-macro-defensive-full-base-comparison.json"
    )
    _write_comparison_report(
        macro_path,
        universe_id=MACRO_DEFENSIVE_UNIVERSE_ID,
        net_total_return=4.8349233881822204,
        excess_return=1.4249898449852982,
        max_drawdown=-0.18960359157553267,
        late_entry_risk=False,
    )
    _write_comparison_report(
        replay_dir
        / (
            "learning-cycle-test-post-election-2017-macro-defensive-"
            "full-base-comparison.json"
        ),
        universe_id=MACRO_DEFENSIVE_UNIVERSE_ID,
        start_date="2017-01-03",
        end_date="2026-05-29",
        net_total_return=4.8349233881822204,
        excess_return=1.9603075307759514,
        max_drawdown=-0.18960359157553267,
        late_entry_risk=False,
    )
    leaderboard = AutonomousLearningLeaderboard(
        generated_at=MARKET_OPEN,
        entry_count=1,
        entries=(
            AutonomousLearningLeaderboardEntry(
                rank=59,
                first_seen_at=MARKET_OPEN,
                last_seen_at=MARKET_OPEN,
                seen_count=15,
                latest_run_id=(
                    "learning-cycle-test-post-election-2017"
                ),
                hypothesis_ids=("hypothesis-macro",),
                universe_id=MACRO_DEFENSIVE_UNIVERSE_ID,
                model_key=MACRO_DEFENSIVE_BENCHMARK_RELATIVE_MODEL_KEY,
                strategy_name="Benchmark-relative ETF strength",
                full_delta=1.9603075307759514,
                net_total_return=None,
                benchmark_total_return=None,
                stress_delta=1.341505314740166,
                min_fold_delta=0.0577611678761325,
                average_fold_delta=0.26949491682533017,
                worst_drawdown=-0.18960359157553267,
                risk_adjusted_score=2.654072041509985,
                positive_folds=3,
                fold_count=3,
                gate_status="general evidence only",
                status="all folds positive",
            ),
        ),
        summary="test macro leaderboard",
    )
    learning_dir = tmp_path / "runtime" / "learning"
    learning_dir.mkdir(parents=True)
    (learning_dir / "learning-leaderboard.json").write_text(
        leaderboard.model_dump_json(indent=2),
        encoding="utf-8",
    )
    runtime = make_macro_defensive_runtime(output_dir=tmp_path / "runtime")

    snapshot = runtime.dashboard_snapshot(as_of=MARKET_OPEN)
    evidence = snapshot.model_cards[0].evidence

    assert snapshot.model_cards[0].label == "Champion"
    assert runtime.strategy.universe == MACRO_DEFENSIVE_UNIVERSE
    assert evidence is not None
    assert evidence.source_report == str(macro_path)
    assert evidence.universe_id == MACRO_DEFENSIVE_UNIVERSE_ID
    assert evidence.net_total_return == pytest.approx(4.8349233881822204)
    assert evidence.worst_drawdown == pytest.approx(-0.18960359157553267)
    assert evidence.late_entry_risk is False
    assert evidence.champion_eligible is True
    assert evidence.portfolio_governance_classification == "portfolio_candidate"


def test_market_open_stale_prices_do_not_consume_daily_attempt(tmp_path) -> None:
    runtime = make_promoted_runtime(
        latest_observed_at=MARKET_OPEN - timedelta(hours=2),
        output_dir=tmp_path,
    )

    stale = runtime.run_once(as_of=MARKET_OPEN)
    runtime.latest_price_fetcher = FixtureLatestPriceFetcher(
        {
            "SOXX": Decimal("210"),
            "SMH": Decimal("250"),
            "SPY": Decimal("530"),
            "QQQ": Decimal("470"),
            "XLK": Decimal("240"),
        },
        observed_at=MARKET_OPEN + timedelta(minutes=5),
    )
    recovered = runtime.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))

    assert stale.strategy_evaluated
    assert stale.orders_submitted == 0
    assert recovered.strategy_evaluated
    assert recovered.orders_submitted == 1


def test_market_open_stale_prices_do_not_consume_attempt_after_restart(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(
        latest_observed_at=MARKET_OPEN - timedelta(hours=2),
        output_dir=tmp_path,
    )
    stale = runtime.run_once(as_of=MARKET_OPEN)

    restarted = make_promoted_runtime(
        latest_observed_at=MARKET_OPEN + timedelta(minutes=5),
        output_dir=tmp_path,
    )
    recovered = restarted.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))

    assert stale.strategy_evaluated
    assert stale.orders_submitted == 0
    assert recovered.strategy_evaluated
    assert recovered.orders_submitted == 1


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


def test_runtime_recovers_filled_runtime_broker_order_missing_from_ledger(
    tmp_path,
) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    recovered_order = Order(
        id="runtime-2026-05-29-AAA-buy-1",
        symbol="AAA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=AFTER_CLOSE,
    )
    runtime.service.broker.submit_order(recovered_order)
    runtime.service.broker.fill_order(
        recovered_order.id,
        price=Decimal("100"),
        filled_at=AFTER_CLOSE,
    )

    result = runtime.run_once(as_of=AFTER_CLOSE - timedelta(hours=1))
    report = runtime.service.portfolio_report(as_of=AFTER_CLOSE)

    assert result.fills_applied == 1
    assert report.reconciliation.reconciled
    assert runtime.service.ledger.get_position("AAA").quantity == Decimal("1")
    assert runtime.service.submissions[0].order.id == recovered_order.id
    assert runtime.service.submissions[0].broker_submitted
    assert "Recovered" in runtime.service.submissions[0].explanation


def test_runtime_recovered_market_open_order_consumes_rebalance_attempt(
    tmp_path,
) -> None:
    runtime = make_promoted_runtime(output_dir=tmp_path)
    recovered_order = Order(
        id="runtime-2026-06-02-SOXX-buy-1",
        symbol="SOXX",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=MARKET_OPEN,
    )
    runtime.service.broker.submit_order(recovered_order)
    runtime.service.broker.fill_order(
        recovered_order.id,
        price=Decimal("210"),
        filled_at=MARKET_OPEN,
    )

    result = runtime.run_once(as_of=MARKET_OPEN)

    assert result.fills_applied == 1
    assert not result.strategy_evaluated
    assert result.orders_submitted == 0
    assert len(runtime.service.submissions) == 1
    assert runtime.service.submissions[0].order.id == recovered_order.id

    restarted = make_promoted_runtime(output_dir=tmp_path)
    repeated = restarted.run_once(as_of=MARKET_OPEN + timedelta(minutes=5))

    assert not repeated.strategy_evaluated
    assert repeated.orders_submitted == 0


def test_runtime_paper_epoch_ignores_older_runtime_broker_orders(tmp_path) -> None:
    runtime = make_promoted_runtime(
        output_dir=tmp_path,
        paper_epoch_started_at=MARKET_OPEN + timedelta(minutes=1),
    )
    old_order = Order(
        id="runtime-2026-06-02-SOXX-buy-1",
        symbol="SOXX",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        created_at=MARKET_OPEN,
    )
    runtime.service.broker.submit_order(old_order)
    runtime.service.broker.fill_order(
        old_order.id,
        price=Decimal("210"),
        filled_at=MARKET_OPEN,
    )

    fills_applied = runtime._sync_broker_orders(
        as_of=MARKET_OPEN + timedelta(minutes=2)
    )

    assert fills_applied == 0
    assert runtime.service.submissions == ()
    assert runtime.service.ledger.snapshot(MARKET_OPEN).positions == ()


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


def test_dashboard_intraday_equity_ignores_cached_daily_report(tmp_path) -> None:
    runtime = make_runtime(
        latest_observed_at=MARKET_OPEN,
        output_dir=tmp_path,
    )
    order = Order(
        id="intraday-position",
        symbol="AAA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("2"),
        created_at=MARKET_OPEN,
    )
    runtime.service.submit_order(
        order,
        strategy_id="manual",
        estimated_price=Decimal("100"),
        latest_prices={"AAA": Decimal("100")},
        as_of=MARKET_OPEN,
    )
    runtime.service.ingest_fill_event(
        runtime.service.broker.fill_order(
            order.id,
            price=Decimal("100"),
            filled_at=MARKET_OPEN,
        )
    )
    runtime._last_prices = runtime.latest_price_fetcher.fetch_latest_prices(
        runtime.config.symbols,
        as_of=MARKET_OPEN,
        feed=runtime.config.feed,
    )
    runtime._write_daily_report(MARKET_OPEN)
    cached_report = runtime._last_report
    assert cached_report is not None
    assert cached_report.pnl_report.estimated_equity == Decimal("10000")

    runtime.service.broker._last_prices["AAA"] = Decimal("125")

    snapshot = runtime.dashboard_snapshot(as_of=MARKET_OPEN + timedelta(minutes=5))

    expected_equity = Decimal("9800") + Decimal("2") * Decimal("125")
    assert snapshot.daily_report is not cached_report
    assert snapshot.estimated_equity == expected_equity
    assert snapshot.portfolio_history[-1].estimated_equity == expected_equity


def test_dashboard_after_close_reuses_same_day_cached_daily_report(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)

    runtime.run_once(as_of=AFTER_CLOSE)
    cached_report = runtime._last_report
    assert cached_report is not None

    paper_report = runtime._portfolio_report(AFTER_CLOSE + timedelta(minutes=5))

    assert (
        runtime._current_daily_report(
            AFTER_CLOSE + timedelta(minutes=5),
            paper_report,
        )
        is cached_report
    )


def test_dashboard_snapshot_reuses_short_cache_for_browser_polling(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    call_count = 0
    original_build = runtime._build_dashboard_snapshot

    def counting_build(*, as_of=None):
        nonlocal call_count
        call_count += 1
        return original_build(as_of=as_of)

    monkeypatch.setattr(runtime, "_build_dashboard_snapshot", counting_build)

    first = runtime.dashboard_snapshot()
    second = runtime.dashboard_snapshot()
    explicit = runtime.dashboard_snapshot(as_of=AFTER_CLOSE)

    assert first is second
    assert explicit is not first
    assert call_count == 2


def test_full_comparison_index_is_cached_for_dashboard_enrichment(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    call_count = 0

    def fake_index(_replay_dir):
        nonlocal call_count
        call_count += 1
        return paper_runtime._FullComparisonIndex({}, {})

    monkeypatch.setattr(paper_runtime, "_build_full_comparison_index", fake_index)

    first = runtime._full_comparison_index()
    second = runtime._full_comparison_index()

    assert first is second
    assert call_count == 1


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
