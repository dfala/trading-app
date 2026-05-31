"""Supervised paper runtime validation sequence."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_app.runtime.cli import parse_symbol_list
from trading_app.runtime.dry_run import (
    AlpacaPaperRuntimeDryRun,
    PaperRuntimeDryRunConfig,
)
from trading_app.runtime.models import (
    OperatorControlAction,
    RuntimeCycleResult,
    RuntimePreflightStatus,
    RuntimeStatus,
    RuntimeValidationChecklistItem,
    RuntimeValidationReport,
    RuntimeValidationStep,
)
from trading_app.runtime.paper import AlwaysOnPaperRuntime, AlwaysOnPaperRuntimeConfig
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.runtime.preflight import AlpacaPaperRuntimePreflight
from trading_app.schemas import DataFeed

RuntimeFactory = Callable[[AlwaysOnPaperRuntimeConfig], AlwaysOnPaperRuntime]


@dataclass(frozen=True)
class PaperRuntimeValidationConfig:
    runtime_config: AlwaysOnPaperRuntimeConfig
    dashboard_host: str = "127.0.0.1"
    require_credentials: bool = True
    include_scheduled_order_check: bool = False
    soak_cycles: int = 0
    soak_sleep_seconds: float = 0
    allow_paper_orders_during_soak: bool = False
    require_report_and_learning_proof: bool = False

    def __post_init__(self) -> None:
        if self.soak_cycles < 0:
            raise ValueError("soak_cycles must be non-negative")
        if self.soak_sleep_seconds < 0:
            raise ValueError("soak_sleep_seconds must be non-negative")


class AlpacaPaperRuntimeValidation:
    """Run the supervised Milestone 18 paper-runtime validation sequence."""

    def __init__(
        self,
        *,
        config: PaperRuntimeValidationConfig,
        env: Mapping[str, str] | None = None,
        runtime_factory: RuntimeFactory | None = None,
        persistence_store: RuntimePersistenceStore | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config
        self.env = env
        self.runtime_factory = runtime_factory or AlwaysOnPaperRuntime.from_alpaca_env
        self.persistence_store = persistence_store or RuntimePersistenceStore(
            config.runtime_config.output_dir
        )
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self.sleeper = sleeper or time.sleep

    def run(self, *, as_of: datetime | None = None) -> RuntimeValidationReport:
        started_at = as_of or self.clock()
        validation_id = _validation_id(started_at)
        steps: list[RuntimeValidationStep] = []

        preflight = AlpacaPaperRuntimePreflight(
            config=self.config.runtime_config,
            dashboard_host=self.config.dashboard_host,
            env=self.env,
            require_credentials=self.config.require_credentials,
            persistence_store=self.persistence_store,
        ).run(as_of=started_at)
        steps.append(
            _step(
                "preflight",
                RuntimePreflightStatus.PASSED
                if preflight.can_start
                else RuntimePreflightStatus.FAILED,
                preflight.summary,
                started_at,
                (preflight.status.value,),
            )
        )
        if not preflight.can_start:
            return self._finalize(
                validation_id,
                started_at,
                started_at,
                preflight,
                steps,
                monitor_dry_run=None,
                scheduled_order_dry_run=None,
                soak_cycles=(),
                soak_health_report=None,
            )

        monitor_dry_run = self._run_dry_run(
            validation_id=validation_id,
            phase="monitor-dry-run",
            monitor_only=True,
            as_of=started_at,
        )
        steps.append(
            _step(
                "monitor_dry_run",
                RuntimePreflightStatus.PASSED
                if monitor_dry_run.can_start_supervised_runtime
                else RuntimePreflightStatus.FAILED,
                monitor_dry_run.summary,
                started_at,
                (f"orders_submitted={monitor_dry_run.orders_submitted}",),
            )
        )

        scheduled_order_dry_run = None
        if self.config.include_scheduled_order_check:
            scheduled_order_dry_run = self._run_dry_run(
                validation_id=validation_id,
                phase="scheduled-order-dry-run",
                monitor_only=False,
                as_of=started_at,
            )
            steps.append(
                _step(
                    "scheduled_order_dry_run",
                    RuntimePreflightStatus.PASSED
                    if scheduled_order_dry_run.can_start_supervised_runtime
                    else RuntimePreflightStatus.FAILED,
                    scheduled_order_dry_run.summary,
                    started_at,
                    (f"orders_submitted={scheduled_order_dry_run.orders_submitted}",),
                )
            )

        soak_cycles: tuple[RuntimeCycleResult, ...] = ()
        soak_health_report = None
        completed_at = started_at
        if self.config.soak_cycles:
            soak_cycles, soak_health_report, completed_at = self._run_soak(
                started_at=started_at,
                steps=steps,
            )
        else:
            steps.append(
                _step(
                    "full_day_soak",
                    RuntimePreflightStatus.WARNING,
                    (
                        "Full-day soak was not run by this validation command; "
                        "start one with --soak-cycles after dry-run evidence is clean."
                    ),
                    started_at,
                )
            )

        return self._finalize(
            validation_id,
            started_at,
            completed_at,
            preflight,
            steps,
            monitor_dry_run=monitor_dry_run,
            scheduled_order_dry_run=scheduled_order_dry_run,
            soak_cycles=soak_cycles,
            soak_health_report=soak_health_report,
        )

    def _run_dry_run(
        self,
        *,
        validation_id: str,
        phase: str,
        monitor_only: bool,
        as_of: datetime,
    ):
        runtime_config = replace(
            self.config.runtime_config,
            output_dir=(
                self.config.runtime_config.output_dir
                / "validation"
                / validation_id
                / phase
            ),
        )
        return AlpacaPaperRuntimeDryRun(
            config=PaperRuntimeDryRunConfig(
                runtime_config=runtime_config,
                dashboard_host=self.config.dashboard_host,
                require_credentials=self.config.require_credentials,
                monitor_only=monitor_only,
            ),
            env=self.env,
            runtime_factory=self.runtime_factory,
            persistence_store=RuntimePersistenceStore(runtime_config.output_dir),
            clock=self.clock,
        ).run(as_of=as_of)

    def _run_soak(
        self,
        *,
        started_at: datetime,
        steps: list[RuntimeValidationStep],
    ) -> tuple[tuple[RuntimeCycleResult, ...], object, datetime]:
        try:
            runtime = self.runtime_factory(self.config.runtime_config)
        except Exception as error:
            steps.append(
                _step(
                    "soak_runtime_construction",
                    RuntimePreflightStatus.FAILED,
                    "Runtime could not be constructed for soak.",
                    started_at,
                    (str(error),),
                )
            )
            return (), None, started_at

        if not self.config.allow_paper_orders_during_soak:
            runtime.apply_control(
                OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
                requested_at=started_at,
                requested_by="validation",
                reason="validation soak monitor-only safety",
            )
            steps.append(
                _step(
                    "soak_paper_order_block",
                    RuntimePreflightStatus.PASSED,
                    "Paper kill switch was enabled for validation soak.",
                    started_at,
                )
            )

        cycles: list[RuntimeCycleResult] = []
        completed_at = started_at
        for index in range(self.config.soak_cycles):
            cycle_time = (
                started_at + timedelta(seconds=index * self.config.soak_sleep_seconds)
                if self.config.soak_sleep_seconds
                else started_at
            )
            cycle = runtime.run_once(as_of=cycle_time)
            cycles.append(cycle)
            completed_at = cycle_time
            steps.append(_soak_cycle_step(cycle, index, cycle_time))
            if index < self.config.soak_cycles - 1 and self.config.soak_sleep_seconds:
                self.sleeper(self.config.soak_sleep_seconds)

        health_report = runtime.health_report(as_of=completed_at)
        steps.append(_dashboard_validation_step(runtime, completed_at))
        return tuple(cycles), health_report, completed_at

    def _finalize(
        self,
        validation_id: str,
        started_at: datetime,
        completed_at: datetime,
        preflight,
        steps: list[RuntimeValidationStep],
        *,
        monitor_dry_run,
        scheduled_order_dry_run,
        soak_cycles: tuple[RuntimeCycleResult, ...],
        soak_health_report,
    ) -> RuntimeValidationReport:
        facts = _collect_facts(
            monitor_dry_run=monitor_dry_run,
            scheduled_order_dry_run=scheduled_order_dry_run,
            soak_cycles=soak_cycles,
            steps=tuple(steps),
        )
        steps.extend(
            _proof_steps(
                completed_at=completed_at,
                facts=facts,
                require_report_and_learning=self.config.require_report_and_learning_proof,
            )
        )
        checklist = _validation_checklist(
            started_at=started_at,
            completed_at=completed_at,
            preflight=preflight,
            monitor_dry_run=monitor_dry_run,
            scheduled_order_dry_run=scheduled_order_dry_run,
            soak_cycles=soak_cycles,
            facts=facts,
            config=self.config,
        )
        failures = sum(
            1 for step in steps if step.status == RuntimePreflightStatus.FAILED
        ) + sum(1 for item in checklist if item.status == RuntimePreflightStatus.FAILED)
        warnings = (
            preflight.warnings
            + sum(1 for step in steps if step.status == RuntimePreflightStatus.WARNING)
            + sum(
                1 for item in checklist if item.status == RuntimePreflightStatus.WARNING
            )
            + _dry_run_warnings(monitor_dry_run)
            + _dry_run_warnings(scheduled_order_dry_run)
            + sum(1 for cycle in soak_cycles if cycle.status == RuntimeStatus.DEGRADED)
        )
        status = (
            RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.WARNING
            if warnings
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimeValidationReport(
            id=validation_id,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            can_start_full_day_soak=failures == 0,
            summary=_summary(status, failures, warnings, self.config.soak_cycles),
            preflight_report=preflight,
            monitor_dry_run_report=monitor_dry_run,
            scheduled_order_dry_run_report=scheduled_order_dry_run,
            soak_cycles=soak_cycles,
            soak_health_report=soak_health_report,
            steps=tuple(steps),
            checklist=checklist,
            warnings=warnings,
            failures=failures,
            latest_prices_refreshed=facts["latest_prices_refreshed"],
            latest_prices_fresh=facts["latest_prices_fresh"],
            broker_synced=facts["broker_synced"],
            dashboard_snapshot_serialized=facts["dashboard_snapshot_serialized"],
            report_written=facts["report_written"],
            nightly_learning_ran=facts["nightly_learning_ran"],
            orders_submitted=facts["orders_submitted"],
            soak_cycles_completed=len(soak_cycles),
            soak_monitor_only=not self.config.allow_paper_orders_during_soak,
            symbols=tuple(self.config.runtime_config.symbols),
            feed=self.config.runtime_config.feed.value,
            dashboard_host=self.config.dashboard_host,
            credential_required=self.config.require_credentials,
            scheduled_order_check_included=(self.config.include_scheduled_order_check),
            paper_orders_allowed_during_soak=(
                self.config.allow_paper_orders_during_soak
            ),
            broker_providers=tuple(facts["broker_providers"]),
            latest_price_sources=tuple(facts["latest_price_sources"]),
            latest_price_feeds=tuple(facts["latest_price_feeds"]),
        )
        markdown_path = write_validation_markdown_report(
            report,
            self.config.runtime_config.output_dir / "reports",
        )
        report = report.model_copy(update={"markdown_path": str(markdown_path)})
        self.persistence_store.persist_validation_report(report)
        return report


def render_validation_text(report: RuntimeValidationReport) -> str:
    """Render a compact paper-runtime validation summary for operators."""

    lines = [
        f"Validation status: {report.status.value}",
        f"Can start full-day soak: {'yes' if report.can_start_full_day_soak else 'no'}",
        f"Soak cycles completed: {report.soak_cycles_completed}",
        report.summary,
        "",
        "Proofs:",
        f"- latest prices refreshed: {_yes_no(report.latest_prices_refreshed)}",
        f"- latest prices fresh: {_yes_no(report.latest_prices_fresh)}",
        f"- broker synced: {_yes_no(report.broker_synced)}",
        f"- dashboard snapshot serialized: "
        f"{_yes_no(report.dashboard_snapshot_serialized)}",
        f"- report written: {_yes_no(report.report_written)}",
        f"- nightly learning ran: {_yes_no(report.nightly_learning_ran)}",
        f"- orders submitted: {report.orders_submitted}",
        f"- broker providers: {', '.join(report.broker_providers) or 'unknown'}",
        (
            "- latest price sources: "
            f"{', '.join(report.latest_price_sources) or 'unknown'}"
        ),
        f"- latest price feeds: {', '.join(report.latest_price_feeds) or 'unknown'}",
        f"- markdown report: {report.markdown_path or 'not written'}",
    ]
    if report.checklist:
        lines.extend(("", "Checklist:"))
        for item in report.checklist:
            lines.append(f"- {item.name}: {item.status.value} - {item.message}")
    lines.extend(("", "Steps:"))
    for step in report.steps:
        lines.append(f"- {step.name}: {step.status.value} - {step.message}")
    return "\n".join(lines)


def render_validation_markdown(report: RuntimeValidationReport) -> str:
    """Render a reviewable paper-runtime validation report."""

    lines = [
        f"# Paper Runtime Validation Report: {report.id}",
        "",
        "> Paper trading only. This report does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Can start full-day soak: `{_yes_no(report.can_start_full_day_soak)}`",
        f"- Started: `{report.started_at.isoformat()}`",
        f"- Completed: `{report.completed_at.isoformat()}`",
        f"- Warnings: `{report.warnings}`",
        f"- Failures: `{report.failures}`",
        f"- Submitted paper orders observed: `{report.orders_submitted}`",
        (
            "- Broker providers observed: "
            f"`{', '.join(report.broker_providers) or 'unknown'}`"
        ),
        (
            "- Latest-price sources observed: "
            f"`{', '.join(report.latest_price_sources) or 'unknown'}`"
        ),
        (
            "- Latest-price feeds observed: "
            f"`{', '.join(report.latest_price_feeds) or 'unknown'}`"
        ),
        "",
        report.summary,
        "",
        "## Validation Configuration",
        "",
        f"- Mode: `{report.mode}`",
        f"- Symbols: `{', '.join(report.symbols) or 'not recorded'}`",
        f"- Feed: `{report.feed or 'not recorded'}`",
        f"- Dashboard host: `{report.dashboard_host or 'not recorded'}`",
        f"- Credentials required: `{_yes_no(report.credential_required)}`",
        (
            "- Scheduled-order dry run included: "
            f"`{_yes_no(report.scheduled_order_check_included)}`"
        ),
        (
            "- Paper orders allowed during soak: "
            f"`{_yes_no(report.paper_orders_allowed_during_soak)}`"
        ),
        "",
        "## Paper Boundary",
        "",
        "- Broker mode must remain Alpaca paper only.",
        "- Live-money trading, margin, shorts, options, futures, forex, crypto, "
        "and non-U.S. markets remain out of scope.",
        "- Monitor-only validation is expected to submit zero paper orders.",
        "",
        "## Proofs",
        "",
        "| Proof | Observed |",
        "| --- | --- |",
        f"| Latest prices refreshed | {_yes_no(report.latest_prices_refreshed)} |",
        f"| Latest prices fresh | {_yes_no(report.latest_prices_fresh)} |",
        f"| Broker synced | {_yes_no(report.broker_synced)} |",
        "| Dashboard snapshot serialized | "
        f"{_yes_no(report.dashboard_snapshot_serialized)} |",
        f"| Daily report written | {_yes_no(report.report_written)} |",
        f"| Nightly learning ran | {_yes_no(report.nightly_learning_ran)} |",
        f"| Soak cycles completed | {report.soak_cycles_completed} |",
        f"| Soak monitor-only | {_yes_no(report.soak_monitor_only)} |",
        "",
        "## Credentialed Paper Validation Checklist",
        "",
        "| Item | Status | Message | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    if report.checklist:
        for item in report.checklist:
            evidence = "<br>".join(item.evidence) if item.evidence else "-"
            lines.append(
                "| "
                f"{_escape_table(item.name)} | "
                f"{_escape_table(item.status.value)} | "
                f"{_escape_table(item.message)} | "
                f"{_escape_table(evidence)} |"
            )
    else:
        lines.append("| No checklist recorded | warning | Legacy report format. | - |")

    lines.extend(
        (
            "",
            "## Validation Steps",
            "",
            "| Step | Status | Message | Evidence |",
            "| --- | --- | --- | --- |",
        )
    )
    for step in report.steps:
        evidence = "<br>".join(step.evidence) if step.evidence else "-"
        lines.append(
            "| "
            f"{_escape_table(step.name)} | "
            f"{_escape_table(step.status.value)} | "
            f"{_escape_table(step.message)} | "
            f"{_escape_table(evidence)} |"
        )

    lines.extend(
        (
            "",
            "## Next Action",
            "",
            _validation_next_action(report),
            "",
        )
    )
    return "\n".join(lines)


def write_validation_markdown_report(
    report: RuntimeValidationReport,
    reports_dir: Path | str,
) -> Path:
    """Write a validation Markdown report and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.id}.md"
    path.write_text(render_validation_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run supervised Alpaca paper runtime validation."""

    parser = argparse.ArgumentParser(description="Validate Alpaca paper runtime.")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--feed", default=DataFeed.IEX.value)
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--no-credential-required", action="store_true")
    parser.add_argument("--include-scheduled-order-check", action="store_true")
    parser.add_argument("--soak-cycles", type=int, default=0)
    parser.add_argument("--soak-sleep-seconds", type=float, default=0)
    parser.add_argument("--allow-paper-orders-during-soak", action="store_true")
    parser.add_argument("--require-report-and-learning-proof", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    symbols = parse_symbol_list(
        args.symbols,
        default=AlwaysOnPaperRuntimeConfig().symbols,
    )
    runtime_config = AlwaysOnPaperRuntimeConfig(
        symbols=symbols,
        feed=DataFeed(args.feed.upper()),
        output_dir=Path(args.output_dir),
    )
    report = AlpacaPaperRuntimeValidation(
        config=PaperRuntimeValidationConfig(
            runtime_config=runtime_config,
            dashboard_host=args.dashboard_host,
            require_credentials=not args.no_credential_required,
            include_scheduled_order_check=args.include_scheduled_order_check,
            soak_cycles=args.soak_cycles,
            soak_sleep_seconds=args.soak_sleep_seconds,
            allow_paper_orders_during_soak=args.allow_paper_orders_during_soak,
            require_report_and_learning_proof=args.require_report_and_learning_proof,
        )
    ).run()
    print(report.model_dump_json() if args.json else render_validation_text(report))
    return 0 if report.can_start_full_day_soak else 1


def _step(
    name: str,
    status: RuntimePreflightStatus,
    message: str,
    checked_at: datetime,
    evidence: tuple[str, ...] = (),
) -> RuntimeValidationStep:
    return RuntimeValidationStep(
        name=name,
        status=status,
        message=message,
        checked_at=checked_at,
        evidence=tuple(str(item) for item in evidence),
    )


def _soak_cycle_step(
    cycle: RuntimeCycleResult,
    index: int,
    checked_at: datetime,
) -> RuntimeValidationStep:
    if cycle.status == RuntimeStatus.BLOCKED:
        status = RuntimePreflightStatus.FAILED
    elif cycle.status == RuntimeStatus.DEGRADED:
        status = RuntimePreflightStatus.WARNING
    else:
        status = RuntimePreflightStatus.PASSED
    return _step(
        f"soak_cycle_{index + 1}",
        status,
        f"Validation soak cycle finished with runtime status {cycle.status.value}.",
        checked_at,
        (
            f"prices_refreshed={cycle.prices_refreshed}",
            f"broker_synced={cycle.broker_synced}",
            f"orders_submitted={cycle.orders_submitted}",
            f"report_written={cycle.report_written}",
            f"nightly_learning_ran={cycle.nightly_learning_ran}",
        ),
    )


def _dashboard_validation_step(
    runtime: AlwaysOnPaperRuntime,
    checked_at: datetime,
) -> RuntimeValidationStep:
    try:
        runtime.dashboard_snapshot().model_dump_json()
    except Exception as error:
        return _step(
            "soak_dashboard_snapshot",
            RuntimePreflightStatus.FAILED,
            "Soak dashboard snapshot could not be serialized.",
            checked_at,
            (str(error),),
        )
    return _step(
        "soak_dashboard_snapshot",
        RuntimePreflightStatus.PASSED,
        "Soak dashboard snapshot serialized successfully.",
        checked_at,
    )


def _proof_steps(
    *,
    completed_at: datetime,
    facts: dict[str, bool | int],
    require_report_and_learning: bool,
) -> list[RuntimeValidationStep]:
    steps = [
        _proof_step(
            "latest_price_proof",
            bool(facts["latest_prices_refreshed"]),
            "Latest-price refresh evidence was observed.",
            "Latest-price refresh evidence was not observed.",
            completed_at,
        ),
        _proof_step(
            "broker_sync_proof",
            bool(facts["broker_synced"]),
            "Broker sync evidence was observed.",
            "Broker sync evidence was not observed.",
            completed_at,
        ),
        _proof_step(
            "dashboard_snapshot_proof",
            bool(facts["dashboard_snapshot_serialized"]),
            "Dashboard snapshot serialization evidence was observed.",
            "Dashboard snapshot serialization evidence was not observed.",
            completed_at,
        ),
    ]
    if require_report_and_learning:
        steps.extend(
            (
                _proof_step(
                    "daily_report_proof",
                    bool(facts["report_written"]),
                    "Daily report generation evidence was observed.",
                    "Daily report generation evidence was not observed.",
                    completed_at,
                ),
                _proof_step(
                    "nightly_learning_proof",
                    bool(facts["nightly_learning_ran"]),
                    "Nightly learning evidence was observed.",
                    "Nightly learning evidence was not observed.",
                    completed_at,
                ),
            )
        )
    return steps


def _proof_step(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    checked_at: datetime,
) -> RuntimeValidationStep:
    return _step(
        name,
        RuntimePreflightStatus.PASSED if passed else RuntimePreflightStatus.FAILED,
        passed_message if passed else failed_message,
        checked_at,
    )


def _collect_facts(
    *,
    monitor_dry_run,
    scheduled_order_dry_run,
    soak_cycles: tuple[RuntimeCycleResult, ...],
    steps: tuple[RuntimeValidationStep, ...],
) -> dict[str, bool | int | tuple[str, ...]]:
    cycles = [
        report.cycle_result
        for report in (monitor_dry_run, scheduled_order_dry_run)
        if report is not None and report.cycle_result is not None
    ]
    cycles.extend(soak_cycles)
    dry_runs = [
        report
        for report in (monitor_dry_run, scheduled_order_dry_run)
        if report is not None
    ]
    dry_run_steps = [
        step
        for report in dry_runs
        for step in report.steps
        if step.name == "dashboard_snapshot"
    ]
    all_steps = (*steps, *dry_run_steps)
    return {
        "latest_prices_refreshed": any(cycle.prices_refreshed for cycle in cycles),
        "latest_prices_fresh": any(
            report.cycle_result is not None
            and report.cycle_result.prices_refreshed
            and report.preflight_report.can_start
            and not any(
                "missing or stale" in event.message
                for event in report.cycle_result.events
            )
            for report in dry_runs
        ),
        "broker_synced": any(cycle.broker_synced for cycle in cycles),
        "dashboard_snapshot_serialized": any(
            step.name in {"dashboard_snapshot", "soak_dashboard_snapshot"}
            and step.status == RuntimePreflightStatus.PASSED
            for step in all_steps
        ),
        "report_written": any(cycle.report_written for cycle in cycles),
        "nightly_learning_ran": any(cycle.nightly_learning_ran for cycle in cycles),
        "orders_submitted": sum(cycle.orders_submitted for cycle in cycles),
        "broker_providers": tuple(
            sorted(
                {
                    report.broker_provider
                    for report in dry_runs
                    if report.broker_provider
                }
            )
        ),
        "latest_price_sources": tuple(
            sorted(
                {
                    report.latest_price_source
                    for report in dry_runs
                    if report.latest_price_source
                }
            )
        ),
        "latest_price_feeds": tuple(
            sorted(
                {
                    report.latest_price_feed
                    for report in dry_runs
                    if report.latest_price_feed
                }
            )
        ),
    }


def _validation_checklist(
    *,
    started_at: datetime,
    completed_at: datetime,
    preflight,
    monitor_dry_run,
    scheduled_order_dry_run,
    soak_cycles: tuple[RuntimeCycleResult, ...],
    facts: dict[str, object],
    config: PaperRuntimeValidationConfig,
) -> tuple[RuntimeValidationChecklistItem, ...]:
    items: list[RuntimeValidationChecklistItem] = []

    items.append(
        _checklist_item(
            "credentialed_preflight",
            RuntimePreflightStatus.PASSED
            if preflight.can_start
            else RuntimePreflightStatus.FAILED,
            (
                "Credentialed preflight can start the paper runtime."
                if preflight.can_start
                else "Credentialed preflight did not clear the paper runtime."
            ),
            (
                f"status={preflight.status.value}",
                f"credentials_required={config.require_credentials}",
            ),
        )
    )

    if monitor_dry_run is None:
        items.append(
            _checklist_item(
                "monitor_only_dry_run",
                RuntimePreflightStatus.FAILED
                if preflight.can_start
                else RuntimePreflightStatus.WARNING,
                (
                    "Monitor-only dry run did not run after a cleared preflight."
                    if preflight.can_start
                    else "Monitor-only dry run was skipped because preflight failed."
                ),
            )
        )
    else:
        monitor_clean = (
            monitor_dry_run.can_start_supervised_runtime
            and monitor_dry_run.monitor_only
            and monitor_dry_run.orders_submitted == 0
        )
        items.append(
            _checklist_item(
                "monitor_only_dry_run",
                RuntimePreflightStatus.PASSED
                if monitor_clean
                else RuntimePreflightStatus.FAILED,
                (
                    "Monitor-only dry run completed without paper order submission."
                    if monitor_clean
                    else "Monitor-only dry run was not clean."
                ),
                (
                    f"monitor_only={monitor_dry_run.monitor_only}",
                    f"orders_submitted={monitor_dry_run.orders_submitted}",
                    f"can_start={monitor_dry_run.can_start_supervised_runtime}",
                ),
            )
        )

    if not config.include_scheduled_order_check:
        items.append(
            _checklist_item(
                "scheduled_order_dry_run",
                RuntimePreflightStatus.WARNING,
                "Scheduled-order dry run was not requested in this validation pass.",
                ("scheduled_order_check_included=False",),
            )
        )
    elif scheduled_order_dry_run is None:
        items.append(
            _checklist_item(
                "scheduled_order_dry_run",
                RuntimePreflightStatus.FAILED,
                "Scheduled-order dry run was requested but did not run.",
            )
        )
    else:
        items.append(
            _checklist_item(
                "scheduled_order_dry_run",
                RuntimePreflightStatus.PASSED
                if scheduled_order_dry_run.can_start_supervised_runtime
                else RuntimePreflightStatus.FAILED,
                (
                    "Scheduled-order dry run completed in isolated validation state."
                    if scheduled_order_dry_run.can_start_supervised_runtime
                    else "Scheduled-order dry run failed in isolated validation state."
                ),
                (
                    f"orders_submitted={scheduled_order_dry_run.orders_submitted}",
                    f"can_start={scheduled_order_dry_run.can_start_supervised_runtime}",
                ),
            )
        )

    latest_prices_clean = bool(facts["latest_prices_refreshed"]) and bool(
        facts["latest_prices_fresh"]
    )
    items.append(
        _checklist_item(
            "latest_price_freshness",
            RuntimePreflightStatus.PASSED
            if latest_prices_clean
            else RuntimePreflightStatus.FAILED,
            (
                "Latest-price refresh and freshness evidence was observed."
                if latest_prices_clean
                else "Latest-price refresh or freshness evidence is missing."
            ),
            (
                f"refreshed={facts['latest_prices_refreshed']}",
                f"fresh={facts['latest_prices_fresh']}",
            ),
        )
    )
    items.append(
        _checklist_item(
            "broker_sync",
            RuntimePreflightStatus.PASSED
            if bool(facts["broker_synced"])
            else RuntimePreflightStatus.FAILED,
            (
                "Broker sync evidence was observed."
                if bool(facts["broker_synced"])
                else "Broker sync evidence is missing."
            ),
        )
    )
    items.append(
        _checklist_item(
            "dashboard_snapshot",
            RuntimePreflightStatus.PASSED
            if bool(facts["dashboard_snapshot_serialized"])
            else RuntimePreflightStatus.FAILED,
            (
                "Dashboard snapshot serialized successfully."
                if bool(facts["dashboard_snapshot_serialized"])
                else "Dashboard snapshot serialization evidence is missing."
            ),
        )
    )

    if soak_cycles:
        items.append(
            _checklist_item(
                "soak_cycle_evidence",
                RuntimePreflightStatus.PASSED,
                "Validation soak cycle evidence was captured.",
                (f"soak_cycles={len(soak_cycles)}",),
            )
        )
    else:
        items.append(
            _checklist_item(
                "soak_cycle_evidence",
                RuntimePreflightStatus.WARNING,
                "No validation soak cycles were captured in this pass.",
            )
        )

    duration = completed_at - started_at
    full_day_soak_proven = bool(soak_cycles) and duration >= timedelta(hours=24)
    items.append(
        _checklist_item(
            "full_day_plus_overnight_soak",
            RuntimePreflightStatus.PASSED
            if full_day_soak_proven
            else RuntimePreflightStatus.WARNING,
            (
                "Validation soak spans at least 24 hours."
                if full_day_soak_proven
                else "Full-day plus overnight soak evidence is still incomplete."
            ),
            (
                f"duration_hours={duration.total_seconds() / 3600:.2f}",
                f"soak_cycles={len(soak_cycles)}",
            ),
        )
    )

    monitor_orders = (
        monitor_dry_run.orders_submitted if monitor_dry_run is not None else 0
    )
    if monitor_orders:
        paper_boundary_status = RuntimePreflightStatus.FAILED
        paper_boundary_message = "Monitor-only validation submitted paper orders."
    elif config.allow_paper_orders_during_soak:
        paper_boundary_status = RuntimePreflightStatus.WARNING
        paper_boundary_message = (
            "Paper orders were explicitly allowed during soak validation."
        )
    else:
        paper_boundary_status = RuntimePreflightStatus.PASSED
        paper_boundary_message = (
            "Monitor-only and soak validation preserve the paper-order boundary."
        )
    items.append(
        _checklist_item(
            "paper_order_boundary",
            paper_boundary_status,
            paper_boundary_message,
            (
                f"monitor_orders_submitted={monitor_orders}",
                f"paper_orders_allowed_during_soak="
                f"{config.allow_paper_orders_during_soak}",
            ),
        )
    )

    items.append(
        _checklist_item(
            "daily_report_proof",
            RuntimePreflightStatus.PASSED
            if bool(facts["report_written"])
            else RuntimePreflightStatus.FAILED
            if config.require_report_and_learning_proof
            else RuntimePreflightStatus.WARNING,
            (
                "Daily report generation evidence was observed."
                if bool(facts["report_written"])
                else "Daily report generation evidence was not required in this pass."
                if not config.require_report_and_learning_proof
                else "Daily report generation evidence is required but missing."
            ),
        )
    )
    items.append(
        _checklist_item(
            "nightly_learning_proof",
            RuntimePreflightStatus.PASSED
            if bool(facts["nightly_learning_ran"])
            else RuntimePreflightStatus.FAILED
            if config.require_report_and_learning_proof
            else RuntimePreflightStatus.WARNING,
            (
                "Nightly learning evidence was observed."
                if bool(facts["nightly_learning_ran"])
                else "Nightly learning evidence was not required in this pass."
                if not config.require_report_and_learning_proof
                else "Nightly learning evidence is required but missing."
            ),
        )
    )

    broker_providers = tuple(str(item) for item in facts["broker_providers"])
    items.append(
        _checklist_item(
            "broker_provider_provenance",
            RuntimePreflightStatus.PASSED
            if broker_providers
            else RuntimePreflightStatus.FAILED,
            (
                "Broker provider provenance was recorded."
                if broker_providers
                else "Broker provider provenance is missing."
            ),
            broker_providers,
        )
    )
    latest_price_sources = tuple(str(item) for item in facts["latest_price_sources"])
    latest_price_feeds = tuple(str(item) for item in facts["latest_price_feeds"])
    items.append(
        _checklist_item(
            "latest_price_source_provenance",
            RuntimePreflightStatus.PASSED
            if latest_price_sources and latest_price_feeds
            else RuntimePreflightStatus.FAILED,
            (
                "Latest-price source and feed provenance were recorded."
                if latest_price_sources and latest_price_feeds
                else "Latest-price source or feed provenance is missing."
            ),
            (*latest_price_sources, *latest_price_feeds),
        )
    )

    return tuple(items)


def _checklist_item(
    name: str,
    status: RuntimePreflightStatus,
    message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeValidationChecklistItem:
    return RuntimeValidationChecklistItem(
        name=name,
        status=status,
        message=message,
        evidence=tuple(str(item) for item in evidence),
    )


def _dry_run_warnings(report) -> int:
    return report.warnings if report is not None else 0


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    warnings: int,
    soak_cycles: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Paper runtime validation passed with clean evidence."
    if status == RuntimePreflightStatus.WARNING:
        if soak_cycles:
            return (
                f"Paper runtime validation completed with {warnings} warning(s); "
                "review evidence before extending the soak."
            )
        return (
            f"Paper runtime validation completed with {warnings} warning(s); "
            "run a full-day soak after reviewing evidence."
        )
    return (
        f"Paper runtime validation failed with {failures} failure(s); "
        "do not start a full-day soak yet."
    )


def _validation_id(started_at: datetime) -> str:
    value = started_at.astimezone(UTC)
    return f"validation-{value.strftime('%Y%m%dT%H%M%S')}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _validation_next_action(report: RuntimeValidationReport) -> str:
    if report.failures:
        return (
            "Do not start or extend the paper runtime. Fix validation failures, "
            "rerun preflight, and repeat monitor-only validation."
        )
    if report.status == RuntimePreflightStatus.WARNING:
        return (
            "Review warnings and evidence before starting or extending a supervised "
            "full-day paper soak."
        )
    if report.soak_cycles_completed == 0:
        return (
            "Validation is clean enough to proceed to a supervised full-day plus "
            "overnight paper soak."
        )
    return (
        "Validation evidence is clean. Review broker paper account history and "
        "completion audit evidence before treating the app as functionally proven."
    )


if __name__ == "__main__":
    raise SystemExit(main())
