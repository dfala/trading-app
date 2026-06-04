"""Run the always-on Alpaca paper runtime."""

from __future__ import annotations

import argparse
import errno
from datetime import datetime
from decimal import Decimal
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
    StrategySchedule,
    default_symbols_for_paper_model,
)
from trading_app.runtime.preflight import (
    AlpacaPaperRuntimePreflight,
    render_preflight_text,
)
from trading_app.schemas import DataFeed

_DASHBOARD_PORT_RETRY_LIMIT = 20
_DEFAULT_OPERATOR_DASHBOARD_URL = "http://127.0.0.1:3003/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Alpaca paper trading runtime.")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--feed", default=DataFeed.IEX.value)
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument(
        "--starting-cash",
        default=str(AlwaysOnPaperRuntimeConfig().starting_cash),
    )
    parser.add_argument(
        "--managed-capital",
        default="",
        help="Optional capital slice used for model target sizing.",
    )
    parser.add_argument("--paper-epoch-started-at", default="")
    parser.add_argument(
        "--active-model-key",
        default=AlwaysOnPaperRuntimeConfig().active_model_key,
    )
    parser.add_argument(
        "--shadow-challenger-model-key",
        default=AlwaysOnPaperRuntimeConfig().shadow_challenger_model_key,
    )
    parser.add_argument(
        "--shadow-challenger-model-keys",
        default="",
        help="Optional comma-separated shadow-only challenger model keys.",
    )
    parser.add_argument(
        "--strategy-schedule",
        default=AlwaysOnPaperRuntimeConfig().strategy_schedule.value,
        choices=[schedule.value for schedule in StrategySchedule],
    )
    parser.add_argument(
        "--max-paper-symbol-allocation",
        default=_optional_decimal_text(
            AlwaysOnPaperRuntimeConfig().max_paper_symbol_allocation
        ),
    )
    parser.add_argument(
        "--max-paper-semiconductor-allocation",
        default=_optional_decimal_text(
            AlwaysOnPaperRuntimeConfig().max_paper_semiconductor_allocation
        ),
    )
    parser.add_argument(
        "--initial-paper-deployment-allocation",
        default=_optional_decimal_text(
            AlwaysOnPaperRuntimeConfig().initial_paper_deployment_allocation
        ),
    )
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=8765)
    parser.add_argument(
        "--dashboard-redirect-url",
        default=_DEFAULT_OPERATOR_DASHBOARD_URL,
        help=(
            "Local operator dashboard URL for browser redirects. "
            "Use an empty value to keep serving the legacy Python dashboard."
        ),
    )
    parser.add_argument("--dashboard-port-auto-increment", action="store_true")
    parser.add_argument("--no-dashboard", action="store_true")
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help=("Rejected safety bypass retained only to fail closed for older scripts."),
    )
    parser.add_argument("--monitor-only-dry-run-first", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=None)
    args = parser.parse_args(argv)
    shadow_challenger_model_keys = _parse_model_key_list(
        args.shadow_challenger_model_keys
    )

    symbols = parse_symbol_list(
        args.symbols,
        default=default_symbols_for_paper_model(
            args.active_model_key,
            shadow_challenger_model_key=args.shadow_challenger_model_key,
            shadow_challenger_model_keys=shadow_challenger_model_keys,
            leaderboard_path=Path(args.output_dir)
            / "learning"
            / "learning-leaderboard.json",
        ),
    )
    config = AlwaysOnPaperRuntimeConfig(
        symbols=symbols,
        starting_cash=Decimal(args.starting_cash),
        managed_capital=_optional_decimal(args.managed_capital),
        paper_epoch_started_at=_optional_aware_datetime(args.paper_epoch_started_at),
        feed=DataFeed(args.feed.upper()),
        output_dir=Path(args.output_dir),
        active_model_key=args.active_model_key,
        shadow_challenger_model_key=args.shadow_challenger_model_key,
        shadow_challenger_model_keys=shadow_challenger_model_keys,
        strategy_schedule=StrategySchedule(args.strategy_schedule),
        max_paper_symbol_allocation=_optional_decimal(args.max_paper_symbol_allocation),
        max_paper_semiconductor_allocation=_optional_decimal(
            args.max_paper_semiconductor_allocation
        ),
        initial_paper_deployment_allocation=_optional_decimal(
            args.initial_paper_deployment_allocation
        ),
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
        server, dashboard_port = create_dashboard_server_with_port_fallback(
            host=args.dashboard_host,
            preferred_port=args.dashboard_port,
            snapshot_provider=runtime.dashboard_snapshot_for_api,
            control_handler=runtime.apply_control,
            health_provider=runtime.health_report,
            dashboard_redirect_url=args.dashboard_redirect_url or None,
            auto_increment=args.dashboard_port_auto_increment,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        if dashboard_port != args.dashboard_port:
            print(
                f"Dashboard port {args.dashboard_port} is in use; "
                f"using {dashboard_port} instead."
            )
        print(
            "Python backend/API running at "
            f"http://{args.dashboard_host}:{dashboard_port}"
        )
        if args.dashboard_redirect_url:
            print(f"Operator dashboard redirect: {args.dashboard_redirect_url}")

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


def create_dashboard_server_with_port_fallback(
    *,
    host: str,
    preferred_port: int,
    snapshot_provider,
    control_handler,
    health_provider,
    dashboard_redirect_url: str | None = None,
    auto_increment: bool = False,
):
    """Create the dashboard server, optionally trying nearby ports."""

    attempts = _dashboard_port_attempts(preferred_port, auto_increment=auto_increment)
    for port in attempts:
        try:
            server = create_dashboard_server(
                host,
                port,
                snapshot_provider=snapshot_provider,
                control_handler=control_handler,
                health_provider=health_provider,
                dashboard_redirect_url=dashboard_redirect_url,
            )
            return server, port
        except OSError as error:
            if not _is_address_in_use(error) or port == attempts[-1]:
                if _is_address_in_use(error):
                    raise SystemExit(
                        _dashboard_port_conflict_message(
                            preferred_port,
                            auto_increment=auto_increment,
                        )
                    ) from error
                raise
    raise SystemExit(
        _dashboard_port_conflict_message(
            preferred_port,
            auto_increment=auto_increment,
        )
    )


def _dashboard_port_attempts(
    preferred_port: int,
    *,
    auto_increment: bool,
) -> list[int]:
    if not auto_increment:
        return [preferred_port]
    last_port = min(65535, preferred_port + _DASHBOARD_PORT_RETRY_LIMIT)
    return list(range(preferred_port, last_port + 1))


def _parse_model_key_list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _is_address_in_use(error: OSError) -> bool:
    return error.errno == errno.EADDRINUSE


def _optional_aware_datetime(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--paper-epoch-started-at must include a timezone")
    return parsed


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "none", "null"}:
        return None
    parsed = Decimal(value)
    if parsed <= 0:
        raise ValueError("optional decimal values must be positive")
    return parsed


def _optional_decimal_text(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _dashboard_port_conflict_message(
    preferred_port: int,
    *,
    auto_increment: bool,
) -> str:
    if auto_increment:
        last_port = min(65535, preferred_port + _DASHBOARD_PORT_RETRY_LIMIT)
        return (
            f"Dashboard ports {preferred_port}-{last_port} are already in use. "
            "Stop an existing dashboard or pass --dashboard-port with a free port."
        )
    return (
        f"Dashboard port {preferred_port} is already in use. Stop the existing "
        "dashboard, pass --dashboard-port with a free port, or use the dev "
        "shortcut for automatic local port selection."
    )


if __name__ == "__main__":
    raise SystemExit(main())
