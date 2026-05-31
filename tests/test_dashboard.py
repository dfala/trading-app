from __future__ import annotations

import json

import pytest

from trading_app.dashboard import (
    build_demo_dashboard_snapshot,
    render_dashboard_html,
    write_dashboard,
)
from trading_app.dashboard.render import render_interactive_dashboard_html
from trading_app.dashboard.server import (
    create_dashboard_server,
    dashboard_response,
    is_local_dashboard_host,
    snapshot_json,
)


def test_dashboard_snapshot_contains_operator_state() -> None:
    snapshot = build_demo_dashboard_snapshot()

    assert snapshot.mode == "Paper Trading"
    assert snapshot.broker == "memory-paper"
    assert not snapshot.kill_switch_enabled
    assert snapshot.cash == 7500
    assert snapshot.estimated_equity == 10000
    assert snapshot.open_orders == 0
    assert len(snapshot.paper_report.ledger_snapshot.positions) == 1
    assert len(snapshot.recent_fills) == 1
    assert snapshot.daily_report.risk_report.rejection_count == 1
    assert snapshot.nightly_learning.active_model_unchanged
    assert snapshot.model_cards[0].label == "Champion"
    assert snapshot.model_cards[1].state == "backtest"
    assert snapshot.model_arena is not None
    assert snapshot.model_arena.promotion_requests[0].manual_approval_required
    assert snapshot.live_readiness is not None
    assert snapshot.live_readiness.status.value == "ready_for_review"
    assert snapshot.health_report is not None
    assert snapshot.health_report.status.value == "degraded"
    assert snapshot.active_strategy_definition is not None
    assert snapshot.active_strategy_definition.strategy_id == "monthly_sector_momentum"
    assert snapshot.daily_report.data_quality_report is not None
    assert snapshot.daily_report.data_quality_report.status.value == "warning"
    assert not snapshot.daily_report.data_quality_report.can_use_for_trading
    assert snapshot.statement_reconciliation is not None
    assert snapshot.statement_reconciliation.reconciled
    assert snapshot.statement_reconciliation_path is not None


def test_dashboard_html_renders_required_sections_and_visuals() -> None:
    html = render_dashboard_html(build_demo_dashboard_snapshot())

    assert "Operator Dashboard" in html
    assert "Paper Portfolio" in html
    assert "Paper Boundary" in html
    assert "Latest Prices" in html
    assert "Data Quality Evidence" in html
    assert "Runtime Proof" in html
    assert "Functional Readiness" in html
    assert "Final Acceptance" in html
    assert "Statement Review" in html
    assert "Reports And Learning" in html
    assert "AI copilot confidence" in html
    assert "manual review is required" in html
    assert "Audit Trail" in html
    assert "Report path" in html
    assert "Accounting" in html
    assert "Tax Estimate" in html
    assert "Research estimate only" in html
    assert "No statement differences above tolerance" in html
    assert "Not filing-grade tax accounting" in html
    assert "Risk State" in html
    assert "Model Arena" in html
    assert "Daily Report" in html
    assert "Operator Controls" in html
    assert "Runtime Alerts" in html
    assert "Runtime Health" in html
    assert "Incident Command" in html
    assert "Active Model" in html
    assert "Monthly Sector ETF Momentum" in html
    assert "Known Failure Modes" in html
    assert "AI Role" in html
    assert "Rejected Signals" in html
    assert "Nightly Learning" in html
    assert "Live Readiness" in html
    assert "Positions" in html
    assert "Recent Fills" in html
    assert "IEX development-grade demo feed" in html
    assert "IEX/free data is development-grade" in html
    assert "Kill switch OFF" in html
    assert "MAX_ORDERS_PER_DAY" in html
    assert "No live-money actions are available" in html
    assert "Benchmark" in html
    assert 'data-field="estimated-equity"' in html
    assert "data-latest-price-list" in html
    assert 'data-field="data-quality-status"' in html
    assert 'data-field="data-quality-chip"' in html
    assert 'data-field="data-quality-research-usable"' in html
    assert 'data-field="data-quality-trading-usable"' in html
    assert 'data-field="data-quality-sources"' in html
    assert 'data-field="data-quality-feeds"' in html
    assert "data-data-quality-issue-list" in html
    assert 'data-field="completion-status"' in html
    assert 'data-field="completion-path"' in html
    assert 'data-field="final-acceptance-status"' in html
    assert 'data-field="final-acceptance-path"' in html
    assert 'data-field="statement-status"' in html
    assert 'data-field="statement-path"' in html
    assert "data-statement-issue-list" in html
    assert 'data-field="tax-active-lots"' in html
    assert 'data-field="tax-lot-method"' in html
    assert 'data-field="tax-estimated-tax"' in html
    assert "data-alert-list" in html
    assert "data-position-list" in html
    assert "data-fill-list" in html
    assert "data-health-check-list" in html
    assert "data-incident-list" in html
    assert "data-control-grid" in html
    assert 'data-field="last-control-action"' in html
    assert 'data-field="daily-report-path"' in html
    assert 'data-field="learning-memo-path"' in html
    assert 'data-field="live-readiness-panel-status"' in html
    assert 'data-field="broker-connection"' in html
    assert 'data-field="active-model-key"' in html
    assert 'data-field="trading-authority"' in html
    assert 'data-field="active-strategy-name"' in html
    assert "data-active-strategy-failure-list" in html
    assert "data-active-strategy-ai-role-list" in html
    assert "Daily close only" in html
    assert "$0 real capital" in html
    assert html.count("<svg") >= 2


def test_interactive_dashboard_shell_fetches_snapshot_api() -> None:
    html = render_interactive_dashboard_html(build_demo_dashboard_snapshot())

    assert "fetch('/api/snapshot'" in html
    assert "fetch('/api/control'" in html
    assert "function applySnapshot" in html
    assert "renderRuntimeProof(snapshot)" in html
    assert "renderActiveStrategy(snapshot)" in html
    assert "renderFinalAcceptance(snapshot)" in html
    assert "renderLatestPrices(snapshot)" in html
    assert "renderDataQuality(snapshot)" in html
    assert "renderStatementReview(snapshot)" in html
    assert "renderAlerts(snapshot)" in html
    assert "renderPositions(snapshot)" in html
    assert "renderFills(snapshot)" in html
    assert "renderHealth(snapshot)" in html
    assert "renderControls(snapshot)" in html
    assert "renderReports(snapshot)" in html
    assert "renderLiveReadiness(snapshot)" in html
    assert "completion_audit" in html
    assert "final_acceptance" in html
    assert "tax_active_lot_count" not in html
    assert "tax-active-lots" in html
    assert "setInterval" in html
    assert "data-refresh-time" in html


def test_dashboard_snapshot_serializes_for_api() -> None:
    payload = json.loads(snapshot_json(build_demo_dashboard_snapshot()))

    assert payload["mode"] == "Paper Trading"
    assert payload["broker"] == "memory-paper"
    assert payload["paper_report"]["reconciliation"]["reconciled"]
    assert payload["daily_report"]["risk_report"]["rejection_count"] == 1
    assert payload["daily_report"]["data_quality_report"]["status"] == "warning"
    assert payload["daily_report"]["data_quality_report"]["warnings"] == 1
    assert not payload["daily_report"]["data_quality_report"]["can_use_for_trading"]
    assert payload["daily_report"]["tax_report"]["active_lot_count"] == 1
    assert payload["daily_report"]["tax_report"]["lot_method"] == "fifo"
    assert payload["daily_report"]["tax_report"]["tax_estimate_available"] is False
    assert payload["model_arena"]["comparisons"][0]["score_delta"] > 0
    assert payload["live_readiness"]["status"] == "ready_for_review"
    assert payload["alerts"][0]["code"] == "risk_rejection"
    assert payload["health_report"]["status"] == "degraded"
    assert payload["statement_reconciliation"]["reconciled"]
    assert payload["statement_reconciliation"]["statement"]["provider"] == (
        "memory-paper"
    )
    assert payload["statement_reconciliation_path"].endswith(
        "statement-reconciliation-statement-2026-05-29.md"
    )
    assert payload["final_acceptance"] is None
    assert payload["active_strategy_definition"]["strategy_id"] == (
        "monthly_sector_momentum"
    )
    assert payload["active_strategy_definition"]["authority"] == "paper"


def test_dashboard_server_route_logic_serves_html_and_json() -> None:
    html_status, html_type, html = dashboard_response(
        "/",
        snapshot_provider=build_demo_dashboard_snapshot,
    )
    api_status, api_type, api_body = dashboard_response(
        "/api/snapshot",
        snapshot_provider=build_demo_dashboard_snapshot,
    )
    payload = json.loads(api_body)
    health_status, health_type, health_body = dashboard_response(
        "/api/health",
        snapshot_provider=build_demo_dashboard_snapshot,
    )
    health_payload = json.loads(health_body)

    assert html_status.value == 200
    assert html_type.startswith("text/html")
    assert "Operator Dashboard" in html
    assert api_status.value == 200
    assert api_type.startswith("application/json")
    assert payload["mode"] == "Paper Trading"
    assert health_status.value == 200
    assert health_type.startswith("application/json")
    assert health_payload["status"] == "degraded"


def test_dashboard_server_is_local_only_by_default() -> None:
    with pytest.raises(ValueError, match="local-only"):
        create_dashboard_server("0.0.0.0", 0)

    assert is_local_dashboard_host("127.0.0.1")
    assert not is_local_dashboard_host("0.0.0.0")


def test_dashboard_writer_creates_reviewable_html_file(tmp_path) -> None:
    output_path = write_dashboard(
        build_demo_dashboard_snapshot(),
        tmp_path / "operator-dashboard.html",
    )

    assert output_path.name == "operator-dashboard.html"
    written = output_path.read_text(encoding="utf-8")
    assert written.startswith("<!doctype html>")
    assert "Trading Lab Operator Dashboard" in written
