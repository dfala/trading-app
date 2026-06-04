from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.runtime import (
    RuntimeDashboardVisualAuditor,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_dashboard_visual_markdown,
    render_dashboard_visual_text,
)
from trading_app.runtime.dashboard_visual import main as dashboard_visual_main

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_dashboard_visual_audit_passes_with_rendered_operator_surfaces(
    tmp_path,
) -> None:
    store = RuntimePersistenceStore(tmp_path)
    store.persist_dashboard_snapshot(
        build_demo_dashboard_snapshot().model_copy(
            update={
                "generated_at": NOW,
                "mode": "Alpaca Paper",
                "broker": "alpaca-paper",
            }
        )
    )

    report = RuntimeDashboardVisualAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_dashboard_visual_text(report)
    markdown = render_dashboard_visual_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.critical_surface_count >= 7
    assert report.responsive_surface_count >= 3
    assert report.failed_visual_scenarios == 0
    assert {check.name for check in report.checks}.issuperset(
        {
            "paper_boundary_visible",
            "next_dashboard_handoff_configured",
            "critical_runtime_surfaces_present",
            "operator_controls_present",
            "alerts_and_degraded_states_visible",
            "data_quality_panel_present",
            "active_model_explanation_present",
            "responsive_css_present",
            "financial_visuals_present",
            "visual_system_tokens_present",
            "live_readiness_gated",
        }
    )
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert report.rendered_html_path is None
    assert "Dashboard visual status" in text
    assert "Dashboard Visual Readiness Audit" in markdown
    assert "Next.js owns dashboard rendering" in text
    assert (tmp_path / "state" / "latest-dashboard-visual-report.json").exists()
    assert (tmp_path / "journal" / "dashboard-visual.jsonl").exists()


def test_dashboard_visual_audit_fails_when_snapshot_is_missing(tmp_path) -> None:
    report = RuntimeDashboardVisualAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.failed_visual_scenarios == 1
    assert by_name["dashboard_snapshot_present"].status == RuntimePreflightStatus.FAILED
    assert report.rendered_html_path is None


def test_dashboard_visual_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    RuntimePersistenceStore(success_dir).persist_dashboard_snapshot(
        build_demo_dashboard_snapshot().model_copy(
            update={"mode": "Alpaca Paper", "broker": "alpaca-paper"}
        )
    )

    success = dashboard_visual_main(["--output-dir", str(success_dir), "--json"])
    failure = dashboard_visual_main(["--output-dir", str(failure_dir), "--json"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output
