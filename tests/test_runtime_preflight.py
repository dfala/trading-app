from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from datetime import time as dt_time
from pathlib import Path

import pytest

from trading_app.runtime import (
    AlpacaPaperRuntimePreflight,
    AlwaysOnPaperRuntimeConfig,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_preflight_text,
)
from trading_app.runtime.preflight import main as preflight_main
from trading_app.runtime.run_alpaca_paper import main as runtime_main
from trading_app.schemas import DataFeed

NOW = datetime(2026, 5, 29, 20, 10, tzinfo=UTC)
VALID_ENV = {
    "ALPACA_API_KEY": "key-present",
    "ALPACA_SECRET_KEY": "secret-present",
}


def make_config(tmp_path: Path, **updates) -> AlwaysOnPaperRuntimeConfig:
    config = AlwaysOnPaperRuntimeConfig(output_dir=tmp_path)
    return replace(config, **updates)


def test_preflight_passes_with_iex_development_warning_and_persists(tmp_path) -> None:
    config = make_config(tmp_path)

    report = AlpacaPaperRuntimePreflight(
        config=config,
        env=VALID_ENV,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).run(as_of=NOW)
    recovered = RuntimePersistenceStore(tmp_path).recover()

    assert report.can_start
    assert report.status == RuntimePreflightStatus.WARNING
    assert report.warnings == 1
    assert any(check.name == "market_data_feed" for check in report.checks)
    assert recovered.preflight_report == report
    assert (tmp_path / "state" / "latest-preflight-report.json").exists()
    assert (tmp_path / "journal" / "preflight.jsonl").exists()


def test_preflight_passes_cleanly_with_sip_feed(tmp_path) -> None:
    config = make_config(tmp_path, feed=DataFeed.SIP)

    report = AlpacaPaperRuntimePreflight(config=config, env=VALID_ENV).run(as_of=NOW)

    assert report.can_start
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.failures == 0
    assert report.warnings == 0


def test_preflight_fails_when_required_credentials_are_missing(tmp_path) -> None:
    config = make_config(tmp_path)

    report = AlpacaPaperRuntimePreflight(config=config, env={}).run(as_of=NOW)

    assert not report.can_start
    assert report.status == RuntimePreflightStatus.FAILED
    assert any(
        check.name == "credentials" and check.status == RuntimePreflightStatus.FAILED
        for check in report.checks
    )


def test_preflight_treats_blank_credentials_as_missing(tmp_path) -> None:
    config = make_config(tmp_path)

    report = AlpacaPaperRuntimePreflight(
        config=config,
        env={"ALPACA_API_KEY": "   ", "ALPACA_SECRET_KEY": "\t"},
    ).run(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.can_start
    assert by_name["credentials"].status == RuntimePreflightStatus.FAILED
    assert "ALPACA_API_KEY=missing" in by_name["credentials"].evidence
    assert "ALPACA_SECRET_KEY=missing" in by_name["credentials"].evidence


def test_preflight_can_warn_when_credentials_are_not_required(tmp_path) -> None:
    config = make_config(tmp_path, feed=DataFeed.SIP)

    report = AlpacaPaperRuntimePreflight(
        config=config,
        env={},
        require_credentials=False,
    ).run(as_of=NOW)

    assert report.can_start
    assert report.status == RuntimePreflightStatus.WARNING
    assert report.warnings == 1


def test_preflight_fails_live_flag_invalid_symbol_public_dashboard_and_schedule(
    tmp_path,
) -> None:
    config = make_config(
        tmp_path,
        symbols=("spy",),
        trade_after_close_time=dt_time(hour=15, minute=30),
    )

    report = AlpacaPaperRuntimePreflight(
        config=config,
        dashboard_host="0.0.0.0",
        env={**VALID_ENV, "ALPACA_LIVE_TRADING_ENABLED": " TRUE "},
    ).run(as_of=NOW)
    failed_names = {
        check.name
        for check in report.checks
        if check.status == RuntimePreflightStatus.FAILED
    }

    assert not report.can_start
    assert {"paper_boundary", "symbol_scope", "dashboard_binding"}.issubset(
        failed_names
    )
    assert "runtime_schedule" in failed_names


def test_preflight_fails_live_alpaca_endpoint_override(tmp_path) -> None:
    config = make_config(tmp_path, feed=DataFeed.SIP)

    report = AlpacaPaperRuntimePreflight(
        config=config,
        env={**VALID_ENV, "APCA_API_BASE_URL": "https://api.alpaca.markets"},
    ).run(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.can_start
    assert by_name["paper_boundary"].status == RuntimePreflightStatus.FAILED
    assert "APCA_API_BASE_URL=live_endpoint" in by_name["paper_boundary"].evidence


def test_preflight_fails_quoted_live_boundary_values(tmp_path) -> None:
    config = make_config(tmp_path, feed=DataFeed.SIP)

    report = AlpacaPaperRuntimePreflight(
        config=config,
        env={
            **VALID_ENV,
            "ALPACA_LIVE_TRADING_ENABLED": '"true"',
            "ALPACA_API_BASE_URL": "'https://api.alpaca.markets'",
        },
    ).run(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.can_start
    assert by_name["paper_boundary"].status == RuntimePreflightStatus.FAILED
    assert "ALPACA_LIVE_TRADING_ENABLED=true" in by_name["paper_boundary"].evidence
    assert "ALPACA_API_BASE_URL=live_endpoint" in by_name["paper_boundary"].evidence


def test_preflight_allows_paper_alpaca_endpoint_override(tmp_path) -> None:
    config = make_config(tmp_path, feed=DataFeed.SIP)

    report = AlpacaPaperRuntimePreflight(
        config=config,
        env={**VALID_ENV, "APCA_API_BASE_URL": "https://paper-api.alpaca.markets"},
    ).run(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert report.can_start
    assert by_name["paper_boundary"].status == RuntimePreflightStatus.PASSED


def test_preflight_fails_unsupported_data_feed(tmp_path) -> None:
    config = make_config(tmp_path, feed=DataFeed.THIRD_PARTY)

    report = AlpacaPaperRuntimePreflight(config=config, env=VALID_ENV).run(as_of=NOW)

    assert not report.can_start
    assert any(
        check.name == "market_data_feed"
        and check.status == RuntimePreflightStatus.FAILED
        for check in report.checks
    )


def test_preflight_text_summary_does_not_leak_secret_values(tmp_path) -> None:
    config = make_config(tmp_path)

    report = AlpacaPaperRuntimePreflight(config=config, env=VALID_ENV).run(as_of=NOW)
    text = render_preflight_text(report)

    assert "Preflight status" in text
    assert "secret-present" not in text
    assert "key-present" not in text


def test_preflight_cli_returns_success_or_failure_without_network(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key-present")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-present")

    success = preflight_main(
        [
            "--feed",
            "SIP",
            "--output-dir",
            str(tmp_path / "success"),
            "--json",
        ]
    )
    monkeypatch.delenv("ALPACA_API_KEY")
    monkeypatch.delenv("ALPACA_SECRET_KEY")
    failure = preflight_main(
        [
            "--feed",
            "SIP",
            "--output-dir",
            str(tmp_path / "failure"),
            "--json",
        ]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"status":"passed"' in output
    assert '"status":"failed"' in output


def test_preflight_cli_rejects_lowercase_symbols_without_normalizing(
    tmp_path,
    capsys,
) -> None:
    result = preflight_main(
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
    assert '"SPY"' not in output


def test_runtime_cli_blocks_start_when_preflight_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    with pytest.raises(SystemExit) as error:
        runtime_main(
            [
                "--output-dir",
                str(tmp_path),
                "--max-cycles",
                "0",
                "--no-dashboard",
            ]
        )

    assert "preflight failed" in str(error.value).lower()


def test_runtime_cli_rejects_lowercase_symbols_at_preflight(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key-present")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-present")

    with pytest.raises(SystemExit) as error:
        runtime_main(
            [
                "--symbols",
                "spy",
                "--feed",
                "SIP",
                "--output-dir",
                str(tmp_path),
                "--max-cycles",
                "0",
                "--no-dashboard",
            ]
        )
    output = capsys.readouterr().out
    report_json = (tmp_path / "state" / "latest-preflight-report.json").read_text(
        encoding="utf-8"
    )

    assert "preflight failed" in str(error.value).lower()
    assert "symbol_scope" in output
    assert '"spy"' in report_json


def test_runtime_cli_rejects_preflight_skip_even_with_credentials(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key-present")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-present")

    with pytest.raises(SystemExit) as error:
        runtime_main(
            [
                "--output-dir",
                str(tmp_path),
                "--max-cycles",
                "0",
                "--no-dashboard",
                "--skip-preflight",
            ]
        )

    assert "preflight cannot be skipped" in str(error.value).lower()


def test_runtime_cli_requires_monitor_only_dry_run_before_startup(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key-present")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-present")

    with pytest.raises(SystemExit) as error:
        runtime_main(
            [
                "--output-dir",
                str(tmp_path),
                "--max-cycles",
                "0",
                "--no-dashboard",
            ]
        )

    assert "--monitor-only-dry-run-first" in str(error.value)
