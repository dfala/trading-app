"""CLI for reconciling saved broker statements against runtime paper state."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from trading_app.paper.statement import (
    load_broker_statement,
    reconcile_statement_snapshot,
    write_statement_reconciliation_markdown,
)
from trading_app.runtime.models import RuntimeSnapshot
from trading_app.runtime.persistence import RuntimePersistenceStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile a saved broker statement against paper runtime state."
    )
    parser.add_argument(
        "--runtime-dir",
        default="data/runtime",
        help=(
            "Runtime artifact directory containing state/latest-runtime-snapshot.json."
        ),
    )
    parser.add_argument(
        "--statement",
        required=True,
        help="Path to a broker statement JSON or CSV file.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory for the Markdown reconciliation report. "
            "Defaults to runtime reports."
        ),
    )
    parser.add_argument("--cash-tolerance", default="0.01")
    parser.add_argument("--quantity-tolerance", default="0.000001")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    runtime_dir = Path(args.runtime_dir)
    output_dir = Path(args.output_dir) if args.output_dir else runtime_dir / "reports"
    try:
        snapshot = _read_runtime_snapshot(runtime_dir)
        if snapshot.paper_report is None:
            raise ValueError("latest runtime snapshot does not include a paper report")
        statement = load_broker_statement(args.statement)
        report = reconcile_statement_snapshot(
            snapshot.paper_report.ledger_snapshot,
            statement,
            as_of=snapshot.as_of,
            cash_tolerance=Decimal(args.cash_tolerance),
            quantity_tolerance=Decimal(args.quantity_tolerance),
            statement_path=args.statement,
        )
        markdown_path = write_statement_reconciliation_markdown(report, output_dir)
        RuntimePersistenceStore(runtime_dir).persist_statement_reconciliation(
            report,
            markdown_path=markdown_path,
        )
    except Exception as error:
        print(f"Statement reconciliation failed: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(report.model_dump_json())
    else:
        status = "reconciled" if report.reconciled else "mismatch"
        print(f"Statement reconciliation status: {status}")
        print(f"Issues: {len(report.issues)}")
        print(f"Report: {markdown_path}")
    return 0 if report.reconciled else 1


def _read_runtime_snapshot(runtime_dir: Path) -> RuntimeSnapshot:
    path = runtime_dir / "state" / "latest-runtime-snapshot.json"
    if not path.exists():
        raise ValueError(f"missing runtime snapshot: {path}")
    return RuntimeSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
