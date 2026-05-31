"""Operator lifecycle drill audit for the paper runtime."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trading_app.runtime.models import (
    OperatorControlAction,
    RuntimeLifecycleDrillCheck,
    RuntimeLifecycleDrillReport,
    RuntimePreflightStatus,
    RuntimeSnapshot,
)
from trading_app.runtime.ops import build_operations_profile
from trading_app.runtime.persistence import RuntimePersistenceStore

_REQUIRED_CONTROL_ACTIONS = (
    OperatorControlAction.PAUSE_RUNTIME,
    OperatorControlAction.RESUME_RUNTIME,
    OperatorControlAction.ENABLE_PAPER_KILL_SWITCH,
    OperatorControlAction.DISABLE_PAPER_KILL_SWITCH,
    OperatorControlAction.FORCE_RECONCILIATION,
    OperatorControlAction.GENERATE_REPORT,
)


class RuntimeLifecycleDrillAuditor:
    """Audit whether startup, shutdown, and operator controls were exercised."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        persistence_store: RuntimePersistenceStore | None = None,
        working_dir: Path | str = ".",
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.working_dir = Path(working_dir)
        self.persist_report = persist_report

    def audit(self, *, as_of: datetime | None = None) -> RuntimeLifecycleDrillReport:
        now = as_of or datetime.now(tz=UTC)
        recovered = self.store.recover()
        operations = self.store.read_operations_readiness_report()
        profile = build_operations_profile(output_dir=self.output_dir)
        startup_command = (
            operations.startup_command
            if operations is not None
            else profile.startup_command
        )
        dashboard_url = (
            operations.dashboard_url
            if operations is not None
            else profile.dashboard_url
        )
        runtime_snapshot = _read_runtime_snapshot(self.store)
        actions = tuple(result.request.action for result in recovered.control_results)
        checks = (
            _check(
                "operations_readiness",
                operations is not None and operations.passed,
                "Operations-readiness evidence passed before lifecycle drill.",
                "Operations-readiness evidence is missing or failed.",
                (
                    f"status={operations.status.value}"
                    if operations is not None
                    else "status=missing",
                    f"dashboard_url={dashboard_url}",
                ),
            ),
            _check(
                "startup_command_documented",
                "python -m trading_app.runtime.run_alpaca_paper" in startup_command
                and "--monitor-only-dry-run-first" in startup_command,
                "The documented startup command is the supervised paper runtime.",
                "The startup command is missing the supervised paper-runtime entry.",
                (f"startup_command={startup_command}",),
            ),
            _check(
                "dashboard_local_only",
                _dashboard_is_local(dashboard_url),
                "Dashboard URL is local-only.",
                "Dashboard URL is not local-only.",
                (f"dashboard_url={dashboard_url}",),
            ),
            _check(
                "runtime_start_evidence",
                recovered.last_cycle is not None or runtime_snapshot is not None,
                "Persisted runtime cycle or snapshot evidence exists.",
                "No persisted runtime cycle or snapshot evidence exists.",
                (
                    f"last_cycle={recovered.last_cycle is not None}",
                    f"runtime_snapshot={runtime_snapshot is not None}",
                ),
            ),
            _check(
                "operator_controls_exercised",
                all(action in actions for action in _REQUIRED_CONTROL_ACTIONS),
                "All required operator controls were exercised and persisted.",
                "One or more required operator controls were not exercised.",
                (
                    "required="
                    f"{_join(action.value for action in _REQUIRED_CONTROL_ACTIONS)}",
                    f"observed={_join(action.value for action in actions)}",
                ),
            ),
            _check(
                "control_state_recovered",
                _control_state_recovered(
                    recovered.control_results, recovered.control_state
                ),
                "Latest operator control state can be recovered from persistence.",
                "Latest operator control state is missing or inconsistent.",
                (
                    f"control_results={len(recovered.control_results)}",
                    f"control_state={recovered.control_state is not None}",
                ),
            ),
            _check(
                "emergency_stop_controls_exercised",
                OperatorControlAction.PAUSE_RUNTIME in actions
                and OperatorControlAction.ENABLE_PAPER_KILL_SWITCH in actions,
                "Emergency-stop controls were exercised.",
                "Emergency-stop controls were not exercised.",
                (
                    f"pause={OperatorControlAction.PAUSE_RUNTIME in actions}",
                    (
                        "kill_switch="
                        f"{OperatorControlAction.ENABLE_PAPER_KILL_SWITCH in actions}"
                    ),
                ),
            ),
            _check(
                "force_reconciliation_and_report_effects",
                _control_effects_present(self.store, actions),
                "Force-reconciliation and report controls produced persisted evidence.",
                "Force-reconciliation or report control evidence is missing.",
                (
                    f"reconciliation={_reconciliation_exists(self.store)}",
                    f"daily_report={_daily_report_exists(self.store)}",
                ),
            ),
            _check(
                "shutdown_procedure_documented",
                _shutdown_procedure_documented(self.working_dir),
                "Shutdown and emergency-stop procedures are documented.",
                "Shutdown or emergency-stop procedures are not documented.",
                (f"runbook={self.working_dir / 'PAPER_RUNTIME_OPERATOR_RUNBOOK.md'}",),
            ),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeLifecycleDrillReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            startup_command=startup_command,
            dashboard_url=dashboard_url,
            checks=checks,
            persisted_control_actions=actions,
            operator_control_count=len(actions),
            emergency_stop_confirmed=(
                OperatorControlAction.PAUSE_RUNTIME in actions
                and OperatorControlAction.ENABLE_PAPER_KILL_SWITCH in actions
            ),
            shutdown_procedure_documented=_shutdown_procedure_documented(
                self.working_dir
            ),
            summary=_summary(status, failures, len(actions)),
        )
        if self.persist_report:
            markdown_path = write_lifecycle_drill_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_lifecycle_drill_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_lifecycle_drill_text(report: RuntimeLifecycleDrillReport) -> str:
    """Render compact lifecycle drill status."""

    lines = [
        f"Lifecycle drill status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_lifecycle_drill_markdown(report: RuntimeLifecycleDrillReport) -> str:
    """Render lifecycle drill Markdown."""

    lines = [
        "# Paper Runtime Lifecycle Drill",
        "",
        "> Paper trading only. This drill does not authorize live-money trading.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Dashboard URL: `{report.dashboard_url}`",
        f"- Operator controls recorded: `{report.operator_control_count}`",
        f"- Emergency stop confirmed: `{_yes_no(report.emergency_stop_confirmed)}`",
        (
            "- Shutdown procedure documented: "
            f"`{_yes_no(report.shutdown_procedure_documented)}`"
        ),
        "",
        report.summary,
        "",
        "## Startup Command",
        "",
        "```bash",
        report.startup_command,
        "```",
        "",
        "## Persisted Operator Actions",
        "",
        ", ".join(action.value for action in report.persisted_control_actions)
        or "No operator control actions were recorded.",
        "",
        "## Checks",
        "",
        "| Check | Status | Message | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        evidence = "<br>".join(check.evidence) if check.evidence else "No evidence"
        lines.append(
            "| "
            f"{_escape_table(check.name)} | "
            f"{check.status.value} | "
            f"{_escape_table(check.message)} | "
            f"{_escape_table(evidence)} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_lifecycle_drill_markdown_report(
    report: RuntimeLifecycleDrillReport,
    reports_dir: Path | str,
) -> Path:
    """Write lifecycle drill Markdown and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"lifecycle-drill-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_lifecycle_drill_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit paper-runtime startup, shutdown, and control drills."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--working-dir", default=".")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeLifecycleDrillAuditor(
        output_dir=args.output_dir,
        working_dir=args.working_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json() if args.json else render_lifecycle_drill_text(report)
    )
    return 0 if report.passed else 1


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeLifecycleDrillCheck:
    return RuntimeLifecycleDrillCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _read_runtime_snapshot(store: RuntimePersistenceStore) -> RuntimeSnapshot | None:
    path = store.state_dir / "latest-runtime-snapshot.json"
    if not path.exists():
        return None
    return RuntimeSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _dashboard_is_local(url: str) -> bool:
    return (
        url.startswith("http://127.0.0.1:")
        or url.startswith("http://localhost:")
        or url.startswith("http://[::1]:")
        or url.startswith("http://::1:")
    )


def _control_state_recovered(control_results, control_state) -> bool:
    if not control_results or control_state is None:
        return False
    return control_results[-1].control_state == control_state


def _control_effects_present(
    store: RuntimePersistenceStore,
    actions: tuple[OperatorControlAction, ...],
) -> bool:
    reconciliation_required = OperatorControlAction.FORCE_RECONCILIATION in actions
    report_required = OperatorControlAction.GENERATE_REPORT in actions
    return (not reconciliation_required or _reconciliation_exists(store)) and (
        not report_required or _daily_report_exists(store)
    )


def _reconciliation_exists(store: RuntimePersistenceStore) -> bool:
    return (store.state_dir / "latest-reconciliation.json").exists()


def _daily_report_exists(store: RuntimePersistenceStore) -> bool:
    recovered = store.recover()
    return (
        recovered.daily_report is not None
        and recovered.daily_report_path is not None
        and recovered.daily_report_path.exists()
    )


def _shutdown_procedure_documented(working_dir: Path) -> bool:
    runbook_path = working_dir / "PAPER_RUNTIME_OPERATOR_RUNBOOK.md"
    if not runbook_path.exists():
        return False
    text = runbook_path.read_text(encoding="utf-8").casefold()
    return all(
        phrase in text
        for phrase in (
            "shutdown",
            "ctrl+c",
            "emergency stop",
            "paper kill switch",
            "post-run review",
        )
    )


def _summary(
    status: RuntimePreflightStatus,
    failures: int,
    control_count: int,
) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return (
            "Lifecycle drill passed; startup, shutdown, emergency-stop, and "
            f"{control_count} operator control action(s) have reviewable evidence."
        )
    return (
        f"Lifecycle drill found {failures} failed check(s). Exercise the local "
        "startup, shutdown, emergency-stop, and dashboard control flow before "
        "operator signoff."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _join(values) -> str:
    values = tuple(values)
    return ", ".join(str(value) for value in values) if values else "none"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
