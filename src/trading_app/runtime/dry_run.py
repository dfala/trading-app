"""Supervised Alpaca paper runtime dry run."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from trading_app.runtime.cli import parse_symbol_list
from trading_app.runtime.models import (
    OperatorControlAction,
    OperatorControlRequest,
    OperatorControlState,
    RuntimeDryRunReport,
    RuntimeDryRunStep,
    RuntimePreflightStatus,
)
from trading_app.runtime.operator import RuntimeControlCenter
from trading_app.runtime.paper import AlwaysOnPaperRuntime, AlwaysOnPaperRuntimeConfig
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.runtime.preflight import AlpacaPaperRuntimePreflight
from trading_app.schemas import DataFeed

RuntimeFactory = Callable[[AlwaysOnPaperRuntimeConfig], AlwaysOnPaperRuntime]


@dataclass(frozen=True)
class PaperRuntimeDryRunConfig:
    runtime_config: AlwaysOnPaperRuntimeConfig
    dashboard_host: str = "127.0.0.1"
    require_credentials: bool = True
    monitor_only: bool = True


class AlpacaPaperRuntimeDryRun:
    """Run a one-cycle, evidence-producing Alpaca paper runtime smoke test."""

    def __init__(
        self,
        *,
        config: PaperRuntimeDryRunConfig,
        env: Mapping[str, str] | None = None,
        runtime_factory: RuntimeFactory | None = None,
        persistence_store: RuntimePersistenceStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.env = env
        self.runtime_factory = runtime_factory or _alpaca_runtime_factory
        self.persistence_store = persistence_store or RuntimePersistenceStore(
            config.runtime_config.output_dir
        )
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def run(self, *, as_of: datetime | None = None) -> RuntimeDryRunReport:
        now = as_of or self.clock()
        steps: list[RuntimeDryRunStep] = []
        preflight = AlpacaPaperRuntimePreflight(
            config=self.config.runtime_config,
            dashboard_host=self.config.dashboard_host,
            env=self.env,
            require_credentials=self.config.require_credentials,
            persistence_store=self.persistence_store,
        ).run(as_of=now)
        steps.append(
            _step(
                "preflight",
                RuntimePreflightStatus.PASSED
                if preflight.can_start
                else RuntimePreflightStatus.FAILED,
                preflight.summary,
                now,
                (preflight.status.value,),
            )
        )
        if not preflight.can_start:
            return self._finalize(
                now,
                preflight,
                steps,
                monitor_only=self.config.monitor_only,
                cycle_result=None,
                health_report=None,
                orders_before=0,
                orders_after=0,
                runtime_mode=None,
                broker_provider=None,
                latest_price_source=None,
                latest_price_feed=None,
            )

        try:
            runtime = self.runtime_factory(self.config.runtime_config)
        except Exception as error:
            steps.append(
                _step(
                    "runtime_construction",
                    RuntimePreflightStatus.FAILED,
                    "Runtime could not be constructed.",
                    now,
                    (str(error),),
                )
            )
            return self._finalize(
                now,
                preflight,
                steps,
                monitor_only=self.config.monitor_only,
                cycle_result=None,
                health_report=None,
                orders_before=0,
                orders_after=0,
                runtime_mode=None,
                broker_provider=None,
                latest_price_source=None,
                latest_price_feed=None,
            )

        steps.append(
            _step(
                "runtime_construction",
                RuntimePreflightStatus.PASSED,
                "Runtime was constructed after preflight passed.",
                now,
                (f"broker_provider={runtime.service.broker.provider}",),
            )
        )
        orders_before = len(runtime.service.submissions)
        previous_control_state = runtime.control_center.state
        previous_control_history = runtime.control_center.history

        if self.config.monitor_only:
            runtime.control_center.apply(
                OperatorControlRequest(
                    action=OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
                    requested_at=now,
                    requested_by="dry-run",
                    reason="monitor-only dry run",
                )
            )
            steps.append(
                _step(
                    "paper_order_block",
                    RuntimePreflightStatus.PASSED,
                    "Paper kill switch was enabled for monitor-only dry run.",
                    now,
                )
            )

        cycle = runtime.run_once(as_of=now)
        if self.config.monitor_only:
            _restore_monitor_only_control_state(
                runtime,
                state=previous_control_state,
                history=previous_control_history,
                as_of=now,
            )
        health_report = runtime.health_report(as_of=now)
        runtime_snapshot = runtime.snapshot(as_of=now)
        latest_prices = runtime_snapshot.latest_prices
        orders_after = len(runtime.service.submissions)
        steps.extend(
            (
                _step(
                    "latest_prices",
                    RuntimePreflightStatus.PASSED
                    if cycle.prices_refreshed
                    else RuntimePreflightStatus.FAILED,
                    "Latest prices refreshed."
                    if cycle.prices_refreshed
                    else "Latest prices did not refresh.",
                    now,
                    _latest_price_evidence(latest_prices),
                ),
                _step(
                    "broker_sync",
                    RuntimePreflightStatus.PASSED
                    if cycle.broker_synced
                    else RuntimePreflightStatus.FAILED,
                    "Broker sync completed."
                    if cycle.broker_synced
                    else "Broker sync did not complete.",
                    now,
                    (f"broker_provider={runtime.service.broker.provider}",),
                ),
                _step(
                    "paper_order_safety",
                    _paper_order_safety_status(
                        monitor_only=self.config.monitor_only,
                        orders_submitted=cycle.orders_submitted,
                    ),
                    _paper_order_safety_message(
                        monitor_only=self.config.monitor_only,
                        orders_submitted=cycle.orders_submitted,
                    ),
                    now,
                    (f"orders_submitted={cycle.orders_submitted}",),
                ),
                _step(
                    "health_report",
                    RuntimePreflightStatus.PASSED
                    if health_report is not None
                    else RuntimePreflightStatus.FAILED,
                    "Runtime health report was generated.",
                    now,
                    (health_report.status.value if health_report else "missing",),
                ),
                _dashboard_step(runtime, now),
                _persistence_step(self.persistence_store, now),
            )
        )

        return self._finalize(
            now,
            preflight,
            steps,
            monitor_only=self.config.monitor_only,
            cycle_result=cycle,
            health_report=health_report,
            orders_before=orders_before,
            orders_after=orders_after,
            runtime_mode=runtime_snapshot.mode,
            broker_provider=runtime.service.broker.provider,
            latest_price_source=latest_prices.source if latest_prices else None,
            latest_price_feed=latest_prices.feed.value if latest_prices else None,
        )

    def _finalize(
        self,
        as_of: datetime,
        preflight,
        steps: list[RuntimeDryRunStep],
        *,
        monitor_only: bool,
        cycle_result,
        health_report,
        orders_before: int,
        orders_after: int,
        runtime_mode: str | None,
        broker_provider: str | None,
        latest_price_source: str | None,
        latest_price_feed: str | None,
    ) -> RuntimeDryRunReport:
        failures = sum(
            1 for step in steps if step.status == RuntimePreflightStatus.FAILED
        )
        warnings = sum(
            1 for step in steps if step.status == RuntimePreflightStatus.WARNING
        )
        status = (
            RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.WARNING
            if warnings or preflight.warnings
            else RuntimePreflightStatus.PASSED
        )
        report = RuntimeDryRunReport(
            as_of=as_of,
            status=status,
            can_start_supervised_runtime=failures == 0,
            monitor_only=monitor_only,
            summary=_summary(status, failures, warnings, preflight.warnings),
            preflight_report=preflight,
            cycle_result=cycle_result,
            health_report=health_report,
            steps=tuple(steps),
            warnings=warnings + preflight.warnings,
            failures=failures,
            orders_before=orders_before,
            orders_after=orders_after,
            orders_submitted=cycle_result.orders_submitted if cycle_result else 0,
            runtime_mode=runtime_mode,
            broker_provider=broker_provider,
            latest_price_source=latest_price_source,
            latest_price_feed=latest_price_feed,
        )
        self.persistence_store.persist_dry_run_report(report)
        return report


def render_dry_run_text(report: RuntimeDryRunReport) -> str:
    """Render a compact dry-run summary for operators."""

    lines = [
        f"Dry-run status: {report.status.value}",
        f"Monitor-only: {'yes' if report.monitor_only else 'no'}",
        f"Can start supervised runtime: "
        f"{'yes' if report.can_start_supervised_runtime else 'no'}",
        report.summary,
        "",
        "Steps:",
    ]
    for step in report.steps:
        lines.append(f"- {step.name}: {step.status.value} - {step.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run a one-cycle Alpaca paper runtime dry run."""

    parser = argparse.ArgumentParser(description="Dry run Alpaca paper runtime.")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--feed", default=DataFeed.IEX.value)
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--allow-scheduled-paper-orders", action="store_true")
    parser.add_argument("--no-credential-required", action="store_true")
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
    report = AlpacaPaperRuntimeDryRun(
        config=PaperRuntimeDryRunConfig(
            runtime_config=runtime_config,
            dashboard_host=args.dashboard_host,
            require_credentials=not args.no_credential_required,
            monitor_only=not args.allow_scheduled_paper_orders,
        )
    ).run()
    print(report.model_dump_json() if args.json else render_dry_run_text(report))
    return 0 if report.can_start_supervised_runtime else 1


def _step(
    name: str,
    status: RuntimePreflightStatus,
    message: str,
    checked_at: datetime,
    evidence: tuple[str, ...] = (),
) -> RuntimeDryRunStep:
    return RuntimeDryRunStep(
        name=name,
        status=status,
        message=message,
        checked_at=checked_at,
        evidence=tuple(str(item) for item in evidence),
    )


def _dashboard_step(
    runtime: AlwaysOnPaperRuntime, as_of: datetime
) -> RuntimeDryRunStep:
    try:
        runtime.dashboard_snapshot().model_dump_json()
    except Exception as error:
        return _step(
            "dashboard_snapshot",
            RuntimePreflightStatus.FAILED,
            "Dashboard snapshot could not be serialized.",
            as_of,
            (str(error),),
        )
    return _step(
        "dashboard_snapshot",
        RuntimePreflightStatus.PASSED,
        "Dashboard snapshot serialized successfully.",
        as_of,
    )


def _persistence_step(
    persistence_store: RuntimePersistenceStore, as_of: datetime
) -> RuntimeDryRunStep:
    if (persistence_store.state_dir / "last-cycle.json").exists() and (
        persistence_store.state_dir / "latest-health-report.json"
    ).exists():
        return _step(
            "persistence",
            RuntimePreflightStatus.PASSED,
            "Runtime cycle and health evidence were persisted.",
            as_of,
        )
    return _step(
        "persistence",
        RuntimePreflightStatus.FAILED,
        "Runtime cycle or health evidence was not persisted.",
        as_of,
    )


def _restore_monitor_only_control_state(
    runtime: AlwaysOnPaperRuntime,
    *,
    state: OperatorControlState,
    history,
    as_of: datetime,
) -> None:
    """Remove temporary dry-run order blocking from live runtime state."""

    runtime.control_center = RuntimeControlCenter(state=state, history=history)
    runtime._last_control_result = runtime.control_center.last_result
    runtime._alerts = runtime.alert_engine.evaluate(
        runtime.snapshot(as_of=as_of),
        control_state=state,
    )
    runtime._health_report = runtime.health_engine.evaluate(
        runtime.snapshot(as_of=as_of)
    )
    runtime.persistence_store.persist_control_state(state)
    runtime.persistence_store.persist_alerts(runtime._alerts)
    runtime.persistence_store.persist_health_report(runtime._health_report)
    runtime.persistence_store.persist_runtime_snapshot(runtime.snapshot(as_of=as_of))
    runtime.persistence_store.persist_dashboard_snapshot(
        runtime.dashboard_snapshot(as_of=as_of)
    )


def _latest_price_evidence(latest_prices) -> tuple[str, ...]:
    if latest_prices is None:
        return ("latest_prices=missing",)
    return (
        f"latest_price_source={latest_prices.source}",
        f"latest_price_feed={latest_prices.feed.value}",
        f"latest_price_status={latest_prices.status.value}",
        f"all_fresh={latest_prices.all_fresh}",
    )


def _paper_order_safety_status(
    *, monitor_only: bool, orders_submitted: int
) -> RuntimePreflightStatus:
    if monitor_only and orders_submitted:
        return RuntimePreflightStatus.FAILED
    return RuntimePreflightStatus.PASSED


def _paper_order_safety_message(*, monitor_only: bool, orders_submitted: int) -> str:
    if monitor_only and orders_submitted:
        return "Monitor-only dry run submitted paper orders unexpectedly."
    if monitor_only:
        return "Monitor-only dry run submitted zero paper orders."
    return f"Scheduled paper order path submitted {orders_submitted} order(s)."


def _alpaca_runtime_factory(
    config: AlwaysOnPaperRuntimeConfig,
) -> AlwaysOnPaperRuntime:
    return AlwaysOnPaperRuntime.from_alpaca_env(config=config)


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    warnings: int,
    preflight_warnings: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Dry run passed; supervised paper runtime may be started."
    if status == RuntimePreflightStatus.WARNING:
        total_warnings = warnings + preflight_warnings
        return (
            f"Dry run passed with {total_warnings} warning(s); review evidence before "
            "a longer supervised run."
        )
    return f"Dry run failed with {failures} failure(s); do not start runtime yet."


if __name__ == "__main__":
    raise SystemExit(main())
