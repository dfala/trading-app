from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.broker import BrokerOrderState
from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.runtime import (
    RuntimeBrokerOrderHistoryAuditor,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_broker_order_history_markdown,
    render_broker_order_history_text,
    write_broker_order_history_json,
)
from trading_app.runtime.broker_history import main as broker_history_main
from trading_app.schemas import OrderStatus

NOW = datetime(2026, 5, 29, 21, tzinfo=UTC)


def test_broker_order_history_audit_passes_with_matching_alpaca_history(
    tmp_path,
) -> None:
    store, orders = _persist_order_evidence(tmp_path)
    history_path = write_broker_order_history_json(
        orders,
        tmp_path / "broker-history",
        as_of=NOW,
    )

    report = RuntimeBrokerOrderHistoryAuditor(
        output_dir=tmp_path,
        order_history_path=history_path,
    ).audit(as_of=NOW)
    text = render_broker_order_history_text(report)
    markdown = render_broker_order_history_markdown(report)

    assert store.read_broker_order_history_report() is not None
    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.provider == "alpaca-paper"
    assert report.local_order_count == 1
    assert report.broker_order_count == 1
    assert report.matched_order_count == 1
    assert report.missing_broker_order_ids == ()
    assert report.unexpected_broker_order_ids == ()
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Broker order history status" in text
    assert "Broker Order History Audit" in markdown
    assert (tmp_path / "state" / "latest-broker-order-history-report.json").exists()
    assert (tmp_path / "journal" / "broker-order-history.jsonl").exists()


def test_broker_order_history_audit_fails_mismatched_history(tmp_path) -> None:
    _store, orders = _persist_order_evidence(tmp_path)
    bad_order = orders[0].model_copy(update={"filled_quantity": Decimal("4")})

    report = RuntimeBrokerOrderHistoryAuditor(
        output_dir=tmp_path,
        broker_orders=(bad_order,),
    ).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["broker_filled_quantities_match_ledger_fills"].status == (
        RuntimePreflightStatus.FAILED
    )
    assert any(
        "filled_quantity_mismatch" in item
        for item in by_name["broker_filled_quantities_match_ledger_fills"].evidence
    )


def test_broker_order_history_filters_to_reviewed_session_window(tmp_path) -> None:
    _store, orders = _persist_order_evidence(tmp_path)
    older_order = orders[0].model_copy(
        update={
            "broker_order_id": "older-alpaca-order",
            "client_order_id": "older-paper-order",
            "submitted_at": NOW - timedelta(days=2),
            "updated_at": NOW - timedelta(days=2),
        }
    )

    report = RuntimeBrokerOrderHistoryAuditor(
        output_dir=tmp_path,
        broker_orders=(older_order, *orders),
        session_started_at=NOW - timedelta(hours=8),
        session_completed_at=NOW + timedelta(minutes=5),
        symbols=("SPY",),
    ).audit(as_of=NOW)

    assert report.passed
    assert report.broker_order_count == 1
    assert report.unexpected_broker_order_ids == ()
    assert report.session_started_at == NOW - timedelta(hours=8)
    assert report.session_completed_at == NOW + timedelta(minutes=5)
    assert report.symbols == ("SPY",)


def test_broker_order_history_allows_empty_alpaca_paper_history(tmp_path) -> None:
    report = RuntimeBrokerOrderHistoryAuditor(
        output_dir=tmp_path,
        broker_factory=lambda: _EmptyAlpacaPaperBroker(),
    ).audit(as_of=NOW)

    assert report.passed
    assert report.provider == "alpaca-paper"
    assert report.source == "alpaca-paper"
    assert report.local_order_count == 0
    assert report.broker_order_count == 0
    assert report.matched_order_count == 0


def test_broker_order_history_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    success_dir = tmp_path / "success"
    failure_dir = tmp_path / "failure"
    _store, orders = _persist_order_evidence(success_dir)
    history_path = write_broker_order_history_json(
        orders,
        success_dir / "broker-history",
        as_of=NOW,
    )

    success = broker_history_main(
        ["--output-dir", str(success_dir), "--orders", str(history_path), "--json"]
    )
    failure = broker_history_main(
        [
            "--output-dir",
            str(failure_dir),
            "--orders",
            str(history_path),
            "--json",
            "--no-persist",
        ]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def _persist_order_evidence(
    tmp_path: Path,
) -> tuple[RuntimePersistenceStore, tuple[BrokerOrderState, ...]]:
    store = RuntimePersistenceStore(tmp_path)
    demo = build_demo_dashboard_snapshot()
    paper_report = demo.paper_report
    orders = _broker_history_orders(paper_report)
    for submission in paper_report.submissions:
        if submission.broker_order is None:
            continue
        store.persist_submission(
            submission.model_copy(
                update={
                    "broker_order": submission.broker_order.model_copy(
                        update={"provider": "alpaca-paper"}
                    )
                }
            )
        )
    for fill in paper_report.fills:
        store.persist_fill(fill)
    return store, orders


def _broker_history_orders(paper_report) -> tuple[BrokerOrderState, ...]:
    filled_by_order = {
        fill.order_id: sum(
            item.quantity
            for item in paper_report.fills
            if item.order_id == fill.order_id
        )
        for fill in paper_report.fills
    }
    orders = []
    for submission in paper_report.submissions:
        broker_order = submission.broker_order
        if broker_order is None:
            continue
        filled = filled_by_order.get(submission.order.id, Decimal("0"))
        orders.append(
            broker_order.model_copy(
                update={
                    "provider": "alpaca-paper",
                    "filled_quantity": filled,
                    "status": OrderStatus.FILLED if filled else broker_order.status,
                    "average_fill_price": Decimal("500") if filled else None,
                    "provider_status": "filled"
                    if filled
                    else broker_order.provider_status,
                }
            )
        )
    return tuple(orders)


class _EmptyAlpacaPaperBroker:
    provider = "alpaca-paper"

    def list_orders(self, status=None) -> tuple[BrokerOrderState, ...]:
        return ()
