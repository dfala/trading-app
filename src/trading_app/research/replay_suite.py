"""Historical replay comparison workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, Field

from trading_app.research.evaluation import (
    StrategyFactory,
    default_strategy_factories,
)
from trading_app.research.replay import (
    HistoricalReplayRunner,
    ReplayConfig,
    ReplayRunResult,
    StrategyReplayPolicy,
)
from trading_app.schemas import DailyBar, TradingModel
from trading_app.strategies import (
    SECTOR_ETF_UNIVERSE,
    StrategyCatalog,
    StrategyDefinition,
    StrategyImplementationStatus,
    benchmark_relative_strength_etf_definition,
    cash_rotation_model_definition,
    defensive_regime_switch_definition,
    market_drawdown_circuit_breaker_definition,
    mean_reversion_etf_definition,
    monthly_sector_momentum_definition,
    trend_following_etf_definition,
    volatility_aware_etf_definition,
)


class ReplayComparisonRow(TradingModel):
    rank: int = Field(ge=1)
    model_key: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    net_total_return: float
    benchmark_total_return: float
    excess_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    turnover: float
    trade_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    leakage_passed: bool
    research_score: float


class ReplayComparisonSkipped(TradingModel):
    model_key: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReplayComparisonReport(TradingModel):
    run_id: str = Field(min_length=1)
    generated_at: AwareDatetime
    start_date: str = Field(min_length=1)
    end_date: str = Field(min_length=1)
    benchmark: str = Field(min_length=1)
    rows: tuple[ReplayComparisonRow, ...]
    skipped: tuple[ReplayComparisonSkipped, ...] = ()
    champion_model_key: str | None = None
    summary: str = Field(min_length=1)


class ReplayStrategyComparisonRunner:
    """Run all implemented strategy cards through historical replay."""

    def __init__(
        self,
        *,
        replay_runner: HistoricalReplayRunner | None = None,
        factories: dict[str, StrategyFactory] | None = None,
    ) -> None:
        self.replay_runner = replay_runner or HistoricalReplayRunner()
        self.factories = factories or default_strategy_factories()

    def run(
        self,
        *,
        catalog: StrategyCatalog,
        bars: tuple[DailyBar, ...] | list[DailyBar],
        benchmark_bars: tuple[DailyBar, ...] | list[DailyBar],
        config: ReplayConfig,
        generated_at: datetime | None = None,
        strategy_ids: tuple[str, ...] = (),
    ) -> tuple[ReplayComparisonReport, tuple[ReplayRunResult, ...]]:
        definitions = _selected_definitions(catalog, strategy_ids)
        results: list[ReplayRunResult] = []
        skipped: list[ReplayComparisonSkipped] = []

        for definition in definitions:
            model_key = _model_key(definition)
            factory = self.factories.get(definition.strategy_id)
            if factory is None:
                skipped.append(
                    ReplayComparisonSkipped(
                        model_key=model_key,
                        strategy_name=definition.name,
                        reason="No strategy factory is registered.",
                    )
                )
                continue

            try:
                strategy = factory(definition.parameters)
                replay_config = _config_for_definition(config, definition)
                results.append(
                    self.replay_runner.run(
                        policy=StrategyReplayPolicy(strategy, key=model_key),
                        bars=bars,
                        benchmark_bars=benchmark_bars,
                        config=replay_config,
                        generated_at=generated_at,
                    )
                )
            except Exception as error:
                skipped.append(
                    ReplayComparisonSkipped(
                        model_key=model_key,
                        strategy_name=definition.name,
                        reason=str(error),
                    )
                )

        ranked_rows = _rank_results(results, catalog)
        report = ReplayComparisonReport(
            run_id=config.run_id,
            generated_at=results[0].generated_at
            if results
            else _require_generated_at(generated_at),
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
            benchmark=config.benchmark,
            rows=ranked_rows,
            skipped=tuple(skipped),
            champion_model_key=ranked_rows[0].model_key if ranked_rows else None,
            summary=_comparison_summary(ranked_rows, skipped),
        )
        return report, tuple(results)


def build_sector_etf_replay_catalog(
    *,
    symbols: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    benchmark: str = "SPY",
) -> StrategyCatalog:
    """Build the implemented ETF strategy catalog for replay comparison."""

    defensive_symbols = tuple(
        symbol for symbol in ("XLP", "XLU", "XLV") if symbol in symbols
    )
    definitions = [
        monthly_sector_momentum_definition(universe=symbols),
        trend_following_etf_definition(universe=symbols),
        mean_reversion_etf_definition(universe=symbols),
        volatility_aware_etf_definition(universe=symbols),
        benchmark_relative_strength_etf_definition(
            universe=symbols,
            benchmark=benchmark,
        ),
        cash_rotation_model_definition(universe=symbols),
    ]
    if defensive_symbols:
        definitions.append(
            defensive_regime_switch_definition(
                universe=symbols,
                defensive_symbols=defensive_symbols,
                benchmark=benchmark,
            )
        )
    return StrategyCatalog(tuple(definitions))


def build_etf_parameter_grid_replay_catalog(
    *,
    symbols: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    benchmark: str = "SPY",
) -> StrategyCatalog:
    """Build an exploratory ETF parameter-grid catalog for replay search."""

    definitions = []
    for lookback in (21, 63, 126, 252):
        for top_n in _top_n_values(symbols):
            definitions.append(
                monthly_sector_momentum_definition(
                    version=f"grid-l{lookback}-n{top_n}",
                    universe=symbols,
                    lookback_days=lookback,
                    top_n=top_n,
                )
            )
            definitions.append(
                trend_following_etf_definition(
                    version=f"grid-w{lookback}-n{top_n}",
                    universe=symbols,
                    trend_window_days=lookback,
                    top_n=top_n,
                )
            )

    for lookback in (21, 63, 126, 252):
        for tracking in (21, 63):
            for top_n in _top_n_values(symbols):
                definitions.append(
                    benchmark_relative_strength_etf_definition(
                        version=f"grid-l{lookback}-t{tracking}-n{top_n}",
                        universe=symbols,
                        benchmark=benchmark,
                        lookback_days=lookback,
                        tracking_window_days=tracking,
                        top_n=top_n,
                    )
                )

    for lookback in (21, 63, 126):
        for volatility_window in (21, 63):
            for top_n in _top_n_values(symbols):
                definitions.append(
                    volatility_aware_etf_definition(
                        version=f"grid-l{lookback}-v{volatility_window}-n{top_n}",
                        universe=symbols,
                        lookback_days=lookback,
                        volatility_window_days=volatility_window,
                        top_n=top_n,
                    )
                )

    for lookback in (21, 63, 126):
        for top_n in _top_n_values(symbols):
            for min_breadth in ("0.20", "0.40"):
                definitions.append(
                    cash_rotation_model_definition(
                        version=(
                            f"grid-l{lookback}-n{top_n}-b{min_breadth.replace('.', '')}"
                        ),
                        universe=symbols,
                        lookback_days=lookback,
                        top_n=top_n,
                        min_breadth=min_breadth,
                    )
                )

    defensive_symbols = tuple(
        symbol for symbol in ("XLP", "XLU", "XLV") if symbol in symbols
    )
    if defensive_symbols:
        for lookback in (63, 126, 252):
            for risk_on_top_n in _top_n_values(symbols):
                definitions.append(
                    defensive_regime_switch_definition(
                        version=f"grid-r{lookback}-n{risk_on_top_n}",
                        universe=symbols,
                        defensive_symbols=defensive_symbols,
                        benchmark=benchmark,
                        regime_lookback_days=lookback,
                        risk_on_top_n=risk_on_top_n,
                        risk_off_top_n=min(2, len(defensive_symbols)),
                    )
                )

    return StrategyCatalog(tuple(definitions))


def build_market_drawdown_circuit_breaker_replay_catalog(
    *,
    benchmark: str = "SPY",
) -> StrategyCatalog:
    """Build the Hypothesis 2 market-drawdown sensitivity catalog."""

    definitions: list[StrategyDefinition] = [
        market_drawdown_circuit_breaker_definition(
            version="top-semi-l126-no-breaker",
            risk_symbols=("SOXX", "SMH"),
            benchmark=benchmark,
            momentum_lookback_days=126,
            drawdown_symbols=("SPY", "QQQ"),
            drawdown_lookback_days=252,
            drawdown_threshold=None,
            triggered_risk_exposure="1",
            trigger_mode="any",
        )
    ]
    sources = {
        "any": ("SPY", "QQQ"),
        "spy": ("SPY",),
        "qqq": ("QQQ",),
    }
    for source_name, drawdown_symbols in sources.items():
        for threshold in ("0.06", "0.08", "0.10", "0.12", "0.15"):
            threshold_slug = threshold.replace("0.", "")
            for risk_exposure in ("0", "0.25", "0.50", "0.75"):
                exposure_slug = risk_exposure.replace(".", "")
                definitions.append(
                    market_drawdown_circuit_breaker_definition(
                        version=(
                            f"top-semi-l126-{source_name}-dd{threshold_slug}-"
                            f"risk{exposure_slug}-cash"
                        ),
                        risk_symbols=("SOXX", "SMH"),
                        risk_off_weights={},
                        benchmark=benchmark,
                        momentum_lookback_days=126,
                        drawdown_symbols=drawdown_symbols,
                        drawdown_lookback_days=252,
                        drawdown_threshold=threshold,
                        triggered_risk_exposure=risk_exposure,
                        trigger_mode="any",
                    )
                )

    for source_name, drawdown_symbols in sources.items():
        for risk_off_symbol in ("SPY", "QQQ", "XLK"):
            definitions.append(
                market_drawdown_circuit_breaker_definition(
                    version=(
                        f"top-semi-l126-{source_name}-dd12-risk0-"
                        f"off-{risk_off_symbol.lower()}"
                    ),
                    risk_symbols=("SOXX", "SMH"),
                    risk_off_weights={risk_off_symbol: "1"},
                    benchmark=benchmark,
                    momentum_lookback_days=126,
                    drawdown_symbols=drawdown_symbols,
                    drawdown_lookback_days=252,
                    drawdown_threshold="0.12",
                    triggered_risk_exposure="0",
                    trigger_mode="any",
                )
            )

    return StrategyCatalog(tuple(definitions))


def render_replay_comparison_markdown_report(
    report: ReplayComparisonReport,
) -> str:
    """Render the strategy comparison report."""

    lines = [
        "# Historical Replay Strategy Comparison",
        "",
        "> This is research evidence only. It compares simulated historical "
        "decisions against the benchmark after costs and leakage checks.",
        "",
        "## Summary",
        "",
        f"- Run id: `{report.run_id}`",
        f"- Range: `{report.start_date}` to `{report.end_date}`",
        f"- Benchmark: `{report.benchmark}`",
        f"- Strategies compared: `{len(report.rows)}`",
        f"- Strategies skipped: `{len(report.skipped)}`",
        f"- Champion: `{report.champion_model_key or 'none'}`",
        "",
        report.summary,
        "",
        "## Ranking",
        "",
        "| Rank | Strategy | Net | Benchmark | Delta vs Benchmark | Max DD | "
        "Vol | Turnover | Trades | Leakage |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.rows:
        leakage = "pass" if row.leakage_passed else "fail"
        lines.append(
            f"| {row.rank} | {_table_text(row.strategy_name)} "
            f"(`{row.model_key}`) | "
            f"{row.net_total_return:.2%} | "
            f"{row.benchmark_total_return:.2%} | "
            f"{row.excess_return:+.2%} | "
            f"{row.max_drawdown:.2%} | "
            f"{row.annualized_volatility:.2%} | "
            f"{row.turnover:.2f} | "
            f"{row.trade_count} | "
            f"{leakage} |"
        )

    if report.skipped:
        lines.extend(
            [
                "",
                "## Skipped",
                "",
                "| Strategy | Reason |",
                "| --- | --- |",
            ]
        )
        for skipped in report.skipped:
            lines.append(f"| `{skipped.model_key}` | {_table_text(skipped.reason)} |")

    lines.extend(
        [
            "",
            "## Interpretation Rules",
            "",
            "- Positive delta means the strategy beat the benchmark over the replay "
            "range after configured trading costs.",
            "- Negative delta means it underperformed the benchmark.",
            "- A strategy is not promotion-ready merely because it ranks first; it "
            "still needs regime slices, cost sensitivity, forward paper evidence, "
            "and manual review.",
            "",
        ]
    )
    return "\n".join(lines)


def write_replay_comparison_report(
    report: ReplayComparisonReport,
    output_dir: Path | str,
) -> Path:
    """Write the aggregate replay comparison markdown report."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.run_id}-comparison.md"
    path.write_text(
        render_replay_comparison_markdown_report(report),
        encoding="utf-8",
    )
    return path


def write_replay_comparison_json(
    report: ReplayComparisonReport,
    output_dir: Path | str,
) -> Path:
    """Write a compact machine-readable comparison report."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.run_id}-comparison.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def _selected_definitions(
    catalog: StrategyCatalog,
    strategy_ids: tuple[str, ...],
) -> tuple[StrategyDefinition, ...]:
    selected = []
    allowed = set(strategy_ids)
    for definition in catalog.all():
        if definition.implementation_status != StrategyImplementationStatus.IMPLEMENTED:
            continue
        if allowed and definition.strategy_id not in allowed:
            continue
        selected.append(definition)
    return tuple(selected)


def _top_n_values(symbols: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(value for value in (1, 2, 3) if value <= len(symbols))


def _config_for_definition(
    config: ReplayConfig,
    definition: StrategyDefinition,
) -> ReplayConfig:
    symbol_universe = tuple(
        symbol for symbol in definition.universe if symbol != definition.benchmark
    )
    return config.model_copy(
        update={
            "run_id": f"{config.run_id}-{_slug(_model_key(definition))}",
            "symbol_universe": symbol_universe,
            "benchmark": definition.benchmark,
        }
    )


def _rank_results(
    results: list[ReplayRunResult],
    catalog: StrategyCatalog,
) -> tuple[ReplayComparisonRow, ...]:
    definitions = {_model_key(definition): definition for definition in catalog.all()}
    sortable = sorted(
        results,
        key=lambda result: (
            result.metrics.excess_return,
            result.metrics.net_total_return,
            result.metrics.max_drawdown,
        ),
        reverse=True,
    )
    rows: list[ReplayComparisonRow] = []
    for rank, result in enumerate(sortable, start=1):
        definition = definitions.get(result.policy_key)
        rows.append(
            ReplayComparisonRow(
                rank=rank,
                model_key=result.policy_key,
                strategy_name=(
                    definition.name if definition is not None else result.policy_key
                ),
                net_total_return=result.metrics.net_total_return,
                benchmark_total_return=result.metrics.benchmark_total_return,
                excess_return=result.metrics.excess_return,
                annualized_return=result.metrics.annualized_return,
                annualized_volatility=result.metrics.annualized_volatility,
                max_drawdown=result.metrics.max_drawdown,
                turnover=result.metrics.turnover,
                trade_count=result.metrics.trade_count,
                decision_count=result.metrics.decision_count,
                leakage_passed=result.leakage_audit.passed,
                research_score=_research_score(result),
            )
        )
    return tuple(rows)


def _research_score(result: ReplayRunResult) -> float:
    return (
        result.metrics.excess_return
        + result.metrics.net_total_return
        - abs(result.metrics.max_drawdown) * 0.5
        - result.metrics.annualized_volatility * 0.1
        - result.metrics.turnover * 0.01
    )


def _comparison_summary(
    rows: tuple[ReplayComparisonRow, ...],
    skipped: list[ReplayComparisonSkipped],
) -> str:
    if not rows:
        return f"No strategies completed replay; skipped {len(skipped)} strategy(s)."
    champion = rows[0]
    delta = champion.excess_return
    direction = "beat" if delta >= 0 else "trailed"
    return (
        f"Top strategy {champion.model_key} {direction} the benchmark by "
        f"{delta:+.2%}. {sum(1 for row in rows if row.excess_return > 0)} of "
        f"{len(rows)} completed strategy replay(s) beat the benchmark."
    )


def _require_generated_at(generated_at: datetime | None) -> datetime:
    if generated_at is not None:
        return generated_at
    return datetime.now().astimezone()


def _model_key(definition: StrategyDefinition) -> str:
    return f"{definition.strategy_id}:{definition.version}"


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value)


def _table_text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
