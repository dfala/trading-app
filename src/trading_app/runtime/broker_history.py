"""Broker order-history audit for Alpaca paper runtime evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from trading_app.broker import PaperBrokerAdapter
from trading_app.broker.models import BrokerOrderState
from trading_app.paper import PaperOrderSubmission
from trading_app.runtime.models import (
    RuntimeBrokerOrderHistoryCheck,
    RuntimeBrokerOrderHistoryReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import Fill, validate_symbol

BrokerFactory = Callable[[], PaperBrokerAdapter]


class RuntimeBrokerOrderHistoryAuditor:
    """Compare persisted paper orders/fills with broker-reported order history."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        persistence_store: RuntimePersistenceStore | None = None,
        broker_factory: BrokerFactory | None = None,
        order_history_path: Path | str | None = None,
        broker_orders: tuple[BrokerOrderState, ...] | None = None,
        session_started_at: datetime | None = None,
        session_completed_at: datetime | None = None,
        symbols: tuple[str, ...] = (),
        limit: int | None = None,
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.broker_factory = broker_factory
        self.order_history_path = (
            Path(order_history_path) if order_history_path else None
        )
        self.broker_orders = broker_orders
        self.session_started_at = session_started_at
        self.session_completed_at = session_completed_at
        self.symbols = tuple(validate_symbol(symbol) for symbol in symbols)
        self.limit = limit
        self.persist_report = persist_report

    def audit(
        self, *, as_of: datetime | None = None
    ) -> RuntimeBrokerOrderHistoryReport:
        now = as_of or datetime.now(tz=UTC)
        recovered = self.store.recover()
        local_submissions = _filter_local_submissions(
            _local_broker_submissions(recovered.submissions),
            session_started_at=self.session_started_at,
            session_completed_at=self.session_completed_at,
            symbols=self.symbols,
        )
        local_fills = _filter_local_fills(
            recovered.fills,
            local_submissions,
            session_started_at=self.session_started_at,
            session_completed_at=self.session_completed_at,
        )
        broker_orders, source, history_path = self._broker_orders(now)
        checks = tuple(_checks(local_submissions, local_fills, broker_orders, source))
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        missing_broker = tuple(_missing_broker_ids(local_submissions, broker_orders))
        unexpected_broker = tuple(
            _unexpected_broker_ids(local_submissions, broker_orders)
        )
        matched = _matched_count(local_submissions, broker_orders)
        provider = _provider(broker_orders, source)
        report = RuntimeBrokerOrderHistoryReport(
            as_of=now,
            status=RuntimePreflightStatus.FAILED
            if failures
            else RuntimePreflightStatus.PASSED,
            passed=failures == 0,
            output_dir=str(self.output_dir),
            provider=provider,
            source=source,
            checks=checks,
            local_order_count=len(local_submissions),
            broker_order_count=len(broker_orders),
            matched_order_count=matched,
            mismatch_count=failures,
            missing_broker_order_ids=missing_broker,
            unexpected_broker_order_ids=unexpected_broker,
            session_started_at=self.session_started_at,
            session_completed_at=self.session_completed_at,
            symbols=self.symbols,
            order_history_path=str(history_path) if history_path else None,
            summary=_summary(failures, matched, len(local_submissions), source),
        )
        if self.persist_report:
            markdown_path = write_broker_order_history_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_broker_order_history_report(
                report,
                markdown_path=markdown_path,
            )
        return report

    def _broker_orders(
        self,
        as_of: datetime,
    ) -> tuple[tuple[BrokerOrderState, ...], str, Path | None]:
        if self.broker_orders is not None:
            return (
                _filter_broker_orders(
                    self.broker_orders,
                    session_started_at=self.session_started_at,
                    session_completed_at=self.session_completed_at,
                    symbols=self.symbols,
                    limit=self.limit,
                ),
                "provided",
                None,
            )
        if self.order_history_path is not None:
            orders = load_broker_order_history(self.order_history_path)
            return (
                _filter_broker_orders(
                    orders,
                    session_started_at=self.session_started_at,
                    session_completed_at=self.session_completed_at,
                    symbols=self.symbols,
                    limit=self.limit,
                ),
                f"file:{self.order_history_path}",
                self.order_history_path,
            )
        if self.broker_factory is None:
            return (), "missing", None
        broker = self.broker_factory()
        orders = _list_broker_orders(
            broker,
            session_started_at=self.session_started_at,
            session_completed_at=self.session_completed_at,
            symbols=self.symbols,
            limit=self.limit,
        )
        orders = _filter_broker_orders(
            orders,
            session_started_at=self.session_started_at,
            session_completed_at=self.session_completed_at,
            symbols=self.symbols,
            limit=self.limit,
        )
        path = write_broker_order_history_json(
            orders,
            self.output_dir / "broker-history",
            as_of=as_of,
        )
        return orders, broker.provider, path


def load_broker_order_history(path: Path | str) -> tuple[BrokerOrderState, ...]:
    """Load broker order history from a JSON array or JSONL file."""

    history_path = Path(path)
    text = history_path.read_text(encoding="utf-8")
    if history_path.suffix == ".jsonl":
        return tuple(
            BrokerOrderState.model_validate_json(line)
            for line in text.splitlines()
            if line.strip()
        )
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("broker order history JSON must be a list")
    return tuple(
        BrokerOrderState.model_validate_json(json.dumps(item)) for item in payload
    )


def write_broker_order_history_json(
    orders: tuple[BrokerOrderState, ...],
    output_dir: Path | str,
    *,
    as_of: datetime,
) -> Path:
    """Write broker order history JSON and return the path."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"broker-order-history-{_timestamp_id(as_of)}.json"
    payload = [json.loads(order.model_dump_json()) for order in orders]
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def render_broker_order_history_text(
    report: RuntimeBrokerOrderHistoryReport,
) -> str:
    """Render compact broker order-history audit status."""

    lines = [
        f"Broker order history status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Provider: {report.provider}",
        f"Source: {report.source}",
        f"Session: {_window_text(report)}",
        f"Symbols: {_join(report.symbols) if report.symbols else 'all'}",
        f"Output dir: {report.output_dir}",
        f"Order history: {report.order_history_path or 'not written'}",
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


def render_broker_order_history_markdown(
    report: RuntimeBrokerOrderHistoryReport,
) -> str:
    """Render broker order-history audit Markdown."""

    lines = [
        "# Broker Order History Audit",
        "",
        "> Paper trading only. This audit compares broker-reported order history "
        "with persisted local paper orders and fills.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Provider: `{report.provider}`",
        f"- Source: `{report.source}`",
        f"- Session window: `{_window_text(report)}`",
        f"- Symbols: `{_join(report.symbols) if report.symbols else 'all'}`",
        f"- Local orders: `{report.local_order_count}`",
        f"- Broker orders: `{report.broker_order_count}`",
        f"- Matched orders: `{report.matched_order_count}`",
        f"- Missing broker orders: `{_join(report.missing_broker_order_ids)}`",
        f"- Unexpected broker orders: `{_join(report.unexpected_broker_order_ids)}`",
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


def write_broker_order_history_markdown_report(
    report: RuntimeBrokerOrderHistoryReport,
    reports_dir: Path | str,
) -> Path:
    """Write broker order-history audit Markdown and return the path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"broker-order-history-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_broker_order_history_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit broker order history.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument(
        "--orders", default=None, help="Saved broker orders JSON/JSONL."
    )
    parser.add_argument(
        "--session-start",
        default=None,
        help="Optional ISO timestamp for the reviewed paper-session start.",
    )
    parser.add_argument(
        "--session-end",
        default=None,
        help="Optional ISO timestamp for the reviewed paper-session end.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated symbol filter for broker order history.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum broker orders to request or review.",
    )
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    broker_factory = None
    if args.orders is None:
        from trading_app.broker import AlpacaPaperBrokerAdapter

        broker_factory = AlpacaPaperBrokerAdapter
    report = RuntimeBrokerOrderHistoryAuditor(
        output_dir=args.output_dir,
        order_history_path=args.orders,
        broker_factory=broker_factory,
        session_started_at=_parse_datetime(args.session_start),
        session_completed_at=_parse_datetime(args.session_end),
        symbols=_parse_symbols(args.symbols),
        limit=args.limit,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json()
        if args.json
        else render_broker_order_history_text(report)
    )
    return 0 if report.passed else 1


def _checks(
    local_submissions: tuple[PaperOrderSubmission, ...],
    local_fills: tuple[Fill, ...],
    broker_orders: tuple[BrokerOrderState, ...],
    source: str,
) -> list[RuntimeBrokerOrderHistoryCheck]:
    return [
        _check(
            "broker_history_source",
            source != "missing",
            "Broker order-history source is available.",
            "Broker order-history source is missing.",
            (f"source={source}",),
        ),
        _check(
            "broker_provider",
            _provider(broker_orders, source) == "alpaca-paper",
            "Broker order history is from Alpaca paper.",
            "Broker order history is not from Alpaca paper.",
            (f"provider={_provider(broker_orders, source)}",),
        ),
        _check(
            "local_orders_have_broker_ids",
            all(
                submission.broker_order is not None for submission in local_submissions
            ),
            "All broker-submitted local orders have broker IDs.",
            "One or more local broker-submitted orders lack broker IDs.",
            (f"local_orders={len(local_submissions)}",),
        ),
        _check(
            "broker_orders_match_local_submissions",
            not _missing_broker_ids(local_submissions, broker_orders)
            and not _unexpected_broker_ids(local_submissions, broker_orders),
            "Broker order IDs match persisted local submissions.",
            "Broker order IDs do not match persisted local submissions.",
            (
                "missing_broker="
                f"{_join(_missing_broker_ids(local_submissions, broker_orders))}",
                "unexpected_broker="
                f"{_join(_unexpected_broker_ids(local_submissions, broker_orders))}",
            ),
        ),
        _check(
            "broker_order_fields_match",
            not _field_mismatches(local_submissions, broker_orders),
            "Broker order fields match persisted local orders.",
            "One or more broker order fields do not match local orders.",
            tuple(_field_mismatches(local_submissions, broker_orders)[:8]),
        ),
        _check(
            "broker_filled_quantities_match_ledger_fills",
            not _fill_mismatches(local_fills, broker_orders),
            "Broker filled quantities match persisted local fills.",
            "Broker filled quantities do not match persisted local fills.",
            tuple(_fill_mismatches(local_fills, broker_orders)[:8]),
        ),
    ]


def _local_broker_submissions(
    submissions: tuple[PaperOrderSubmission, ...],
) -> tuple[PaperOrderSubmission, ...]:
    return tuple(
        submission
        for submission in submissions
        if submission.accepted and submission.broker_submitted
    )


def _filter_local_submissions(
    submissions: tuple[PaperOrderSubmission, ...],
    *,
    session_started_at: datetime | None,
    session_completed_at: datetime | None,
    symbols: tuple[str, ...],
) -> tuple[PaperOrderSubmission, ...]:
    allowed_symbols = set(symbols)
    filtered = []
    for submission in submissions:
        submitted_at = submission.submitted_at
        if session_started_at is not None and submitted_at < session_started_at:
            continue
        if session_completed_at is not None and submitted_at > session_completed_at:
            continue
        if allowed_symbols and submission.order.symbol not in allowed_symbols:
            continue
        filtered.append(submission)
    return tuple(filtered)


def _filter_local_fills(
    fills: tuple[Fill, ...],
    submissions: tuple[PaperOrderSubmission, ...],
    *,
    session_started_at: datetime | None,
    session_completed_at: datetime | None,
) -> tuple[Fill, ...]:
    order_ids = {submission.order.id for submission in submissions}
    filtered = []
    for fill in fills:
        if fill.order_id not in order_ids:
            continue
        if session_started_at is not None and fill.filled_at < session_started_at:
            continue
        if session_completed_at is not None and fill.filled_at > session_completed_at:
            continue
        filtered.append(fill)
    return tuple(filtered)


def _list_broker_orders(
    broker: PaperBrokerAdapter,
    *,
    session_started_at: datetime | None,
    session_completed_at: datetime | None,
    symbols: tuple[str, ...],
    limit: int | None,
) -> tuple[BrokerOrderState, ...]:
    try:
        return broker.list_orders(
            after=session_started_at,
            until=session_completed_at,
            symbols=symbols or None,
            limit=limit,
        )
    except TypeError:
        return broker.list_orders()


def _filter_broker_orders(
    orders: tuple[BrokerOrderState, ...],
    *,
    session_started_at: datetime | None,
    session_completed_at: datetime | None,
    symbols: tuple[str, ...],
    limit: int | None,
) -> tuple[BrokerOrderState, ...]:
    allowed_symbols = set(symbols)
    filtered = []
    for order in sorted(orders, key=lambda item: item.submitted_at):
        if session_started_at is not None and order.submitted_at < session_started_at:
            continue
        if (
            session_completed_at is not None
            and order.submitted_at > session_completed_at
        ):
            continue
        if allowed_symbols and order.symbol not in allowed_symbols:
            continue
        filtered.append(order)
    result = tuple(filtered)
    return result[:limit] if limit is not None else result


def _missing_broker_ids(
    local_submissions: tuple[PaperOrderSubmission, ...],
    broker_orders: tuple[BrokerOrderState, ...],
) -> tuple[str, ...]:
    broker_ids = {order.broker_order_id for order in broker_orders}
    return tuple(
        submission.broker_order.broker_order_id
        for submission in local_submissions
        if submission.broker_order is not None
        and submission.broker_order.broker_order_id not in broker_ids
    )


def _unexpected_broker_ids(
    local_submissions: tuple[PaperOrderSubmission, ...],
    broker_orders: tuple[BrokerOrderState, ...],
) -> tuple[str, ...]:
    local_ids = {
        submission.broker_order.broker_order_id
        for submission in local_submissions
        if submission.broker_order is not None
    }
    return tuple(
        order.broker_order_id
        for order in broker_orders
        if order.broker_order_id not in local_ids
    )


def _field_mismatches(
    local_submissions: tuple[PaperOrderSubmission, ...],
    broker_orders: tuple[BrokerOrderState, ...],
) -> list[str]:
    broker_by_id = {order.broker_order_id: order for order in broker_orders}
    mismatches: list[str] = []
    for submission in local_submissions:
        local_broker_order = submission.broker_order
        if local_broker_order is None:
            continue
        broker_order = broker_by_id.get(local_broker_order.broker_order_id)
        if broker_order is None:
            continue
        order = submission.order
        expected = (
            order.id,
            order.symbol,
            order.side,
            order.order_type,
            order.quantity,
        )
        actual = (
            broker_order.client_order_id,
            broker_order.symbol,
            broker_order.side,
            broker_order.order_type,
            broker_order.quantity,
        )
        if expected != actual:
            mismatches.append(f"field_mismatch={local_broker_order.broker_order_id}")
    return mismatches


def _fill_mismatches(
    local_fills: tuple[Fill, ...],
    broker_orders: tuple[BrokerOrderState, ...],
) -> list[str]:
    local_filled_by_order: dict[str, Decimal] = {}
    for fill in local_fills:
        local_filled_by_order[fill.order_id] = (
            local_filled_by_order.get(fill.order_id, Decimal("0")) + fill.quantity
        )
    mismatches = []
    for broker_order in broker_orders:
        order_id = broker_order.client_order_id or broker_order.broker_order_id
        local_filled = local_filled_by_order.get(order_id, Decimal("0"))
        if local_filled != broker_order.filled_quantity:
            mismatches.append(
                f"filled_quantity_mismatch={order_id}:"
                f"local={local_filled}:broker={broker_order.filled_quantity}"
            )
    return mismatches


def _matched_count(
    local_submissions: tuple[PaperOrderSubmission, ...],
    broker_orders: tuple[BrokerOrderState, ...],
) -> int:
    local_ids = {
        submission.broker_order.broker_order_id
        for submission in local_submissions
        if submission.broker_order is not None
    }
    broker_ids = {order.broker_order_id for order in broker_orders}
    return len(local_ids & broker_ids)


def _provider(broker_orders: tuple[BrokerOrderState, ...], source: str) -> str:
    providers = sorted({order.provider for order in broker_orders})
    if not providers:
        if source == "alpaca-paper":
            return "alpaca-paper"
        return "missing"
    return providers[0] if len(providers) == 1 else "mixed"


def _check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeBrokerOrderHistoryCheck:
    return RuntimeBrokerOrderHistoryCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _summary(failures: int, matched: int, local: int, source: str) -> str:
    if failures == 0:
        return (
            f"Broker order-history audit passed; {matched}/{local} local "
            f"broker-submitted order(s) matched source {source}."
        )
    return (
        f"Broker order-history audit found {failures} failed check(s). "
        "Do not treat broker order history as reviewed yet."
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


def _window_text(report: RuntimeBrokerOrderHistoryReport) -> str:
    start = (
        report.session_started_at.isoformat()
        if report.session_started_at
        else "unbounded"
    )
    end = (
        report.session_completed_at.isoformat()
        if report.session_completed_at
        else "unbounded"
    )
    return f"{start} -> {end}"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("session timestamps must include a timezone")
    return parsed


def _parse_symbols(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        validate_symbol(symbol.strip()) for symbol in value.split(",") if symbol.strip()
    )


if __name__ == "__main__":
    raise SystemExit(main())
