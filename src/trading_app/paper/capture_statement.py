"""CLI for capturing a paper broker statement snapshot."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from trading_app.broker import AlpacaPaperBrokerAdapter, PaperBrokerAdapter
from trading_app.paper.statement import (
    capture_broker_statement_snapshot,
    write_broker_statement_json,
)

BrokerFactory = Callable[[], PaperBrokerAdapter]


def main(
    argv: list[str] | None = None,
    *,
    broker_factory: BrokerFactory | None = None,
    clock: Callable[[], datetime] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Capture an Alpaca paper broker statement snapshot."
    )
    parser.add_argument("--output-dir", default="data/runtime/statements")
    parser.add_argument("--statement-id", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    now = clock() if clock is not None else datetime.now(tz=UTC)
    factory = broker_factory or AlpacaPaperBrokerAdapter
    try:
        broker = factory()
        statement = capture_broker_statement_snapshot(
            broker,
            as_of=now,
            statement_id=args.statement_id,
            source=args.source,
        )
        path = write_broker_statement_json(statement, Path(args.output_dir))
    except Exception as error:
        print(f"Statement capture failed: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(statement.model_dump_json())
    else:
        print("Paper broker statement captured.")
        print(f"Provider: {statement.provider}")
        print(f"Statement: {statement.statement_id}")
        print(f"Positions: {len(statement.positions)}")
        print(f"Path: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
