from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from trading_app.broker import InMemoryPaperBrokerAdapter
from trading_app.market_data import (
    FixtureHistoricalBarFetcher,
    FixtureLatestPriceFetcher,
)
from trading_app.paper import PaperTradingService
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.runtime import (
    AlpacaPaperRuntimeDryRun,
    AlwaysOnPaperRuntime,
    AlwaysOnPaperRuntimeConfig,
    PaperRuntimeDryRunConfig,
    RuntimeAlertCode,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_dry_run_text,
)
from trading_app.runtime.dry_run import _alpaca_runtime_factory
from trading_app.runtime.dry_run import main as dry_run_main
from trading_app.schemas import DataFeed
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
VALID_ENV = {
    "ALPACA_API_KEY": "key-present",
    "ALPACA_SECRET_KEY": "secret-present",
}


def runtime_factory(config: AlwaysOnPaperRuntimeConfig) -> AlwaysOnPaperRuntime:
    symbols = config.symbols
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=False,
            us_tradable_universe=frozenset(symbols),
            tradable_symbols=frozenset(symbols),
        )
    )
    prices = {symbol: Decimal("100") for symbol in symbols}
    return AlwaysOnPaperRuntime(
        service=PaperTradingService(
            broker=InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000")),
            starting_cash=Decimal("10000"),
            risk_engine=risk_engine,
        ),
        latest_price_fetcher=FixtureLatestPriceFetcher(
            prices,
            observed_at=AFTER_CLOSE,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="dry-run-test"),
        strategy=MonthlySectorMomentumStrategy(
            universe=tuple(symbol for symbol in symbols if symbol != "SPY")[:2],
            lookback_days=5,
            top_n=1,
        ),
        risk_engine=risk_engine,
        config=config,
        persistence_store=RuntimePersistenceStore(config.output_dir),
    )


def make_config(
    tmp_path: Path,
    *,
    monitor_only: bool = True,
    require_credentials: bool = True,
    feed: DataFeed = DataFeed.SIP,
) -> PaperRuntimeDryRunConfig:
    return PaperRuntimeDryRunConfig(
        runtime_config=AlwaysOnPaperRuntimeConfig(
            symbols=("AAA", "BBB", "SPY"),
            output_dir=tmp_path,
            feed=feed,
        ),
        require_credentials=require_credentials,
        monitor_only=monitor_only,
    )


def test_dry_run_fails_before_runtime_construction_when_preflight_fails(
    tmp_path,
) -> None:
    called = False

    def factory(config):
        nonlocal called
        called = True
        return runtime_factory(config)

    report = AlpacaPaperRuntimeDryRun(
        config=make_config(tmp_path),
        env={},
        runtime_factory=factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)

    assert not called
    assert not report.can_start_supervised_runtime
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.cycle_result is None


def test_default_alpaca_runtime_factory_uses_keyword_config(monkeypatch, tmp_path):
    received = None
    sentinel = object()

    def fake_from_alpaca_env(*, config, risk_engine=None):
        nonlocal received
        received = (config, risk_engine)
        return sentinel

    monkeypatch.setattr(AlwaysOnPaperRuntime, "from_alpaca_env", fake_from_alpaca_env)
    config = AlwaysOnPaperRuntimeConfig(output_dir=tmp_path)

    runtime = _alpaca_runtime_factory(config)

    assert runtime is sentinel
    assert received == (config, None)


def test_dry_run_cli_rejects_lowercase_symbols_without_normalizing(
    tmp_path,
    capsys,
) -> None:
    result = dry_run_main(
        [
            "--symbols",
            "spy",
            "--feed",
            "SIP",
            "--output-dir",
            str(tmp_path),
            "--json",
            "--no-credential-required",
        ]
    )
    output = capsys.readouterr().out

    assert result == 1
    assert '"name":"symbol_scope"' in output
    assert '"spy"' in output


def test_monitor_only_dry_run_blocks_paper_orders_and_persists(tmp_path) -> None:
    store = RuntimePersistenceStore(tmp_path)

    report = AlpacaPaperRuntimeDryRun(
        config=make_config(tmp_path),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=store,
    ).run(as_of=AFTER_CLOSE)
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert report.can_start_supervised_runtime
    assert report.monitor_only
    assert report.orders_submitted == 0
    assert report.orders_after == 0
    assert report.health_report is not None
    assert report.cycle_result is not None
    assert report.cycle_result.broker_synced
    assert recovered.dry_run_report == report
    assert recovered.control_state is not None
    assert not recovered.control_state.paper_kill_switch_enabled
    assert recovered.dashboard_snapshot is not None
    assert not recovered.dashboard_snapshot.kill_switch_enabled
    assert RuntimeAlertCode.PAPER_KILL_SWITCH_ENABLED not in {
        alert.code for alert in recovered.alerts
    }
    assert (tmp_path / "state" / "latest-dry-run-report.json").exists()
    assert (tmp_path / "journal" / "dry-runs.jsonl").exists()


def test_dry_run_can_explicitly_allow_scheduled_paper_orders(tmp_path) -> None:
    report = AlpacaPaperRuntimeDryRun(
        config=make_config(tmp_path, monitor_only=False),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)

    assert report.can_start_supervised_runtime
    assert not report.monitor_only
    assert report.orders_submitted == 1
    assert report.orders_after == 1
    assert any(step.name == "paper_order_safety" for step in report.steps)


def test_dry_run_reports_warning_for_iex_but_can_start(tmp_path) -> None:
    report = AlpacaPaperRuntimeDryRun(
        config=make_config(tmp_path, feed=DataFeed.IEX),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)

    assert report.can_start_supervised_runtime
    assert report.status == RuntimePreflightStatus.WARNING
    assert report.warnings >= 1


def test_dry_run_text_does_not_leak_secret_values(tmp_path) -> None:
    report = AlpacaPaperRuntimeDryRun(
        config=make_config(tmp_path),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)
    text = render_dry_run_text(report)

    assert "Dry-run status" in text
    assert "secret-present" not in text
    assert "key-present" not in text


def test_operator_runbook_covers_supervised_operations() -> None:
    text = Path("PAPER_RUNTIME_OPERATOR_RUNBOOK.md").read_text(encoding="utf-8")

    assert "Preflight" in text
    assert "Monitor-Only Dry Run" in text
    assert "Recommended One-Command Startup" in text
    assert "Dependency Installation" in text
    assert "uv sync --dev" in text
    assert "python -m trading_app.runtime.ops" in text
    assert "Start The Always-On Paper Runtime" in text
    assert "Markdown validation report" in text
    assert "Post-Soak Evidence Review" in text
    assert "python -m trading_app.runtime.soak" in text
    assert "Post-Run Secret Scan" in text
    assert "python -m trading_app.runtime.security" in text
    assert "Functional Completion Audit" in text
    assert "python -m trading_app.runtime.ops --audit" in text
    assert "python -m trading_app.runtime.governance" in text
    assert "python -m trading_app.runtime.completion" in text
    assert "Stop The Runtime" in text
    assert "Emergency Stop Procedure" in text
    assert "Runtime Artifact Layout" in text
    assert "Runtime Health" in text
    assert "Reconciliation Response" in text
    assert "Restart Recovery" in text
