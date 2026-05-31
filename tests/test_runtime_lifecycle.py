from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.reporting import write_markdown_report
from trading_app.runtime import (
    OperatorControlAction,
    OperatorControlRequest,
    RuntimeControlCenter,
    RuntimeCycleResult,
    RuntimeLifecycleDrillAuditor,
    RuntimeOperationsReadinessAuditor,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    RuntimeSnapshot,
    RuntimeStatus,
    render_lifecycle_drill_markdown,
    render_lifecycle_drill_text,
)
from trading_app.runtime.lifecycle import main as lifecycle_main

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_lifecycle_drill_passes_with_startup_shutdown_and_controls(
    tmp_path,
) -> None:
    _persist_lifecycle_base(tmp_path)

    report = RuntimeLifecycleDrillAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_lifecycle_drill_text(report)
    markdown = render_lifecycle_drill_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.operator_control_count == 6
    assert report.emergency_stop_confirmed
    assert report.shutdown_procedure_documented
    assert {check.name for check in report.checks} == {
        "operations_readiness",
        "startup_command_documented",
        "dashboard_local_only",
        "runtime_start_evidence",
        "operator_controls_exercised",
        "control_state_recovered",
        "emergency_stop_controls_exercised",
        "force_reconciliation_and_report_effects",
        "shutdown_procedure_documented",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Lifecycle drill status" in text
    assert "Paper Runtime Lifecycle Drill" in markdown
    assert (tmp_path / "state" / "latest-lifecycle-drill-report.json").exists()
    assert (tmp_path / "journal" / "lifecycle-drills.jsonl").exists()


def test_lifecycle_drill_fails_when_controls_are_not_exercised(tmp_path) -> None:
    store = RuntimePersistenceStore(tmp_path)
    RuntimeOperationsReadinessAuditor(output_dir=tmp_path).audit(as_of=NOW)
    store.persist_cycle(RuntimeCycleResult(as_of=NOW, status=RuntimeStatus.RUNNING))

    report = RuntimeLifecycleDrillAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["operator_controls_exercised"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert by_name["control_state_recovered"].status == RuntimePreflightStatus.FAILED
    assert by_name["emergency_stop_controls_exercised"].status == (
        RuntimePreflightStatus.FAILED
    )


def test_lifecycle_drill_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    _persist_lifecycle_base(success_dir)

    success = lifecycle_main(["--output-dir", str(success_dir), "--json"])
    failure = lifecycle_main(
        ["--output-dir", str(failure_dir), "--json", "--no-persist"]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def _persist_lifecycle_base(tmp_path: Path) -> RuntimePersistenceStore:
    store = RuntimePersistenceStore(tmp_path)
    demo = build_demo_dashboard_snapshot()
    daily_report_path = write_markdown_report(demo.daily_report, tmp_path / "reports")
    store.persist_daily_report(demo.daily_report, markdown_path=daily_report_path)
    store.persist_runtime_snapshot(
        RuntimeSnapshot(
            as_of=NOW,
            status=RuntimeStatus.RUNNING,
            mode="Alpaca Paper",
            paper_report=demo.paper_report,
            daily_report=demo.daily_report,
            active_model_key="monthly_sector_momentum:1.0.0",
            daily_report_path=str(daily_report_path),
            control_state=demo.control_state,
        )
    )
    store.persist_cycle(
        RuntimeCycleResult(
            as_of=NOW,
            status=RuntimeStatus.RUNNING,
            prices_refreshed=True,
            broker_synced=True,
        )
    )
    store.persist_reconciliation(demo.paper_report.reconciliation)
    RuntimeOperationsReadinessAuditor(output_dir=tmp_path).audit(as_of=NOW)
    _persist_lifecycle_controls(store)
    return store


def _persist_lifecycle_controls(store: RuntimePersistenceStore) -> None:
    center = RuntimeControlCenter()
    for index, action in enumerate(
        (
            OperatorControlAction.PAUSE_RUNTIME,
            OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
            OperatorControlAction.FORCE_RECONCILIATION,
            OperatorControlAction.GENERATE_REPORT,
            OperatorControlAction.RESUME_RUNTIME,
            OperatorControlAction.DISABLE_PAPER_KILL_SWITCH,
        )
    ):
        store.persist_control_result(
            center.apply(
                OperatorControlRequest(
                    action=action,
                    requested_at=NOW + timedelta(seconds=index),
                    requested_by="test-operator",
                    reason="lifecycle drill",
                )
            )
        )
