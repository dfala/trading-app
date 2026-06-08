from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.learning.autonomous import (
    AutonomousLearningCandidate,
    AutonomousLearningCycleConfig,
    AutonomousLearningCycleMode,
    AutonomousLearningCycleRun,
    AutonomousLearningCycleRunner,
    AutonomousLearningCycleStatus,
    AutonomousLearningLeaderboard,
    AutonomousLearningLeaderboardEntry,
    _autonomous_catalog,
    _candidate_is_pilot_eligible,
    _candidate_is_promotion_qualified,
    _candidate_passes_shadow_gate,
    _filtered_catalog,
    _limited_catalog,
    render_autonomous_learning_cycle_markdown,
    update_autonomous_learning_leaderboard,
)
from trading_app.market_data.storage import ParquetBarStore
from trading_app.research.replay_suite import (
    ReplayComparisonReport,
    ReplayComparisonRow,
)
from trading_app.research.run_replay_discovery import (
    DiscoveryRun,
    score_discovery_candidates,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DailyBar, DataFeed

NOW = datetime(2026, 6, 1, 23, tzinfo=UTC)
SYMBOLS = ("QQQ", "XLK", "SMH", "SOXX", "SPY")


def make_bar(symbol: str, trading_date: date, close: Decimal) -> DailyBar:
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
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=Decimal("1000000"),
        source="autonomous-learning-test",
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


def autonomous_bars() -> tuple[DailyBar, ...]:
    bars: list[DailyBar] = []
    for index, trading_day in enumerate(business_days(date(2021, 6, 1), 560)):
        prices = {
            "SPY": Decimal("100") + Decimal(index) * Decimal("0.08"),
            "QQQ": Decimal("100") + Decimal(index) * Decimal("0.16"),
            "XLK": Decimal("100") + Decimal(index) * Decimal("0.14"),
            "SMH": Decimal("100") + Decimal(index) * Decimal("0.32"),
            "SOXX": Decimal("100") + Decimal(index) * Decimal("0.30"),
        }
        bars.extend(
            make_bar(symbol, trading_day, close) for symbol, close in prices.items()
        )
    return tuple(bars)


def test_autonomous_cycle_scores_candidates_and_writes_artifacts(tmp_path) -> None:
    ParquetBarStore(tmp_path / "bars").write_bars(autonomous_bars())

    run = AutonomousLearningCycleRunner().run(
        AutonomousLearningCycleConfig(
            run_id="learning-cycle-test",
            start_date=date(2023, 1, 3),
            end_date=date(2023, 7, 31),
            benchmark="SPY",
            universes=("semiconductor-champions",),
            strategy_ids=("market_drawdown_circuit_breaker",),
            feed=DataFeed.IEX,
            root=tmp_path / "bars",
            output_dir=tmp_path / "reports",
            status_dir=tmp_path / "runtime" / "learning",
            warmup_calendar_days=620,
            warmup_trading_days=20,
            max_strategies=8,
        ),
        generated_at=NOW,
    )
    markdown = render_autonomous_learning_cycle_markdown(run)

    assert run.status == AutonomousLearningCycleStatus.COMPLETED
    assert run.candidate_count > 0
    assert run.completed_report_count == 3
    assert run.manual_approval_required
    assert run.active_model_unchanged
    assert run.recommended_challenger_model_key is None
    assert run.research_fingerprint
    assert not run.tuning_mode
    assert run.shadow_arena is not None
    assert not run.shadow_arena.broker_orders_submitted
    assert run.shadow_arena.candidates
    assert run.shadow_arena.candidates[0].authority == "shadow"
    assert not run.shadow_arena.candidates[0].broker_orders_submitted
    assert run.leaderboard is not None
    assert run.leaderboard.entries
    assert run.candidate_readiness is not None
    assert run.candidate_readiness.pilot_status == "research_only"
    assert any(candidate.late_entry_risk for candidate in run.top_candidates)
    assert run.top_candidates[0].manual_approval_required
    assert "cannot grant paper or live trading authority" in markdown
    assert "Shadow Arena" in markdown
    assert "Candidate Readiness" in markdown
    assert (tmp_path / "reports" / "learning-cycle-test.md").exists()
    assert (tmp_path / "reports" / "learning-cycle-test.json").exists()
    assert (
        tmp_path / "reports" / "learning-cycle-test-candidate-readiness.md"
    ).exists()
    assert (
        tmp_path / "reports" / "learning-cycle-test-raw-alpha-watchlist.md"
    ).exists()
    assert (
        tmp_path / "reports" / "learning-cycle-test-low-drawdown-watchlist.md"
    ).exists()
    assert (
        tmp_path / "reports" / "learning-cycle-test-promotion-qualified.md"
    ).exists()
    assert (tmp_path / "reports" / "learning-cycle-test-experiment-queue.md").exists()
    assert (tmp_path / "runtime" / "learning" / "research-fingerprints.json").exists()
    assert (tmp_path / "runtime" / "learning" / "learning-leaderboard.json").exists()
    assert (tmp_path / "runtime" / "learning" / "learning-leaderboard.md").exists()
    assert (tmp_path / "runtime" / "learning" / "shadow-arena.json").exists()
    assert (tmp_path / "runtime" / "learning" / "shadow-arena.md").exists()
    assert (tmp_path / "runtime" / "learning" / "candidate-readiness.md").exists()
    assert (tmp_path / "runtime" / "learning" / "raw-alpha-watchlist.md").exists()
    assert (tmp_path / "runtime" / "learning" / "low-drawdown-watchlist.md").exists()
    assert (tmp_path / "runtime" / "learning" / "promotion-qualified.md").exists()
    assert (tmp_path / "runtime" / "learning" / "experiment-queue.md").exists()
    assert run.artifact_paths["markdown"].endswith("learning-cycle-test.md")
    assert run.artifact_paths["leaderboard_markdown"].endswith(
        "learning-leaderboard.md"
    )
    assert run.artifact_paths["shadow_arena_markdown"].endswith("shadow-arena.md")
    assert run.artifact_paths["candidate_readiness_markdown"].endswith(
        "learning-cycle-test-candidate-readiness.md"
    )
    assert Path(run.artifact_paths["markdown"]).exists()
    assert (tmp_path / "runtime" / "learning" / "latest-learning-cycle.json").exists()
    latest_payload = json.loads(
        (tmp_path / "runtime" / "learning" / "latest-learning-cycle.json").read_text(
            encoding="utf-8"
        )
    )
    assert latest_payload["artifact_paths"]["markdown"].endswith(
        "learning-cycle-test.md"
    )
    assert latest_payload["research_fingerprint"] == run.research_fingerprint
    assert latest_payload["shadow_arena"]["broker_orders_submitted"] is False
    assert latest_payload["leaderboard"]["entries"]
    assert latest_payload["candidate_readiness"]["pilot_status"]
    recovered = RuntimePersistenceStore(
        tmp_path / "runtime"
    ).read_autonomous_learning_cycle()
    assert recovered is not None
    assert recovered.run_id == "learning-cycle-test"


def test_leaderboard_merge_drops_stale_baseline_control_entries(tmp_path) -> None:
    path = tmp_path / "learning-leaderboard.json"
    markdown_path = tmp_path / "learning-leaderboard.md"
    stale_entry = AutonomousLearningLeaderboardEntry(
        rank=1,
        first_seen_at=NOW,
        last_seen_at=NOW,
        seen_count=1,
        latest_run_id="old-run",
        hypothesis_ids=("old-hypothesis",),
        universe_id="semiconductor-champions",
        model_key="market_drawdown_circuit_breaker:top-semi-l126-no-breaker",
        strategy_name="Market Drawdown Circuit Breaker Semiconductor Sleeve",
        full_delta=10.0,
        stress_delta=9.0,
        min_fold_delta=0.1,
        average_fold_delta=1.0,
        worst_drawdown=-0.45,
        risk_adjusted_score=15.0,
        positive_folds=3,
        fold_count=3,
        gate_status="return positive; risk gates incomplete",
        status="all folds positive",
    )
    stale = AutonomousLearningLeaderboard(
        generated_at=NOW,
        entry_count=1,
        entries=(stale_entry,),
        summary="stale",
    )
    path.write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    valid_candidate = AutonomousLearningCandidate(
        rank=1,
        universe_id="semiconductor-champions",
        model_key="market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk0-cash",
        strategy_name="Market Drawdown Circuit Breaker Semiconductor Sleeve",
        full_delta=6.0,
        stress_delta=5.0,
        min_fold_delta=0.2,
        average_fold_delta=1.0,
        worst_drawdown=-0.25,
        risk_adjusted_score=8.0,
        positive_folds=3,
        fold_count=3,
        gate_status="risk gates passed",
        status="all folds positive",
    )
    control_candidate = valid_candidate.model_copy(
        update={
            "rank": 2,
            "model_key": "market_drawdown_circuit_breaker:top-semi-l126-no-breaker",
            "full_delta": 20.0,
            "risk_adjusted_score": 25.0,
        }
    )
    run = AutonomousLearningCycleRun(
        run_id="new-run",
        generated_at=NOW,
        mode=AutonomousLearningCycleMode.WEEKLY,
        hypothesis_id="new-hypothesis",
        status=AutonomousLearningCycleStatus.COMPLETED,
        start_date=date(2016, 1, 4),
        end_date=date(2026, 5, 29),
        benchmark="SPY",
        feed=DataFeed.IEX,
        universe_ids=("semiconductor-champions",),
        strategy_ids=("market_drawdown_circuit_breaker",),
        candidate_count=2,
        completed_report_count=1,
        skipped_count=0,
        current_champion_model_key="champion",
        top_candidates=(control_candidate, valid_candidate),
        summary="completed",
        next_actions=("review",),
    )

    leaderboard = update_autonomous_learning_leaderboard(
        run,
        path=path,
        markdown_path=markdown_path,
    )

    keys = [entry.model_key for entry in leaderboard.entries]
    assert keys == ["market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk0-cash"]
    assert markdown_path.exists()


def test_late_entry_risk_blocks_candidate_authority_gates() -> None:
    candidate = AutonomousLearningCandidate(
        rank=1,
        universe_id="semiconductor-champions",
        model_key="market_drawdown_circuit_breaker:top-semi-l126-any-dd10-risk0-cash",
        strategy_name="Market Drawdown Circuit Breaker Semiconductor Sleeve",
        full_delta=9.0,
        stress_delta=8.0,
        min_fold_delta=0.2,
        average_fold_delta=1.0,
        worst_drawdown=-0.25,
        risk_adjusted_score=12.0,
        positive_folds=3,
        fold_count=3,
        gate_status="late-entry risk review",
        status="all folds positive",
        benchmark_ladder={"QQQ": 1.0, "XLK": 1.0},
        late_entry_risk=True,
        late_entry_risk_reason=(
            "Latest 63 trading days account for 51.5% of full-period excess return."
        ),
    )

    assert not _candidate_is_promotion_qualified(candidate)
    assert not _candidate_is_pilot_eligible(candidate)
    assert not _candidate_passes_shadow_gate(candidate)


def test_sector_sleeve_blocks_authority_but_can_shadow() -> None:
    candidate = AutonomousLearningCandidate(
        rank=1,
        universe_id="liquid-risk-on",
        model_key="risk_managed_semiconductor:vol-smh-v63-t020-off-cash",
        strategy_name="Risk Managed Semiconductor",
        full_delta=6.0,
        stress_delta=5.0,
        min_fold_delta=0.2,
        average_fold_delta=1.0,
        worst_drawdown=-0.25,
        risk_adjusted_score=8.0,
        positive_folds=3,
        fold_count=3,
        gate_status="sector sleeve only",
        status="all folds positive",
        benchmark_ladder={"QQQ": 1.0, "XLK": 1.0},
        portfolio_governance_classification="sector_sleeve",
        champion_eligible=False,
        average_semiconductor_exposure=0.75,
        peak_semiconductor_exposure=1.0,
    )

    assert not _candidate_is_promotion_qualified(candidate)
    assert not _candidate_is_pilot_eligible(candidate)
    assert _candidate_passes_shadow_gate(candidate)


def test_autonomous_cycle_records_blocked_state_when_data_is_missing(tmp_path) -> None:
    run = AutonomousLearningCycleRunner().run(
        AutonomousLearningCycleConfig(
            run_id="learning-cycle-blocked",
            start_date=date(2023, 1, 3),
            end_date=date(2023, 1, 31),
            universes=("semiconductor-champions",),
            feed=DataFeed.IEX,
            root=tmp_path / "missing-bars",
            output_dir=tmp_path / "reports",
            status_dir=tmp_path / "runtime" / "learning",
            warmup_trading_days=5,
        ),
        generated_at=NOW,
    )

    assert run.status == AutonomousLearningCycleStatus.BLOCKED
    assert run.candidate_count == 0
    assert run.blocked_reasons
    assert "No replay reports completed." in run.blocked_reasons
    assert (tmp_path / "reports" / "learning-cycle-blocked.md").exists()
    assert (tmp_path / "runtime" / "learning" / "latest-learning-cycle.json").exists()


def test_autonomous_catalog_does_not_generate_static_allocation_candidates() -> None:
    catalog = _limited_catalog(
        _filtered_catalog(
            _autonomous_catalog(
                symbols=("XLB", "XLC", "XLE", "XLF", "XLI", "XLK"),
                benchmark="SPY",
                mode=AutonomousLearningCycleMode.WEEKLY,
            ),
            ("static_etf_allocation",),
        ),
        2,
    )

    definitions = catalog.all()

    assert definitions == ()


def test_discovery_scoring_excludes_baseline_and_control_rows() -> None:
    full_report = _report(
        run_id="full",
        rows=(
            _comparison_row(
                rank=1,
                model_key="static_etf_allocation:single-qqq",
                strategy_name="Buy and Hold QQQ",
                net_total_return=0.8,
                excess_return=0.5,
            ),
            _comparison_row(
                rank=2,
                model_key="market_drawdown_circuit_breaker:top-semi-l126-no-breaker",
                strategy_name="Market Drawdown Circuit Breaker Semiconductor Sleeve",
                net_total_return=0.75,
                excess_return=0.45,
            ),
            _comparison_row(
                rank=3,
                model_key="monthly_sector_momentum:grid-l21-n1",
                strategy_name="Monthly Sector Momentum",
                net_total_return=0.7,
                excess_return=0.4,
            ),
        ),
    )
    fold_report = _report(
        run_id="fold-a",
        rows=(
            _comparison_row(
                rank=1,
                model_key="static_etf_allocation:single-qqq",
                strategy_name="Buy and Hold QQQ",
                net_total_return=0.3,
                excess_return=0.2,
            ),
            _comparison_row(
                rank=2,
                model_key="market_drawdown_circuit_breaker:top-semi-l126-no-breaker",
                strategy_name="Market Drawdown Circuit Breaker Semiconductor Sleeve",
                net_total_return=0.4,
                excess_return=0.3,
            ),
            _comparison_row(
                rank=3,
                model_key="monthly_sector_momentum:grid-l21-n1",
                strategy_name="Monthly Sector Momentum",
                net_total_return=0.35,
                excess_return=0.25,
            ),
        ),
    )

    scores = score_discovery_candidates(
        [
            DiscoveryRun(
                universe_id="sector-spdr",
                period_id="full",
                cost_label="base",
                report=full_report,
            ),
            DiscoveryRun(
                universe_id="sector-spdr",
                period_id="fold-a",
                cost_label="base",
                report=fold_report,
            ),
        ],
        fold_ids=("fold-a",),
    )

    assert [score.model_key for score in scores] == [
        "monthly_sector_momentum:grid-l21-n1"
    ]
    assert scores[0].gate_status == "general evidence only"


def test_discovery_scoring_marks_late_entry_risk() -> None:
    reason = (
        "Latest 63 trading days account for 51.5% of full-period excess return."
    )
    full_report = _report(
        run_id="full",
        rows=(
            _comparison_row(
                rank=1,
                model_key=(
                    "market_drawdown_circuit_breaker:"
                    "top-semi-l126-any-dd10-risk0-cash"
                ),
                strategy_name="Market Drawdown Circuit Breaker Semiconductor Sleeve",
                net_total_return=10.0,
                excess_return=9.0,
                late_entry_risk=True,
                late_entry_risk_reason=reason,
                recent_window_excess_share={"63d": 0.515},
            ),
        ),
    )
    fold_report = _report(
        run_id="fold-a",
        rows=(
            _comparison_row(
                rank=1,
                model_key=(
                    "market_drawdown_circuit_breaker:"
                    "top-semi-l126-any-dd10-risk0-cash"
                ),
                strategy_name="Market Drawdown Circuit Breaker Semiconductor Sleeve",
                net_total_return=0.5,
                excess_return=0.2,
            ),
        ),
    )

    scores = score_discovery_candidates(
        [
            DiscoveryRun(
                universe_id="semiconductor-champions",
                period_id="full",
                cost_label="base",
                report=full_report,
            ),
            DiscoveryRun(
                universe_id="semiconductor-champions",
                period_id="fold-a",
                cost_label="base",
                report=fold_report,
            ),
        ],
        fold_ids=("fold-a",),
    )

    assert scores[0].late_entry_risk
    assert scores[0].gate_status == reason


def _report(
    *,
    run_id: str,
    rows: tuple[ReplayComparisonRow, ...],
) -> ReplayComparisonReport:
    return ReplayComparisonReport(
        run_id=run_id,
        generated_at=NOW,
        start_date="2023-01-03",
        end_date="2023-07-31",
        benchmark="SPY",
        rows=rows,
        champion_model_key=rows[0].model_key,
        summary="Test report.",
    )


def _comparison_row(
    *,
    rank: int,
    model_key: str,
    strategy_name: str,
    net_total_return: float,
    excess_return: float,
    late_entry_risk: bool = False,
    late_entry_risk_reason: str | None = None,
    recent_window_excess_share: dict[str, float] | None = None,
) -> ReplayComparisonRow:
    return ReplayComparisonRow(
        rank=rank,
        model_key=model_key,
        strategy_name=strategy_name,
        net_total_return=net_total_return,
        benchmark_total_return=net_total_return - excess_return,
        excess_return=excess_return,
        annualized_return=0.12,
        annualized_volatility=0.18,
        max_drawdown=-0.2,
        turnover=1.0,
        trade_count=4,
        decision_count=6,
        leakage_passed=True,
        research_score=excess_return,
        recent_window_excess_share=recent_window_excess_share or {},
        late_entry_risk=late_entry_risk,
        late_entry_risk_reason=late_entry_risk_reason,
    )
