from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from trading_app.learning.autonomous import (
    AutonomousLearningCandidate,
    AutonomousLearningCycleMode,
    AutonomousLearningCycleRun,
    AutonomousLearningCycleStatus,
)
from trading_app.learning.autonomous_service import (
    DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES,
    AutonomousLearningPromotionObservation,
    AutonomousLearningPromotionStatus,
    AutonomousLearningService,
    AutonomousLearningServiceConfig,
    AutonomousLearningServiceStatus,
    AutonomousLearningServiceTask,
    _generated_historical_backlog_profiles,
    _historical_profile_lane,
    _initial_state,
    _promotion_gate,
    _with_due_times,
    market_learning_window,
    next_due_task,
)
from trading_app.schemas import DataFeed

AFTER_CLOSE = datetime(2026, 6, 1, 21, tzinfo=UTC)
MARKET_HOURS = datetime(2026, 6, 1, 15, tzinfo=UTC)


class RecordingRunner:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.configs = []

    def run(self, config, *, generated_at):
        self.configs.append(config)
        if self.fail:
            raise RuntimeError("simulated cycle failure")
        return _cycle(
            config.run_id,
            generated_at,
            mode=config.mode,
            hypothesis_id=config.hypothesis_id,
            universe_ids=config.universes,
            strategy_ids=config.strategy_ids,
        )


def test_after_close_learning_uses_latest_closed_trading_day(tmp_path) -> None:
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=_config(tmp_path),
        runner=runner,
        clock=lambda: AFTER_CLOSE,
        sleeper=lambda seconds: None,
    )

    state = service.run_forever(max_loops=1)

    assert state.service_status == AutonomousLearningServiceStatus.IDLE
    assert state.last_completed_task == AutonomousLearningServiceTask.FRESH_MARKET_DATA
    assert state.last_fresh_market_data_trading_day == date(2026, 6, 1)
    assert runner.configs[0].end_date == date(2026, 6, 1)
    assert runner.configs[0].fetch_missing
    assert runner.configs[0].hypothesis_id == "fresh-market-data-learning"
    assert runner.configs[0].mode == AutonomousLearningCycleMode.NIGHTLY
    assert state.next_fresh_market_data_due_at == datetime(
        2026, 6, 2, 20, 15, tzinfo=UTC
    )


def test_historical_experiments_are_due_during_market_hours(tmp_path) -> None:
    config = _config(tmp_path)
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )
    state = service.run_once(now=MARKET_HOURS)

    assert state.last_completed_task == (
        AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT
    )
    assert runner.configs[0].run_id.startswith(
        "learning-cycle-historical-semiconductor-risk-overlays-"
    )
    assert runner.configs[0].hypothesis_id == "semiconductor-risk-overlays"
    assert runner.configs[0].universes == ("semiconductor-champions",)
    assert runner.configs[0].mode == AutonomousLearningCycleMode.SMOKE
    assert runner.configs[0].max_strategies == 2
    assert state.last_historical_hypothesis_id == "semiconductor-risk-overlays"
    assert state.last_historical_fingerprint
    assert state.next_historical_fingerprint
    assert state.current_historical_hypothesis_id is None
    assert state.current_historical_fingerprint is None
    assert state.current_historical_lane is None
    assert state.last_historical_lane == "finalist_tuning"
    assert state.next_historical_lane
    assert state.next_historical_hypothesis_id == (
        "champion-breaker-sensitivity-expanded"
    )
    assert state.historical_hypothesis_counts == {
        "semiconductor-risk-overlays": 1,
    }
    assert state.historical_fingerprint_counts == {
        state.last_historical_fingerprint: 1,
    }
    assert state.historical_lane_counts == {"finalist_tuning": 1}
    assert next_due_task(state=state, now=MARKET_HOURS, config=config) is None
    assert (
        next_due_task(
            state=state,
            now=MARKET_HOURS + timedelta(minutes=2),
            config=config,
        )
        == AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT
    )


def test_historical_experiments_rotate_hypothesis_profiles(tmp_path) -> None:
    config = _config(tmp_path)
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )

    first = service.run_once(now=MARKET_HOURS)
    second = service.run_once(now=MARKET_HOURS + timedelta(minutes=2))

    assert first.last_historical_hypothesis_id == "semiconductor-risk-overlays"
    assert second.last_historical_hypothesis_id == (
        "champion-breaker-sensitivity-expanded"
    )
    assert second.next_historical_hypothesis_id == "semiconductor-alpha-blends"
    assert runner.configs[1].hypothesis_id == "champion-breaker-sensitivity-expanded"
    assert runner.configs[1].mode == AutonomousLearningCycleMode.WEEKLY
    assert runner.configs[1].universes == ("semiconductor-champions",)
    assert runner.configs[1].strategy_ids == ("market_drawdown_circuit_breaker",)
    assert runner.configs[1].max_strategies == 2
    assert second.historical_hypothesis_counts == {
        "semiconductor-risk-overlays": 1,
        "champion-breaker-sensitivity-expanded": 1,
    }


def test_historical_experiments_stop_after_one_novelty_sweep(tmp_path) -> None:
    config = _config(tmp_path).model_copy(update={"dynamic_historical_backlog": False})
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )
    state = None

    for index, profile in enumerate(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES):
        state = service.run_once(now=MARKET_HOURS + timedelta(minutes=index * 2))
        assert state.last_historical_hypothesis_id == profile.profile_id

    assert state is not None
    assert len(runner.configs) == len(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES)
    assert state.next_historical_hypothesis_id is None
    assert state.next_historical_experiment_due_at is None
    assert (
        next_due_task(
            state=state,
            now=MARKET_HOURS + timedelta(minutes=20),
            config=config,
        )
        is None
    )

    exhausted = service.run_once(now=MARKET_HOURS + timedelta(minutes=20))

    assert exhausted.service_status == AutonomousLearningServiceStatus.IDLE
    assert exhausted.current_task is None
    assert exhausted.next_historical_hypothesis_id is None
    assert len(runner.configs) == len(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES)


def test_historical_experiments_can_repeat_sweeps_when_explicitly_enabled(
    tmp_path,
) -> None:
    config = _config(tmp_path).model_copy(
        update={
            "dynamic_historical_backlog": False,
            "repeat_historical_sweeps": True,
        }
    )
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )

    for index in range(len(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES) + 1):
        state = service.run_once(now=MARKET_HOURS + timedelta(minutes=index * 2))

    assert state.next_historical_hypothesis_id == (
        "champion-breaker-sensitivity-expanded"
    )
    assert runner.configs[-1].hypothesis_id == "semiconductor-risk-overlays"
    assert len(runner.configs) == len(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES) + 1


def test_dynamic_historical_backlog_continues_after_base_sweep(tmp_path) -> None:
    config = _config(tmp_path)
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )

    for index in range(len(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES) + 1):
        state = service.run_once(now=MARKET_HOURS + timedelta(minutes=index * 2))

    assert state.dynamic_historical_backlog_enabled
    assert state.dynamic_historical_profile_count > 0
    assert state.dynamic_historical_profile_count > 480
    assert state.last_historical_hypothesis_id is not None
    assert state.last_historical_hypothesis_id.startswith("priority-tune-")
    assert runner.configs[-1].hypothesis_id.startswith("priority-tune-")
    assert state.next_historical_hypothesis_id is not None
    assert state.next_historical_lane in {
        "priority_tuning",
        "new_exploration",
        "finalist_tuning",
        "stress_validation",
    }


def test_dynamic_backlog_prefers_priority_tuning_profiles(tmp_path) -> None:
    status_dir = tmp_path / "runtime" / "learning"
    status_dir.mkdir(parents=True)
    (status_dir / "learning-leaderboard.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "universe_id": "semiconductor-champions",
                        "model_key": (
                            "market_drawdown_circuit_breaker:"
                            "top-semi-l126-any-dd08-risk0-cash"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    profiles = _generated_historical_backlog_profiles(_config(tmp_path))

    assert profiles[0].profile_id.startswith("priority-tune-")
    assert profiles[0].universes == ("semiconductor-champions",)
    assert profiles[0].strategy_ids == ("benchmark_relative_strength_etf",)
    assert profiles[0].max_strategies == 2
    assert any(profile.profile_id.startswith("auto-tune-") for profile in profiles)
    assert any(profile.profile_id.startswith("auto-explore-") for profile in profiles)


def test_priority_tuning_profiles_include_requested_model_rotations(tmp_path) -> None:
    config = _config(tmp_path).model_copy(update={"max_strategies_historical": 36})
    profiles = _generated_historical_backlog_profiles(config)

    requested_targets = {
        "benchmark_relative_strength_etf:grid-l126-t63-n1": (
            "benchmark_relative_strength_etf",
        ),
        "cash_rotation_model:grid-l63-n3-b040": ("cash_rotation_model",),
        "cash_rotation_model:grid-l63-n2-b040": ("cash_rotation_model",),
        ("market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk025-cash"): (
            "market_drawdown_circuit_breaker",
        ),
    }

    for model_key, strategy_ids in requested_targets.items():
        matches = [
            profile
            for profile in profiles
            if profile.profile_id.startswith("priority-tune-")
            and model_key in profile.summary
        ]
        assert matches
        assert {profile.strategy_ids for profile in matches} == {strategy_ids}
        assert {profile.universes for profile in matches} == {
            ("semiconductor-champions",)
        }
        assert {_historical_profile_lane(profile) for profile in matches} == {
            "priority_tuning"
        }
        assert max(profile.max_strategies for profile in matches) >= 36


def test_default_historical_profiles_exclude_static_allocation_candidates() -> None:
    for profile in DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES:
        assert "static_etf_allocation" not in profile.strategy_ids


def test_default_historical_profiles_include_macro_risk_state_exploration() -> None:
    profile_ids = {
        profile.profile_id for profile in DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES
    }

    assert "macro-risk-state-overlay" in profile_ids
    assert "cross-asset-risk-barometer" in profile_ids


def test_screening_controls_are_passed_to_cycle_config(tmp_path) -> None:
    config = _config(tmp_path).model_copy(
        update={
            "screening_enabled": True,
            "screening_max_strategies": 10,
            "screening_top_k": 4,
        }
    )
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )

    state = service.run_once(now=MARKET_HOURS)

    assert runner.configs[0].screening_enabled
    assert runner.configs[0].screening_max_strategies == 10
    assert runner.configs[0].screening_top_k == 4
    assert "cheap first-pass screening enabled" in state.policy_summary


def test_legacy_historical_state_seeds_first_hypothesis_profile(tmp_path) -> None:
    config = _config(tmp_path)
    legacy = _initial_state(MARKET_HOURS, config).model_copy(
        update={
            "last_historical_experiment_at": MARKET_HOURS,
            "last_historical_experiment_attempt_at": MARKET_HOURS,
            "last_cycle_run_id": "learning-cycle-historical-20260601T150000Z",
            "last_cycle_status": "completed",
        }
    )

    migrated = _with_due_times(
        legacy,
        now=MARKET_HOURS + timedelta(minutes=1),
        config=config,
    )

    assert migrated.last_historical_hypothesis_id == "semiconductor-risk-overlays"
    assert migrated.last_historical_fingerprint
    assert migrated.historical_hypothesis_counts == {
        "semiconductor-risk-overlays": 1,
    }
    assert migrated.historical_fingerprint_counts == {
        migrated.last_historical_fingerprint: 1,
    }
    assert migrated.next_historical_hypothesis_id == (
        "champion-breaker-sensitivity-expanded"
    )


def test_failed_cycle_is_throttled_until_retry_window(tmp_path) -> None:
    runner = RecordingRunner(fail=True)
    config = _config(tmp_path)
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )

    failed = service.run_once(now=MARKET_HOURS)
    throttled = service.run_once(now=MARKET_HOURS + timedelta(minutes=10))

    assert failed.service_status == AutonomousLearningServiceStatus.FAILED
    assert failed.last_error == "simulated cycle failure"
    assert failed.current_historical_hypothesis_id is None
    assert throttled.service_status == AutonomousLearningServiceStatus.IDLE
    assert throttled.last_error == "simulated cycle failure"
    assert len(runner.configs) == 1


def test_interrupted_historical_attempt_retries_after_cooldown(tmp_path) -> None:
    config = _config(tmp_path)
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )
    completed = service.run_once(now=MARKET_HOURS)
    interrupted_at = MARKET_HOURS + timedelta(minutes=2)
    stale = completed.model_copy(
        update={
            "service_status": AutonomousLearningServiceStatus.RUNNING_CYCLE,
            "current_task": AutonomousLearningServiceTask.HISTORICAL_EXPERIMENT,
            "active_run_id": "interrupted-run",
            "current_historical_hypothesis_id": completed.next_historical_hypothesis_id,
            "current_historical_fingerprint": completed.next_historical_fingerprint,
            "last_historical_experiment_attempt_at": interrupted_at,
            "last_error": None,
        }
    )
    service._write_state(stale)

    throttled = service.run_once(now=interrupted_at + timedelta(seconds=30))
    resumed = service.run_once(now=interrupted_at + timedelta(minutes=1, seconds=1))

    assert throttled.service_status == AutonomousLearningServiceStatus.IDLE
    assert throttled.current_historical_hypothesis_id is None
    assert throttled.next_historical_experiment_due_at == (
        interrupted_at + timedelta(minutes=1)
    )
    assert len(runner.configs) == 2
    assert resumed.last_historical_hypothesis_id == (
        "champion-breaker-sensitivity-expanded"
    )


def test_tuning_mode_marks_repeated_historical_cycle_configs(tmp_path) -> None:
    config = _config(tmp_path).model_copy(
        update={
            "dynamic_historical_backlog": False,
            "tuning_mode": True,
        }
    )
    runner = RecordingRunner()
    service = AutonomousLearningService(
        config=config,
        runner=runner,
        clock=lambda: MARKET_HOURS,
        sleeper=lambda seconds: None,
    )

    for index in range(len(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES) + 1):
        state = service.run_once(now=MARKET_HOURS + timedelta(minutes=index * 2))

    assert state.next_historical_hypothesis_id == (
        "champion-breaker-sensitivity-expanded"
    )
    assert runner.configs[-1].hypothesis_id == "semiconductor-risk-overlays"
    assert runner.configs[-1].tuning_mode
    assert len(runner.configs) == len(DEFAULT_HISTORICAL_HYPOTHESIS_PROFILES) + 1


def test_promotion_gate_requires_repeated_cross_day_evidence(tmp_path) -> None:
    config = _config(tmp_path)
    same_day = tuple(
        _observation(
            observed_at=AFTER_CLOSE + timedelta(hours=index),
            trading_day=date(2026, 6, 1),
            run_id=f"same-day-{index}",
        )
        for index in range(3)
    )
    cross_day = tuple(
        _observation(
            observed_at=AFTER_CLOSE + timedelta(days=index),
            trading_day=date(2026, 6, 1 + index),
            run_id=f"cross-day-{index}",
        )
        for index in range(3)
    )

    same_day_gate = _promotion_gate(same_day, config=config)
    cross_day_gate = _promotion_gate(cross_day, config=config)

    assert same_day_gate.status == AutonomousLearningPromotionStatus.WAITING
    assert cross_day_gate.status == (
        AutonomousLearningPromotionStatus.READY_FOR_MANUAL_REVIEW
    )
    assert cross_day_gate.manual_approval_required


def test_market_window_detects_after_close() -> None:
    window = market_learning_window(AFTER_CLOSE, _config(tmp_path=None))

    assert not window.is_market_open
    assert window.is_after_close_learning_window
    assert window.trading_day == date(2026, 6, 1)


def _config(tmp_path) -> AutonomousLearningServiceConfig:
    root = tmp_path / "bars" if tmp_path is not None else Path("data/market_data/bars")
    output_dir = (
        tmp_path / "reports" if tmp_path is not None else Path("data/research/replay")
    )
    status_dir = (
        tmp_path / "runtime" / "learning"
        if tmp_path is not None
        else Path("data/runtime/learning")
    )
    return AutonomousLearningServiceConfig(
        start_date=date(2023, 1, 3),
        feed=DataFeed.IEX,
        root=root,
        output_dir=output_dir,
        status_dir=status_dir,
        poll_seconds=1,
        max_strategies_historical=2,
        max_strategies_fresh=2,
    )


def _cycle(
    run_id: str,
    generated_at: datetime,
    *,
    mode: AutonomousLearningCycleMode = AutonomousLearningCycleMode.NIGHTLY,
    hypothesis_id: str = "default",
    universe_ids: tuple[str, ...] = ("semiconductor-champions",),
    strategy_ids: tuple[str, ...] = ("market_drawdown_circuit_breaker",),
) -> AutonomousLearningCycleRun:
    candidate = AutonomousLearningCandidate(
        rank=1,
        universe_id="semiconductor-champions",
        model_key="candidate:1",
        strategy_name="Candidate",
        full_delta=0.2,
        stress_delta=0.1,
        positive_folds=3,
        fold_count=3,
        min_fold_delta=0.05,
        average_fold_delta=0.08,
        worst_drawdown=-0.2,
        risk_adjusted_score=1.5,
        gate_status="risk gates passed",
        status="all folds positive",
    )
    return AutonomousLearningCycleRun(
        run_id=run_id,
        generated_at=generated_at,
        mode=mode,
        hypothesis_id=hypothesis_id,
        status=AutonomousLearningCycleStatus.COMPLETED,
        start_date=date(2023, 1, 3),
        end_date=date(2026, 6, 1),
        benchmark="SPY",
        feed=DataFeed.IEX,
        universe_ids=universe_ids,
        strategy_ids=strategy_ids,
        candidate_count=1,
        completed_report_count=1,
        skipped_count=0,
        current_champion_model_key="champion:1",
        recommended_challenger_model_key="candidate:1",
        top_candidates=(candidate,),
        summary="Candidate repeated enough to be observed.",
        next_actions=("Manual review remains required.",),
    )


def _observation(
    *,
    observed_at: datetime,
    trading_day: date,
    run_id: str,
) -> AutonomousLearningPromotionObservation:
    return AutonomousLearningPromotionObservation(
        observed_at=observed_at,
        trading_day=trading_day,
        run_id=run_id,
        candidate_model_key="candidate:1",
        full_delta=0.2,
        stress_delta=0.1,
        min_fold_delta=0.05,
        worst_drawdown=-0.2,
        gate_status="risk gates passed",
        candidate_status="all folds positive",
    )
