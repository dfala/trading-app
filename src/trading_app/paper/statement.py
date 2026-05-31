"""File-based broker statement reconciliation for paper trading."""

from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_app.broker import PaperBrokerAdapter
from trading_app.broker.models import (
    BrokerPositionState,
    BrokerReconciliationIssue,
    BrokerStatementReconciliationReport,
    BrokerStatementSnapshot,
    ReconciliationIssueType,
    aware_datetime,
)
from trading_app.schemas import PortfolioSnapshot, Position


def capture_broker_statement_snapshot(
    broker: PaperBrokerAdapter,
    *,
    as_of: datetime | None = None,
    statement_id: str | None = None,
    source: str | None = None,
) -> BrokerStatementSnapshot:
    """Capture current paper broker cash and positions as a statement snapshot."""

    checked_at = as_of or datetime.now(tz=UTC)
    portfolio = broker.get_portfolio(checked_at)
    resolved_statement_id = statement_id or _statement_id(
        portfolio.provider,
        checked_at,
    )
    return BrokerStatementSnapshot(
        statement_id=resolved_statement_id,
        as_of=portfolio.as_of,
        provider=portfolio.provider,
        account_id=portfolio.account_id,
        cash=portfolio.cash,
        positions=portfolio.positions,
        source=source or f"{portfolio.provider}:paper-portfolio-capture",
        metadata={
            "captured_at": checked_at.isoformat(),
            "buying_power": str(portfolio.buying_power)
            if portfolio.buying_power is not None
            else None,
        },
    )


def write_broker_statement_json(
    statement: BrokerStatementSnapshot,
    output_dir: Path | str,
) -> Path:
    """Write a broker statement snapshot JSON file and return its path."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"broker-statement-{_slug(statement.statement_id)}.json"
    path.write_text(statement.model_dump_json(), encoding="utf-8")
    return path


def load_broker_statement_json(path: Path | str) -> BrokerStatementSnapshot:
    """Load a strict broker statement snapshot from JSON."""

    statement_path = Path(path)
    return BrokerStatementSnapshot.model_validate_json(
        statement_path.read_text(encoding="utf-8")
    )


def load_broker_statement_csv(path: Path | str) -> BrokerStatementSnapshot:
    """Load a broker statement snapshot from a simple local CSV format."""

    statement_path = Path(path)
    rows = _read_statement_rows(statement_path)
    account_rows = [row for row in rows if _record_type(row) == "account"]
    position_rows = [row for row in rows if _record_type(row) == "position"]
    unknown_rows = [
        row
        for row in rows
        if _record_type(row) not in {"account", "position"} and not _is_blank(row)
    ]

    if unknown_rows:
        record_type = _record_type(unknown_rows[0]) or "<missing>"
        raise ValueError(f"unsupported statement record_type: {record_type}")
    if len(account_rows) != 1:
        raise ValueError("statement CSV requires exactly one account row")

    account = account_rows[0]
    statement_id = _required(account, "statement_id")
    provider = _required(account, "provider")
    as_of = aware_datetime(_required(account, "as_of"))
    cash = _required_decimal(account, "cash")
    source = _optional(account, "source") or statement_path.name
    account_id = _optional(account, "account_id")
    positions = tuple(_position_from_row(row) for row in position_rows)

    return BrokerStatementSnapshot(
        statement_id=statement_id,
        as_of=as_of,
        provider=provider,
        account_id=account_id,
        cash=cash,
        positions=positions,
        source=source,
        metadata={"statement_file": str(statement_path)},
    )


def load_broker_statement(path: Path | str) -> BrokerStatementSnapshot:
    """Load a broker statement snapshot from JSON or CSV."""

    statement_path = Path(path)
    suffix = statement_path.suffix.lower()
    if suffix == ".json":
        return load_broker_statement_json(statement_path)
    if suffix == ".csv":
        return load_broker_statement_csv(statement_path)
    raise ValueError(f"unsupported broker statement file extension: {suffix}")


def reconcile_statement_snapshot(
    ledger_snapshot: PortfolioSnapshot,
    statement: BrokerStatementSnapshot,
    *,
    as_of=None,
    cash_tolerance: Decimal = Decimal("0.01"),
    quantity_tolerance: Decimal = Decimal("0.000001"),
    statement_path: Path | str | None = None,
) -> BrokerStatementReconciliationReport:
    """Compare an internal paper ledger snapshot to a broker statement."""

    issues = _statement_reconciliation_issues(
        ledger_snapshot=ledger_snapshot,
        statement=statement,
        cash_tolerance=cash_tolerance,
        quantity_tolerance=quantity_tolerance,
    )
    resolved_statement_path = (
        Path(statement_path)
        if statement_path is not None
        else _statement_path_from_metadata(statement)
    )
    return BrokerStatementReconciliationReport(
        as_of=as_of or statement.as_of,
        reconciled=not issues,
        ledger_snapshot=ledger_snapshot,
        statement=statement,
        issues=tuple(issues),
        cash_tolerance=cash_tolerance,
        quantity_tolerance=quantity_tolerance,
        statement_path=str(resolved_statement_path)
        if resolved_statement_path is not None
        else None,
        statement_sha256=_statement_sha256(resolved_statement_path),
    )


def render_statement_reconciliation_markdown(
    report: BrokerStatementReconciliationReport,
) -> str:
    """Render a reviewable Markdown statement reconciliation report."""

    status = "reconciled" if report.reconciled else "mismatch"
    lines = [
        "# Broker Statement Reconciliation",
        "",
        (
            "Paper/research-only accounting review. This report does not mutate "
            "the ledger and is not filing-grade tax accounting."
        ),
        "",
        f"- Status: {status}",
        f"- Statement: {report.statement.statement_id}",
        f"- Provider: {report.statement.provider}",
        f"- Account: {report.statement.account_id or 'not supplied'}",
        f"- Statement source file: {report.statement_path or 'not supplied'}",
        f"- Statement source SHA-256: {report.statement_sha256 or 'not available'}",
        f"- Statement as of: {report.statement.as_of.isoformat()}",
        f"- Checked at: {report.as_of.isoformat()}",
        f"- Cash tolerance: {_format_decimal(report.cash_tolerance)}",
        f"- Quantity tolerance: {_format_decimal(report.quantity_tolerance)}",
        f"- Issue count: {len(report.issues)}",
        "",
        "## Summary",
        "",
        f"- Ledger cash: {_format_decimal(report.ledger_snapshot.cash)}",
        f"- Statement cash: {_format_decimal(report.statement.cash)}",
        f"- Ledger positions: {len(report.ledger_snapshot.positions)}",
        f"- Statement positions: {len(report.statement.positions)}",
        "",
        "## Issues",
        "",
    ]
    if not report.issues:
        lines.append("No cash or position quantity differences exceeded tolerance.")
    else:
        lines.extend(
            [
                "| Issue | Symbol | Ledger | Statement | Difference | Message |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for issue in report.issues:
            lines.append(
                "| "
                f"{_humanize(issue.issue_type.value)} | "
                f"{issue.symbol or '-'} | "
                f"{_format_decimal(issue.expected)} | "
                f"{_format_decimal(issue.actual)} | "
                f"{_format_decimal(issue.difference)} | "
                f"{issue.message} |"
            )

    lines.extend(
        [
            "",
            "## Operator Notes",
            "",
            "- Investigate mismatches before allowing new paper orders.",
            "- Do not edit ledger state to force this report to pass.",
            "- Use broker statements only as evidence for review, not as tax filings.",
            "",
        ]
    )
    return "\n".join(lines)


def write_statement_reconciliation_markdown(
    report: BrokerStatementReconciliationReport,
    output_dir: Path | str,
) -> Path:
    """Write a statement reconciliation Markdown report and return its path."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    statement_id = _slug(report.statement.statement_id)
    path = directory / f"statement-reconciliation-{statement_id}.md"
    path.write_text(
        render_statement_reconciliation_markdown(report),
        encoding="utf-8",
    )
    return path


def _statement_reconciliation_issues(
    *,
    ledger_snapshot: PortfolioSnapshot,
    statement: BrokerStatementSnapshot,
    cash_tolerance: Decimal,
    quantity_tolerance: Decimal,
) -> list[BrokerReconciliationIssue]:
    issues: list[BrokerReconciliationIssue] = []
    cash_difference = ledger_snapshot.cash - statement.cash
    if abs(cash_difference) > cash_tolerance:
        issues.append(
            BrokerReconciliationIssue(
                issue_type=ReconciliationIssueType.CASH_MISMATCH,
                expected=ledger_snapshot.cash,
                actual=statement.cash,
                difference=cash_difference,
                message="Ledger cash does not match broker statement cash.",
                provider=statement.provider,
            )
        )

    ledger_positions = {
        position.symbol: position for position in ledger_snapshot.positions
    }
    statement_positions = {
        position.symbol: position for position in statement.positions
    }
    for symbol in sorted(set(ledger_positions) | set(statement_positions)):
        ledger_position: Position | None = ledger_positions.get(symbol)
        statement_position = statement_positions.get(symbol)
        if ledger_position is None and statement_position is not None:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=ReconciliationIssueType.MISSING_LEDGER_POSITION,
                    symbol=symbol,
                    expected=Decimal("0"),
                    actual=statement_position.quantity,
                    difference=-statement_position.quantity,
                    message="Broker statement has a position missing from the ledger.",
                    provider=statement.provider,
                )
            )
            continue
        if ledger_position is not None and statement_position is None:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=ReconciliationIssueType.MISSING_BROKER_POSITION,
                    symbol=symbol,
                    expected=ledger_position.quantity,
                    actual=Decimal("0"),
                    difference=ledger_position.quantity,
                    message="Ledger has a position missing from the broker statement.",
                    provider=statement.provider,
                )
            )
            continue
        if ledger_position is None or statement_position is None:
            continue
        quantity_difference = ledger_position.quantity - statement_position.quantity
        if abs(quantity_difference) > quantity_tolerance:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=ReconciliationIssueType.POSITION_QUANTITY_MISMATCH,
                    symbol=symbol,
                    expected=ledger_position.quantity,
                    actual=statement_position.quantity,
                    difference=quantity_difference,
                    message="Ledger quantity does not match broker statement quantity.",
                    provider=statement.provider,
                )
            )
    return issues


def _statement_path_from_metadata(statement: BrokerStatementSnapshot) -> Path | None:
    path = statement.metadata.get("statement_file")
    return Path(str(path)) if path else None


def _statement_sha256(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_statement_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        return [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def _position_from_row(row: dict[str, str]) -> BrokerPositionState:
    return BrokerPositionState(
        symbol=_required(row, "symbol"),
        quantity=_required_decimal(row, "quantity"),
        average_entry_price=_required_decimal(row, "average_entry_price"),
        market_value=_optional_decimal(row, "market_value"),
        current_price=_optional_decimal(row, "current_price"),
    )


def _record_type(row: dict[str, str]) -> str:
    return row.get("record_type", "").strip().lower()


def _is_blank(row: dict[str, str]) -> bool:
    return all(not value for value in row.values())


def _required(row: dict[str, str], key: str) -> str:
    value = _optional(row, key)
    if value is None:
        raise ValueError(f"statement CSV missing required field: {key}")
    return value


def _optional(row: dict[str, str], key: str) -> str | None:
    value = row.get(key)
    return value if value else None


def _required_decimal(row: dict[str, str], key: str) -> Decimal:
    return Decimal(_required(row, key))


def _optional_decimal(row: dict[str, str], key: str) -> Decimal | None:
    value = _optional(row, key)
    return Decimal(value) if value is not None else None


def _format_decimal(value: Any) -> str:
    return str(value)


def _humanize(value: str) -> str:
    return value.replace("_", " ").title()


def _slug(value: str) -> str:
    slug = "".join(
        character.lower() if character.isalnum() else "-" for character in value.strip()
    ).strip("-")
    return slug or "statement"


def _statement_id(provider: str, as_of: datetime) -> str:
    return f"{provider}-{as_of.astimezone(UTC).strftime('%Y%m%dT%H%M%S')}"
