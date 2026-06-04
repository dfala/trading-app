from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_app.market_data.storage import ParquetBarStore
from trading_app.research import (
    ReplayConfig,
    ReplayStrategyComparisonRunner,
    build_etf_parameter_grid_replay_catalog,
    build_market_drawdown_circuit_breaker_replay_catalog,
    build_sector_etf_replay_catalog,
    render_replay_comparison_markdown_report,
    write_replay_comparison_json,
    write_replay_comparison_report,
    write_replay_decision_log_json,
)
from trading_app.research.run_historical_replay import main as replay_cli_main
from trading_app.schemas import DailyBar, DataFeed

NOW = datetime(2026, 6, 1, 18, tzinfo=UTC)
SYMBOLS = ("XLK", "XLP", "XLU", "XLV")


def make_bar(symbol: str, trading_date: date, close: Decimal) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            21,
            tzinfo=UTC,
        ),
        ingested_at=NOW,
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=Decimal("1000000"),
        source="replay-suite-test",
        data_feed=DataFeed.IEX,
    )


def business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def suite_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...], list[date]]:
    dates = business_days(date(2023, 1, 2), 170)
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(dates):
        benchmark.append(
            make_bar("SPY", trading_day, Decimal("100") + Decimal(index) / 10)
        )
        bars.append(make_bar("XLK", trading_day, Decimal("100") + Decimal(index)))
        bars.append(make_bar("XLP", trading_day, Decimal("100") + Decimal(index) / 5))
        bars.append(make_bar("XLU", trading_day, Decimal("100")))
        xlv_close = Decimal("120") - Decimal(index) / 10
        bars.append(make_bar("XLV", trading_day, max(Decimal("80"), xlv_close)))
    return tuple(bars), tuple(benchmark), dates


def test_replay_strategy_comparison_ranks_by_delta_and_writes_reports(tmp_path) -> None:
    bars, benchmark, dates = suite_bars()
    config = ReplayConfig(
        run_id="suite-test",
        start_date=dates[130],
        end_date=dates[-1],
        symbol_universe=SYMBOLS,
        warmup_trading_days=126,
        slippage_bps=Decimal("0"),
    )

    report, results = ReplayStrategyComparisonRunner().run(
        catalog=build_sector_etf_replay_catalog(symbols=SYMBOLS),
        bars=bars,
        benchmark_bars=benchmark,
        config=config,
        generated_at=NOW,
    )
    markdown = render_replay_comparison_markdown_report(report)
    markdown_path = write_replay_comparison_report(report, tmp_path)
    json_path = write_replay_comparison_json(report, tmp_path)
    decision_log_path = write_replay_decision_log_json(results[0], tmp_path)

    assert len(results) == len(report.rows)
    assert report.rows
    assert report.rows[0].rank == 1
    assert report.champion_model_key == report.rows[0].model_key
    assert [row.excess_return for row in report.rows] == sorted(
        (row.excess_return for row in report.rows),
        reverse=True,
    )
    assert "Delta vs Benchmark" in markdown
    assert "beat the benchmark" in report.summary
    assert markdown_path.exists()
    assert json_path.exists()
    assert decision_log_path.exists()
    assert "decisions" in decision_log_path.read_text(encoding="utf-8")


def test_parameter_grid_catalog_expands_unique_strategy_variants() -> None:
    catalog = build_etf_parameter_grid_replay_catalog(symbols=SYMBOLS)
    keys = [
        f"{definition.strategy_id}:{definition.version}" for definition in catalog.all()
    ]

    assert len(keys) > len(build_sector_etf_replay_catalog(symbols=SYMBOLS).all())
    assert len(keys) == len(set(keys))
    assert any(key.startswith("monthly_sector_momentum:grid-l21-n1") for key in keys)


def test_market_drawdown_circuit_breaker_catalog_includes_threshold_sensitivity() -> (
    None
):
    catalog = build_market_drawdown_circuit_breaker_replay_catalog()
    keys = [
        f"{definition.strategy_id}:{definition.version}" for definition in catalog.all()
    ]

    assert len(keys) == len(set(keys))
    assert "market_drawdown_circuit_breaker:top-semi-l126-no-breaker" in keys
    assert "market_drawdown_circuit_breaker:top-semi-l126-any-dd12-risk0-cash" in keys
    assert "market_drawdown_circuit_breaker:top-semi-l126-any-dd06-risk025-cash" in keys
    assert "market_drawdown_circuit_breaker:top-semi-l126-any-dd08-risk050-cash" in keys
    assert (
        "market_drawdown_circuit_breaker:top-semi-l126-qqq-dd12-risk0-off-xlk" in keys
    )


def test_historical_replay_cli_runs_from_parquet_store(tmp_path, capsys) -> None:
    bars, benchmark, dates = suite_bars()
    ParquetBarStore(tmp_path / "bars").write_bars(tuple(bars) + tuple(benchmark))

    status = replay_cli_main(
        [
            "--run-id",
            "cli-suite-test",
            "--start",
            dates[130].isoformat(),
            "--end",
            dates[-1].isoformat(),
            "--data-start",
            dates[0].isoformat(),
            "--symbols",
            ",".join(SYMBOLS),
            "--strategies",
            "monthly_sector_momentum",
            "--root",
            str(tmp_path / "bars"),
            "--output-dir",
            str(tmp_path / "reports"),
            "--slippage-bps",
            "0",
        ]
    )
    output = capsys.readouterr().out

    assert status == 0
    assert "champion=monthly_sector_momentum:1.0.0" in output
    assert (tmp_path / "reports" / "cli-suite-test-comparison.md").exists()
    assert (tmp_path / "reports" / "cli-suite-test-comparison.json").exists()


def test_historical_replay_cli_reports_missing_data(tmp_path, capsys) -> None:
    status = replay_cli_main(
        [
            "--run-id",
            "missing-data",
            "--start",
            "2024-01-02",
            "--end",
            "2024-02-01",
            "--data-start",
            "2023-01-02",
            "--symbols",
            ",".join(SYMBOLS),
            "--root",
            str(tmp_path / "missing"),
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )
    output = capsys.readouterr().out

    assert status == 2
    assert "Missing historical bars for:" in output
    assert "--fetch-missing" in output
