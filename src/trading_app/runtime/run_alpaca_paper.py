"""Run the always-on Alpaca paper runtime."""

from __future__ import annotations

import argparse
from pathlib import Path
from threading import Thread

from trading_app.dashboard.server import create_dashboard_server
from trading_app.runtime.cli import parse_symbol_list
from trading_app.runtime.dry_run import (
    AlpacaPaperRuntimeDryRun,
    PaperRuntimeDryRunConfig,
    render_dry_run_text,
)
from trading_app.runtime.paper import (
    AlwaysOnPaperRuntime,
    AlwaysOnPaperRuntimeConfig,
)
from trading_app.runtime.preflight import (
    AlpacaPaperRuntimePreflight,
    render_preflight_text,
)
from trading_app.schemas import DataFeed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Alpaca paper trading runtime.")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--feed", default=DataFeed.IEX.value)
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=8765)
    parser.add_argument("--no-dashboard", action="store_true")
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help=("Rejected safety bypass retained only to fail closed for older scripts."),
    )
    parser.add_argument("--monitor-only-dry-run-first", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=None)
    args = parser.parse_args(argv)

    symbols = parse_symbol_list(
        args.symbols,
        default=AlwaysOnPaperRuntimeConfig().symbols,
    )
    config = AlwaysOnPaperRuntimeConfig(
        symbols=symbols,
        feed=DataFeed(args.feed.upper()),
        output_dir=Path(args.output_dir),
    )
    if args.skip_preflight:
        raise SystemExit(
            "Alpaca paper runtime preflight cannot be skipped in this phase."
        )

    preflight = AlpacaPaperRuntimePreflight(
        config=config,
        dashboard_host=args.dashboard_host,
    ).run()
    print(render_preflight_text(preflight))
    if not preflight.can_start:
        raise SystemExit("Alpaca paper runtime preflight failed.")

    if not args.monitor_only_dry_run_first:
        raise SystemExit(
            "Alpaca paper runtime requires --monitor-only-dry-run-first before startup."
        )

    dry_run = AlpacaPaperRuntimeDryRun(
        config=PaperRuntimeDryRunConfig(
            runtime_config=config,
            dashboard_host=args.dashboard_host,
            monitor_only=True,
        )
    ).run()
    print(render_dry_run_text(dry_run))
    if not dry_run.can_start_supervised_runtime:
        raise SystemExit("Alpaca paper runtime monitor-only dry run failed.")

    runtime = AlwaysOnPaperRuntime.from_alpaca_env(config=config)

    server = None
    thread = None
    if not args.no_dashboard:
        server = create_dashboard_server(
            args.dashboard_host,
            args.dashboard_port,
            snapshot_provider=runtime.dashboard_snapshot,
            control_handler=runtime.apply_control,
            health_provider=runtime.health_report,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(
            f"Dashboard running at http://{args.dashboard_host}:{args.dashboard_port}"
        )

    print("Alpaca paper runtime started. Press Ctrl+C to stop.")
    try:
        runtime.run_forever(max_cycles=args.max_cycles)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
