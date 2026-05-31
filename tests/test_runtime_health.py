from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.dashboard.server import dashboard_response
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime import (
    AlwaysOnPaperRuntime,
    AlwaysOnPaperRuntimeConfig,
    OperatorControlAction,
    RuntimeAlertCode,
    RuntimeHealthEngine,
    RuntimeHealthStatus,
    RuntimePersistenceStore,
    render_health_markdown_report,
)
from trading_app.schemas import DataFeed
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)


def make_runtime(
    *,
    latest_observed_at: datetime = AFTER_CLOSE,
    output_dir=None,
) -> AlwaysOnPaperRuntime:
    symbols = ("AAA", "BBB", "SPY")
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(symbols),
            tradable_symbols=frozenset(symbols),
        )
    )
    service = PaperTradingService(
        broker=InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000")),
        starting_cash=Decimal("10000"),
        risk_engine=risk_engine,
    )
    return AlwaysOnPaperRuntime(
        service=service,
        latest_price_fetcher=FixtureLatestPriceFetcher(
            {"AAA": Decimal("100"), "BBB": Decimal("120"), "SPY": Decimal("500")},
            observed_at=latest_observed_at,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="health-test"),
        strategy=MonthlySectorMomentumStrategy(
            universe=("AAA", "BBB"),
            lookback_days=5,
            top_n=1,
        ),
        risk_engine=risk_engine,
        config=AlwaysOnPaperRuntimeConfig(
            symbols=symbols,
            output_dir=output_dir or AlwaysOnPaperRuntimeConfig().output_dir,
            feed=DataFeed.IEX,
        ),
    )


def test_health_engine_reports_watch_before_first_cycle(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)

    report = RuntimeHealthEngine().evaluate(runtime.snapshot(as_of=AFTER_CLOSE))

    assert report.status == RuntimeHealthStatus.WATCH
    assert any(check.name == "runtime_loop" for check in report.checks)
    assert report.incidents[0].status == RuntimeHealthStatus.WATCH


def test_runtime_run_once_exposes_and_persists_healthy_report(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)

    cycle = runtime.run_once(as_of=AFTER_CLOSE)
    report = runtime.snapshot(as_of=AFTER_CLOSE).health_report
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert cycle.orders_submitted == 1
    assert report is not None
    assert report.status == RuntimeHealthStatus.HEALTHY
    assert recovered.health_report == report
    assert recovered.health_report_path is not None
    assert recovered.health_report_path.exists()
    assert recovered.health_report_path.read_text(encoding="utf-8").startswith(
        "# Runtime Health Incident Review"
    )
    assert (tmp_path / "state" / "latest-health-report.json").exists()
    assert (tmp_path / "state" / "latest-health-report-path.json").exists()


def test_health_engine_marks_stale_heartbeat_critical(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.run_once(as_of=AFTER_CLOSE)

    report = RuntimeHealthEngine(max_cycle_age=timedelta(minutes=30)).evaluate(
        runtime.snapshot(as_of=AFTER_CLOSE + timedelta(hours=1))
    )

    assert report.status == RuntimeHealthStatus.CRITICAL
    assert any(incident.id == "check-runtime_loop" for incident in report.incidents)


def test_health_engine_marks_stale_prices_degraded(tmp_path) -> None:
    runtime = make_runtime(
        latest_observed_at=AFTER_CLOSE - timedelta(hours=2),
        output_dir=tmp_path,
    )

    runtime.run_once(as_of=AFTER_CLOSE)
    report = runtime.snapshot(as_of=AFTER_CLOSE).health_report

    assert report is not None
    assert report.status == RuntimeHealthStatus.DEGRADED
    assert RuntimeAlertCode.MARKET_DATA_STALE in {
        alert.code for alert in runtime.snapshot(as_of=AFTER_CLOSE).alerts
    }


def test_health_engine_marks_reconciliation_break_critical(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.run_once(as_of=AFTER_CLOSE)
    runtime.service.broker._cash = Decimal("9999")

    report = RuntimeHealthEngine().evaluate(runtime.snapshot(as_of=AFTER_CLOSE))

    assert report.status == RuntimeHealthStatus.CRITICAL
    assert any(incident.id == "check-reconciliation" for incident in report.incidents)


def test_health_markdown_report_is_operator_reviewable(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.run_once(as_of=AFTER_CLOSE)
    runtime.service.broker._cash = Decimal("9999")

    report = RuntimeHealthEngine().evaluate(runtime.snapshot(as_of=AFTER_CLOSE))
    markdown = render_health_markdown_report(report)

    assert "# Runtime Health Incident Review" in markdown
    assert "Alpaca paper mode only" in markdown
    assert "## Incident Command" in markdown
    assert "Broker and internal ledger reconciliation is not clean" in markdown
    assert "Do not submit new paper orders while critical incidents are open" in (
        markdown
    )


def test_pause_is_watch_and_paper_kill_switch_is_degraded(tmp_path) -> None:
    paused = make_runtime(output_dir=tmp_path / "paused")
    paused.apply_control(
        OperatorControlAction.PAUSE_RUNTIME,
        requested_at=AFTER_CLOSE,
        requested_by="test",
    )
    paused_cycle = paused.run_once(as_of=AFTER_CLOSE)

    killed = make_runtime(output_dir=tmp_path / "killed")
    killed.apply_control(
        OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
        requested_at=AFTER_CLOSE,
        requested_by="test",
    )
    killed_cycle = killed.run_once(as_of=AFTER_CLOSE)

    assert paused_cycle.alerts[0].code == RuntimeAlertCode.OPERATOR_PAUSED
    assert paused.snapshot(as_of=AFTER_CLOSE).health_report.status == (
        RuntimeHealthStatus.WATCH
    )
    assert RuntimeAlertCode.PAPER_KILL_SWITCH_ENABLED in {
        alert.code for alert in killed_cycle.alerts
    }
    assert killed.snapshot(as_of=AFTER_CLOSE).health_report.status == (
        RuntimeHealthStatus.DEGRADED
    )


def test_dashboard_health_route_uses_health_provider(tmp_path) -> None:
    runtime = make_runtime(output_dir=tmp_path)
    runtime.run_once(as_of=AFTER_CLOSE)

    status, content_type, body = dashboard_response(
        "/api/health",
        snapshot_provider=runtime.dashboard_snapshot,
        health_provider=lambda: runtime.health_report(as_of=AFTER_CLOSE),
    )
    payload = json.loads(body)

    assert status.value == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "healthy"
    assert payload["checks"][0]["name"] == "runtime_loop"
