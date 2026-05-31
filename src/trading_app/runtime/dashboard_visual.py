"""Rendered dashboard readiness audit for paper-runtime operator review."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.render import render_interactive_dashboard_html
from trading_app.runtime.models import (
    RuntimeDashboardVisualCheck,
    RuntimeDashboardVisualReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

_CRITICAL_CHECKS = {
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


class RuntimeDashboardVisualAuditor:
    """Audit rendered dashboard HTML for operator-critical surfaces."""

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
        html = render_interactive_dashboard_html(snapshot) if snapshot else ""
        checks = tuple(_checks(snapshot, html))
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
            html_path = _write_dashboard_html(html, self.output_dir / "dashboard", now)
            report = report.model_copy(update={"rendered_html_path": str(html_path)})
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
        f"Rendered HTML: {report.rendered_html_path or 'not written'}",
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
            "dashboard shell for critical paper-runtime surfaces."
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Rendered HTML: `{report.rendered_html_path or 'not written'}`",
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
        description="Audit rendered dashboard visual readiness."
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
    html: str,
) -> list[RuntimeDashboardVisualCheck]:
    if snapshot is None:
        return [
            _check(
                "dashboard_snapshot_present",
                False,
                "Dashboard snapshot is available for visual audit.",
                "Dashboard snapshot is missing; rendered dashboard cannot be audited.",
                ("state/latest-dashboard-snapshot.json=missing",),
            )
        ]

    return [
        _contains_check(
            "html_document_rendered",
            html,
            (
                "<!doctype html>",
                "<html",
                "<style>",
                "<script>",
                "Trading Lab Operator Dashboard",
            ),
            "Interactive dashboard HTML rendered.",
            "Interactive dashboard HTML is incomplete.",
        ),
        _contains_check(
            "paper_boundary_visible",
            html,
            (
                "Alpaca Paper",
                "Paper Boundary",
                "Live disabled",
                "Paper only",
                "$0 real capital",
                "No live-money actions are available",
            ),
            "Paper/live boundary is visible in the first operator surface.",
            "Paper/live boundary is not explicit enough in rendered HTML.",
        ),
        _contains_check(
            "critical_runtime_surfaces_present",
            html,
            (
                "Latest Prices",
                "Broker connection",
                "Cash",
                "Positions",
                "Open orders",
                "Recent Fills",
                "Risk State",
                "Reconciliation",
                "Daily Report",
                "Nightly Learning",
                "Runtime Proof",
                "Final Acceptance",
                "Statement Review",
            ),
            (
                "Critical runtime, broker, portfolio, report, and learning "
                "surfaces render."
            ),
            "One or more critical runtime surfaces are missing.",
        ),
        _contains_check(
            "operator_controls_present",
            html,
            (
                "Operator Controls",
                'data-control-action="resume_runtime"',
                'data-control-action="pause_runtime"',
                'data-control-action="enable_paper_kill_switch"',
                'data-control-action="force_reconciliation"',
                'data-control-action="generate_report"',
                "fetch('/api/control'",
            ),
            "Local operator controls are rendered and wired to the control API.",
            "Operator controls are missing or not wired in rendered HTML.",
        ),
        _alerts_check(snapshot, html),
        _contains_check(
            "data_quality_panel_present",
            html,
            (
                "Data Quality Evidence",
                'data-field="data-quality-status"',
                'data-field="data-quality-research-usable"',
                'data-field="data-quality-trading-usable"',
                "Quality Issues",
                "IEX/free data is development-grade",
            ),
            "Market-data quality and provenance are visible.",
            "Market-data quality evidence is missing from rendered HTML.",
        ),
        _contains_check(
            "active_model_explanation_present",
            html,
            (
                "Active Model",
                'data-field="active-strategy-name"',
                'data-field="active-strategy-hypothesis"',
                'data-field="active-strategy-id"',
                "Known Failure Modes",
                "AI Role",
                "Daily close only",
            ),
            "Active model explanation and authority are visible.",
            "Active model explanation is missing from rendered HTML.",
        ),
        _contains_check(
            "live_readiness_gated",
            html,
            (
                "Live Readiness",
                'data-field="live-readiness-panel-status"',
                "Live disabled",
                "No margin, shorts, options",
                "No live-money actions are available",
            ),
            "Live readiness remains visible and gated.",
            "Live-readiness gating is not obvious in rendered HTML.",
        ),
        _contains_check(
            "responsive_css_present",
            html,
            (
                '<meta name="viewport"',
                "display: grid",
                "display: flex",
                "grid-template-columns",
                "@media (max-width: 940px)",
            ),
            "Responsive desktop/mobile layout rules are present.",
            "Responsive layout rules are missing from rendered HTML.",
        ),
        _contains_check(
            "financial_visuals_present",
            html,
            (
                "hero__chart",
                "area-chart",
                "bar-compare",
                "<svg",
                "Model Arena",
            ),
            "Financial visuals and model comparison elements are rendered.",
            "Financial visual elements are missing from rendered HTML.",
            minimum_svg_count=2,
        ),
        _contains_check(
            "visual_system_tokens_present",
            html,
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
            "Operator-dashboard visual system tokens are present.",
            "Expected dashboard visual-system tokens are missing.",
        ),
    ]


def _alerts_check(
    snapshot: OperatorDashboardSnapshot,
    html: str,
) -> RuntimeDashboardVisualCheck:
    required = [
        "Runtime Alerts",
        "data-alert-list",
        "Runtime Health",
        "Incident Command",
        "row--danger",
        "row--warn",
    ]
    required.extend(_field(alert, "title", "") for alert in snapshot.alerts)
    if snapshot.health_report is not None:
        required.append(_enum_value(_field(snapshot.health_report, "status"), ""))
    missing = tuple(value for value in required if value not in html)
    return _check(
        "alerts_and_degraded_states_visible",
        not missing,
        "Alerts, incidents, and degraded-state styling are visible.",
        "Alerts or degraded-state indicators are missing from rendered HTML.",
        _evidence(required, missing),
    )


def _contains_check(
    name: str,
    html: str,
    required: tuple[str, ...],
    passed_message: str,
    failed_message: str,
    *,
    minimum_svg_count: int = 0,
) -> RuntimeDashboardVisualCheck:
    missing = [value for value in required if value not in html]
    if minimum_svg_count and html.count("<svg") < minimum_svg_count:
        missing.append(f"<svg count>={minimum_svg_count}")
    return _check(
        name,
        not missing,
        passed_message,
        failed_message,
        _evidence(required, tuple(missing)),
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


def _enum_value(value, fallback: str) -> str:
    return getattr(value, "value", value) if value is not None else fallback


def _write_dashboard_html(html: str, dashboard_dir: Path, as_of: datetime) -> Path:
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    path = dashboard_dir / f"dashboard-visual-{_timestamp_id(as_of)}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _summary(status: RuntimePreflightStatus, failures: int, total: int) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return (
            f"Rendered dashboard visual audit passed across {total} operator "
            "surface check(s)."
        )
    return (
        f"Rendered dashboard visual audit found {failures} failed check(s). "
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
