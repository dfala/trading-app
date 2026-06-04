"""CLI for the autonomous self-feeding research cycle."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from pathlib import Path

from trading_app.learning.autonomous import (
    DEFAULT_AUTONOMOUS_STRATEGY_IDS,
    DEFAULT_AUTONOMOUS_UNIVERSES,
    DEFAULT_LEARNING_STATUS_DIR,
    DEFAULT_RESEARCH_OUTPUT_DIR,
    AutonomousLearningCycleConfig,
    AutonomousLearningCycleMode,
    AutonomousLearningCycleRunner,
    AutonomousLearningCycleStatus,
)
from trading_app.market_data.storage import DEFAULT_BAR_ROOT
from trading_app.research.run_replay_discovery import (
    DEFAULT_WARMUP_CALENDAR_DAYS,
    DEFAULT_WARMUP_TRADING_DAYS,
    _load_env_file,
)
from trading_app.schemas import DataFeed


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if (args.fetch_missing or args.refresh_data) and not args.no_env_file:
        _load_env_file(args.env_file)

    config = AutonomousLearningCycleConfig(
        mode=AutonomousLearningCycleMode(args.mode),
        run_id=args.run_id,
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end) if args.end else None,
        benchmark=args.benchmark,
        universes=_csv_tuple(args.universes),
        extra_symbols=_csv_tuple(args.extra_symbols),
        strategy_ids=_csv_tuple(args.strategies),
        feed=DataFeed(args.feed),
        root=Path(args.root),
        output_dir=Path(args.output_dir),
        status_dir=Path(args.status_dir),
        starting_cash=Decimal(args.starting_cash),
        slippage_bps=Decimal(args.slippage_bps),
        stress_slippage_bps=Decimal(args.stress_slippage_bps),
        warmup_calendar_days=args.warmup_calendar_days,
        warmup_trading_days=args.warmup_trading_days,
        max_strategies=args.max_strategies,
        fetch_missing=args.fetch_missing,
        refresh_data=args.refresh_data,
        champion_model_key=args.champion_model_key,
    )
    run = AutonomousLearningCycleRunner().run(config)
    print(f"learning_cycle_status={run.status.value}")
    print(f"learning_cycle_run_id={run.run_id}")
    print(f"candidate_count={run.candidate_count}")
    print(f"recommended_challenger={run.recommended_challenger_model_key or 'none'}")
    if run.blocked_reasons:
        print("blocked_reasons=" + " | ".join(run.blocked_reasons))
    for label, path in sorted(run.artifact_paths.items()):
        print(f"{label}={path}")
    return 0 if run.status == AutonomousLearningCycleStatus.COMPLETED else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the autonomous trading-research learning cycle."
    )
    parser.add_argument(
        "--mode",
        default=AutonomousLearningCycleMode.NIGHTLY.value,
        choices=[mode.value for mode in AutonomousLearningCycleMode],
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--start", default="2016-01-04")
    parser.add_argument("--end", default="")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument(
        "--universes",
        default=",".join(DEFAULT_AUTONOMOUS_UNIVERSES),
        help="Comma-separated replay-discovery universe ids.",
    )
    parser.add_argument(
        "--extra-symbols",
        default="",
        help="Optional symbols appended to every selected universe.",
    )
    parser.add_argument(
        "--strategies",
        default=",".join(DEFAULT_AUTONOMOUS_STRATEGY_IDS),
        help="Comma-separated strategy ids to evaluate.",
    )
    parser.add_argument(
        "--feed",
        default=DataFeed.SIP.value,
        choices=[DataFeed.IEX.value, DataFeed.SIP.value],
    )
    parser.add_argument("--root", default=str(DEFAULT_BAR_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_RESEARCH_OUTPUT_DIR))
    parser.add_argument("--status-dir", default=str(DEFAULT_LEARNING_STATUS_DIR))
    parser.add_argument("--starting-cash", default="100000")
    parser.add_argument("--slippage-bps", default="5")
    parser.add_argument("--stress-slippage-bps", default="25")
    parser.add_argument(
        "--warmup-calendar-days",
        type=int,
        default=DEFAULT_WARMUP_CALENDAR_DAYS,
    )
    parser.add_argument(
        "--warmup-trading-days",
        type=int,
        default=DEFAULT_WARMUP_TRADING_DAYS,
    )
    parser.add_argument(
        "--max-strategies",
        type=int,
        default=0,
        help="Optional catalog cap for smoke runs.",
    )
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--refresh-data", action="store_true")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-env-file", action="store_true")
    parser.add_argument(
        "--champion-model-key",
        default=("market_drawdown_circuit_breaker:top-semi-l126-any-dd12-risk0-cash"),
    )
    return parser


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


if __name__ == "__main__":
    raise SystemExit(main())
