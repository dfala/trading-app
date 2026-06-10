"""Local watchdog for the Alpaca paper runtime service."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from pydantic import AwareDatetime, Field

from trading_app.runtime.models import RuntimePreflightStatus
from trading_app.schemas import TradingModel

DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8765/api/snapshot"
DEFAULT_LAUNCHD_LABEL = "com.trading-app.alpaca-paper"


class RuntimeWatchdogAction(StrEnum):
    NONE = "none"
    RESTARTED = "restarted"
    RESTART_FAILED = "restart_failed"


class RuntimeWatchdogCheck(TradingModel):
    name: str = Field(min_length=1)
    status: RuntimePreflightStatus
    message: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RuntimeWatchdogReport(TradingModel):
    as_of: AwareDatetime
    status: RuntimePreflightStatus
    restart_requested: bool
    action: RuntimeWatchdogAction
    launchd_label: str = Field(min_length=1)
    dashboard_url: str = Field(min_length=1)
    checks: tuple[RuntimeWatchdogCheck, ...]
    summary: str = Field(min_length=1)
    markdown_path: str | None = None


@dataclass(frozen=True)
class RuntimeWatchdogConfig:
    dashboard_url: str = DEFAULT_DASHBOARD_URL
    output_dir: Path = Path("data/runtime")
    launchd_label: str = DEFAULT_LAUNCHD_LABEL
    max_heartbeat_age: timedelta = timedelta(minutes=5)
    restart: bool = False
    restart_on_runtime_health_failure: bool = False


def run_watchdog(
    config: RuntimeWatchdogConfig | None = None,
    *,
    as_of: datetime | None = None,
) -> RuntimeWatchdogReport:
    config = config or RuntimeWatchdogConfig()
    checked_at = as_of or datetime.now(UTC)
    checks: list[RuntimeWatchdogCheck] = []
    payload: dict[str, Any] | None = None

    try:
        payload = _fetch_snapshot(config.dashboard_url)
        checks.append(
            RuntimeWatchdogCheck(
                name="api_snapshot",
                status=RuntimePreflightStatus.PASSED,
                message="Runtime API snapshot responded.",
                evidence=(config.dashboard_url,),
            )
        )
    except Exception as error:
        checks.append(
            RuntimeWatchdogCheck(
                name="api_snapshot",
                status=RuntimePreflightStatus.FAILED,
                message="Runtime API snapshot did not respond.",
                evidence=(f"{type(error).__name__}: {error}",),
            )
        )

    stale = False
    if payload is not None:
        heartbeat_at = _snapshot_heartbeat_at(payload)
        if heartbeat_at is None:
            checks.append(
                RuntimeWatchdogCheck(
                    name="heartbeat",
                    status=RuntimePreflightStatus.WARNING,
                    message="Runtime snapshot has no heartbeat yet.",
                )
            )
        else:
            age = checked_at - heartbeat_at
            stale = age > config.max_heartbeat_age
            checks.append(
                RuntimeWatchdogCheck(
                    name="heartbeat",
                    status=(
                        RuntimePreflightStatus.FAILED
                        if stale
                        else RuntimePreflightStatus.PASSED
                    ),
                    message=(
                        "Runtime heartbeat is stale."
                        if stale
                        else "Runtime heartbeat is fresh."
                    ),
                    evidence=(
                        f"heartbeat_at={heartbeat_at.isoformat()}",
                        f"age_seconds={int(age.total_seconds())}",
                    ),
                )
            )
        health_status = str(_nested(payload, "health_report", "status") or "")
        if health_status in {"critical", "degraded"}:
            checks.append(
                RuntimeWatchdogCheck(
                    name="runtime_health",
                    status=(
                        RuntimePreflightStatus.FAILED
                        if config.restart_on_runtime_health_failure
                        else RuntimePreflightStatus.WARNING
                    ),
                    message=f"Runtime health is {health_status}.",
                )
            )
        elif health_status:
            checks.append(
                RuntimeWatchdogCheck(
                    name="runtime_health",
                    status=RuntimePreflightStatus.PASSED,
                    message=f"Runtime health is {health_status}.",
                )
            )

    restartable_failed_checks = {"api_snapshot", "heartbeat"}
    if config.restart_on_runtime_health_failure:
        restartable_failed_checks.add("runtime_health")
    needs_restart = any(
        check.status == RuntimePreflightStatus.FAILED
        and check.name in restartable_failed_checks
        for check in checks
    )
    action = RuntimeWatchdogAction.NONE
    if needs_restart and config.restart:
        action = _restart_launchd(config.launchd_label)
        checks.append(
            RuntimeWatchdogCheck(
                name="restart",
                status=(
                    RuntimePreflightStatus.PASSED
                    if action == RuntimeWatchdogAction.RESTARTED
                    else RuntimePreflightStatus.FAILED
                ),
                message=(
                    "Launchd runtime restart was requested."
                    if action == RuntimeWatchdogAction.RESTARTED
                    else "Launchd runtime restart request failed."
                ),
                evidence=(config.launchd_label,),
            )
        )

    status = _report_status(checks, restarted=action == RuntimeWatchdogAction.RESTARTED)
    report = RuntimeWatchdogReport(
        as_of=checked_at,
        status=status,
        restart_requested=needs_restart and config.restart,
        action=action,
        launchd_label=config.launchd_label,
        dashboard_url=config.dashboard_url,
        checks=tuple(checks),
        summary=_summary(status, action),
    )
    return _write_watchdog_report(report, config.output_dir)


def render_watchdog_markdown(report: RuntimeWatchdogReport) -> str:
    lines = [
        "# Runtime Watchdog Report",
        "",
        f"- Status: {report.status.value}",
        f"- Action: {report.action.value}",
        f"- Restart requested: {'yes' if report.restart_requested else 'no'}",
        f"- Launchd label: `{report.launchd_label}`",
        f"- Dashboard URL: `{report.dashboard_url}`",
        f"- Checked at: {report.as_of.isoformat()}",
        "",
        "## Checks",
    ]
    for check in report.checks:
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        for item in check.evidence:
            lines.append(f"  - {item}")
    lines.extend(["", "## Summary", report.summary])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Watch and optionally restart the Alpaca paper runtime."
    )
    parser.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD_URL)
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--launchd-label", default=DEFAULT_LAUNCHD_LABEL)
    parser.add_argument("--max-heartbeat-age-minutes", type=float, default=5)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument(
        "--restart-on-runtime-health-failure",
        action="store_true",
        help=(
            "Restart on degraded/critical runtime health even when the "
            "heartbeat is fresh."
        ),
    )
    args = parser.parse_args(argv)

    report = run_watchdog(
        RuntimeWatchdogConfig(
            dashboard_url=args.dashboard_url,
            output_dir=Path(args.output_dir),
            launchd_label=args.launchd_label,
            max_heartbeat_age=timedelta(minutes=args.max_heartbeat_age_minutes),
            restart=args.restart,
            restart_on_runtime_health_failure=args.restart_on_runtime_health_failure,
        )
    )
    print(render_watchdog_text(report))
    return 0 if report.status != RuntimePreflightStatus.FAILED else 1


def render_watchdog_text(report: RuntimeWatchdogReport) -> str:
    lines = [
        f"watchdog_status={report.status.value}",
        f"watchdog_action={report.action.value}",
        f"watchdog_restart_requested={'yes' if report.restart_requested else 'no'}",
        f"watchdog_label={report.launchd_label}",
    ]
    for check in report.checks:
        evidence = ";".join(check.evidence)
        lines.append(
            f"check={check.name} status={check.status.value} "
            f"message={check.message} evidence={evidence}"
        )
    if report.markdown_path:
        lines.append(f"watchdog_report={report.markdown_path}")
    return "\n".join(lines)


def _fetch_snapshot(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=10) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise URLError(f"HTTP {status}")
        payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("snapshot payload must be a JSON object")
        return payload


def _snapshot_heartbeat_at(payload: dict[str, Any]) -> datetime | None:
    candidates = (
        _nested(payload, "health_report", "as_of"),
        _nested(payload, "last_cycle", "as_of"),
        payload.get("generated_at"),
    )
    for candidate in candidates:
        if isinstance(candidate, str):
            parsed = _parse_datetime(candidate)
            if parsed is not None:
                return parsed
    return None


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _restart_launchd(label: str) -> RuntimeWatchdogAction:
    target = f"gui/{os.getuid()}/{label}"
    result = subprocess.run(
        ["launchctl", "kickstart", "-k", target],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return RuntimeWatchdogAction.RESTARTED
    return RuntimeWatchdogAction.RESTART_FAILED


def _report_status(
    checks: list[RuntimeWatchdogCheck],
    *,
    restarted: bool,
) -> RuntimePreflightStatus:
    if restarted:
        return RuntimePreflightStatus.WARNING
    if any(check.status == RuntimePreflightStatus.FAILED for check in checks):
        return RuntimePreflightStatus.FAILED
    if any(check.status == RuntimePreflightStatus.WARNING for check in checks):
        return RuntimePreflightStatus.WARNING
    return RuntimePreflightStatus.PASSED


def _summary(
    status: RuntimePreflightStatus,
    action: RuntimeWatchdogAction,
) -> str:
    if action == RuntimeWatchdogAction.RESTARTED:
        return "Runtime watchdog restarted the Alpaca paper launchd job."
    if status == RuntimePreflightStatus.PASSED:
        return "Runtime watchdog found a healthy local paper runtime."
    if status == RuntimePreflightStatus.WARNING:
        return "Runtime watchdog found incomplete startup evidence."
    return "Runtime watchdog found failed runtime evidence."


def _write_watchdog_report(
    report: RuntimeWatchdogReport,
    output_dir: Path,
) -> RuntimeWatchdogReport:
    state_dir = output_dir / "state"
    journal_dir = output_dir / "journal"
    reports_dir = output_dir / "reports"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = reports_dir / "runtime-watchdog-report.md"
    report_with_path = report.model_copy(update={"markdown_path": str(markdown_path)})
    json_text = report_with_path.model_dump_json()
    (state_dir / "latest-runtime-watchdog-report.json").write_text(
        json_text,
        encoding="utf-8",
    )
    with (journal_dir / "runtime-watchdog.jsonl").open("a", encoding="utf-8") as file:
        file.write(json_text)
        file.write("\n")
    markdown_path.write_text(
        render_watchdog_markdown(report_with_path),
        encoding="utf-8",
    )
    return report_with_path


if __name__ == "__main__":
    raise SystemExit(main())
