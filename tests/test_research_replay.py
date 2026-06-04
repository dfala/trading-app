from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from trading_app.learning import ModelEvidenceType
from trading_app.research import (
    CallableAIReplayPolicy,
    HistoricalReplayRunner,
    ReplayConfig,
    ReplayDecisionFrequency,
    ReplayExecutionPrice,
    ReplayPolicyDecision,
    ReplayPolicyKind,
    ReplayUniverseKind,
    StrategyReplayPolicy,
    render_replay_markdown_report,
    write_replay_markdown_report,
)
from trading_app.schemas import DailyBar, DataFeed
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

NOW = datetime(2026, 6, 1, 16, tzinfo=UTC)


def make_bar(
    symbol: str,
    trading_date: date,
    close: Decimal,
    *,
    open_price: Decimal | None = None,
) -> DailyBar:
    resolved_open = open_price or close
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            21,
            tzinfo=UTC,
        ),
        ingested_at=NOW,
        open_price=resolved_open,
        high_price=max(resolved_open, close),
        low_price=min(resolved_open, close),
        close_price=close,
        volume=Decimal("1000000"),
        source="replay-test",
        data_feed=DataFeed.IEX,
    )


def business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def replay_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(business_days(date(2024, 1, 1), 70)):
        aaa_close = Decimal("100") + Decimal(index) * Decimal("0.35")
        bbb_close = Decimal("100") + Decimal(index) * Decimal("0.05")
        if index >= 30:
            bbb_close += Decimal(index - 29) * Decimal("0.75")
        spy_close = Decimal("100") + Decimal(index) * Decimal("0.12")
        bars.append(make_bar("AAA", trading_day, aaa_close))
        bars.append(make_bar("BBB", trading_day, bbb_close))
        benchmark.append(make_bar("SPY", trading_day, spy_close))
    return tuple(bars), tuple(benchmark)


def replay_config(**updates) -> ReplayConfig:
    values = {
        "run_id": "unit-replay",
        "start_date": date(2024, 2, 1),
        "end_date": date(2024, 3, 29),
        "symbol_universe": ("AAA", "BBB"),
        "benchmark": "SPY",
        "warmup_trading_days": 10,
        "decision_frequency": ReplayDecisionFrequency.MONTH_START,
        "slippage_bps": Decimal("0"),
    }
    values.update(updates)
    return ReplayConfig(**values)


def test_historical_replay_records_decisions_trades_and_evidence(tmp_path) -> None:
    bars, benchmark = replay_bars()
    strategy = MonthlySectorMomentumStrategy(
        universe=("AAA", "BBB"),
        lookback_days=5,
        top_n=1,
    )

    result = HistoricalReplayRunner().run(
        policy=StrategyReplayPolicy(strategy),
        bars=bars,
        benchmark_bars=benchmark,
        config=replay_config(),
        generated_at=NOW,
    )
    markdown = render_replay_markdown_report(result)
    path = write_replay_markdown_report(result, tmp_path)

    assert result.decisions
    assert result.trades
    assert result.metrics.decision_count == len(result.decisions)
    assert result.metrics.trade_count == len(result.trades)
    assert result.leakage_audit.passed
    start_spy = next(bar for bar in benchmark if bar.trading_date == date(2024, 2, 1))
    end_spy = next(bar for bar in benchmark if bar.trading_date == date(2024, 3, 29))
    assert result.metrics.benchmark_total_return == pytest.approx(
        float(end_spy.close_price / start_spy.close_price - Decimal("1"))
    )
    assert result.model_evidence.evidence_type == ModelEvidenceType.HISTORICAL_REPLAY
    assert (
        result.model_evidence.metrics.net_total_return
        == result.metrics.net_total_return
    )
    assert "Historical Replay Report" in markdown
    assert "Stock replay requires point-in-time universe data" in markdown
    assert path.exists()
    assert all(
        decision.visible_data_end is not None
        and decision.visible_data_end < decision.as_of
        for decision in result.decisions
    )


def test_historical_replay_can_target_benchmark_as_risk_off_asset() -> None:
    bars, benchmark = replay_bars()

    class BenchmarkRiskOffPolicy:
        key = "benchmark-risk-off:1"
        kind = ReplayPolicyKind.STRATEGY

        def generate_decision(self, context):
            return ReplayPolicyDecision(
                target_weights={"SPY": Decimal("1")},
                explanation="Rotate to benchmark as risk-off asset.",
            )

    result = HistoricalReplayRunner().run(
        policy=BenchmarkRiskOffPolicy(),
        bars=bars,
        benchmark_bars=benchmark,
        config=replay_config(),
        generated_at=NOW,
    )

    assert result.trades
    assert {trade.symbol for trade in result.trades} == {"SPY"}
    assert result.metrics.net_total_return == pytest.approx(
        result.metrics.benchmark_total_return
    )


def test_historical_replay_can_execute_at_open_and_mark_to_close() -> None:
    trading_days = business_days(date(2024, 1, 1), 12)
    bars = tuple(
        make_bar(
            "AAA",
            trading_day,
            close=Decimal("120"),
            open_price=Decimal("100"),
        )
        for trading_day in trading_days
    )
    benchmark = tuple(
        make_bar(
            "SPY",
            trading_day,
            close=Decimal("110"),
            open_price=Decimal("100"),
        )
        for trading_day in trading_days
    )

    class AlwaysLongPolicy:
        key = "always-long:1"
        kind = ReplayPolicyKind.STRATEGY

        def generate_decision(self, context):
            return ReplayPolicyDecision(
                target_weights={"AAA": Decimal("1")},
                explanation="Always hold AAA.",
            )

    result = HistoricalReplayRunner().run(
        policy=AlwaysLongPolicy(),
        bars=bars,
        benchmark_bars=benchmark,
        config=replay_config(
            start_date=trading_days[-2],
            end_date=trading_days[-1],
            symbol_universe=("AAA",),
            decision_frequency=ReplayDecisionFrequency.DAILY,
            execution_price=ReplayExecutionPrice.OPEN,
        ),
        generated_at=NOW,
    )
    markdown = render_replay_markdown_report(result)

    assert result.trades
    first_trade = result.trades[0]
    assert first_trade.price == Decimal("100")
    assert result.metrics.net_total_return > 0
    assert result.model_evidence.cost_assumptions["execution_price"] == "open"
    assert "Execution price: `open`" in markdown


def test_replay_policy_cannot_see_same_day_or_future_bars() -> None:
    bars, benchmark = replay_bars()
    observed_boundaries: list[tuple[date, date | None]] = []

    class BoundaryRecordingPolicy:
        key = "boundary-policy:1"
        kind = ReplayPolicyKind.STRATEGY

        def generate_decision(self, context):
            max_visible = max(
                (bar.trading_date for bar in context.visible_bars),
                default=None,
            )
            observed_boundaries.append((context.as_of, max_visible))
            return ReplayPolicyDecision(
                target_weights={"AAA": Decimal("1")},
                explanation="Always hold AAA from visible replay data.",
            )

    result = HistoricalReplayRunner().run(
        policy=BoundaryRecordingPolicy(),
        bars=bars,
        benchmark_bars=benchmark,
        config=replay_config(decision_frequency=ReplayDecisionFrequency.DAILY),
        generated_at=NOW,
    )

    assert result.decisions
    assert observed_boundaries
    assert all(
        max_visible is not None and max_visible < as_of
        for as_of, max_visible in observed_boundaries
    )


def test_stock_replay_requires_point_in_time_universe() -> None:
    with pytest.raises(ValueError, match="point_in_time_universe"):
        replay_config(universe_kind=ReplayUniverseKind.STOCK)


def test_replay_rejects_universe_data_that_starts_after_requested_window() -> None:
    bars, benchmark = replay_bars()

    with pytest.raises(ValueError, match="do not cover the replay start"):
        HistoricalReplayRunner().run(
            policy=StrategyReplayPolicy(
                MonthlySectorMomentumStrategy(
                    universe=("AAA", "BBB"),
                    lookback_days=5,
                    top_n=1,
                )
            ),
            bars=bars,
            benchmark_bars=benchmark,
            config=replay_config(start_date=date(2023, 1, 1)),
            generated_at=NOW,
        )


def test_ai_replay_policy_masks_dates_and_symbols_and_maps_alias_targets() -> None:
    bars, benchmark = replay_bars()
    captured_packets = []

    def decide(packet):
        captured_packets.append(packet)
        return ReplayPolicyDecision(
            target_weights={packet.symbols[0]: Decimal("1")},
            explanation="AI challenger selected the strongest masked asset.",
            metadata={"source": "test-ai"},
        )

    result = HistoricalReplayRunner().run(
        policy=CallableAIReplayPolicy(
            key="masked-ai:1",
            decision_fn=decide,
            instructions="Select target weights from point-in-time features only.",
        ),
        bars=bars,
        benchmark_bars=benchmark,
        config=replay_config(decision_frequency=ReplayDecisionFrequency.DAILY),
        generated_at=NOW,
    )

    first_packet = captured_packets[0]
    first_decision = result.decisions[0]

    assert result.decisions
    assert first_packet.as_of is None
    assert first_packet.market_day_label.startswith("replay_day_")
    assert set(first_packet.symbols) == {"ASSET_001", "ASSET_002"}
    assert set(first_packet.features_by_symbol) == {"ASSET_001", "ASSET_002"}
    assert set(first_decision.target_weights).issubset({"AAA", "BBB"})
    assert first_decision.metadata["ai_packet_masked_date"]
    assert first_decision.metadata["ai_packet_masked_symbols"]
    assert result.leakage_audit.passed
