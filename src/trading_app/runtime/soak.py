"""Post-run evidence analysis for full-day Alpaca paper soaks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.runtime.models import (
    RuntimeCycleResult,
    RuntimeEvent,
    RuntimeEventSeverity,
    RuntimeHealthStatus,
    RuntimePreflightStatus,
    RuntimeSoakEvidenceCheck,
    RuntimeSoakEvidenceReport,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

MARKET_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class RuntimeSoakEvidenceConfig:
    output_dir: Path | str = Path("data/runtime")
    min_duration: timedelta = timedelta(hours=24)
    max_market_gap: timedelta = timedelta(seconds=180)
    max_off_hours_gap: timedelta = timedelta(minutes=30)
    trade_after_close_time: dt_time = dt_time(hour=16, minute=5)
    require_market_cycle: bool = True
    require_off_hours_cycle: bool = True
    require_overnight_cycle: bool = True
    require_report: bool = True
    require_learning: bool = True
    require_dashboard_snapshot: bool = True
    require_health_report: bool = True
    persist_report: bool = True


class RuntimeSoakEvidenceAnalyzer:
    """Analyze persisted runtime journals for full-day soak proof."""

    def __init__(self, config: RuntimeSoakEvidenceConfig | None = None) -> None:
        self.config = config or RuntimeSoakEvidenceConfig()
        self.output_dir = Path(self.config.output_dir)
        self.store = RuntimePersistenceStore(self.output_dir)

    def analyze(self, *, as_of: datetime | None = None) -> RuntimeSoakEvidenceReport:
        now = as_of or datetime.now(tz=UTC)
        cycles = tuple(
            sorted(
                _read_jsonl(
                    self.store.journal_dir / "cycles.jsonl", RuntimeCycleResult
                ),
                key=lambda cycle: cycle.as_of,
            )
        )
        events = tuple(
            _read_jsonl(self.store.journal_dir / "events.jsonl", RuntimeEvent)
        )
        runtime_events = _unique_events(
            (*events, *(event for cycle in cycles for event in cycle.events))
        )
        warning_events = tuple(
            event
            for event in runtime_events
            if event.severity == RuntimeEventSeverity.WARNING
        )
        error_events = tuple(
            event
            for event in runtime_events
            if event.severity == RuntimeEventSeverity.ERROR
        )
        latest_dashboard_snapshot = _read_model(
            self.store.state_dir / "latest-dashboard-snapshot.json",
            OperatorDashboardSnapshot,
        )
        recovered = self.store.recover()

        started_at = cycles[0].as_of if cycles else None
        completed_at = cycles[-1].as_of if cycles else None
        duration = (
            completed_at - started_at
            if started_at is not None and completed_at is not None
            else timedelta(0)
        )
        market_cycles = tuple(
            cycle for cycle in cycles if _is_market_hours(cycle.as_of)
        )
        off_hours_cycles = tuple(
            cycle for cycle in cycles if not _is_market_hours(cycle.as_of)
        )
        overnight_cycles = tuple(
            cycle for cycle in cycles if _is_overnight(cycle.as_of)
        )
        prices_refreshed_cycles = tuple(
            cycle for cycle in cycles if cycle.prices_refreshed
        )
        broker_synced_cycles = tuple(cycle for cycle in cycles if cycle.broker_synced)
        missed_price_refresh_cycles = len(cycles) - len(prices_refreshed_cycles)
        missed_broker_sync_cycles = len(cycles) - len(broker_synced_cycles)
        order_cycles = tuple(cycle for cycle in cycles if cycle.orders_submitted > 0)
        off_schedule_order_cycles = tuple(
            cycle
            for cycle in order_cycles
            if not _is_allowed_order_cycle(cycle, self.config)
        )
        max_market_gap = _max_gap_seconds(market_cycles)
        max_off_hours_gap = _max_gap_seconds(off_hours_cycles)
        report_written = any(cycle.report_written for cycle in cycles) or (
            recovered.daily_report is not None
        )
        nightly_learning_ran = any(cycle.nightly_learning_ran for cycle in cycles) or (
            recovered.nightly_learning is not None
        )
        dashboard_snapshot_available = _dashboard_snapshot_valid(
            latest_dashboard_snapshot
        )
        final_health_status = (
            recovered.health_report.status.value
            if recovered.health_report is not None
            else None
        )

        checks = (
            _check(
                "cycle_journal",
                bool(cycles),
                "Runtime cycle journal exists.",
                "Runtime cycle journal is missing or empty.",
                (f"cycles={len(cycles)}",),
            ),
            _check(
                "duration",
                duration >= self.config.min_duration,
                "Soak duration meets the configured minimum.",
                "Soak duration is shorter than the configured minimum.",
                (
                    f"duration_hours={duration.total_seconds() / 3600:.2f}",
                    (
                        "required_hours="
                        f"{self.config.min_duration.total_seconds() / 3600:.2f}"
                    ),
                ),
            ),
            _check(
                "market_coverage",
                (not self.config.require_market_cycle) or bool(market_cycles),
                "Regular-market cycle evidence is present.",
                "Regular-market cycle evidence is missing.",
                (f"market_cycles={len(market_cycles)}",),
            ),
            _check(
                "off_hours_coverage",
                (not self.config.require_off_hours_cycle) or bool(off_hours_cycles),
                "Off-hours cycle evidence is present.",
                "Off-hours cycle evidence is missing.",
                (f"off_hours_cycles={len(off_hours_cycles)}",),
            ),
            _check(
                "overnight_coverage",
                (not self.config.require_overnight_cycle) or bool(overnight_cycles),
                "Overnight cycle evidence is present.",
                "Overnight cycle evidence is missing.",
                (f"overnight_cycles={len(overnight_cycles)}",),
            ),
            _gap_check(
                "market_polling_gap",
                max_market_gap,
                self.config.max_market_gap.total_seconds(),
                bool(market_cycles),
            ),
            _gap_check(
                "off_hours_polling_gap",
                max_off_hours_gap,
                self.config.max_off_hours_gap.total_seconds(),
                bool(off_hours_cycles),
            ),
            _check(
                "price_refresh_cycles",
                bool(cycles) and missed_price_refresh_cycles == 0,
                "Every persisted runtime cycle refreshed latest prices.",
                "One or more persisted runtime cycles missed latest-price refresh.",
                (
                    f"prices_refreshed_cycles={len(prices_refreshed_cycles)}",
                    f"missed_price_refresh_cycles={missed_price_refresh_cycles}",
                ),
            ),
            _check(
                "broker_sync_cycles",
                bool(cycles) and missed_broker_sync_cycles == 0,
                "Every persisted runtime cycle synced broker state.",
                "One or more persisted runtime cycles missed broker sync.",
                (
                    f"broker_synced_cycles={len(broker_synced_cycles)}",
                    f"missed_broker_sync_cycles={missed_broker_sync_cycles}",
                ),
            ),
            _check(
                "off_schedule_orders",
                not off_schedule_order_cycles,
                "No paper orders were submitted outside the approved close window.",
                (
                    "One or more paper orders were submitted outside the approved "
                    "close window."
                ),
                (
                    f"order_cycles={len(order_cycles)}",
                    f"off_schedule_order_cycles={len(off_schedule_order_cycles)}",
                ),
            ),
            _check(
                "daily_report",
                (not self.config.require_report) or report_written,
                "Daily report evidence is present.",
                "Daily report evidence is missing.",
                (f"report_written={report_written}",),
            ),
            _check(
                "nightly_learning",
                (not self.config.require_learning) or nightly_learning_ran,
                "Nightly learning evidence is present.",
                "Nightly learning evidence is missing.",
                (f"nightly_learning_ran={nightly_learning_ran}",),
            ),
            _check(
                "dashboard_snapshot",
                (not self.config.require_dashboard_snapshot)
                or dashboard_snapshot_available,
                "Latest runtime dashboard snapshot evidence is present.",
                "Latest runtime dashboard snapshot evidence is missing.",
                (f"dashboard_snapshot_available={dashboard_snapshot_available}",),
            ),
            _check(
                "final_health",
                (not self.config.require_health_report)
                or _health_allows_completion(final_health_status),
                "Final runtime health evidence allows completion.",
                "Final runtime health evidence is missing or critical.",
                (f"final_health_status={final_health_status or 'missing'}",),
            ),
            _check(
                "runtime_error_events",
                len(error_events) == 0,
                "No error-severity runtime events were captured during the soak.",
                (
                    "Error-severity runtime events were captured during the soak "
                    "and require incident review."
                ),
                (
                    f"runtime_event_count={len(runtime_events)}",
                    f"warning_events={len(warning_events)}",
                    f"error_events={len(error_events)}",
                ),
            ),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        warnings = sum(
            1 for cycle in cycles if cycle.status.value in {"degraded", "blocked"}
        ) + len(warning_events)
        status = (
            RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.WARNING
            if warnings
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimeSoakEvidenceReport(
            as_of=now,
            status=status,
            passed=failures == 0,
            output_dir=str(self.output_dir),
            started_at=started_at,
            completed_at=completed_at,
            duration_hours=round(duration.total_seconds() / 3600, 4),
            cycle_count=len(cycles),
            market_cycle_count=len(market_cycles),
            off_hours_cycle_count=len(off_hours_cycles),
            overnight_cycle_count=len(overnight_cycles),
            prices_refreshed_cycle_count=len(prices_refreshed_cycles),
            broker_synced_cycle_count=len(broker_synced_cycles),
            missed_price_refresh_cycles=missed_price_refresh_cycles,
            missed_broker_sync_cycles=missed_broker_sync_cycles,
            order_cycles=len(order_cycles),
            off_schedule_order_cycles=len(off_schedule_order_cycles),
            max_market_gap_seconds=max_market_gap,
            max_off_hours_gap_seconds=max_off_hours_gap,
            report_written=report_written,
            nightly_learning_ran=nightly_learning_ran,
            dashboard_snapshot_available=dashboard_snapshot_available,
            final_health_status=final_health_status,
            runtime_event_count=len(runtime_events),
            runtime_warning_event_count=len(warning_events),
            runtime_error_event_count=len(error_events),
            checks=checks,
        )
        if self.config.persist_report:
            self.store.persist_soak_evidence_report(report)
        return report


def render_soak_evidence_text(report: RuntimeSoakEvidenceReport) -> str:
    """Render a compact operator-facing soak evidence summary."""

    lines = [
        f"Soak evidence status: {report.status.value}",
        f"Passed: {'yes' if report.passed else 'no'}",
        f"Output dir: {report.output_dir}",
        f"Started: {report.started_at.isoformat() if report.started_at else 'missing'}",
        (
            "Completed: "
            f"{report.completed_at.isoformat() if report.completed_at else 'missing'}"
        ),
        f"Duration hours: {report.duration_hours:.2f}",
        f"Cycles: {report.cycle_count}",
        f"Market cycles: {report.market_cycle_count}",
        f"Off-hours cycles: {report.off_hours_cycle_count}",
        f"Overnight cycles: {report.overnight_cycle_count}",
        (
            "Price refresh cycles: "
            f"{report.prices_refreshed_cycle_count}/{report.cycle_count}"
        ),
        f"Missed price refresh cycles: {report.missed_price_refresh_cycles}",
        (
            "Broker sync cycles: "
            f"{report.broker_synced_cycle_count}/{report.cycle_count}"
        ),
        f"Missed broker sync cycles: {report.missed_broker_sync_cycles}",
        f"Off-schedule order cycles: {report.off_schedule_order_cycles}",
        f"Daily report: {'yes' if report.report_written else 'no'}",
        f"Nightly learning: {'yes' if report.nightly_learning_ran else 'no'}",
        f"Dashboard snapshot: {'yes' if report.dashboard_snapshot_available else 'no'}",
        f"Final health: {report.final_health_status or 'missing'}",
        f"Runtime events: {report.runtime_event_count}",
        f"Runtime warning events: {report.runtime_warning_event_count}",
        f"Runtime error events: {report.runtime_error_event_count}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Analyze persisted full-day soak evidence."""

    parser = argparse.ArgumentParser(description="Analyze paper-runtime soak evidence.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--min-duration-hours", type=float, default=24)
    parser.add_argument("--max-market-gap-seconds", type=float, default=180)
    parser.add_argument("--max-off-hours-gap-seconds", type=float, default=1800)
    parser.add_argument("--no-require-report", action="store_true")
    parser.add_argument("--no-require-learning", action="store_true")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeSoakEvidenceAnalyzer(
        RuntimeSoakEvidenceConfig(
            output_dir=Path(args.output_dir),
            min_duration=timedelta(hours=args.min_duration_hours),
            max_market_gap=timedelta(seconds=args.max_market_gap_seconds),
            max_off_hours_gap=timedelta(seconds=args.max_off_hours_gap_seconds),
            require_report=not args.no_require_report,
            require_learning=not args.no_require_learning,
            persist_report=not args.no_persist,
        )
    ).analyze()
    print(report.model_dump_json() if args.json else render_soak_evidence_text(report))
    return 0 if report.passed else 1


def _read_jsonl(path: Path, model_type):
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(model_type.model_validate_json(line))
    return records


def _read_model(path: Path, model_type):
    if not path.exists():
        return None
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _unique_events(events: tuple[RuntimeEvent, ...]) -> tuple[RuntimeEvent, ...]:
    seen: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
    unique: list[RuntimeEvent] = []
    for event in events:
        key = (
            event.timestamp.isoformat(),
            event.severity.value,
            event.category,
            event.message,
            event.evidence,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return tuple(unique)


def _dashboard_snapshot_valid(
    snapshot: OperatorDashboardSnapshot | None,
) -> bool:
    if snapshot is None or snapshot.mode != "Alpaca Paper":
        return False
    runtime_state = snapshot.runtime_state
    if runtime_state is None:
        return True
    return _field(runtime_state, "mode") == "Alpaca Paper"


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeSoakEvidenceCheck:
    return RuntimeSoakEvidenceCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _gap_check(
    name: str,
    observed_seconds: float | None,
    allowed_seconds: float,
    has_cycles: bool,
) -> RuntimeSoakEvidenceCheck:
    if not has_cycles or observed_seconds is None:
        return _check(
            name,
            True,
            "Polling gap check has no applicable cycle pairs.",
            "Polling gap check has no applicable cycle pairs.",
        )
    return _check(
        name,
        observed_seconds <= allowed_seconds,
        "Polling gaps are within the configured limit.",
        "Polling gaps exceed the configured limit.",
        (
            f"observed_seconds={observed_seconds:.2f}",
            f"allowed_seconds={allowed_seconds:.2f}",
        ),
    )


def _is_market_hours(as_of: datetime) -> bool:
    local = as_of.astimezone(MARKET_TZ)
    return local.weekday() < 5 and dt_time(hour=9, minute=30) <= local.time() < dt_time(
        hour=16
    )


def _is_overnight(as_of: datetime) -> bool:
    local = as_of.astimezone(MARKET_TZ)
    return local.time() >= dt_time(hour=20) or local.time() < dt_time(hour=9, minute=30)


def _is_allowed_order_cycle(
    cycle: RuntimeCycleResult, config: RuntimeSoakEvidenceConfig
) -> bool:
    local = cycle.as_of.astimezone(MARKET_TZ)
    return local.weekday() < 5 and local.time() >= config.trade_after_close_time


def _max_gap_seconds(cycles: tuple[RuntimeCycleResult, ...]) -> float | None:
    if len(cycles) < 2:
        return None
    return max(
        (later.as_of - earlier.as_of).total_seconds()
        for earlier, later in zip(cycles, cycles[1:], strict=False)
    )


def _health_allows_completion(status: str | None) -> bool:
    return status in {
        RuntimeHealthStatus.HEALTHY.value,
        RuntimeHealthStatus.WATCH.value,
        RuntimeHealthStatus.DEGRADED.value,
    }


if __name__ == "__main__":
    raise SystemExit(main())
