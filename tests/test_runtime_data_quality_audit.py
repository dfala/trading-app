from __future__ import annotations

from pathlib import Path

from trading_app.runtime import (
    RuntimeDataQualityAuditor,
    RuntimePreflightStatus,
    render_data_quality_audit_markdown,
    render_data_quality_audit_text,
)
from trading_app.runtime.data_quality import main as data_quality_main


def test_data_quality_audit_passes_and_persists(tmp_path) -> None:
    report = RuntimeDataQualityAuditor(output_dir=tmp_path).audit()
    text = render_data_quality_audit_text(report)
    markdown = render_data_quality_audit_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.latest_price_scenarios == 3
    assert report.daily_bar_scenarios == 3
    assert report.symbol_universe_scenarios == 1
    assert report.failed_quality_scenarios == 0
    assert {check.name for check in report.checks} == {
        "fresh_sip_latest_prices_pass",
        "iex_latest_prices_warn_development_grade",
        "stale_missing_latest_prices_fail",
        "clean_sip_daily_bars_pass",
        "iex_missing_daily_bars_warn",
        "duplicate_mixed_lookahead_daily_bars_fail",
        "invalid_symbol_universe_fail",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Data quality audit status" in text
    assert "Symbol-universe scenarios: 1" in text
    assert "Paper Runtime Data Quality Audit" in markdown
    assert (tmp_path / "state" / "latest-data-quality-audit-report.json").exists()
    assert (tmp_path / "journal" / "data-quality-audits.jsonl").exists()


def test_data_quality_audit_cli_outputs_json_and_exit_code(tmp_path, capsys) -> None:
    status = data_quality_main(["--output-dir", str(tmp_path), "--json"])
    output = capsys.readouterr().out

    assert status == 0
    assert '"passed":true' in output
    assert '"latest_price_scenarios":3' in output
    assert '"symbol_universe_scenarios":1' in output
