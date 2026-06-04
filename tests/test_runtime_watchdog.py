from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trading_app.runtime.models import RuntimePreflightStatus
from trading_app.runtime.watchdog import (
    RuntimeWatchdogAction,
    RuntimeWatchdogConfig,
    run_watchdog,
)

NOW = datetime(2026, 6, 3, 15, 0, tzinfo=UTC)


def test_runtime_watchdog_passes_on_fresh_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "trading_app.runtime.watchdog._fetch_snapshot",
        lambda _url: {
            "health_report": {
                "as_of": (NOW - timedelta(minutes=1)).isoformat(),
                "status": "healthy",
            }
        },
    )

    report = run_watchdog(
        RuntimeWatchdogConfig(
            output_dir=tmp_path,
            restart=True,
        ),
        as_of=NOW,
    )

    assert report.status == RuntimePreflightStatus.PASSED
    assert report.action == RuntimeWatchdogAction.NONE
    assert not report.restart_requested
    assert (tmp_path / "state" / "latest-runtime-watchdog-report.json").exists()
    assert (tmp_path / "journal" / "runtime-watchdog.jsonl").exists()
    assert (tmp_path / "reports" / "runtime-watchdog-report.md").exists()


def test_runtime_watchdog_restarts_on_stale_runtime_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    restarted: list[str] = []
    monkeypatch.setattr(
        "trading_app.runtime.watchdog._fetch_snapshot",
        lambda _url: {
            "health_report": {
                "as_of": (NOW - timedelta(minutes=10)).isoformat(),
                "status": "healthy",
            }
        },
    )

    def fake_restart(label: str) -> RuntimeWatchdogAction:
        restarted.append(label)
        return RuntimeWatchdogAction.RESTARTED

    monkeypatch.setattr("trading_app.runtime.watchdog._restart_launchd", fake_restart)

    report = run_watchdog(
        RuntimeWatchdogConfig(
            output_dir=tmp_path,
            launchd_label="com.example.paper",
            max_heartbeat_age=timedelta(minutes=5),
            restart=True,
        ),
        as_of=NOW,
    )

    assert report.status == RuntimePreflightStatus.WARNING
    assert report.action == RuntimeWatchdogAction.RESTARTED
    assert report.restart_requested
    assert restarted == ["com.example.paper"]
    assert any(check.name == "heartbeat" for check in report.checks)


def test_runtime_watchdog_fails_without_restart_when_api_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    def fail(_url: str):
        raise OSError("connection refused")

    monkeypatch.setattr("trading_app.runtime.watchdog._fetch_snapshot", fail)

    report = run_watchdog(
        RuntimeWatchdogConfig(output_dir=tmp_path, restart=False),
        as_of=NOW,
    )

    assert report.status == RuntimePreflightStatus.FAILED
    assert report.action == RuntimeWatchdogAction.NONE
    assert not report.restart_requested
