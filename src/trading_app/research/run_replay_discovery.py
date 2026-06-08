"""Search replay candidates across universes, periods, and cost assumptions."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
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
from trading_app.research.replay import (
    ReplayConfig,
    ReplayDecisionFrequency,
    ReplayExecutionPrice,
)
from trading_app.research.replay_suite import (
    ReplayComparisonReport,
    ReplayComparisonRow,
    ReplayStrategyComparisonRunner,
    build_etf_parameter_grid_replay_catalog,
    write_replay_comparison_json,
    write_replay_comparison_report,
)
from trading_app.schemas import DailyBar, DataFeed, validate_symbol
from trading_app.strategies import (
    StrategyCatalog,
    risk_managed_semiconductor_definition,
    static_etf_allocation_definition,
)

DEFAULT_OUTPUT_DIR = Path("data/research/replay")
DEFAULT_WARMUP_CALENDAR_DAYS = 540
DEFAULT_WARMUP_TRADING_DAYS = 126
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
STATIC_ALLOCATION_STRATEGY_ID = "static_etf_allocation"
STATIC_ALLOCATION_MODEL_PREFIX = f"{STATIC_ALLOCATION_STRATEGY_ID}:"
BENCHMARK_LADDER_KEYS = {
    "QQQ": "static_etf_allocation:single-qqq",
    "XLK": "static_etf_allocation:single-xlk",
    "SOXX": "static_etf_allocation:single-soxx",
    "SMH": "static_etf_allocation:single-smh",
    "Semis Basket": "static_etf_allocation:basket-semis",
}

DISCOVERY_UNIVERSES: dict[str, tuple[str, ...]] = {
    "sector-spdr": (
        "XLB",
        "XLC",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLRE",
        "XLU",
        "XLV",
        "XLY",
    ),
    "broad-core": (
        "DIA",
        "QQQ",
        "IWM",
        "MDY",
        "TLT",
        "GLD",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLU",
        "XLV",
        "XLY",
    ),
    "growth-industries": (
        "QQQ",
        "XLK",
        "XLY",
        "SMH",
        "SOXX",
        "IGV",
        "IBB",
        "XBI",
        "IYT",
        "XRT",
        "XHB",
        "ITB",
        "XME",
        "XOP",
        "KRE",
    ),
    "macro-defensive": (
        "DIA",
        "QQQ",
        "IWM",
        "MDY",
        "TLT",
        "GLD",
        "XLP",
        "XLU",
        "XLV",
        "XLE",
    ),
    "liquid-risk-on": (
        "DIA",
        "QQQ",
        "IWM",
        "MDY",
        "XLK",
        "XLY",
        "XLF",
        "XLI",
        "XLE",
        "SMH",
        "IBB",
        "XBI",
        "KRE",
    ),
    "semiconductor-champions": (
        "QQQ",
        "XLK",
        "SMH",
        "SOXX",
    ),
}


@dataclass(frozen=True)
class DiscoveryPeriod:
    period_id: str
    start: date
    end: date


@dataclass
class DiscoveryRun:
    universe_id: str
    period_id: str
    cost_label: str
    report: ReplayComparisonReport


@dataclass
class CandidateScore:
    universe_id: str
    model_key: str
    strategy_name: str
    full: ReplayComparisonRow
    folds: dict[str, ReplayComparisonRow]
    stress: ReplayComparisonRow | None
    positive_folds: int
    min_fold_delta: float
    average_fold_delta: float
    full_delta: float
    stress_delta: float | None
    worst_drawdown: float
    benchmark_ladder: dict[str, float]
    retention_vs_soxx: float | None
    drawdown_delta_vs_semis: float | None
    recent_window_excess_share: dict[str, float]
    late_entry_risk: bool
    late_entry_risk_reason: str | None
    portfolio_governance_classification: str
    champion_eligible: bool
    average_semiconductor_exposure: float
    peak_semiconductor_exposure: float
    material_semiconductor_exposure_ratio: float
    portfolio_governance_notes: tuple[str, ...]
    risk_adjusted_score: float
    gate_status: str
    status: str

    @property
    def sort_key(self) -> tuple[float, ...]:
        stress_delta = self.stress_delta if self.stress_delta is not None else -99.0
        return (
            0.0 if self.late_entry_risk else 1.0,
            1.0 if self.champion_eligible else 0.0,
            self.risk_adjusted_score,
            float(self.positive_folds),
            self.min_fold_delta,
            stress_delta,
            self.full_delta,
            self.worst_drawdown,
        )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if (args.fetch_missing or args.refresh_data) and not args.no_env_file:
        _load_env_file(args.env_file)

    end = date.fromisoformat(args.end) if args.end else _default_end_date()
    start = date.fromisoformat(args.start)
    if end < start:
        parser.error("--end cannot be before --start")

    feed = DataFeed(args.feed)
    benchmark = validate_symbol(args.benchmark)
    universes = _selected_universes(args.universes, benchmark)
    if args.extra_symbols:
        universes = _with_extra_symbols(universes, args.extra_symbols, benchmark)

    output_dir = Path(args.output_dir)
    root = Path(args.root)
    base_cost = Decimal(args.slippage_bps)
    stress_cost = Decimal(args.stress_slippage_bps)
    decision_frequency = ReplayDecisionFrequency(args.decision_frequency)
    execution_price = ReplayExecutionPrice(args.execution_price)
    run_id = args.run_id or f"replay-discovery-{datetime.now(tz=UTC):%Y%m%dT%H%M%SZ}"
    periods = _discovery_periods(start, end)
    required_symbols = _required_symbols(universes, benchmark)
    strategy_ids = _parse_strategy_ids(args.strategies)

    if args.refresh_data:
        _fetch_and_store(
            root=root,
            symbols=required_symbols,
            start=start - timedelta(days=args.warmup_calendar_days),
            end=end,
            feed=feed,
        )
    elif args.fetch_missing:
        _fetch_missing_symbols(
            root=root,
            symbols=required_symbols,
            start=start - timedelta(days=args.warmup_calendar_days),
            end=end,
            feed=feed,
        )

    generated_at = datetime.now(tz=UTC)
    runs: list[DiscoveryRun] = []
    skipped: list[str] = []
    for universe_id, symbols in universes.items():
        universe_runs, universe_skipped = _run_universe(
            universe_id=universe_id,
            symbols=symbols,
            benchmark=benchmark,
            periods=periods,
            root=root,
            feed=feed,
            output_dir=output_dir,
            run_id=run_id,
            generated_at=generated_at,
            starting_cash=Decimal(args.starting_cash),
            base_slippage_bps=base_cost,
            stress_slippage_bps=stress_cost,
            decision_frequency=decision_frequency,
            execution_price=execution_price,
            warmup_calendar_days=args.warmup_calendar_days,
            warmup_trading_days=args.warmup_trading_days,
            max_strategies=args.max_strategies,
            strategy_ids=strategy_ids,
        )
        runs.extend(universe_runs)
        skipped.extend(universe_skipped)

    scores = score_discovery_candidates(
        runs,
        fold_ids=tuple(
            period.period_id for period in periods if period.period_id != "full"
        ),
    )
    markdown = render_discovery_markdown(
        run_id=run_id,
        generated_at=generated_at,
        benchmark=benchmark,
        feed=feed,
        universes=universes,
        periods=periods,
        base_cost=base_cost,
        stress_cost=stress_cost,
        scores=scores,
        skipped=tuple(skipped),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{run_id}.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path = output_dir / f"{run_id}.json"
    json_path.write_text(
        json.dumps(_json_payload(run_id, generated_at, scores, skipped), indent=2),
        encoding="utf-8",
    )

    strong = [score for score in scores if score.status == "all folds positive"]
    print(
        f"Discovery evaluated {len(scores)} candidate(s); "
        f"{len(strong)} were positive across every validation fold."
    )
    if scores:
        leader = scores[0]
        print(
            "leader="
            f"{leader.universe_id}:{leader.model_key} "
            f"full_delta={leader.full_delta:.2%} "
            f"min_fold_delta={leader.min_fold_delta:.2%} "
            f"stress_delta={_format_optional_pct(leader.stress_delta)}"
        )
    print(f"discovery_report={markdown_path}")
    print(f"discovery_json={json_path}")
    return 0


def score_discovery_candidates(
    runs: list[DiscoveryRun],
    *,
    fold_ids: tuple[str, ...],
) -> list[CandidateScore]:
    grouped: dict[tuple[str, str], dict[str, ReplayComparisonRow]] = {}
    run_rows: dict[tuple[str, str], dict[str, ReplayComparisonRow]] = {}
    strategy_names: dict[tuple[str, str], str] = {}
    for run in runs:
        slot = _run_slot(run)
        run_key = (run.universe_id, slot)
        run_rows[run_key] = {row.model_key: row for row in run.report.rows}
        for row in run.report.rows:
            key = (run.universe_id, row.model_key)
            grouped.setdefault(key, {})[slot] = row
            strategy_names[key] = row.strategy_name

    scores: list[CandidateScore] = []
    for (universe_id, model_key), rows in grouped.items():
        if _is_baseline_or_control_model(model_key):
            continue
        full = rows.get("full:base")
        if full is None:
            continue
        folds = {
            fold_id: rows[fold_key]
            for fold_id in fold_ids
            if (fold_key := f"{fold_id}:base") in rows
        }
        if not folds:
            continue
        stress = rows.get("full:stress")
        fold_deltas = [row.excess_return for row in folds.values()]
        positive_folds = sum(1 for delta in fold_deltas if delta > 0)
        min_fold_delta = min(fold_deltas)
        average_fold_delta = sum(fold_deltas) / len(fold_deltas)
        stress_delta = stress.excess_return if stress is not None else None
        worst_drawdown = min(
            [full.max_drawdown, *(row.max_drawdown for row in folds.values())]
        )
        ladder = _benchmark_ladder(
            universe_id=universe_id,
            row=full,
            run_rows=run_rows,
            slot="full:base",
        )
        soxx_baseline = run_rows.get((universe_id, "full:base"), {}).get(
            "static_etf_allocation:single-soxx"
        )
        semis_baseline = run_rows.get((universe_id, "full:base"), {}).get(
            "static_etf_allocation:basket-semis"
        )
        retention_vs_soxx = (
            full.excess_return / soxx_baseline.excess_return
            if soxx_baseline is not None and soxx_baseline.excess_return > 0
            else None
        )
        drawdown_delta_vs_semis = (
            worst_drawdown - semis_baseline.max_drawdown
            if semis_baseline is not None
            else (
                worst_drawdown - soxx_baseline.max_drawdown
                if soxx_baseline is not None
                else None
            )
        )
        risk_adjusted_score = _risk_adjusted_score(
            full=full,
            positive_folds=positive_folds,
            fold_count=len(fold_ids),
            min_fold_delta=min_fold_delta,
            average_fold_delta=average_fold_delta,
            stress_delta=stress_delta,
            worst_drawdown=worst_drawdown,
            ladder=ladder,
            retention_vs_soxx=retention_vs_soxx,
            drawdown_delta_vs_semis=drawdown_delta_vs_semis,
            late_entry_risk=full.late_entry_risk,
            champion_eligible=full.champion_eligible,
        )
        gate_status = _gate_status(
            model_key=model_key,
            full=full,
            positive_folds=positive_folds,
            fold_count=len(fold_ids),
            stress_delta=stress_delta,
            ladder=ladder,
            retention_vs_soxx=retention_vs_soxx,
            drawdown_delta_vs_semis=drawdown_delta_vs_semis,
        )
        status = (
            "all folds positive"
            if positive_folds == len(fold_ids)
            and full.excess_return > 0
            and (stress_delta is None or stress_delta > 0)
            else "mixed evidence"
        )
        scores.append(
            CandidateScore(
                universe_id=universe_id,
                model_key=model_key,
                strategy_name=strategy_names[(universe_id, model_key)],
                full=full,
                folds=folds,
                stress=stress,
                positive_folds=positive_folds,
                min_fold_delta=min_fold_delta,
                average_fold_delta=average_fold_delta,
                full_delta=full.excess_return,
                stress_delta=stress_delta,
                worst_drawdown=worst_drawdown,
                benchmark_ladder=ladder,
                retention_vs_soxx=retention_vs_soxx,
                drawdown_delta_vs_semis=drawdown_delta_vs_semis,
                recent_window_excess_share=full.recent_window_excess_share,
                late_entry_risk=full.late_entry_risk,
                late_entry_risk_reason=full.late_entry_risk_reason,
                portfolio_governance_classification=(
                    full.portfolio_governance_classification
                ),
                champion_eligible=full.champion_eligible,
                average_semiconductor_exposure=full.average_semiconductor_exposure,
                peak_semiconductor_exposure=full.peak_semiconductor_exposure,
                material_semiconductor_exposure_ratio=(
                    full.material_semiconductor_exposure_ratio
                ),
                portfolio_governance_notes=full.portfolio_governance_notes,
                risk_adjusted_score=risk_adjusted_score,
                gate_status=gate_status,
                status=status,
            )
        )
    return sorted(scores, key=lambda score: score.sort_key, reverse=True)


def _benchmark_ladder(
    *,
    universe_id: str,
    row: ReplayComparisonRow,
    run_rows: dict[tuple[str, str], dict[str, ReplayComparisonRow]],
    slot: str,
) -> dict[str, float]:
    rows = run_rows.get((universe_id, slot), {})
    ladder = {"SPY": row.excess_return}
    for label, model_key in BENCHMARK_LADDER_KEYS.items():
        baseline = rows.get(model_key)
        if baseline is not None:
            ladder[label] = row.net_total_return - baseline.net_total_return
    return ladder


def _risk_adjusted_score(
    *,
    full: ReplayComparisonRow,
    positive_folds: int,
    fold_count: int,
    min_fold_delta: float,
    average_fold_delta: float,
    stress_delta: float | None,
    worst_drawdown: float,
    ladder: dict[str, float],
    retention_vs_soxx: float | None,
    drawdown_delta_vs_semis: float | None,
    late_entry_risk: bool,
    champion_eligible: bool,
) -> float:
    fold_bonus = positive_folds / max(fold_count, 1)
    stress_component = stress_delta if stress_delta is not None else -1.0
    ladder_component = sum(
        min(delta, 1.0) for delta in (ladder.get("QQQ"), ladder.get("XLK")) if delta
    )
    retention_component = min(retention_vs_soxx or 0.0, 1.0)
    drawdown_component = max(drawdown_delta_vs_semis or 0.0, 0.0)
    late_entry_penalty = 1.0 if late_entry_risk else 0.0
    governance_penalty = 0.75 if not champion_eligible else 0.0
    return (
        full.excess_return
        + min_fold_delta * 2.0
        + average_fold_delta
        + stress_component * 0.25
        + fold_bonus
        + ladder_component * 0.25
        + retention_component * 0.5
        + drawdown_component * 2.0
        - abs(worst_drawdown) * 2.0
        - full.annualized_volatility * 0.5
        - full.turnover * 0.01
        - late_entry_penalty
        - governance_penalty
    )


def _gate_status(
    *,
    model_key: str,
    full: ReplayComparisonRow,
    positive_folds: int,
    fold_count: int,
    stress_delta: float | None,
    ladder: dict[str, float],
    retention_vs_soxx: float | None,
    drawdown_delta_vs_semis: float | None,
) -> str:
    if _is_baseline_or_control_model(model_key):
        return "benchmark baseline"
    if full.late_entry_risk:
        return full.late_entry_risk_reason or "late-entry risk review"
    if not full.champion_eligible:
        return (
            full.portfolio_governance_notes[0]
            if full.portfolio_governance_notes
            else f"{full.portfolio_governance_classification}; not champion eligible"
        )
    if not (
        model_key.startswith("risk_managed_semiconductor:")
        or model_key.startswith("market_drawdown_circuit_breaker:")
    ):
        return "general evidence only"
    base_pass = (
        positive_folds == fold_count
        and full.excess_return > 0
        and (stress_delta is None or stress_delta > 0)
    )
    beats_tech = (ladder.get("QQQ", -99.0) > 0) or (ladder.get("XLK", -99.0) > 0)
    retains_alpha = retention_vs_soxx is not None and retention_vs_soxx >= 0.50
    improves_drawdown = full.max_drawdown >= -0.30 or (
        drawdown_delta_vs_semis is not None and drawdown_delta_vs_semis >= 0.05
    )
    if base_pass and beats_tech and retains_alpha and improves_drawdown:
        return "risk gates passed"
    if base_pass:
        return "return positive; risk gates incomplete"
    return "mixed evidence"


def _is_static_allocation_model(model_key: str) -> bool:
    return model_key.startswith(STATIC_ALLOCATION_MODEL_PREFIX)


def _is_baseline_or_control_model(model_key: str) -> bool:
    return _is_static_allocation_model(model_key) or model_key.endswith("-no-breaker")


def render_discovery_markdown(
    *,
    run_id: str,
    generated_at: datetime,
    benchmark: str,
    feed: DataFeed,
    universes: dict[str, tuple[str, ...]],
    periods: tuple[DiscoveryPeriod, ...],
    base_cost: Decimal,
    stress_cost: Decimal,
    scores: list[CandidateScore],
    skipped: tuple[str, ...],
) -> str:
    strong = [score for score in scores if score.status == "all folds positive"]
    lines = [
        "# Replay Discovery Report",
        "",
        "> Research evidence only. This is a broad candidate search, not a "
        "promotion decision and not permission to trade live capital.",
        "",
        "## Summary",
        "",
        f"- Run id: `{run_id}`",
        f"- Generated at: `{generated_at.isoformat()}`",
        f"- Feed: `{feed.value}`",
        f"- Benchmark: `{benchmark}`",
        f"- Base slippage bps: `{base_cost}`",
        f"- Stress slippage bps: `{stress_cost}`",
        f"- Universes searched: `{len(universes)}`",
        f"- Candidate rows scored: `{len(scores)}`",
        f"- All-fold positive candidates: `{len(strong)}`",
        "",
        _summary_sentence(strong, scores),
        "",
        "## Validation Periods",
        "",
        "| Period | Range |",
        "| --- | --- |",
    ]
    for period in periods:
        lines.append(
            f"| `{period.period_id}` | `{period.start.isoformat()}` to "
            f"`{period.end.isoformat()}` |"
        )

    lines.extend(
        [
            "",
            "## Consistency Leaders",
            "",
            "| Rank | Universe | Strategy | Full Delta | Stress Delta | "
            "Positive Folds | Min Fold Delta | Avg Fold Delta | Worst DD | "
            "Governance | Semi Avg/Peak | Recent Risk | Risk Score | "
            "Gate Status | Trades | Status |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
            "--- | ---: | --- | ---: | --- | ---: | --- |",
        ]
    )
    for rank, score in enumerate(scores[:25], start=1):
        recent_risk = (
            score.late_entry_risk_reason if score.late_entry_risk else "clear"
        )
        semi_exposure = (
            f"{score.average_semiconductor_exposure:.1%}/"
            f"{score.peak_semiconductor_exposure:.1%}"
        )
        lines.append(
            f"| {rank} | `{score.universe_id}` | "
            f"{_table_text(score.strategy_name)} (`{score.model_key}`) | "
            f"{score.full_delta:+.2%} | "
            f"{_format_optional_pct(score.stress_delta)} | "
            f"{score.positive_folds}/{len(score.folds)} | "
            f"{score.min_fold_delta:+.2%} | "
            f"{score.average_fold_delta:+.2%} | "
            f"{score.worst_drawdown:.2%} | "
            f"{_table_text(score.portfolio_governance_classification)} | "
            f"{semi_exposure} | "
            f"{_table_text(recent_risk)} | "
            f"{score.risk_adjusted_score:.2f} | "
            f"{score.gate_status} | "
            f"{score.full.trade_count} | "
            f"{score.status} |"
        )

    lines.extend(
        [
            "",
            "## Benchmark Ladder For Leaders",
            "",
            "| Universe | Strategy | vs SPY | vs QQQ | vs XLK | vs SOXX | "
            "vs SMH | vs Semis Basket | SOXX Retention | DD Improvement |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for score in scores[:15]:
        lines.append(
            f"| `{score.universe_id}` | `{score.model_key}` | "
            f"{_ladder_delta(score, 'SPY')} | "
            f"{_ladder_delta(score, 'QQQ')} | "
            f"{_ladder_delta(score, 'XLK')} | "
            f"{_ladder_delta(score, 'SOXX')} | "
            f"{_ladder_delta(score, 'SMH')} | "
            f"{_ladder_delta(score, 'Semis Basket')} | "
            f"{_format_optional_ratio(score.retention_vs_soxx)} | "
            f"{_format_optional_pct(score.drawdown_delta_vs_semis)} |"
        )

    lines.extend(
        [
            "",
            "## Fold Detail For Leaders",
            "",
            "| Universe | Strategy | 2016-2018 | 2019-2022 | 2023-forward |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for score in scores[:15]:
        lines.append(
            f"| `{score.universe_id}` | `{score.model_key}` | "
            f"{_fold_delta(score, '2016-2018')} | "
            f"{_fold_delta(score, '2019-2022')} | "
            f"{_fold_delta(score, '2023-forward')} |"
        )

    lines.extend(
        [
            "",
            "## Universes",
            "",
            "| Universe | Symbols |",
            "| --- | --- |",
        ]
    )
    for universe_id, symbols in universes.items():
        lines.append(f"| `{universe_id}` | `{', '.join(symbols)}` |")

    if skipped:
        lines.extend(["", "## Skipped Runs", "", "| Reason |", "| --- |"])
        for reason in skipped[:80]:
            lines.append(f"| {_table_text(reason)} |")

    lines.extend(
        [
            "",
            "## Interpretation Rules",
            "",
            "- A strong candidate should beat SPY in every validation period, not only "
            "over the full sample.",
            "- Stress-cost results matter because turnover-heavy strategies can look "
            "good before realistic friction.",
            "- This report intentionally includes weak and mixed candidates so the "
            "search does not hide data-mining failures.",
            "- No strategy is promotion-ready without forward paper evidence, "
            "manual review, data-quality checks, and explicit risk limits.",
            "- Do not treat a model as a winner just because the latest 21-63 "
            "trading days spiked upward. Champion recommendations need "
            "3/6/12-month consistency checks and a late-entry risk review.",
            "",
        ]
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run replay discovery across ETF universes and validation periods."
        )
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--start", default="2016-01-04")
    parser.add_argument("--end", default="")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument(
        "--universes",
        default="all",
        help="Comma-separated universe ids or all.",
    )
    parser.add_argument(
        "--extra-symbols",
        default="",
        help="Optional symbols appended to every selected universe.",
    )
    parser.add_argument(
        "--feed",
        default=DataFeed.SIP.value,
        choices=[DataFeed.IEX.value, DataFeed.SIP.value],
    )
    parser.add_argument("--root", default=str(DEFAULT_BAR_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--starting-cash", default="100000")
    parser.add_argument("--slippage-bps", default="5")
    parser.add_argument("--stress-slippage-bps", default="25")
    parser.add_argument(
        "--decision-frequency",
        default=ReplayDecisionFrequency.DAILY.value,
        choices=[frequency.value for frequency in ReplayDecisionFrequency],
        help="Replay decision cadence. Default daily to match live-like research.",
    )
    parser.add_argument(
        "--execution-price",
        default=ReplayExecutionPrice.OPEN.value,
        choices=[price.value for price in ReplayExecutionPrice],
        help="Replay fill proxy. Default open to mimic market-open execution.",
    )
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
        help="Optional cap per universe for faster smoke runs.",
    )
    parser.add_argument(
        "--strategies",
        default="",
        help=(
            "Optional comma-separated strategy ids, e.g. "
            "monthly_sector_momentum,trend_following_etf."
        ),
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-env-file", action="store_true")
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--refresh-data", action="store_true")
    return parser


def _run_universe(
    *,
    universe_id: str,
    symbols: tuple[str, ...],
    benchmark: str,
    periods: tuple[DiscoveryPeriod, ...],
    root: Path,
    feed: DataFeed,
    output_dir: Path,
    run_id: str,
    generated_at: datetime,
    starting_cash: Decimal,
    base_slippage_bps: Decimal,
    stress_slippage_bps: Decimal,
    decision_frequency: ReplayDecisionFrequency,
    execution_price: ReplayExecutionPrice,
    warmup_calendar_days: int,
    warmup_trading_days: int,
    max_strategies: int,
    strategy_ids: tuple[str, ...],
) -> tuple[list[DiscoveryRun], list[str]]:
    query = DuckDBBarQuery(root)
    runs: list[DiscoveryRun] = []
    skipped: list[str] = []
    catalog = _limited_catalog(_discovery_catalog(symbols, benchmark), max_strategies)
    runner = ReplayStrategyComparisonRunner()
    required_symbols = tuple(sorted(set(symbols) | {benchmark}))

    for period in periods:
        data_start = period.start - timedelta(days=warmup_calendar_days)
        bars = query.load_daily_bars(list(symbols), data_start, period.end, feed)
        benchmark_bars = query.load_daily_bars(
            [benchmark],
            data_start,
            period.end,
            feed,
        )
        missing = _missing_symbols(required_symbols, (*bars, *benchmark_bars))
        if missing:
            skipped.append(
                f"{universe_id}:{period.period_id} missing bars for {','.join(missing)}"
            )
            continue

        runs.append(
            _run_catalog(
                runner=runner,
                catalog=catalog,
                universe_id=universe_id,
                period_id=period.period_id,
                cost_label="base",
                bars=bars,
                benchmark_bars=benchmark_bars,
                config=_config(
                    run_id=f"{run_id}-{universe_id}-{period.period_id}-base",
                    start=period.start,
                    end=period.end,
                    symbols=symbols,
                    benchmark=benchmark,
                    feed=feed,
                    starting_cash=starting_cash,
                    slippage_bps=base_slippage_bps,
                    decision_frequency=decision_frequency,
                    execution_price=execution_price,
                    warmup_trading_days=warmup_trading_days,
                ),
                output_dir=output_dir,
                generated_at=generated_at,
                strategy_ids=strategy_ids,
            )
        )
        if period.period_id == "full":
            runs.append(
                _run_catalog(
                    runner=runner,
                    catalog=catalog,
                    universe_id=universe_id,
                    period_id=period.period_id,
                    cost_label="stress",
                    bars=bars,
                    benchmark_bars=benchmark_bars,
                    config=_config(
                        run_id=(
                            f"{run_id}-{universe_id}-{period.period_id}-stress-cost"
                        ),
                        start=period.start,
                        end=period.end,
                        symbols=symbols,
                        benchmark=benchmark,
                        feed=feed,
                        starting_cash=starting_cash,
                        slippage_bps=stress_slippage_bps,
                        decision_frequency=decision_frequency,
                        execution_price=execution_price,
                        warmup_trading_days=warmup_trading_days,
                    ),
                    output_dir=output_dir,
                    generated_at=generated_at,
                    strategy_ids=strategy_ids,
                )
            )
    return runs, skipped


def _run_catalog(
    *,
    runner: ReplayStrategyComparisonRunner,
    catalog: StrategyCatalog,
    universe_id: str,
    period_id: str,
    cost_label: str,
    bars: tuple[DailyBar, ...],
    benchmark_bars: tuple[DailyBar, ...],
    config: ReplayConfig,
    output_dir: Path,
    generated_at: datetime,
    strategy_ids: tuple[str, ...],
) -> DiscoveryRun:
    report, _ = runner.run(
        catalog=catalog,
        bars=bars,
        benchmark_bars=benchmark_bars,
        config=config,
        generated_at=generated_at,
        strategy_ids=strategy_ids,
    )
    write_replay_comparison_report(report, output_dir)
    write_replay_comparison_json(report, output_dir)
    return DiscoveryRun(
        universe_id=universe_id,
        period_id=period_id,
        cost_label=cost_label,
        report=report,
    )


def _config(
    *,
    run_id: str,
    start: date,
    end: date,
    symbols: tuple[str, ...],
    benchmark: str,
    feed: DataFeed,
    starting_cash: Decimal,
    slippage_bps: Decimal,
    warmup_trading_days: int,
    decision_frequency: ReplayDecisionFrequency = ReplayDecisionFrequency.DAILY,
    execution_price: ReplayExecutionPrice = ReplayExecutionPrice.OPEN,
) -> ReplayConfig:
    return ReplayConfig(
        run_id=run_id,
        start_date=start,
        end_date=end,
        symbol_universe=symbols,
        benchmark=benchmark,
        decision_frequency=decision_frequency,
        execution_price=execution_price,
        warmup_trading_days=warmup_trading_days,
        starting_cash=starting_cash,
        commission_per_trade=Decimal("0"),
        slippage_bps=slippage_bps,
        sell_fee_bps=Decimal("0"),
        data_feed=feed,
    )


def _limited_catalog(catalog: StrategyCatalog, max_strategies: int) -> StrategyCatalog:
    if max_strategies <= 0:
        return catalog
    return StrategyCatalog(catalog.all()[:max_strategies])


def _discovery_catalog(symbols: tuple[str, ...], benchmark: str) -> StrategyCatalog:
    definitions = list(
        build_etf_parameter_grid_replay_catalog(
            symbols=symbols,
            benchmark=benchmark,
        ).all()
    )
    definitions.extend(_risk_managed_semiconductor_definitions(symbols, benchmark))
    return StrategyCatalog(tuple(definitions))


def _static_allocation_definitions(
    symbols: tuple[str, ...],
    benchmark: str,
):
    definitions = [
        static_etf_allocation_definition(
            version=f"single-{symbol.lower()}",
            weights={symbol: "1"},
            benchmark=benchmark,
        )
        for symbol in symbols
    ]
    baskets = {
        "tech-core": ("QQQ", "XLK"),
        "semis": ("SMH", "SOXX"),
        "tech-semis": ("QQQ", "XLK", "SMH", "SOXX"),
        "consistent-static": ("SOXX", "SMH", "XLK", "QQQ", "XME"),
    }
    for name, basket_symbols in baskets.items():
        if all(symbol in symbols for symbol in basket_symbols):
            weight = Decimal("1") / Decimal(len(basket_symbols))
            definitions.append(
                static_etf_allocation_definition(
                    version=f"basket-{name}",
                    weights={symbol: str(weight) for symbol in basket_symbols},
                    benchmark=benchmark,
                )
            )
    return definitions


def _risk_managed_semiconductor_definitions(
    symbols: tuple[str, ...],
    benchmark: str,
):
    available = set(symbols) | {benchmark}
    sleeve_specs: dict[str, dict[str, str]] = {}
    if "SOXX" in available:
        sleeve_specs["soxx"] = {"SOXX": "1"}
    if "SMH" in available:
        sleeve_specs["smh"] = {"SMH": "1"}
    if {"SMH", "SOXX"} <= available:
        sleeve_specs["semis"] = {"SMH": "0.5", "SOXX": "0.5"}
    if {"QQQ", "XLK", "SMH", "SOXX"} <= available:
        sleeve_specs["semis-tech-qqq"] = {
            "SMH": "0.20",
            "SOXX": "0.20",
            "XLK": "0.40",
            "QQQ": "0.20",
        }
        sleeve_specs["semis-qqq-spy"] = {
            "SMH": "0.25",
            "SOXX": "0.25",
            "QQQ": "0.25",
            benchmark: "0.25",
        }

    risk_off_specs = {
        "cash": {},
        "spy": {benchmark: "1"},
        "qqq": {"QQQ": "1"} if "QQQ" in available else {},
        "xlk": {"XLK": "1"} if "XLK" in available else {},
    }
    risk_off_specs = {
        name: weights
        for name, weights in risk_off_specs.items()
        if name == "cash" or weights
    }

    definitions = []
    for sleeve_name, sleeve_weights in sleeve_specs.items():
        for risk_off_name in ("cash", "spy"):
            definitions.append(
                risk_managed_semiconductor_definition(
                    version=f"trend-{sleeve_name}-w200-off-{risk_off_name}",
                    sleeve_weights=sleeve_weights,
                    risk_off_weights=risk_off_specs[risk_off_name],
                    benchmark=benchmark,
                    trend_window_days=200,
                )
            )

        relative_risk_off_by_lookback = {
            63: "cash",
            126: "qqq" if "qqq" in risk_off_specs else "cash",
            252: "xlk" if "xlk" in risk_off_specs else "cash",
        }
        for lookback in (63, 126, 252):
            comparator_sets = (
                [("spy-qqq", (benchmark, "QQQ"))]
                if ("QQQ" in available)
                else [("spy", (benchmark,))]
            )
            for comparator_name, comparators in comparator_sets:
                risk_off_name = relative_risk_off_by_lookback[lookback]
                definitions.append(
                    risk_managed_semiconductor_definition(
                        version=(
                            f"rel-{sleeve_name}-l{lookback}-vs-"
                            f"{comparator_name}-off-{risk_off_name}"
                        ),
                        sleeve_weights=sleeve_weights,
                        risk_off_weights=risk_off_specs[risk_off_name],
                        benchmark=benchmark,
                        trend_window_days=None,
                        relative_momentum_days=lookback,
                        relative_momentum_symbols=comparators,
                    )
                )

        definitions.append(
            risk_managed_semiconductor_definition(
                version=f"vol-{sleeve_name}-v63-t020-off-cash",
                sleeve_weights=sleeve_weights,
                risk_off_weights=risk_off_specs["cash"],
                benchmark=benchmark,
                trend_window_days=None,
                volatility_window_days=63,
                target_volatility="0.20",
            )
        )

        definitions.append(
            risk_managed_semiconductor_definition(
                version=f"dd-{sleeve_name}-m015-off-cash",
                sleeve_weights=sleeve_weights,
                risk_off_weights=risk_off_specs["cash"],
                benchmark=benchmark,
                trend_window_days=200,
                drawdown_limit="-0.15",
            )
        )

        if "QQQ" in available:
            definitions.append(
                risk_managed_semiconductor_definition(
                    version=f"combo-{sleeve_name}-off-spy",
                    sleeve_weights=sleeve_weights,
                    risk_off_weights=risk_off_specs["spy"],
                    benchmark=benchmark,
                    trend_window_days=200,
                    relative_momentum_days=126,
                    relative_momentum_symbols=(benchmark, "QQQ"),
                    volatility_window_days=63,
                    target_volatility="0.20",
                    drawdown_limit="-0.15",
                )
            )

    definitions.extend(
        _next_branch_semiconductor_definitions(
            sleeve_specs=sleeve_specs,
            risk_off_specs=risk_off_specs,
            benchmark=benchmark,
        )
    )
    return definitions


def _next_branch_semiconductor_definitions(
    *,
    sleeve_specs: dict[str, dict[str, str]],
    risk_off_specs: dict[str, dict[str, str]],
    benchmark: str,
):
    definitions = []
    next_sleeves = {
        name: weights
        for name, weights in sleeve_specs.items()
        if name in {"semis", "semis-tech-qqq"}
    }
    if "qqq" not in risk_off_specs:
        return definitions

    risk_off_names = tuple(name for name in ("qqq", "xlk") if name in risk_off_specs)
    volatility_band_specs = {
        "f50": (("0.35", "1"), ("0.50", "0.75"), ("0.65", "0.50"), ("999", "0")),
        "f60": (("0.35", "1"), ("0.50", "0.80"), ("0.65", "0.60"), ("999", "0")),
        "f70": (("0.35", "1"), ("0.50", "0.85"), ("0.65", "0.70"), ("999", "0")),
    }
    drawdown_bands = (
        ("0.12", "1"),
        ("0.18", "0.75"),
        ("0.25", "0.50"),
        ("999", "0"),
    )

    for sleeve_name, sleeve_weights in next_sleeves.items():
        for volatility_window in (21, 42, 63):
            for floor_name, bands in volatility_band_specs.items():
                for risk_off_name in risk_off_names:
                    definitions.append(
                        risk_managed_semiconductor_definition(
                            version=(
                                f"next-softvol-{sleeve_name}-r126-"
                                f"v{volatility_window}-{floor_name}-"
                                f"off-{risk_off_name}"
                            ),
                            sleeve_weights=sleeve_weights,
                            risk_off_weights=risk_off_specs[risk_off_name],
                            benchmark=benchmark,
                            trend_window_days=None,
                            relative_momentum_days=126,
                            relative_momentum_symbols=(benchmark, "QQQ"),
                            volatility_window_days=volatility_window,
                            volatility_exposure_bands=bands,
                        )
                    )

        for trend_window in (150, 200):
            for risk_off_name in risk_off_names:
                definitions.append(
                    risk_managed_semiconductor_definition(
                        version=(
                            f"next-reltrend-{sleeve_name}-r126-"
                            f"w{trend_window}-off-{risk_off_name}"
                        ),
                        sleeve_weights=sleeve_weights,
                        risk_off_weights=risk_off_specs[risk_off_name],
                        benchmark=benchmark,
                        trend_window_days=trend_window,
                        relative_momentum_days=126,
                        relative_momentum_symbols=(benchmark, "QQQ"),
                    )
                )

        for risk_off_name in risk_off_names:
            definitions.append(
                risk_managed_semiconductor_definition(
                    version=f"next-ddbands-{sleeve_name}-r126-off-{risk_off_name}",
                    sleeve_weights=sleeve_weights,
                    risk_off_weights=risk_off_specs[risk_off_name],
                    benchmark=benchmark,
                    trend_window_days=None,
                    relative_momentum_days=126,
                    relative_momentum_symbols=(benchmark, "QQQ"),
                    drawdown_exposure_bands=drawdown_bands,
                )
            )

    return definitions


def _selected_universes(
    value: str,
    benchmark: str,
) -> dict[str, tuple[str, ...]]:
    requested = tuple(item.strip() for item in value.split(",") if item.strip())
    if not requested or requested == ("all",):
        selected = DISCOVERY_UNIVERSES
    else:
        unknown = sorted(set(requested) - set(DISCOVERY_UNIVERSES))
        if unknown:
            raise ValueError(f"unknown universe id(s): {','.join(unknown)}")
        selected = {
            universe_id: DISCOVERY_UNIVERSES[universe_id] for universe_id in requested
        }
    return {
        universe_id: _normalize_symbols(symbols, benchmark)
        for universe_id, symbols in selected.items()
    }


def _with_extra_symbols(
    universes: dict[str, tuple[str, ...]],
    extra_symbols: str,
    benchmark: str,
) -> dict[str, tuple[str, ...]]:
    extras = _normalize_symbols(
        tuple(symbol.strip() for symbol in extra_symbols.split(",") if symbol.strip()),
        benchmark,
    )
    return {
        universe_id: _normalize_symbols((*symbols, *extras), benchmark)
        for universe_id, symbols in universes.items()
    }


def _normalize_symbols(symbols: tuple[str, ...], benchmark: str) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized = []
    for symbol in symbols:
        value = validate_symbol(symbol)
        if value == benchmark or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    if not normalized:
        raise ValueError("universe must contain at least one non-benchmark symbol")
    return tuple(normalized)


def _required_symbols(
    universes: dict[str, tuple[str, ...]],
    benchmark: str,
) -> tuple[str, ...]:
    symbols = {benchmark}
    for universe_symbols in universes.values():
        symbols.update(universe_symbols)
    return tuple(sorted(symbols))


def _parse_strategy_ids(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _fetch_missing_symbols(
    *,
    root: Path,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    feed: DataFeed,
) -> None:
    query = DuckDBBarQuery(root)
    existing = query.load_daily_bars(list(symbols), start, end, feed)
    missing = _missing_symbols(symbols, existing)
    if missing:
        _fetch_and_store(root=root, symbols=missing, start=start, end=end, feed=feed)


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


def _missing_symbols(
    required_symbols: tuple[str, ...],
    bars: tuple[DailyBar, ...],
) -> tuple[str, ...]:
    present = {bar.symbol for bar in bars}
    return tuple(symbol for symbol in required_symbols if symbol not in present)


def _discovery_periods(start: date, end: date) -> tuple[DiscoveryPeriod, ...]:
    fold_specs = [
        ("2016-2018", date(2016, 1, 4), date(2018, 12, 31)),
        ("2019-2022", date(2019, 1, 2), date(2022, 12, 30)),
        ("2023-forward", date(2023, 1, 3), end),
    ]
    periods = [DiscoveryPeriod("full", start, end)]
    for period_id, fold_start, fold_end in fold_specs:
        resolved_start = max(start, fold_start)
        resolved_end = min(end, fold_end)
        if resolved_start <= resolved_end:
            periods.append(DiscoveryPeriod(period_id, resolved_start, resolved_end))
    return tuple(periods)


def _default_end_date(today: date | None = None) -> date:
    candidate = (today or date.today()) - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _run_slot(run: DiscoveryRun) -> str:
    return f"{run.period_id}:{run.cost_label}"


def _summary_sentence(
    strong: list[CandidateScore],
    scores: list[CandidateScore],
) -> str:
    if strong:
        leader = strong[0]
        return (
            f"{len(strong)} candidate(s) beat the benchmark in every validation "
            f"fold. The current consistency leader is "
            f"{leader.universe_id}:{leader.model_key}, with full-period delta "
            f"{leader.full_delta:+.2%} and worst fold delta "
            f"{leader.min_fold_delta:+.2%}."
        )
    if scores:
        leader = scores[0]
        return (
            "No candidate beat the benchmark in every validation fold. The best "
            f"mixed-evidence leader is {leader.universe_id}:{leader.model_key}, "
            f"with full-period delta {leader.full_delta:+.2%} and worst fold "
            f"delta {leader.min_fold_delta:+.2%}."
        )
    return "No replay candidates completed discovery."


def _fold_delta(score: CandidateScore, fold_id: str) -> str:
    row = score.folds.get(fold_id)
    if row is None:
        return "n/a"
    return f"{row.excess_return:+.2%}"


def _ladder_delta(score: CandidateScore, label: str) -> str:
    value = score.benchmark_ladder.get(label)
    return "n/a" if value is None else f"{value:+.2%}"


def _format_optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2%}"


def _format_optional_ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def _table_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _json_payload(
    run_id: str,
    generated_at: datetime,
    scores: list[CandidateScore],
    skipped: list[str],
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "generated_at": generated_at.isoformat(),
        "scores": [
            {
                "universe_id": score.universe_id,
                "model_key": score.model_key,
                "strategy_name": score.strategy_name,
                "full_delta": score.full_delta,
                "stress_delta": score.stress_delta,
                "positive_folds": score.positive_folds,
                "min_fold_delta": score.min_fold_delta,
                "average_fold_delta": score.average_fold_delta,
                "worst_drawdown": score.worst_drawdown,
                "benchmark_ladder": score.benchmark_ladder,
                "retention_vs_soxx": score.retention_vs_soxx,
                "drawdown_delta_vs_semis": score.drawdown_delta_vs_semis,
                "risk_adjusted_score": score.risk_adjusted_score,
                "gate_status": score.gate_status,
                "status": score.status,
                "folds": {
                    fold_id: row.excess_return
                    for fold_id, row in sorted(score.folds.items())
                },
            }
            for score in scores
        ],
        "skipped": skipped,
    }


def _load_env_file(path: str | Path) -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False
    for line_number, line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, raw_value = stripped.split("=", 1)
        name = name.strip()
        if not _ENV_NAME.fullmatch(name):
            raise ValueError(f"invalid env var name on line {line_number}: {name!r}")
        normalized = normalize_alpaca_env_value(raw_value)
        if normalized is not None:
            os.environ.setdefault(name, normalized)
    return True


if __name__ == "__main__":
    raise SystemExit(main())
