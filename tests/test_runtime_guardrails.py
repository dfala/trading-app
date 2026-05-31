from __future__ import annotations

from pathlib import Path

from trading_app.runtime import (
    RuntimeOrderGuardrailAuditor,
    RuntimePreflightStatus,
    render_order_guardrail_markdown,
    render_order_guardrail_text,
)
from trading_app.runtime.guardrails import main as guardrails_main


def test_order_guardrail_audit_passes_and_persists(tmp_path) -> None:
    report = RuntimeOrderGuardrailAuditor(output_dir=tmp_path).audit()
    text = render_order_guardrail_text(report)
    markdown = render_order_guardrail_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.blocked_order_scenarios == 6
    assert report.unexpected_order_scenarios == 0
    assert {check.name for check in report.checks} == {
        "missing_latest_price_blocks_orders",
        "stale_latest_price_blocks_orders",
        "risk_rejection_blocks_orders",
        "dirty_reconciliation_blocks_orders",
        "paper_kill_switch_blocks_orders",
        "operator_pause_blocks_orders",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Order guardrail status" in text
    assert "Paper Runtime Order Guardrail Audit" in markdown
    assert (tmp_path / "state" / "latest-order-guardrail-report.json").exists()
    assert (tmp_path / "journal" / "order-guardrails.jsonl").exists()


def test_order_guardrail_cli_outputs_json_and_exit_code(tmp_path, capsys) -> None:
    status = guardrails_main(["--output-dir", str(tmp_path), "--json"])
    output = capsys.readouterr().out

    assert status == 0
    assert '"passed":true' in output
    assert '"blocked_order_scenarios":6' in output
