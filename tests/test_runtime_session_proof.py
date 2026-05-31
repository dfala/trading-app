from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.broker import BrokerPositionState, BrokerStatementSnapshot
from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.market_data import FixtureLatestPriceFetcher
from trading_app.paper import (
    reconcile_statement_snapshot,
    write_statement_reconciliation_markdown,
)
from trading_app.runtime import (
    RuntimeBrokerOrderHistoryAuditor,
    RuntimeCredentialedSessionAuditor,
    RuntimeCycleResult,
    RuntimeDryRunReport,
    RuntimeDryRunStep,
    RuntimePersistenceStore,
    RuntimePreflightCheck,
    RuntimePreflightReport,
    RuntimePreflightStatus,
    RuntimeSnapshot,
    RuntimeSoakEvidenceReport,
    RuntimeStatus,
    RuntimeValidationReport,
    render_credentialed_session_markdown,
    render_credentialed_session_text,
    write_broker_order_history_json,
)
from trading_app.runtime.audit_coverage import credentialed_session_coverage_gap
from trading_app.runtime.models import RuntimeSecretScanReport
from trading_app.runtime.session_proof import main as session_proof_main
from trading_app.schemas import DataFeed, OrderStatus

START = datetime(2026, 5, 28, 19, tzinfo=UTC)
NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_credentialed_session_proof_passes_with_external_like_artifacts(
    tmp_path,
) -> None:
    _persist_session_base(tmp_path)

    report = RuntimeCredentialedSessionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_credentialed_session_text(report)
    markdown = render_credentialed_session_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.validation_id == "validation-20260529T210000"
    assert report.paper_account_id == "paper-account-1"
    assert report.reviewed_artifact_count == 9
    assert report.external_source_count >= 3
    assert {check.name for check in report.checks} == {
        "preflight_credentials",
        "credentialed_validation",
        "runtime_snapshot_alpaca_paper",
        "dashboard_snapshot_alpaca_paper",
        "latest_price_provenance",
        "soak_session_window",
        "statement_provenance",
        "broker_order_history_provenance",
        "secret_scan_clean",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Credentialed session status" in text
    assert "Credentialed Alpaca Paper Session Proof" in markdown
    assert (tmp_path / "state" / "latest-credentialed-session-report.json").exists()
    assert (tmp_path / "journal" / "credentialed-sessions.jsonl").exists()


def test_credentialed_session_proof_rejects_fixture_and_account_mismatch(
    tmp_path,
) -> None:
    store = _persist_session_base(tmp_path)
    store.persist_validation_report(
        _validation_report().model_copy(update={"id": "validation-fixture"})
    )
    statement_report = reconcile_statement_snapshot(
        _alpaca_paper_report(
            build_demo_dashboard_snapshot().paper_report
        ).ledger_snapshot,
        _matching_statement().model_copy(
            update={
                "account_id": "paper-account-2",
                "source": "fixture-statement",
            }
        ),
        as_of=NOW,
    )
    statement_path = write_statement_reconciliation_markdown(
        statement_report,
        tmp_path / "reports",
    )
    store.persist_statement_reconciliation(
        statement_report,
        markdown_path=statement_path,
    )
    broker_history = store.read_broker_order_history_report()
    assert broker_history is not None
    store.persist_broker_order_history_report(
        broker_history.model_copy(update={"source": "provided"})
    )

    report = RuntimeCredentialedSessionAuditor(
        output_dir=tmp_path,
        expected_paper_account_id="paper-account-1",
    ).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["credentialed_validation"].status == RuntimePreflightStatus.FAILED
    assert by_name["statement_provenance"].status == RuntimePreflightStatus.FAILED
    assert by_name["broker_order_history_provenance"].status == (
        RuntimePreflightStatus.FAILED
    )


def test_credentialed_session_proof_requires_credential_value_secret_scan(
    tmp_path,
) -> None:
    store = _persist_session_base(tmp_path)
    secret_scan = store.read_secret_scan_report()
    assert secret_scan is not None
    store.persist_secret_scan_report(
        secret_scan.model_copy(update={"secret_names_checked": ()})
    )

    report = RuntimeCredentialedSessionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["secret_scan_clean"].status == RuntimePreflightStatus.FAILED
    assert any(
        "secret_names_checked=" in item
        for item in by_name["secret_scan_clean"].evidence
    )


def test_credentialed_session_coverage_requires_reviewable_markdown(
    tmp_path,
) -> None:
    _persist_session_base(tmp_path)
    report = RuntimeCredentialedSessionAuditor(output_dir=tmp_path).audit(as_of=NOW)
    assert credentialed_session_coverage_gap(report) == ()
    assert report.markdown_path is not None
    Path(report.markdown_path).unlink()

    gaps = credentialed_session_coverage_gap(report)

    assert "markdown_path_file=missing" in gaps


def test_credentialed_session_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    _persist_session_base(success_dir)

    success = session_proof_main(["--output-dir", str(success_dir), "--json"])
    failure = session_proof_main(
        ["--output-dir", str(failure_dir), "--json", "--no-persist"]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def _persist_session_base(tmp_path: Path) -> RuntimePersistenceStore:
    store = RuntimePersistenceStore(tmp_path)
    demo = build_demo_dashboard_snapshot()
    paper_report = _alpaca_paper_report(demo.paper_report)
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
        daily_report=demo.daily_report,
        active_model_key="monthly_sector_momentum:1.0.0",
    )
    store.persist_preflight_report(_preflight_report())
    store.persist_dry_run_report(_dry_run_report())
    store.persist_validation_report(_validation_report())
    store.persist_soak_evidence_report(_soak_report(tmp_path))
    store.persist_secret_scan_report(_secret_scan_report(tmp_path))
    store.persist_runtime_snapshot(snapshot)
    store.persist_dashboard_snapshot(
        demo.model_copy(
            update={
                "generated_at": NOW,
                "mode": "Alpaca Paper",
                "broker": "alpaca-paper",
                "runtime_state": snapshot,
                "paper_report": paper_report,
            }
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
    for submission in paper_report.submissions:
        store.persist_submission(submission)
    for status in paper_report.order_statuses:
        store.persist_order_status(status)
    for fill in demo.recent_fills:
        store.persist_fill(fill)
    statement_report = reconcile_statement_snapshot(
        paper_report.ledger_snapshot,
        _matching_statement(),
        as_of=NOW,
    )
    statement_path = write_statement_reconciliation_markdown(
        statement_report,
        tmp_path / "reports",
    )
    store.persist_statement_reconciliation(
        statement_report,
        markdown_path=statement_path,
    )
    broker_history_path = write_broker_order_history_json(
        _broker_history_orders(paper_report),
        tmp_path / "broker-history",
        as_of=NOW,
    )
    RuntimeBrokerOrderHistoryAuditor(
        output_dir=tmp_path,
        order_history_path=broker_history_path,
    ).audit(as_of=NOW)
    return store


def _preflight_report() -> RuntimePreflightReport:
    return RuntimePreflightReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        can_start=True,
        summary="Preflight passed.",
        checks=(
            _preflight_check("credentials", "Alpaca credential variables are present."),
            _preflight_check("paper_boundary", "Runtime is configured for paper mode."),
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
        orders_submitted=0,
        runtime_mode="Alpaca Paper",
        broker_provider="alpaca-paper",
        latest_price_source="alpaca",
        latest_price_feed=DataFeed.IEX.value,
    )


def _validation_report() -> RuntimeValidationReport:
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
    )


def _soak_report(tmp_path: Path) -> RuntimeSoakEvidenceReport:
    return RuntimeSoakEvidenceReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        passed=True,
        output_dir=str(tmp_path),
        started_at=START,
        completed_at=NOW,
        duration_hours=26,
        cycle_count=26,
        market_cycle_count=8,
        off_hours_cycle_count=18,
        overnight_cycle_count=10,
        prices_refreshed_cycle_count=26,
        broker_synced_cycle_count=26,
        order_cycles=1,
        off_schedule_order_cycles=0,
        report_written=True,
        nightly_learning_ran=True,
        dashboard_snapshot_available=True,
        final_health_status="healthy",
        checks=(),
    )


def _secret_scan_report(tmp_path: Path) -> RuntimeSecretScanReport:
    return RuntimeSecretScanReport(
        as_of=NOW,
        status=RuntimePreflightStatus.PASSED,
        passed=True,
        output_dir=str(tmp_path),
        files_scanned=3,
        files_skipped=0,
        secret_names_checked=("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
        summary="No configured secret values were found.",
    )


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
