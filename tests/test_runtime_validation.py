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
    AlpacaPaperRuntimeValidation,
    AlwaysOnPaperRuntime,
    AlwaysOnPaperRuntimeConfig,
    PaperRuntimeValidationConfig,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_validation_markdown,
    render_validation_text,
)
from trading_app.runtime.validation import main as validation_main
from trading_app.schemas import DataFeed
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

AFTER_CLOSE = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
NIGHT = datetime(2026, 5, 30, 1, 0, tzinfo=UTC)
VALID_ENV = {
    "ALPACA_API_KEY": "key-present",
    "ALPACA_SECRET_KEY": "secret-present",
}


def runtime_factory(
    config: AlwaysOnPaperRuntimeConfig,
    *,
    observed_at: datetime = AFTER_CLOSE,
) -> AlwaysOnPaperRuntime:
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
            observed_at=observed_at,
        ),
        historical_bar_fetcher=FixtureHistoricalBarFetcher(source="validation-test"),
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
    include_scheduled_order_check: bool = False,
    soak_cycles: int = 0,
    require_report_and_learning_proof: bool = False,
) -> PaperRuntimeValidationConfig:
    return PaperRuntimeValidationConfig(
        runtime_config=AlwaysOnPaperRuntimeConfig(
            symbols=("AAA", "BBB", "SPY"),
            output_dir=tmp_path,
            feed=DataFeed.SIP,
        ),
        include_scheduled_order_check=include_scheduled_order_check,
        soak_cycles=soak_cycles,
        require_report_and_learning_proof=require_report_and_learning_proof,
    )


def test_validation_fails_before_dry_run_when_preflight_fails(tmp_path) -> None:
    called = False

    def factory(config):
        nonlocal called
        called = True
        return runtime_factory(config)

    report = AlpacaPaperRuntimeValidation(
        config=make_config(tmp_path),
        env={},
        runtime_factory=factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)

    assert not called
    assert not report.can_start_full_day_soak
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.monitor_dry_run_report is None


def test_monitor_only_validation_persists_safe_evidence(tmp_path) -> None:
    store = RuntimePersistenceStore(tmp_path)

    report = AlpacaPaperRuntimeValidation(
        config=make_config(tmp_path),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=store,
    ).run(as_of=AFTER_CLOSE)
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert report.can_start_full_day_soak
    assert report.monitor_dry_run_report is not None
    assert report.monitor_dry_run_report.orders_submitted == 0
    assert report.orders_submitted == 0
    assert report.latest_prices_refreshed
    assert report.latest_prices_fresh
    assert report.broker_synced
    assert report.dashboard_snapshot_serialized
    assert report.broker_providers == ("memory-paper",)
    assert report.latest_price_sources == ("latest-fixture",)
    assert report.latest_price_feeds == ("SIP",)
    assert report.symbols == ("AAA", "BBB", "SPY")
    assert report.feed == "SIP"
    assert report.dashboard_host == "127.0.0.1"
    assert report.credential_required
    assert report.monitor_dry_run_report.broker_provider == "memory-paper"
    assert report.monitor_dry_run_report.latest_price_source == "latest-fixture"
    checklist = {item.name: item for item in report.checklist}
    assert checklist["credentialed_preflight"].status == RuntimePreflightStatus.PASSED
    assert checklist["monitor_only_dry_run"].status == RuntimePreflightStatus.PASSED
    assert checklist["latest_price_freshness"].status == RuntimePreflightStatus.PASSED
    assert checklist["broker_sync"].status == RuntimePreflightStatus.PASSED
    assert checklist["dashboard_snapshot"].status == RuntimePreflightStatus.PASSED
    assert checklist["scheduled_order_dry_run"].status == RuntimePreflightStatus.WARNING
    assert (
        checklist["full_day_plus_overnight_soak"].status
        == RuntimePreflightStatus.WARNING
    )
    assert recovered.validation_report == report
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    markdown = Path(report.markdown_path).read_text(encoding="utf-8")
    assert "Paper Runtime Validation Report" in markdown
    assert "Credentialed Paper Validation Checklist" in markdown
    assert "monitor_only_dry_run" in markdown
    assert "Broker providers observed: `memory-paper`" in markdown
    assert "Latest-price sources observed: `latest-fixture`" in markdown
    assert "Latest prices refreshed" in markdown
    assert "Submitted paper orders observed: `0`" in markdown
    assert (tmp_path / "state" / "latest-validation-report.json").exists()
    assert (tmp_path / "journal" / "validation.jsonl").exists()


def test_scheduled_order_validation_uses_isolated_state(tmp_path) -> None:
    report = AlpacaPaperRuntimeValidation(
        config=make_config(tmp_path, include_scheduled_order_check=True),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)

    assert report.can_start_full_day_soak
    assert report.monitor_dry_run_report is not None
    assert report.scheduled_order_dry_run_report is not None
    assert report.monitor_dry_run_report.orders_submitted == 0
    assert report.scheduled_order_dry_run_report.orders_submitted == 1
    assert report.orders_submitted == 1
    checklist = {item.name: item for item in report.checklist}
    assert checklist["scheduled_order_dry_run"].status == RuntimePreflightStatus.PASSED


def test_soak_validation_applies_paper_kill_switch_by_default(tmp_path) -> None:
    report = AlpacaPaperRuntimeValidation(
        config=make_config(tmp_path, soak_cycles=1),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)

    assert report.can_start_full_day_soak
    assert report.soak_monitor_only
    assert report.soak_cycles_completed == 1
    assert report.soak_cycles[0].orders_submitted == 0
    assert any(step.name == "soak_paper_order_block" for step in report.steps)
    checklist = {item.name: item for item in report.checklist}
    assert checklist["soak_cycle_evidence"].status == RuntimePreflightStatus.PASSED
    assert (
        checklist["full_day_plus_overnight_soak"].status
        == RuntimePreflightStatus.WARNING
    )
    assert checklist["paper_order_boundary"].status == RuntimePreflightStatus.PASSED


def test_validation_can_require_report_and_learning_proof(tmp_path) -> None:
    def factory(config):
        return runtime_factory(config, observed_at=NIGHT)

    report = AlpacaPaperRuntimeValidation(
        config=make_config(
            tmp_path,
            soak_cycles=1,
            require_report_and_learning_proof=True,
        ),
        env=VALID_ENV,
        runtime_factory=factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=NIGHT)

    assert report.report_written
    assert report.nightly_learning_ran
    assert any(step.name == "daily_report_proof" for step in report.steps)
    assert any(step.name == "nightly_learning_proof" for step in report.steps)
    checklist = {item.name: item for item in report.checklist}
    assert checklist["daily_report_proof"].status == RuntimePreflightStatus.PASSED
    assert checklist["nightly_learning_proof"].status == RuntimePreflightStatus.PASSED


def test_validation_text_does_not_leak_secret_values(tmp_path) -> None:
    report = AlpacaPaperRuntimeValidation(
        config=make_config(tmp_path),
        env=VALID_ENV,
        runtime_factory=runtime_factory,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=AFTER_CLOSE)
    text = render_validation_text(report)
    markdown = render_validation_markdown(report)

    assert "Validation status" in text
    assert "Checklist:" in text
    assert "secret-present" not in text
    assert "key-present" not in text
    assert "Paper Runtime Validation Report" in markdown
    assert "Credentialed Paper Validation Checklist" in markdown
    assert "secret-present" not in markdown
    assert "key-present" not in markdown


def test_validation_cli_fails_fast_without_credentials(tmp_path, capsys) -> None:
    result = validation_main(
        [
            "--feed",
            "SIP",
            "--output-dir",
            str(tmp_path),
            "--json",
        ]
    )
    output = capsys.readouterr().out

    assert result == 1
    assert '"status":"failed"' in output


def test_validation_cli_rejects_lowercase_symbols_without_normalizing(
    tmp_path,
    capsys,
) -> None:
    result = validation_main(
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
