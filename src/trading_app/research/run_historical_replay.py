"""CLI for plug-and-play historical replay strategy comparison."""

from __future__ import annotations

import argparse
import os
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.alpaca_credentials import normalize_alpaca_env_value
from trading_app.market_data.historical import AlpacaHistoricalBarFetcher
from trading_app.market_data.storage import (
    DEFAULT_BAR_ROOT,
    DuckDBBarQuery,
    ParquetBarStore,
)
from trading_app.research import (
    ReplayConfig,
    ReplayDecisionFrequency,
    ReplayExecutionPrice,
    ReplayStrategyComparisonRunner,
    build_etf_parameter_grid_replay_catalog,
    build_market_drawdown_circuit_breaker_replay_catalog,
    build_sector_etf_replay_catalog,
    write_replay_comparison_json,
    write_replay_comparison_report,
    write_replay_decision_log_json,
    write_replay_markdown_report,
)
from trading_app.schemas import DataFeed, validate_symbol
from trading_app.strategies import SECTOR_ETF_UNIVERSE

DEFAULT_REPLAY_START = date(2014, 1, 2)
DEFAULT_WARMUP_CALENDAR_DAYS = 540
DEFAULT_OUTPUT_DIR = Path("data/research/replay")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.candidate_grid and args.market_drawdown_circuit_breaker_grid:
        parser.error(
            "--candidate-grid and --market-drawdown-circuit-breaker-grid "
            "are mutually exclusive"
        )
    if (args.fetch_missing or args.refresh_data) and not args.no_env_file:
        _load_env_file(args.env_file)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    data_start = (
        date.fromisoformat(args.data_start)
        if args.data_start
        else start - timedelta(days=args.warmup_calendar_days)
    )
    if end < start:
        parser.error("--end cannot be before --start")
    if data_start >= start:
        parser.error("--data-start must be before --start")

    feed = DataFeed(args.feed)
    symbols = _parse_symbols(args.symbols)
    benchmark = validate_symbol(args.benchmark)
    if benchmark in symbols:
        parser.error("--symbols must not include the benchmark")
    if args.market_drawdown_circuit_breaker_grid:
        catalog = build_market_drawdown_circuit_breaker_replay_catalog(
            benchmark=benchmark,
        )
    elif args.candidate_grid:
        catalog = build_etf_parameter_grid_replay_catalog(
            symbols=symbols,
            benchmark=benchmark,
        )
    else:
        catalog = build_sector_etf_replay_catalog(symbols=symbols, benchmark=benchmark)
    strategy_ids = _parse_strategy_ids(args.strategies)
    required_symbols = _required_symbols(catalog, strategy_ids, benchmark)
    root = Path(args.root)
    output_dir = Path(args.output_dir)

    if args.refresh_data:
        _fetch_and_store(
            root=root,
            symbols=tuple(sorted(required_symbols)),
            start=data_start,
            end=end,
            feed=feed,
        )

    bars, benchmark_bars = _load_bars(
        root=root,
        symbols=tuple(symbol for symbol in required_symbols if symbol != benchmark),
        benchmark=benchmark,
        start=data_start,
        end=end,
        feed=feed,
    )
    missing = _missing_symbols(required_symbols, bars + benchmark_bars)
    if missing and args.fetch_missing:
        _fetch_and_store(
            root=root,
            symbols=tuple(sorted(required_symbols)),
            start=data_start,
            end=end,
            feed=feed,
        )
        bars, benchmark_bars = _load_bars(
            root=root,
            symbols=tuple(symbol for symbol in required_symbols if symbol != benchmark),
            benchmark=benchmark,
            start=data_start,
            end=end,
            feed=feed,
        )
        missing = _missing_symbols(required_symbols, bars + benchmark_bars)

    if missing:
        missing_text = ",".join(sorted(missing))
        print(
            "Missing historical bars for: "
            f"{missing_text}. Re-run with --fetch-missing after configuring "
            "Alpaca credentials, or fetch bars into the Parquet store first."
        )
        return 2

    config = ReplayConfig(
        run_id=args.run_id,
        start_date=start,
        end_date=end,
        symbol_universe=symbols,
        benchmark=benchmark,
        decision_frequency=ReplayDecisionFrequency(args.decision_frequency),
        execution_price=ReplayExecutionPrice(args.execution_price),
        warmup_trading_days=args.warmup_trading_days,
        starting_cash=Decimal(args.starting_cash),
        commission_per_trade=Decimal(args.commission_per_trade),
        slippage_bps=Decimal(args.slippage_bps),
        sell_fee_bps=Decimal(args.sell_fee_bps),
        data_feed=feed,
    )
    generated_at = datetime.now(tz=UTC)
    report, results = ReplayStrategyComparisonRunner().run(
        catalog=catalog,
        bars=bars,
        benchmark_bars=benchmark_bars,
        config=config,
        generated_at=generated_at,
        strategy_ids=strategy_ids,
    )

    comparison_path = write_replay_comparison_report(report, output_dir)
    json_path = write_replay_comparison_json(report, output_dir)
    strategy_dir = output_dir / "strategies"
    for result in results:
        write_replay_markdown_report(result, strategy_dir)
    if args.write_decision_logs:
        decision_log_dir = output_dir / "decision-logs"
        for result in results:
            write_replay_decision_log_json(result, decision_log_dir)

    print(report.summary)
    print(f"comparison_report={comparison_path}")
    print(f"comparison_json={json_path}")
    if report.rows:
        champion = report.rows[0]
        print(
            "champion="
            f"{champion.model_key} net={champion.net_total_return:.2%} "
            f"benchmark={champion.benchmark_total_return:.2%} "
            f"delta={champion.excess_return:+.2%}"
        )
    if report.skipped:
        print(f"skipped={len(report.skipped)}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run leakage-safe historical replay across implemented ETF strategies "
            "and rank them against SPY."
        )
    )
    parser.add_argument("--run-id", default="sector-etf-replay")
    parser.add_argument("--start", default=DEFAULT_REPLAY_START.isoformat())
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-start", default=None)
    parser.add_argument(
        "--warmup-calendar-days",
        type=int,
        default=DEFAULT_WARMUP_CALENDAR_DAYS,
    )
    parser.add_argument("--warmup-trading-days", type=int, default=126)
    parser.add_argument(
        "--symbols",
        default=",".join(SECTOR_ETF_UNIVERSE),
        help="Comma-separated ETF universe.",
    )
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument(
        "--strategies",
        default="",
        help="Optional comma-separated strategy ids. Defaults to all implemented.",
    )
    parser.add_argument(
        "--candidate-grid",
        action="store_true",
        help="Run exploratory parameter-grid variants instead of default cards.",
    )
    parser.add_argument(
        "--market-drawdown-circuit-breaker-grid",
        action="store_true",
        help=(
            "Run the Hypothesis 2 semiconductor market-drawdown circuit-breaker "
            "sensitivity grid."
        ),
    )
    parser.add_argument(
        "--write-decision-logs",
        action="store_true",
        help="Write full per-strategy replay decision logs as JSON.",
    )
    parser.add_argument(
        "--decision-frequency",
        default=ReplayDecisionFrequency.DAILY.value,
        choices=[frequency.value for frequency in ReplayDecisionFrequency],
    )
    parser.add_argument(
        "--execution-price",
        default=ReplayExecutionPrice.CLOSE.value,
        choices=[price.value for price in ReplayExecutionPrice],
    )
    parser.add_argument(
        "--feed",
        default=DataFeed.IEX.value,
        choices=[DataFeed.IEX.value, DataFeed.SIP.value],
    )
    parser.add_argument("--root", default=str(DEFAULT_BAR_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--no-env-file",
        action="store_true",
        help="Do not load a local env file before optional Alpaca fetches.",
    )
    parser.add_argument("--starting-cash", default="100000")
    parser.add_argument("--commission-per-trade", default="0")
    parser.add_argument("--slippage-bps", default="5")
    parser.add_argument("--sell-fee-bps", default="0")
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help="Fetch missing bars from Alpaca before running replay.",
    )
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Fetch and merge the full requested data window before replay.",
    )
    return parser


def _load_bars(
    *,
    root: Path,
    symbols: tuple[str, ...],
    benchmark: str,
    start: date,
    end: date,
    feed: DataFeed,
):
    query = DuckDBBarQuery(root)
    bars = query.load_daily_bars(list(symbols), start, end, feed)
    benchmark_bars = query.load_daily_bars([benchmark], start, end, feed)
    return bars, benchmark_bars


def _fetch_and_store(
    *,
    root: Path,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    feed: DataFeed,
) -> None:
    fetcher = AlpacaHistoricalBarFetcher()
    bars = fetcher.fetch_daily_bars(list(symbols), start, end, feed)
    ParquetBarStore(root).write_bars(bars)


def _parse_symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(
        validate_symbol(symbol.strip()) for symbol in value.split(",") if symbol.strip()
    )
    if not symbols:
        raise ValueError("at least one symbol is required")
    return symbols


def _parse_strategy_ids(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _load_env_file(path: str | Path) -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False
    for line_number, line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        parsed = _parse_env_line(line, line_number=line_number, path=env_path)
        if parsed is None:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)
    return True


def _parse_env_line(
    line: str,
    *,
    line_number: int,
    path: Path,
) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()
    key, separator, value = stripped.partition("=")
    key = key.strip()
    if not separator or not _ENV_NAME.fullmatch(key):
        raise ValueError(f"invalid env line {line_number} in {path}")
    return key, normalize_alpaca_env_value(value) or ""


def _required_symbols(
    catalog,
    strategy_ids: tuple[str, ...],
    benchmark: str,
) -> set[str]:
    allowed = set(strategy_ids)
    required = {benchmark}
    for definition in catalog.all():
        if allowed and definition.strategy_id not in allowed:
            continue
        required.update(definition.universe)
        required.add(definition.benchmark)
    return required


def _missing_symbols(required_symbols: set[str], bars: tuple) -> set[str]:
    available = {bar.symbol for bar in bars}
    return required_symbols - available


if __name__ == "__main__":
    raise SystemExit(main())
