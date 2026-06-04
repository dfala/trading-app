from __future__ import annotations

import json
from http import HTTPStatus
from http.client import HTTPConnection
from threading import Thread

import pytest

from trading_app.dashboard import (
    build_demo_dashboard_snapshot,
)
from trading_app.dashboard.model_performance import _strategy_profile
from trading_app.dashboard.server import (
    create_dashboard_server,
    dashboard_response,
    is_local_dashboard_host,
    is_local_dashboard_url,
    snapshot_json,
)
from trading_app.strategies.catalog import (
    benchmark_relative_strength_etf_definition,
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


def test_dashboard_response_returns_503_when_snapshot_provider_raises() -> None:
    def failing_provider():
        raise RuntimeError("snapshot failed")

    status, content_type, body = dashboard_response(
        "/api/snapshot",
        snapshot_provider=failing_provider,
    )
    payload = json.loads(body)

    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert content_type == "application/json; charset=utf-8"
    assert payload == {
        "error": "dashboard snapshot unavailable",
        "detail": "snapshot failed",
    }


def test_dashboard_response_returns_503_when_health_provider_raises() -> None:
    def failing_health_provider():
        raise RuntimeError("health failed")

    status, content_type, body = dashboard_response(
        "/api/health",
        health_provider=failing_health_provider,
    )
    payload = json.loads(body)

    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert content_type == "application/json; charset=utf-8"
    assert payload == {
        "error": "dashboard health unavailable",
        "detail": "health failed",
    }


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


def test_dashboard_server_route_logic_serves_moved_notice_and_json() -> None:
    moved_status, moved_type, moved_body = dashboard_response(
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

    assert moved_status == HTTPStatus.GONE
    assert moved_type.startswith("text/plain")
    assert "Next.js operator dashboard" in moved_body
    assert api_status.value == 200
    assert api_type.startswith("application/json")
    assert payload["mode"] == "Paper Trading"
    assert health_status.value == 200
    assert health_type.startswith("application/json")
    assert health_payload["status"] == "degraded"


def test_dashboard_model_performance_route(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_payload(model_key: str, *, universe_id: str | None = None):
        return {
            "model_key": model_key,
            "universe_id": universe_id,
            "points": [],
        }

    monkeypatch.setattr(
        "trading_app.dashboard.server.build_model_performance_payload",
        fake_payload,
    )

    missing_status, missing_type, missing_body = dashboard_response(
        "/api/model-performance",
        snapshot_provider=build_demo_dashboard_snapshot,
    )
    status, content_type, body = dashboard_response(
        "/api/model-performance?model_key=test_strategy%3Av1&universe_id=semis",
        snapshot_provider=build_demo_dashboard_snapshot,
    )
    payload = json.loads(body)

    assert missing_status == HTTPStatus.BAD_REQUEST
    assert missing_type.startswith("application/json")
    assert json.loads(missing_body)["error"] == "model_key is required"
    assert status == HTTPStatus.OK
    assert content_type.startswith("application/json")
    assert payload["model_key"] == "test_strategy:v1"
    assert payload["universe_id"] == "semis"


def test_model_strategy_profile_explains_catalog_definition() -> None:
    definition = benchmark_relative_strength_etf_definition(
        version="grid-l126-t63-n1",
        universe=("QQQ", "XLK", "SMH", "SOXX", "SPY"),
        lookback_days=126,
        tracking_window_days=63,
        top_n=1,
    )

    profile = _strategy_profile(definition, ("QQQ", "XLK", "SMH", "SOXX"))

    assert profile is not None
    assert profile.hypothesis == definition.hypothesis
    assert profile.signal_logic == definition.signal_logic
    assert profile.sizing_logic == "Equal weight the top 1 qualifying ETF(s)."
    assert profile.exit_logic == definition.exit_logic
    assert profile.trading_cadence == "daily_close"
    assert profile.invests_in == ("QQQ", "XLK", "SMH", "SOXX")
    assert profile.failure_modes == definition.failure_modes
    assert profile.parameters["lookback_days"] == "126"
    assert profile.parameters["tracking_window_days"] == "63"
    assert profile.parameters["top_n"] == "1"
    assert "universe" not in profile.parameters
    assert "benchmark" not in profile.parameters


def test_model_strategy_profile_is_none_without_catalog_definition() -> None:
    assert _strategy_profile(None, ("QQQ",)) is None


def test_dashboard_server_redirects_browser_routes_to_next_when_configured() -> None:
    redirect_url = "http://127.0.0.1:3003/"
    html_status, html_type, html_body = dashboard_response(
        "/",
        snapshot_provider=build_demo_dashboard_snapshot,
        dashboard_redirect_url=redirect_url,
    )
    dashboard_status, _, dashboard_body = dashboard_response(
        "/dashboard",
        snapshot_provider=build_demo_dashboard_snapshot,
        dashboard_redirect_url=redirect_url,
    )
    api_status, api_type, api_body = dashboard_response(
        "/api/snapshot",
        snapshot_provider=build_demo_dashboard_snapshot,
        dashboard_redirect_url=redirect_url,
    )

    assert html_status == dashboard_status == HTTPStatus.FOUND
    assert html_type.startswith("text/plain")
    assert html_body == redirect_url
    assert dashboard_body == redirect_url
    assert api_status == HTTPStatus.OK
    assert api_type.startswith("application/json")
    assert json.loads(api_body)["mode"] == "Paper Trading"


def test_dashboard_http_redirect_sets_location_header() -> None:
    redirect_url = "http://127.0.0.1:3003/"
    server = create_dashboard_server(
        "127.0.0.1",
        0,
        dashboard_redirect_url=redirect_url,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = HTTPConnection(host, port, timeout=5)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.request("HEAD", "/dashboard")
            head_response = connection.getresponse()
            head_response.read()
        finally:
            connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.status == HTTPStatus.FOUND
    assert response.getheader("Location") == redirect_url
    assert redirect_url in body
    assert head_response.status == HTTPStatus.FOUND
    assert head_response.getheader("Location") == redirect_url
    assert head_response.getheader("Content-Length") == "0"


def test_dashboard_server_is_local_only_by_default() -> None:
    with pytest.raises(ValueError, match="local-only"):
        create_dashboard_server("0.0.0.0", 0)

    assert is_local_dashboard_host("127.0.0.1")
    assert not is_local_dashboard_host("0.0.0.0")
    assert is_local_dashboard_url("http://127.0.0.1:3003/")
    assert is_local_dashboard_url("http://localhost:3003/")
    assert not is_local_dashboard_url("https://127.0.0.1:3003/")
    assert not is_local_dashboard_url("http://example.com/")
    with pytest.raises(ValueError, match="local-only"):
        create_dashboard_server(
            "127.0.0.1",
            0,
            dashboard_redirect_url="http://example.com/",
        )
