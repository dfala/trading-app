from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.broker import BrokerPositionState, BrokerStatementSnapshot
from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.market_data import FixtureLatestPriceFetcher
from trading_app.reporting import write_markdown_report
from trading_app.runtime import (
    OperatorControlAction,
    OperatorControlRequest,
    RuntimeControlCenter,
    RuntimeCycleResult,
    RuntimeDryRunReport,
    RuntimeDryRunStep,
    RuntimeEvent,
    RuntimeEventSeverity,
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimePersistenceStore,
    RuntimePostRunReviewer,
    RuntimePreflightCheck,
    RuntimePreflightReport,
    RuntimePreflightStatus,
    RuntimeSnapshot,
    RuntimeStatus,
    RuntimeValidationChecklistItem,
    RuntimeValidationReport,
    render_post_run_review_markdown,
    render_post_run_review_text,
    write_broker_order_history_json,
)
from trading_app.runtime.audit_coverage import REQUIRED_VALIDATION_CHECKLIST_ITEMS
from trading_app.runtime.review import main as review_main
from trading_app.schemas import DataFeed, OrderStatus

START = datetime(2026, 5, 29, 13, 30, tzinfo=UTC)
NOW = START + timedelta(hours=26)
SECRET_ENV = {
    "ALPACA_API_KEY": "paper-secret-value-1234",
    "ALPACA_SECRET_KEY": "paper-secret-value-5678",
}


def test_post_run_review_passes_with_complete_artifacts_and_statement(
    tmp_path,
) -> None:
    statement_path, order_history_path = _persist_review_base(tmp_path)

    report = RuntimePostRunReviewer(
        output_dir=tmp_path,
        statement_path=statement_path,
        broker_order_history_path=order_history_path,
        env=SECRET_ENV,
        max_market_gap=timedelta(hours=1, seconds=1),
        max_off_hours_gap=timedelta(hours=1, seconds=1),
    ).review(as_of=NOW)
    text = render_post_run_review_text(report)
    markdown = render_post_run_review_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert {step.name for step in report.steps} == {
        "operations_readiness",
        "lifecycle_drill",
        "soak_evidence",
        "restart_recovery",
        "dashboard_consistency",
        "dashboard_visual",
        "statement_reconciliation",
        "secret_scan",
        "model_governance",
        "schedule_guardrails",
        "order_guardrails",
        "fill_sync",
        "data_quality_audit",
        "broker_order_history",
        "credentialed_session",
        "evidence_coherence",
        "completion_audit",
        "artifact_integrity",
        "evidence_bundle",
    }
    assert report.operations_readiness_report.passed
    assert report.lifecycle_drill_report.passed
    assert report.dashboard_consistency_report.passed
    assert report.dashboard_visual_report.passed
    assert report.recovery_audit_report.passed
    assert report.model_governance_report.passed
    assert report.order_guardrail_report.passed
    assert report.schedule_guardrail_report.passed
    assert report.fill_sync_report.passed
    assert report.data_quality_audit_report.passed
    assert report.broker_order_history_report.passed
    assert report.credentialed_session_report.passed
    assert report.evidence_coherence_report.passed
    assert report.artifact_integrity_report.passed
    assert report.artifact_integrity_report.hash_mismatch_count == 0
    integrity_labels = {item.label for item in report.artifact_integrity_report.items}
    assert "evidence bundle state" in integrity_labels
    assert "evidence bundle markdown" in integrity_labels
    assert report.statement_reconciliation_report.reconciled
    assert report.completion_audit_report.passed
    assert report.evidence_bundle_report.ready_for_operator_review
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Post-run review status" in text
    assert "Paper Runtime Post-Run Review" in markdown
    assert "paper-secret-value" not in text
    assert "paper-secret-value" not in markdown
    assert (tmp_path / "state" / "latest-post-run-review-report.json").exists()
    assert (tmp_path / "journal" / "post-run-reviews.jsonl").exists()


def test_post_run_review_fails_for_mismatched_statement(tmp_path) -> None:
    _statement_path, order_history_path = _persist_review_base(tmp_path)
    mismatched = _matching_statement().model_copy(update={"cash": Decimal("7501")})
    statement_path = tmp_path / "mismatched-statement.json"
    statement_path.write_text(mismatched.model_dump_json(), encoding="utf-8")

    report = RuntimePostRunReviewer(
        output_dir=tmp_path,
        statement_path=statement_path,
        broker_order_history_path=order_history_path,
        env=SECRET_ENV,
        max_market_gap=timedelta(hours=1, seconds=1),
        max_off_hours_gap=timedelta(hours=1, seconds=1),
    ).review(as_of=NOW)
    by_name = {step.name: step for step in report.steps}

    assert not report.passed
    assert by_name["statement_reconciliation"].status == RuntimePreflightStatus.FAILED
    assert by_name["completion_audit"].status == RuntimePreflightStatus.FAILED


def test_post_run_review_scans_extra_secret_artifact_paths(tmp_path) -> None:
    statement_path, order_history_path = _persist_review_base(tmp_path)
    exported_dashboard = tmp_path / "exported-dashboard.html"
    exported_dashboard.write_text(
        "<html>paper-secret-value-5678</html>",
        encoding="utf-8",
    )

    report = RuntimePostRunReviewer(
        output_dir=tmp_path,
        statement_path=statement_path,
        broker_order_history_path=order_history_path,
        env=SECRET_ENV,
        secret_scan_paths=(exported_dashboard,),
        max_market_gap=timedelta(hours=1, seconds=1),
        max_off_hours_gap=timedelta(hours=1, seconds=1),
    ).review(as_of=NOW)
    by_name = {step.name: step for step in report.steps}
    text = render_post_run_review_text(report)
    markdown = render_post_run_review_markdown(report)

    assert not report.passed
    assert by_name["secret_scan"].status == RuntimePreflightStatus.FAILED
    assert "scan_roots=3" in by_name["secret_scan"].evidence
    assert not report.secret_scan_report.passed
    assert str(exported_dashboard) in report.secret_scan_report.scan_roots
    assert str(statement_path) in report.secret_scan_report.scan_roots
    assert "paper-secret-value" not in text
    assert "paper-secret-value" not in markdown


def test_post_run_review_scans_external_statement_source_path(tmp_path) -> None:
    runtime_dir = tmp_path / "runtime"
    _statement_path, order_history_path = _persist_review_base(runtime_dir)
    external_statement = tmp_path / "external-statement.csv"
    external_statement.write_text(
        _matching_statement_csv(secret_note=SECRET_ENV["ALPACA_SECRET_KEY"]),
        encoding="utf-8",
    )

    report = RuntimePostRunReviewer(
        output_dir=runtime_dir,
        statement_path=external_statement,
        broker_order_history_path=order_history_path,
        env=SECRET_ENV,
        max_market_gap=timedelta(hours=1, seconds=1),
        max_off_hours_gap=timedelta(hours=1, seconds=1),
    ).review(as_of=NOW)
    by_name = {step.name: step for step in report.steps}
    text = render_post_run_review_text(report)
    markdown = render_post_run_review_markdown(report)

    assert not report.passed
    assert by_name["statement_reconciliation"].status == RuntimePreflightStatus.PASSED
    assert by_name["secret_scan"].status == RuntimePreflightStatus.FAILED
    assert str(external_statement) in report.secret_scan_report.scan_roots
    assert report.secret_scan_report.findings[0].path == "external-statement.csv"
    assert report.secret_scan_report.findings[0].secret_name == "ALPACA_SECRET_KEY"
    assert "paper-secret-value" not in text
    assert "paper-secret-value" not in markdown


def test_post_run_review_preserves_warning_soak_status(tmp_path) -> None:
    statement_path, order_history_path = _persist_review_base(
        tmp_path, include_warning_event=True
    )

    report = RuntimePostRunReviewer(
        output_dir=tmp_path,
        statement_path=statement_path,
        broker_order_history_path=order_history_path,
        env=SECRET_ENV,
        max_market_gap=timedelta(hours=1, seconds=1),
        max_off_hours_gap=timedelta(hours=1, seconds=1),
    ).review(as_of=NOW)
    by_name = {step.name: step for step in report.steps}

    assert not report.passed
    assert report.status == RuntimePreflightStatus.WARNING
    assert by_name["soak_evidence"].status == RuntimePreflightStatus.WARNING
    assert any(
        "runtime_warning_events=1" in item for item in by_name["soak_evidence"].evidence
    )


def test_post_run_review_cli_outputs_json_and_exit_codes(
    tmp_path, monkeypatch, capsys
) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    statement_path, order_history_path = _persist_review_base(success_dir)
    monkeypatch.setenv("ALPACA_API_KEY", SECRET_ENV["ALPACA_API_KEY"])
    monkeypatch.setenv("ALPACA_SECRET_KEY", SECRET_ENV["ALPACA_SECRET_KEY"])

    success = review_main(
        [
            "--output-dir",
            str(success_dir),
            "--statement",
            str(statement_path),
            "--broker-order-history",
            str(order_history_path),
            "--max-market-gap-seconds",
            "3601",
            "--max-off-hours-gap-seconds",
            "3601",
            "--max-dashboard-age-seconds",
            "315360000",
            "--include-secret-scan-path",
            str(success_dir / "reports"),
            "--json",
        ]
    )
    failure = review_main(
        [
            "--output-dir",
            str(failure_dir),
            "--statement",
            str(statement_path),
            "--broker-order-history",
            str(order_history_path),
            "--json",
            "--no-persist",
        ]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output
    assert "paper-secret-value" not in output


def _persist_review_base(
    tmp_path: Path, *, include_warning_event: bool = False
) -> tuple[Path, Path]:
    store = RuntimePersistenceStore(tmp_path)
    demo = build_demo_dashboard_snapshot()
    paper_report = _alpaca_paper_report(demo.paper_report)
    daily_report, daily_report_path = _daily_report_artifact(
        demo.daily_report, tmp_path
    )
    nightly_learning = _external_like_model(demo.nightly_learning)
    control_state = _external_like_model(demo.control_state)
    alerts = _external_like_models(demo.alerts)
    latest_prices = FixtureLatestPriceFetcher(
        {"SPY": Decimal("500")},
        observed_at=NOW,
        source="alpaca",
    ).fetch_latest_prices(("SPY",), as_of=NOW, feed=DataFeed.IEX)
    snapshot = RuntimeSnapshot(
        as_of=NOW,
        status=RuntimeStatus.RUNNING,
        mode="Alpaca Paper",
        latest_prices=latest_prices,
        paper_report=paper_report,
        daily_report=daily_report,
        nightly_learning=nightly_learning,
        active_model_key="monthly_sector_momentum:1.0.0",
        daily_report_path=str(daily_report_path),
        control_state=control_state,
        alerts=alerts,
        health_report=_health_report(),
    )
    for index in range(26):
        as_of = START + timedelta(hours=index)
        events = ()
        if include_warning_event and index == 5:
            events = (
                RuntimeEvent(
                    timestamp=as_of,
                    severity=RuntimeEventSeverity.WARNING,
                    category="market_data",
                    message="Latest prices were briefly stale.",
                    evidence=("SPY",),
                ),
            )
        store.persist_cycle(
            RuntimeCycleResult(
                as_of=as_of,
                status=RuntimeStatus.RUNNING,
                prices_refreshed=True,
                broker_synced=True,
                orders_submitted=0,
                report_written=index == 7,
                nightly_learning_ran=index == 11,
                events=events,
            )
        )
        store.persist_events(events)
    store.persist_preflight_report(_preflight_report())
    store.persist_dry_run_report(_dry_run_report())
    store.persist_validation_report(_validation_report(tmp_path))
    store.persist_runtime_snapshot(snapshot)
    store.persist_dashboard_snapshot(
        _external_like_dashboard_snapshot(
            demo,
            update={
                "generated_at": NOW,
                "mode": "Alpaca Paper",
                "broker": "alpaca-paper",
                "runtime_state": snapshot,
                "paper_report": paper_report,
                "daily_report": daily_report,
                "nightly_learning": nightly_learning,
                "control_state": snapshot.control_state,
                "alerts": snapshot.alerts,
                "health_report": snapshot.health_report,
                "statement_reconciliation": None,
                "statement_reconciliation_path": None,
                "completion_audit": None,
            },
        )
    )
    store.persist_health_report(_health_report())
    store.persist_daily_report(daily_report, markdown_path=daily_report_path)
    store.persist_learning_run(nightly_learning)
    for submission in paper_report.submissions:
        store.persist_submission(submission)
    for status in paper_report.order_statuses:
        store.persist_order_status(status)
    for fill in demo.recent_fills:
        store.persist_fill(fill)
    store.persist_reconciliation(paper_report.reconciliation)
    _persist_lifecycle_controls(store)

    statement_path = tmp_path / "statement.json"
    statement_path.write_text(_matching_statement().model_dump_json(), encoding="utf-8")
    order_history_path = write_broker_order_history_json(
        _broker_history_orders(paper_report),
        tmp_path / "broker-history",
        as_of=NOW,
    )
    return statement_path, order_history_path


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


def _external_like_dashboard_snapshot(
    snapshot: OperatorDashboardSnapshot,
    *,
    update: dict,
) -> OperatorDashboardSnapshot:
    payload = json.loads(snapshot.model_dump_json())
    payload = _replace_demo_provenance(payload)
    payload["session_state"] = None
    return OperatorDashboardSnapshot.model_validate_json(
        json.dumps(payload)
    ).model_copy(update=update)


def _external_like_model(model):
    payload = json.loads(model.model_dump_json())
    payload = _replace_demo_provenance(payload)
    return model.__class__.model_validate_json(json.dumps(payload))


def _external_like_models(values):
    return tuple(_external_like_model(value) for value in values)


def _replace_demo_provenance(value):
    if isinstance(value, dict):
        return {key: _replace_demo_provenance(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_replace_demo_provenance(child) for child in value]
    if isinstance(value, str):
        return (
            value.replace("demo", "paper")
            .replace("Demo", "Paper")
            .replace("fixture", "market")
        )
    return value


def _matching_statement() -> BrokerStatementSnapshot:
    demo = build_demo_dashboard_snapshot()
    positions = tuple(
        BrokerPositionState(
            symbol=position.symbol,
            quantity=position.quantity,
            average_entry_price=position.average_cost,
        )
        for position in demo.paper_report.ledger_snapshot.positions
    )
    return BrokerStatementSnapshot(
        statement_id="statement-2026-05-29",
        as_of=NOW,
        provider="alpaca-paper",
        account_id="paper-account-1",
        cash=demo.paper_report.ledger_snapshot.cash,
        positions=positions,
        source="alpaca-paper:paper-portfolio-capture",
    )


def _matching_statement_csv(*, secret_note: str) -> str:
    statement = _matching_statement()
    position = statement.positions[0]
    market_value = position.quantity * position.average_entry_price
    return "\n".join(
        [
            (
                "record_type,statement_id,as_of,provider,account_id,cash,source,"
                "symbol,quantity,average_entry_price,market_value,current_price,"
                "operator_note"
            ),
            (
                f"account,{statement.statement_id},{statement.as_of.isoformat()},"
                f"{statement.provider},{statement.account_id},{statement.cash},"
                f"{statement.source},,,,,,{secret_note}"
            ),
            (
                f"position,,,,,,,{position.symbol},{position.quantity},"
                f"{position.average_entry_price},{market_value},,"
            ),
            "",
        ]
    )


def _alpaca_paper_report(report):
    broker_portfolio = report.broker_portfolio.model_copy(
        update={"provider": "alpaca-paper"}
    )
    reconciliation = report.reconciliation.model_copy(
        update={"broker_portfolio": broker_portfolio}
    )
    submissions = tuple(
        submission.model_copy(
            update={
                "broker_order": submission.broker_order.model_copy(
                    update={"provider": "alpaca-paper"}
                )
            }
        )
        if submission.broker_order is not None
        else submission
        for submission in report.submissions
    )
    return report.model_copy(
        update={
            "broker_portfolio": broker_portfolio,
            "reconciliation": reconciliation,
            "submissions": submissions,
        }
    )


def _broker_history_orders(paper_report):
    filled_by_order = {
        fill.order_id: sum(
            item.quantity
            for item in paper_report.fills
            if item.order_id == fill.order_id
        )
        for fill in paper_report.fills
    }
    orders = []
    for submission in paper_report.submissions:
        broker_order = submission.broker_order
        if broker_order is None:
            continue
        filled = filled_by_order.get(submission.order.id, Decimal("0"))
        orders.append(
            broker_order.model_copy(
                update={
                    "provider": "alpaca-paper",
                    "filled_quantity": filled,
                    "status": OrderStatus.FILLED if filled else broker_order.status,
                    "average_fill_price": Decimal("500") if filled else None,
                    "provider_status": "filled"
                    if filled
                    else broker_order.provider_status,
                }
            )
        )
    return tuple(orders)


def _daily_report_artifact(report, tmp_path: Path):
    report = _external_like_model(report)
    generated_at = START + timedelta(hours=7)
    reports_dir = tmp_path / "reports"
    markdown_path = reports_dir / f"daily-report-{report.trading_day.isoformat()}.md"
    metadata = report.report_metadata.model_copy(
        update={
            "generated_at": generated_at,
            "markdown_path": str(markdown_path),
        }
    )
    updated = report.model_copy(
        update={
            "generated_at": generated_at,
            "report_metadata": metadata,
        }
    )
    written_path = write_markdown_report(updated, reports_dir)
    return updated, written_path


def _preflight_report() -> RuntimePreflightReport:
    return RuntimePreflightReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        can_start=True,
        summary="Preflight passed.",
        checks=(
            _preflight_check("credentials", "Alpaca credential variables are present."),
            _preflight_check("paper_boundary", "Runtime is configured for paper mode."),
            _preflight_check("runtime_schedule", "Daily-close schedule is configured."),
        ),
        warnings=0,
        failures=0,
    )


def _preflight_check(name: str, message: str) -> RuntimePreflightCheck:
    return RuntimePreflightCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED,
        message=message,
        remediation="No action required.",
        checked_at=NOW,
    )


def _dry_run_report() -> RuntimeDryRunReport:
    return RuntimeDryRunReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        can_start_supervised_runtime=True,
        monitor_only=True,
        summary="Monitor-only dry run passed.",
        preflight_report=_preflight_report(),
        cycle_result=RuntimeCycleResult(
            as_of=NOW,
            status=RuntimeStatus.RUNNING,
            prices_refreshed=True,
            broker_synced=True,
            orders_submitted=0,
        ),
        steps=(
            RuntimeDryRunStep(
                name="paper_order_safety",
                status=RuntimePreflightStatus.PASSED,
                message="Monitor-only dry run submitted no orders.",
                checked_at=NOW,
            ),
        ),
        warnings=0,
        failures=0,
        orders_before=0,
        orders_after=0,
        orders_submitted=0,
        runtime_mode="Alpaca Paper",
        broker_provider="alpaca-paper",
        latest_price_source="alpaca",
        latest_price_feed=DataFeed.IEX.value,
    )


def _validation_report(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = reports_dir / "validation.md"
    markdown_path.write_text("validation evidence", encoding="utf-8")
    return RuntimeValidationReport(
        id="validation-20260529T210000",
        started_at=START - timedelta(minutes=30),
        completed_at=START - timedelta(minutes=1),
        status=RuntimePreflightStatus.PASSED,
        can_start_full_day_soak=True,
        summary="Validation passed.",
        preflight_report=_preflight_report(),
        monitor_dry_run_report=_dry_run_report(),
        steps=(),
        checklist=_validation_checklist(),
        warnings=0,
        failures=0,
        latest_prices_refreshed=True,
        latest_prices_fresh=True,
        broker_synced=True,
        dashboard_snapshot_serialized=True,
        report_written=True,
        nightly_learning_ran=True,
        orders_submitted=0,
        broker_providers=("alpaca-paper",),
        latest_price_sources=("alpaca",),
        latest_price_feeds=(DataFeed.IEX.value,),
        markdown_path=str(markdown_path),
    )


def _validation_checklist() -> tuple[RuntimeValidationChecklistItem, ...]:
    return tuple(
        RuntimeValidationChecklistItem(
            name=name,
            status=RuntimePreflightStatus.PASSED,
            message="Validation checklist item passed.",
            evidence=("passed=true",),
        )
        for name in sorted(REQUIRED_VALIDATION_CHECKLIST_ITEMS)
    )


def _health_report() -> RuntimeHealthReport:
    return RuntimeHealthReport(
        as_of=NOW,
        status=RuntimeHealthStatus.HEALTHY,
        summary="Runtime health is clean.",
        next_action="Continue monitoring.",
        checks=(
            RuntimeHealthCheck(
                name="runtime_loop",
                status=RuntimeHealthStatus.HEALTHY,
                message="Runtime heartbeat is fresh.",
                checked_at=NOW,
            ),
        ),
    )
