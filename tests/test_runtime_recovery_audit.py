from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.market_data import FixtureLatestPriceFetcher
from trading_app.runtime import (
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    RuntimeRecoveryAuditor,
    RuntimeSnapshot,
    RuntimeStatus,
    render_recovery_audit_markdown,
    render_recovery_audit_text,
)
from trading_app.runtime.recovery import main as recovery_main
from trading_app.schemas import DataFeed

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_recovery_audit_passes_with_clean_persisted_journals(tmp_path) -> None:
    _persist_recovery_fixture(tmp_path)

    report = RuntimeRecoveryAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_recovery_audit_text(report)
    markdown = render_recovery_audit_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.raw_submission_count == 2
    assert report.recovered_submission_count == 2
    assert report.raw_order_status_count == 1
    assert report.recovered_order_status_count == 1
    assert report.raw_fill_count == 1
    assert report.recovered_fill_count == 1
    assert report.duplicate_order_ids == ()
    assert report.duplicate_fill_ids == ()
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Recovery audit status" in text
    assert "Paper Runtime Restart Recovery Audit" in markdown
    assert (tmp_path / "state" / "latest-recovery-audit-report.json").exists()
    assert (tmp_path / "journal" / "recovery-audits.jsonl").exists()


def test_recovery_audit_fails_duplicate_orders_and_fills(tmp_path) -> None:
    store = _persist_recovery_fixture(tmp_path)
    demo = build_demo_dashboard_snapshot()
    store.persist_submission(demo.paper_report.submissions[0])
    store.persist_fill(demo.recent_fills[0])

    report = RuntimeRecoveryAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.duplicate_order_ids == ("daily-order-1",)
    assert report.duplicate_fill_ids == ("paper-fill-1",)
    assert by_name["duplicate_order_ids"].status == RuntimePreflightStatus.FAILED
    assert by_name["duplicate_fill_ids"].status == RuntimePreflightStatus.FAILED
    assert by_name["runtime_snapshot_alignment"].status == RuntimePreflightStatus.PASSED


def test_recovery_audit_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    complete_dir = tmp_path / "complete"
    missing_dir = tmp_path / "missing"
    _persist_recovery_fixture(complete_dir)

    success = recovery_main(["--output-dir", str(complete_dir), "--json"])
    failure = recovery_main(["--output-dir", str(missing_dir), "--json"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def _persist_recovery_fixture(tmp_path: Path) -> RuntimePersistenceStore:
    store = RuntimePersistenceStore(tmp_path)
    demo = build_demo_dashboard_snapshot()
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
        paper_report=demo.paper_report,
        daily_report=demo.daily_report,
        nightly_learning=demo.nightly_learning,
        active_model_key="monthly_sector_momentum:1.0.0",
    )
    store.persist_runtime_snapshot(snapshot)
    for submission in demo.paper_report.submissions:
        store.persist_submission(submission)
    for status in demo.paper_report.order_statuses:
        store.persist_order_status(status)
    for fill in demo.recent_fills:
        store.persist_fill(fill)
    return store
