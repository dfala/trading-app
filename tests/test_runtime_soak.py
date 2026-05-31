from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.runtime import (
    RuntimeCycleResult,
    RuntimeEvent,
    RuntimeEventSeverity,
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    RuntimeSnapshot,
    RuntimeSoakEvidenceAnalyzer,
    RuntimeSoakEvidenceConfig,
    RuntimeStatus,
    render_soak_evidence_text,
)
from trading_app.runtime.soak import main as soak_main

START = datetime(2026, 5, 29, 13, 30, tzinfo=UTC)


def persist_complete_soak(
    tmp_path: Path,
    *,
    off_schedule_order: bool = False,
    missed_price_refresh_cycle: bool = False,
    missed_broker_sync_cycle: bool = False,
    runtime_warning_event: bool = False,
    runtime_error_event: bool = False,
    include_report: bool = True,
    include_learning: bool = True,
    include_snapshot: bool = True,
    include_health: bool = True,
) -> None:
    store = RuntimePersistenceStore(tmp_path)
    for index in range(26):
        as_of = START + timedelta(hours=index)
        events = []
        if runtime_warning_event and index == 5:
            events.append(
                RuntimeEvent(
                    timestamp=as_of,
                    severity=RuntimeEventSeverity.WARNING,
                    category="market_data",
                    message="Latest prices were briefly stale.",
                    evidence=("SPY",),
                )
            )
        if runtime_error_event and index == 6:
            events.append(
                RuntimeEvent(
                    timestamp=as_of,
                    severity=RuntimeEventSeverity.ERROR,
                    category="broker_sync",
                    message="Paper broker sync failed during soak.",
                    evidence=("alpaca-paper",),
                )
            )
        cycle = RuntimeCycleResult(
            as_of=as_of,
            status=RuntimeStatus.RUNNING,
            prices_refreshed=not (missed_price_refresh_cycle and index == 3),
            broker_synced=not (missed_broker_sync_cycle and index == 4),
            orders_submitted=1 if off_schedule_order and index == 1 else 0,
            report_written=include_report and index == 7,
            nightly_learning_ran=include_learning and index == 11,
            events=tuple(events),
        )
        store.persist_cycle(cycle)
        store.persist_events(tuple(events))

    completed_at = START + timedelta(hours=25)
    if include_snapshot:
        runtime_snapshot = RuntimeSnapshot(
            as_of=completed_at,
            status=RuntimeStatus.RUNNING,
            mode="Alpaca Paper",
            active_model_key="monthly_sector_momentum:1.0.0",
        )
        store.persist_runtime_snapshot(runtime_snapshot)
        store.persist_dashboard_snapshot(
            build_demo_dashboard_snapshot().model_copy(
                update={
                    "mode": "Alpaca Paper",
                    "broker": "alpaca-paper",
                    "runtime_state": runtime_snapshot,
                }
            )
        )
    if include_health:
        store.persist_health_report(
            RuntimeHealthReport(
                as_of=completed_at,
                status=RuntimeHealthStatus.HEALTHY,
                summary="Soak runtime remained healthy.",
                next_action="Review final broker account order history.",
                checks=(
                    RuntimeHealthCheck(
                        name="runtime_loop",
                        status=RuntimeHealthStatus.HEALTHY,
                        message="Runtime heartbeat is fresh.",
                        checked_at=completed_at,
                    ),
                ),
            )
        )


def analyzer(tmp_path: Path) -> RuntimeSoakEvidenceAnalyzer:
    return RuntimeSoakEvidenceAnalyzer(
        RuntimeSoakEvidenceConfig(
            output_dir=tmp_path,
            max_market_gap=timedelta(hours=1, seconds=1),
            max_off_hours_gap=timedelta(hours=1, seconds=1),
        )
    )


def test_complete_soak_evidence_passes_and_persists(tmp_path) -> None:
    persist_complete_soak(tmp_path)

    report = analyzer(tmp_path).analyze(as_of=START + timedelta(hours=26))

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.duration_hours == 25
    assert report.market_cycle_count > 0
    assert report.off_hours_cycle_count > 0
    assert report.overnight_cycle_count > 0
    assert report.prices_refreshed_cycle_count == 26
    assert report.broker_synced_cycle_count == 26
    assert report.missed_price_refresh_cycles == 0
    assert report.missed_broker_sync_cycles == 0
    assert report.runtime_event_count == 0
    assert report.runtime_warning_event_count == 0
    assert report.runtime_error_event_count == 0
    assert report.report_written
    assert report.nightly_learning_ran
    assert report.dashboard_snapshot_available
    assert report.final_health_status == "healthy"
    assert (tmp_path / "state" / "latest-soak-evidence-report.json").exists()
    assert (tmp_path / "journal" / "soak-evidence.jsonl").exists()


def test_too_short_soak_fails_duration_check(tmp_path) -> None:
    store = RuntimePersistenceStore(tmp_path)
    store.persist_cycle(
        RuntimeCycleResult(
            as_of=START,
            status=RuntimeStatus.RUNNING,
            prices_refreshed=True,
            broker_synced=True,
        )
    )
    store.persist_cycle(
        RuntimeCycleResult(
            as_of=START + timedelta(hours=1),
            status=RuntimeStatus.RUNNING,
            prices_refreshed=True,
            broker_synced=True,
        )
    )

    report = analyzer(tmp_path).analyze(as_of=START + timedelta(hours=2))
    failed = {
        check.name
        for check in report.checks
        if check.status == RuntimePreflightStatus.FAILED
    }

    assert not report.passed
    assert "duration" in failed


def test_off_schedule_order_fails_soak_evidence(tmp_path) -> None:
    persist_complete_soak(tmp_path, off_schedule_order=True)

    report = analyzer(tmp_path).analyze(as_of=START + timedelta(hours=26))
    failed = {
        check.name
        for check in report.checks
        if check.status == RuntimePreflightStatus.FAILED
    }

    assert not report.passed
    assert report.off_schedule_order_cycles == 1
    assert "off_schedule_orders" in failed


def test_missed_price_refresh_or_broker_sync_fails_soak_evidence(tmp_path) -> None:
    missed_price_dir = tmp_path / "missed-price"
    missed_broker_dir = tmp_path / "missed-broker"
    persist_complete_soak(missed_price_dir, missed_price_refresh_cycle=True)
    persist_complete_soak(missed_broker_dir, missed_broker_sync_cycle=True)

    price_report = analyzer(missed_price_dir).analyze(as_of=START + timedelta(hours=26))
    broker_report = analyzer(missed_broker_dir).analyze(
        as_of=START + timedelta(hours=26)
    )
    price_failed = {
        check.name
        for check in price_report.checks
        if check.status == RuntimePreflightStatus.FAILED
    }
    broker_failed = {
        check.name
        for check in broker_report.checks
        if check.status == RuntimePreflightStatus.FAILED
    }

    assert not price_report.passed
    assert price_report.missed_price_refresh_cycles == 1
    assert "price_refresh_cycles" in price_failed
    assert not broker_report.passed
    assert broker_report.missed_broker_sync_cycles == 1
    assert "broker_sync_cycles" in broker_failed


def test_runtime_error_events_fail_soak_evidence(tmp_path) -> None:
    warning_dir = tmp_path / "warning"
    error_dir = tmp_path / "error"
    persist_complete_soak(warning_dir, runtime_warning_event=True)
    persist_complete_soak(error_dir, runtime_error_event=True)

    warning_report = analyzer(warning_dir).analyze(as_of=START + timedelta(hours=26))
    error_report = analyzer(error_dir).analyze(as_of=START + timedelta(hours=26))
    error_failed = {
        check.name
        for check in error_report.checks
        if check.status == RuntimePreflightStatus.FAILED
    }

    assert warning_report.passed
    assert warning_report.status == RuntimePreflightStatus.WARNING
    assert warning_report.runtime_event_count == 1
    assert warning_report.runtime_warning_event_count == 1
    assert warning_report.runtime_error_event_count == 0
    assert not error_report.passed
    assert error_report.runtime_event_count == 1
    assert error_report.runtime_error_event_count == 1
    assert "runtime_error_events" in error_failed


def test_missing_report_learning_dashboard_and_health_evidence_fail(tmp_path) -> None:
    persist_complete_soak(
        tmp_path,
        include_report=False,
        include_learning=False,
        include_snapshot=False,
        include_health=False,
    )

    report = analyzer(tmp_path).analyze(as_of=START + timedelta(hours=26))
    failed = {
        check.name
        for check in report.checks
        if check.status == RuntimePreflightStatus.FAILED
    }

    assert not report.passed
    assert {
        "daily_report",
        "nightly_learning",
        "dashboard_snapshot",
        "final_health",
    }.issubset(failed)


def test_soak_evidence_text_does_not_leak_credentials(tmp_path) -> None:
    persist_complete_soak(tmp_path)
    report = analyzer(tmp_path).analyze(as_of=START + timedelta(hours=26))

    text = render_soak_evidence_text(report)

    assert "Soak evidence status" in text
    assert "key-present" not in text
    assert "secret-present" not in text


def test_soak_cli_returns_success_and_failure(tmp_path, capsys) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    persist_complete_soak(success_dir)

    success = soak_main(
        [
            "--output-dir",
            str(success_dir),
            "--max-market-gap-seconds",
            "3601",
            "--max-off-hours-gap-seconds",
            "3601",
            "--json",
        ]
    )
    failure = soak_main(
        [
            "--output-dir",
            str(failure_dir),
            "--json",
            "--no-persist",
        ]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output
