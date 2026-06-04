"""Next dashboard readiness audit for paper-runtime operator review."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.runtime.models import (
    RuntimeDashboardVisualCheck,
    RuntimeDashboardVisualReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

_CRITICAL_CHECKS = {
    "next_dashboard_handoff_configured",
    "paper_boundary_visible",
    "critical_runtime_surfaces_present",
    "operator_controls_present",
    "alerts_and_degraded_states_visible",
    "data_quality_panel_present",
    "active_model_explanation_present",
    "live_readiness_gated",
}

_RESPONSIVE_CHECKS = {
    "responsive_css_present",
    "financial_visuals_present",
    "visual_system_tokens_present",
}
_NEXT_SOURCE_PATHS = (
    Path("web/app/page.tsx"),
    Path("web/components/dashboard-client.tsx"),
    Path("web/app/globals.css"),
)


class RuntimeDashboardVisualAuditor:
    """Audit the Next dashboard handoff and operator-critical surfaces."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        persistence_store: RuntimePersistenceStore | None = None,
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.persist_report = persist_report

    def audit(self, *, as_of: datetime | None = None) -> RuntimeDashboardVisualReport:
        now = as_of or datetime.now(tz=UTC)
        snapshot = self.store.recover().dashboard_snapshot
        next_source = _read_next_source()
        checks = tuple(_checks(snapshot, next_source))
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeDashboardVisualReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            checks=checks,
            critical_surface_count=sum(
                1
                for check in checks
                if check.name in _CRITICAL_CHECKS
                and check.status == RuntimePreflightStatus.PASSED
            ),
            responsive_surface_count=sum(
                1
                for check in checks
                if check.name in _RESPONSIVE_CHECKS
                and check.status == RuntimePreflightStatus.PASSED
            ),
            failed_visual_scenarios=failures,
            summary=_summary(status, failures, len(checks)),
        )
        if self.persist_report:
            markdown_path = write_dashboard_visual_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_dashboard_visual_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_dashboard_visual_text(report: RuntimeDashboardVisualReport) -> str:
    """Render compact dashboard visual audit status."""

    lines = [
        f"Dashboard visual status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        "Rendered HTML: not written; Next.js owns dashboard rendering",
        f"Markdown report: {report.markdown_path or 'not written'}",
        f"Critical surfaces passed: {report.critical_surface_count}",
        f"Responsive surfaces passed: {report.responsive_surface_count}",
        f"Failed visual scenarios: {report.failed_visual_scenarios}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_dashboard_visual_markdown(report: RuntimeDashboardVisualReport) -> str:
    """Render dashboard visual audit Markdown."""

    lines = [
        "# Dashboard Visual Readiness Audit",
        "",
        (
            "> Paper trading only. This audit inspects the rendered operator "
            "dashboard handoff, persisted snapshot, and Next.js source markers "
            "for critical paper-runtime surfaces."
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        "- Rendered HTML: `not written; Next.js owns dashboard rendering`",
        f"- Critical surfaces passed: `{report.critical_surface_count}`",
        f"- Responsive surfaces passed: `{report.responsive_surface_count}`",
        f"- Failed visual scenarios: `{report.failed_visual_scenarios}`",
        "",
        report.summary,
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


def write_dashboard_visual_markdown_report(
    report: RuntimeDashboardVisualReport,
    reports_dir: Path | str,
) -> Path:
    """Write dashboard visual audit Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"dashboard-visual-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_dashboard_visual_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Next dashboard visual readiness."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeDashboardVisualAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json() if args.json else render_dashboard_visual_text(report)
    )
    return 0 if report.passed else 1


def _checks(
    snapshot: OperatorDashboardSnapshot | None,
    next_source: str,
) -> list[RuntimeDashboardVisualCheck]:
    if snapshot is None:
        return [
            _check(
                "dashboard_snapshot_present",
                False,
                "Dashboard snapshot is available for visual audit.",
                "Dashboard snapshot is missing; Next dashboard cannot be audited.",
                ("state/latest-dashboard-snapshot.json=missing",),
            )
        ]

    return [
        _snapshot_check(
            "next_dashboard_handoff_configured",
            snapshot,
            (
                ("mode", "Alpaca Paper"),
                ("broker", "paper-provider"),
            ),
            "Python backend exposes an Alpaca Paper snapshot for the Next dashboard.",
            "Python backend snapshot is not ready for the Next dashboard.",
        ),
        _snapshot_check(
            "paper_boundary_visible",
            snapshot,
            (
                ("mode", "Alpaca Paper"),
                ("broker", "paper-provider"),
                ("live_readiness", "present"),
            ),
            "Paper/live boundary data is present for the operator surface.",
            "Paper/live boundary data is not explicit enough.",
        ),
        _snapshot_surface_check(
            "critical_runtime_surfaces_present",
            snapshot,
            (
                "latest_prices",
                "cash",
                "estimated_equity",
                "open_orders",
                "paper_report",
                "daily_report",
                "nightly_learning",
                "runtime_state",
            ),
            (
                "Critical runtime, broker, portfolio, report, and learning "
                "surfaces are present in the dashboard snapshot."
            ),
            "One or more critical runtime surfaces are missing from the snapshot.",
        ),
        _next_source_check(
            "operator_controls_present",
            next_source,
            (
                "resume_runtime",
                "pause_runtime",
                "enable_paper_kill_switch",
                "force_reconciliation",
                "generate_report",
                "/api/control",
            ),
            "Next operator controls are present and wired to the control API.",
            "Next operator controls are missing or not wired.",
        ),
        _alerts_check(snapshot),
        _snapshot_surface_check(
            "data_quality_panel_present",
            snapshot,
            ("daily_report.data_quality_report",),
            "Market-data quality and provenance are present in the snapshot.",
            "Market-data quality evidence is missing from the snapshot.",
        ),
        _snapshot_surface_check(
            "active_model_explanation_present",
            snapshot,
            (
                "active_strategy_definition",
                "active_strategy_definition.hypothesis",
                "active_strategy_definition.failure_modes",
                "active_strategy_definition.ai_role",
                "active_strategy_definition.authority",
            ),
            "Active model explanation and authority are present in the snapshot.",
            "Active model explanation is missing from the snapshot.",
        ),
        _snapshot_surface_check(
            "live_readiness_gated",
            snapshot,
            (
                "live_readiness",
                "live_readiness.status",
            ),
            "Live readiness remains visible and gated in the snapshot.",
            "Live-readiness gating is missing from the snapshot.",
        ),
        _next_source_check(
            "responsive_css_present",
            next_source,
            (
                "display: grid",
                "display: flex",
                "grid-template-columns",
                "@media (max-width: 940px)",
            ),
            "Responsive desktop/mobile layout rules are present in Next CSS.",
            "Responsive layout rules are missing from Next CSS.",
        ),
        _next_source_check(
            "financial_visuals_present",
            next_source,
            (
                "hero-chart",
                "replay-scoreboard",
                "model_arena",
                "Model Arena",
            ),
            "Financial visuals and model comparison elements are present in Next.",
            "Financial visual elements are missing from Next.",
        ),
        _next_source_check(
            "visual_system_tokens_present",
            next_source,
            (
                "--canvas: #07090c",
                "--pos: #2bd576",
                "--ai: #5ee3ff",
                "--warn: #f4b740",
                "--neg: #ff4d5e",
                "pill--danger",
                "pill--warn",
                "pill--good",
            ),
            "Operator-dashboard visual system tokens are present in Next CSS.",
            "Expected dashboard visual-system tokens are missing from Next CSS.",
        ),
    ]


def _alerts_check(snapshot: OperatorDashboardSnapshot) -> RuntimeDashboardVisualCheck:
    required = ("alerts", "health_report")
    missing = tuple(value for value in required if not _surface_value(snapshot, value))
    return _check(
        "alerts_and_degraded_states_visible",
        not missing,
        "Alerts, incidents, and degraded-state data are present.",
        "Alerts or degraded-state data are missing from the snapshot.",
        _evidence(required, missing),
    )


def _next_source_check(
    name: str,
    source: str,
    required: tuple[str, ...],
    passed_message: str,
    failed_message: str,
) -> RuntimeDashboardVisualCheck:
    missing = tuple(value for value in required if value not in source)
    return _check(
        name,
        not missing,
        passed_message,
        failed_message,
        _evidence(required, tuple(missing)),
    )


def _snapshot_check(
    name: str,
    snapshot: OperatorDashboardSnapshot,
    required: tuple[tuple[str, str], ...],
    passed_message: str,
    failed_message: str,
) -> RuntimeDashboardVisualCheck:
    missing: list[str] = []
    for path, expected in required:
        value = _surface_value(snapshot, path)
        if expected == "present":
            if value is None:
                missing.append(path)
        elif expected == "paper-provider":
            if not _enum_value(value, "").endswith("paper"):
                missing.append(f"{path}=paper-provider")
        elif _enum_value(value, "") != expected:
            missing.append(f"{path}={expected}")
    return _check(
        name,
        not missing,
        passed_message,
        failed_message,
        _evidence([path for path, _ in required], tuple(missing)),
    )


def _snapshot_surface_check(
    name: str,
    snapshot: OperatorDashboardSnapshot,
    required: tuple[str, ...],
    passed_message: str,
    failed_message: str,
) -> RuntimeDashboardVisualCheck:
    missing = tuple(path for path in required if _surface_value(snapshot, path) is None)
    return _check(
        name,
        not missing,
        passed_message,
        failed_message,
        _evidence(required, missing),
    )


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeDashboardVisualCheck:
    return RuntimeDashboardVisualCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _evidence(required: tuple[str, ...] | list[str], missing: tuple[str, ...]):
    return (
        f"required={len(required)}",
        f"missing={len(missing)}",
        *(f"missing={value}" for value in missing[:6]),
    )


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _surface_value(value, path: str):
    current = value
    for part in path.split("."):
        current = _field(current, part)
        if current is None:
            return None
    return current


def _enum_value(value, fallback: str) -> str:
    return getattr(value, "value", value) if value is not None else fallback


def _read_next_source() -> str:
    parts: list[str] = []
    for path in _NEXT_SOURCE_PATHS:
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(parts)


def _summary(status: RuntimePreflightStatus, failures: int, total: int) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return (
            f"Next dashboard readiness audit passed across {total} operator "
            "surface check(s)."
        )
    return (
        f"Next dashboard readiness audit found {failures} failed check(s). "
        "Do not claim product-grade dashboard readiness yet."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
