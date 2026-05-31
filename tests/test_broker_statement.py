from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trading_app.broker import (
    BrokerPositionState,
    BrokerStatementSnapshot,
    InMemoryPaperBrokerAdapter,
    ReconciliationIssueType,
)
from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.paper import (
    capture_broker_statement_snapshot,
    load_broker_statement,
    load_broker_statement_csv,
    load_broker_statement_json,
    reconcile_statement_snapshot,
    render_statement_reconciliation_markdown,
    write_broker_statement_json,
    write_statement_reconciliation_markdown,
)
from trading_app.paper.capture_statement import main as capture_statement_main
from trading_app.paper.reconcile_statement import main as reconcile_statement_main
from trading_app.runtime import RuntimePersistenceStore, RuntimeSnapshot, RuntimeStatus
from trading_app.schemas import Order, OrderSide, OrderType, PortfolioSnapshot

NOW = datetime(2026, 5, 29, 16, tzinfo=UTC)


def test_load_broker_statement_json_validates_snapshot(tmp_path) -> None:
    statement = _statement(cash=Decimal("7500"))
    path = tmp_path / "statement.json"
    path.write_text(statement.model_dump_json(), encoding="utf-8")

    loaded = load_broker_statement_json(path)

    assert loaded.statement_id == "statement-2026-05-29"
    assert loaded.positions[0].symbol == "SPY"
    assert loaded.model_dump(mode="json")["cash"] == "7500"


def test_load_broker_statement_csv_parses_account_and_positions(tmp_path) -> None:
    path = tmp_path / "statement.csv"
    path.write_text(_statement_csv(cash="7500", quantity="5"), encoding="utf-8")

    statement = load_broker_statement_csv(path)

    assert statement.statement_id == "statement-2026-05-29"
    assert statement.provider == "alpaca-paper"
    assert statement.cash == Decimal("7500")
    assert statement.positions[0].quantity == Decimal("5")
    assert statement.positions[0].average_entry_price == Decimal("500")
    assert statement.metadata["statement_file"] == str(path)


def test_load_broker_statement_rejects_unsupported_extensions(tmp_path) -> None:
    path = tmp_path / "statement.txt"
    path.write_text("not a statement", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported broker statement"):
        load_broker_statement(path)


def test_render_statement_reconciliation_markdown_includes_caveats(tmp_path) -> None:
    ledger = _ledger_snapshot(cash=Decimal("7500"), quantity=Decimal("5"))
    report = reconcile_statement_snapshot(
        ledger,
        _statement(cash=Decimal("7501"), quantity=Decimal("4")),
        as_of=NOW,
        statement_path=tmp_path / "statement-source.json",
    )

    markdown = render_statement_reconciliation_markdown(report)
    path = write_statement_reconciliation_markdown(report, tmp_path)

    assert not report.reconciled
    assert {issue.issue_type for issue in report.issues} == {
        ReconciliationIssueType.CASH_MISMATCH,
        ReconciliationIssueType.POSITION_QUANTITY_MISMATCH,
    }
    assert "Paper/research-only accounting review" in markdown
    assert "Statement source file" in markdown
    assert report.statement_path == str(tmp_path / "statement-source.json")
    assert "Cash Mismatch" in markdown
    assert "Position Quantity Mismatch" in markdown
    assert path.exists()
    assert "not filing-grade tax accounting" in path.read_text(encoding="utf-8")


def test_capture_broker_statement_snapshot_from_paper_broker(tmp_path) -> None:
    broker = _filled_broker()

    statement = capture_broker_statement_snapshot(
        broker,
        as_of=NOW,
        statement_id="captured-statement",
    )
    path = write_broker_statement_json(statement, tmp_path)
    loaded = load_broker_statement_json(path)

    assert statement.statement_id == "captured-statement"
    assert statement.provider == "memory-paper"
    assert statement.cash == Decimal("7500")
    assert statement.positions[0].symbol == "SPY"
    assert statement.positions[0].quantity == Decimal("5")
    assert statement.positions[0].average_entry_price == Decimal("500")
    assert statement.source == "memory-paper:paper-portfolio-capture"
    assert loaded == statement
    assert path.name == "broker-statement-captured-statement.json"


def test_capture_statement_cli_writes_json_snapshot(tmp_path, capsys) -> None:
    broker = _filled_broker()

    exit_code = capture_statement_main(
        [
            "--output-dir",
            str(tmp_path),
            "--statement-id",
            "cli-captured-statement",
            "--json",
        ],
        broker_factory=lambda: broker,
        clock=lambda: NOW,
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"statement_id":"cli-captured-statement"' in output
    assert "ALPACA_SECRET_KEY" not in output
    assert (tmp_path / "broker-statement-cli-captured-statement.json").exists()


def test_reconcile_statement_cli_reports_clean_runtime_snapshot(
    tmp_path,
    capsys,
) -> None:
    _persist_demo_runtime_snapshot(tmp_path)
    statement_path = tmp_path / "statement.csv"
    statement_path.write_text(
        _statement_csv(cash="7500", quantity="5"), encoding="utf-8"
    )

    exit_code = reconcile_statement_main(
        [
            "--runtime-dir",
            str(tmp_path),
            "--statement",
            str(statement_path),
        ]
    )
    output = capsys.readouterr().out
    report_path = (
        tmp_path / "reports" / "statement-reconciliation-statement-2026-05-29.md"
    )

    assert exit_code == 0
    assert "status: reconciled" in output
    assert report_path.exists()
    recovered = RuntimePersistenceStore(tmp_path).recover()
    assert recovered.statement_reconciliation is not None
    assert recovered.statement_reconciliation.reconciled
    assert recovered.statement_reconciliation.statement_path == str(statement_path)
    assert (
        recovered.statement_reconciliation.statement_sha256
        == hashlib.sha256(statement_path.read_bytes()).hexdigest()
    )
    assert recovered.statement_reconciliation_path == report_path
    assert (tmp_path / "journal" / "statement-reconciliation.jsonl").exists()


def test_reconcile_statement_cli_returns_nonzero_for_mismatches(
    tmp_path,
    capsys,
) -> None:
    _persist_demo_runtime_snapshot(tmp_path)
    statement_path = tmp_path / "statement.csv"
    statement_path.write_text(
        _statement_csv(cash="7501", quantity="4"), encoding="utf-8"
    )

    exit_code = reconcile_statement_main(
        [
            "--runtime-dir",
            str(tmp_path),
            "--statement",
            str(statement_path),
            "--json",
        ]
    )
    output = capsys.readouterr().out
    report_path = (
        tmp_path / "reports" / "statement-reconciliation-statement-2026-05-29.md"
    )

    assert exit_code == 1
    assert '"reconciled":false' in output
    assert '"CASH_MISMATCH"' in output
    assert report_path.exists()
    assert "Cash Mismatch" in report_path.read_text(encoding="utf-8")
    recovered = RuntimePersistenceStore(tmp_path).recover()
    assert recovered.statement_reconciliation is not None
    assert not recovered.statement_reconciliation.reconciled


def _statement(
    *,
    cash: Decimal,
    quantity: Decimal = Decimal("5"),
) -> BrokerStatementSnapshot:
    return BrokerStatementSnapshot(
        statement_id="statement-2026-05-29",
        as_of=NOW,
        provider="alpaca-paper",
        account_id="paper-account-1",
        cash=cash,
        positions=(
            BrokerPositionState(
                symbol="SPY",
                quantity=quantity,
                average_entry_price=Decimal("500"),
                market_value=quantity * Decimal("500"),
                current_price=Decimal("500"),
            ),
        ),
        source="manual-statement-export",
    )


def _ledger_snapshot(*, cash: Decimal, quantity: Decimal) -> PortfolioSnapshot:
    demo = build_demo_dashboard_snapshot()
    position = demo.paper_report.ledger_snapshot.positions[0].model_copy(
        update={"quantity": quantity}
    )
    return demo.paper_report.ledger_snapshot.model_copy(
        update={"cash": cash, "positions": (position,)}
    )


def _persist_demo_runtime_snapshot(tmp_path) -> None:
    demo = build_demo_dashboard_snapshot()
    snapshot = RuntimeSnapshot(
        as_of=NOW,
        status=RuntimeStatus.RUNNING,
        mode="Alpaca Paper",
        paper_report=demo.paper_report,
        active_model_key="monthly_sector_momentum:1.0.0",
    )
    RuntimePersistenceStore(tmp_path).persist_runtime_snapshot(snapshot)


def _filled_broker() -> InMemoryPaperBrokerAdapter:
    broker = InMemoryPaperBrokerAdapter(starting_cash=Decimal("10000"))
    order = Order(
        id="capture-order-1",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("5"),
        created_at=NOW,
    )
    broker.submit_order(order)
    broker.fill_order(order.id, price=Decimal("500"), filled_at=NOW)
    return broker


def _statement_csv(*, cash: str, quantity: str) -> str:
    market_value = Decimal(quantity) * Decimal("500")
    return "\n".join(
        [
            (
                "record_type,statement_id,as_of,provider,account_id,cash,source,"
                "symbol,quantity,average_entry_price,market_value,current_price"
            ),
            (
                "account,statement-2026-05-29,2026-05-29T16:00:00+00:00,"
                f"alpaca-paper,paper-account-1,{cash},manual-statement-export,,,,,"
            ),
            f"position,,,,,,,SPY,{quantity},500,{market_value},500",
            "",
        ]
    )
