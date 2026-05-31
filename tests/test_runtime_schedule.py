from __future__ import annotations

from pathlib import Path

from trading_app.runtime import (
    RuntimePreflightStatus,
    RuntimeScheduleGuardrailAuditor,
    render_schedule_guardrail_markdown,
    render_schedule_guardrail_text,
)
from trading_app.runtime.schedule import main as schedule_main


def test_schedule_guardrail_audit_passes_and_persists(tmp_path) -> None:
    report = RuntimeScheduleGuardrailAuditor(output_dir=tmp_path).audit()
    text = render_schedule_guardrail_text(report)
    markdown = render_schedule_guardrail_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.approved_schedule_scenarios == 1
    assert report.protected_schedule_scenarios == 4
    assert report.unexpected_schedule_scenarios == 0
    assert {check.name for check in report.checks} == {
        "regular_hours_monitor_only",
        "pre_trade_window_monitor_only",
        "daily_close_evaluates",
        "same_day_repeat_blocks",
        "weekend_blocks_strategy",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Schedule guardrail status" in text
    assert "Paper Runtime Schedule Guardrail Audit" in markdown
    assert (tmp_path / "state" / "latest-schedule-guardrail-report.json").exists()
    assert (tmp_path / "journal" / "schedule-guardrails.jsonl").exists()


def test_schedule_guardrail_cli_outputs_json_and_exit_code(tmp_path, capsys) -> None:
    status = schedule_main(["--output-dir", str(tmp_path), "--json"])
    output = capsys.readouterr().out

    assert status == 0
    assert '"passed":true' in output
    assert '"protected_schedule_scenarios":4' in output
