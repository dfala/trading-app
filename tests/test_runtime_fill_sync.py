from __future__ import annotations

from pathlib import Path

from trading_app.runtime import (
    RuntimeFillSyncAuditor,
    RuntimePreflightStatus,
    render_fill_sync_markdown,
    render_fill_sync_text,
)
from trading_app.runtime.fills import main as fills_main


def test_fill_sync_audit_passes_and_persists(tmp_path) -> None:
    report = RuntimeFillSyncAuditor(output_dir=tmp_path).audit()
    text = render_fill_sync_text(report)
    markdown = render_fill_sync_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.incremental_fill_scenarios == 2
    assert report.duplicate_fill_scenarios == 2
    assert report.unexpected_fill_scenarios == 0
    assert {check.name for check in report.checks} == {
        "first_incremental_fill_applies_once",
        "repeat_sync_does_not_duplicate_fill",
        "second_incremental_fill_applies_once",
        "restart_sync_does_not_duplicate_fill",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Fill sync status" in text
    assert "Paper Runtime Fill Sync Audit" in markdown
    assert (tmp_path / "state" / "latest-fill-sync-report.json").exists()
    assert (tmp_path / "journal" / "fill-sync.jsonl").exists()


def test_fill_sync_cli_outputs_json_and_exit_code(tmp_path, capsys) -> None:
    status = fills_main(["--output-dir", str(tmp_path), "--json"])
    output = capsys.readouterr().out

    assert status == 0
    assert '"passed":true' in output
    assert '"incremental_fill_scenarios":2' in output
