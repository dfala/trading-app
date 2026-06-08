"""On-demand model performance curves for the operator dashboard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, Field

from trading_app.learning.autonomous import (
    AutonomousLearningCycleMode,
    _autonomous_catalog,
)
from trading_app.market_data.storage import DEFAULT_BAR_ROOT, DuckDBBarQuery
from trading_app.research.evaluation import default_strategy_factories
from trading_app.research.replay import (
    HistoricalReplayRunner,
    ReplayConfig,
    ReplayDecisionFrequency,
    ReplayExecutionPrice,
    ReplayMetrics,
    StrategyReplayPolicy,
)
from trading_app.research.recent_windows import (
    ReturnCurvePoint,
    assess_recent_window_concentration,
    late_entry_risk_summary,
)
from trading_app.research.run_replay_discovery import DISCOVERY_UNIVERSES
from trading_app.runtime.paper import build_paper_strategy
from trading_app.schemas import DataFeed, TradingModel, validate_symbol

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPLAY_REPORT_DIR = PROJECT_ROOT / "data/research/replay"
DEFAULT_MODEL_PERFORMANCE_CACHE_DIR = PROJECT_ROOT / "data/runtime/model-performance"
DEFAULT_MODEL_PERFORMANCE_BAR_ROOT = PROJECT_ROOT / DEFAULT_BAR_ROOT
DEFAULT_STARTING_CASH = Decimal("100000")
DEFAULT_WARMUP_CALENDAR_DAYS = 540
DEFAULT_WARMUP_TRADING_DAYS = 126
MODEL_PERFORMANCE_CACHE_VERSION = "v5"


class ModelStrategyProfile(TradingModel):
    """Plain-language explanation of how a researched model invests."""

    hypothesis: str = Field(min_length=1)
    trading_cadence: str = Field(min_length=1)
    holding_period: str = Field(min_length=1)
    signal_logic: str = Field(min_length=1)
    sizing_logic: str = Field(min_length=1)
    exit_logic: str = Field(min_length=1)
    invests_in: tuple[str, ...] = Field(min_length=1)
    failure_modes: tuple[str, ...] = ()
    parameters: dict[str, str] = Field(default_factory=dict)


class ModelPerformancePoint(TradingModel):
    trading_date: date
    model_equity: float
    benchmark_equity: float
    model_return: float
    benchmark_return: float
    excess_return: float


class ModelPerformanceRecentWindow(TradingModel):
    trading_days: int = Field(ge=1)
    start_date: date
    end_date: date
    model_return_delta: float
    benchmark_return_delta: float
    excess_return_delta: float
    excess_contribution_share: float | None = None
    late_entry_risk: bool = False


class ModelPerformancePayload(TradingModel):
    model_key: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    universe_id: str | None = None
    benchmark: str = Field(min_length=1)
    data_feed: str = Field(min_length=1)
    decision_frequency: str = Field(min_length=1)
    execution_price: str = Field(min_length=1)
    start_date: date
    end_date: date
    generated_at: AwareDatetime
    source_report: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    source_rank: int | None = None
    source_research_score: float | None = None
    window_policy: str = Field(min_length=1)
    available_window_count: int = Field(ge=1)
    strategy_profile: ModelStrategyProfile | None = None
    recent_windows: tuple[ModelPerformanceRecentWindow, ...] = ()
    late_entry_risk: bool = False
    late_entry_risk_summary: str | None = None
    metrics: ReplayMetrics
    points: tuple[ModelPerformancePoint, ...]


@dataclass(frozen=True)
class _ComparisonSource:
    path: Path
    run_id: str
    generated_at: datetime
    start_date: date
    end_date: date
    benchmark: str
    universe_id: str | None
    row: dict[str, Any]


def build_model_performance_payload(
    model_key: str,
    *,
    universe_id: str | None = None,
    replay_report_dir: Path | str = DEFAULT_REPLAY_REPORT_DIR,
    bar_root: Path | str = DEFAULT_MODEL_PERFORMANCE_BAR_ROOT,
    cache_dir: Path | str = DEFAULT_MODEL_PERFORMANCE_CACHE_DIR,
    generated_at: datetime | None = None,
) -> ModelPerformancePayload:
    """Build an equity curve for a stored research model comparison."""

    clean_model_key = model_key.strip()
    clean_universe_id = universe_id.strip() if universe_id else None
    if not clean_model_key:
        raise ValueError("model_key is required")
    sources = _comparison_sources_for_model(
        clean_model_key,
        universe_id=clean_universe_id,
        replay_report_dir=Path(replay_report_dir),
    )
    if not sources:
        suffix = f" in universe {clean_universe_id}" if clean_universe_id else ""
        raise ValueError(
            f"no stored comparison report contains {clean_model_key}{suffix}"
        )
    source = _select_longest_source(sources)
    cache_path = _cache_path(
        cache_dir=Path(cache_dir),
        model_key=clean_model_key,
        universe_id=source.universe_id,
        source=source,
    )
    cached = _read_cached_payload(cache_path)
    if cached is not None:
        return cached

    (
        strategy,
        strategy_name,
        symbol_universe,
        benchmark,
        definition,
    ) = _strategy_for_source(clean_model_key, source)
    result, feed, decision_frequency, execution_price = _run_replay(
        model_key=clean_model_key,
        strategy=strategy,
        symbol_universe=symbol_universe,
        benchmark=benchmark,
        source=source,
        bar_root=Path(bar_root),
        generated_at=generated_at,
    )
    points = _performance_points(result.equity_curve, result.config.starting_cash)
    recent_windows = _recent_window_payloads(points)
    recent_summary = late_entry_risk_summary(
        assess_recent_window_concentration(_return_curve_points(points))
    )
    payload = ModelPerformancePayload(
        model_key=clean_model_key,
        strategy_id=clean_model_key.split(":", 1)[0],
        version=clean_model_key.split(":", 1)[1] if ":" in clean_model_key else "",
        strategy_name=strategy_name,
        universe_id=source.universe_id,
        benchmark=benchmark,
        data_feed=feed.value,
        decision_frequency=decision_frequency.value,
        execution_price=execution_price.value,
        start_date=result.config.start_date,
        end_date=result.equity_curve[-1].trading_date,
        generated_at=result.generated_at,
        source_report=str(source.path),
        source_run_id=source.run_id,
        source_rank=_int_or_none(source.row.get("rank")),
        source_research_score=_float_or_none(source.row.get("research_score")),
        window_policy="longest stored full-period comparison for this model",
        available_window_count=len(sources),
        strategy_profile=_strategy_profile(definition, symbol_universe),
        recent_windows=recent_windows,
        late_entry_risk=recent_summary is not None,
        late_entry_risk_summary=recent_summary,
        metrics=result.metrics,
        points=points,
    )
    _write_cached_payload(cache_path, payload)
    return payload


def _comparison_sources_for_model(
    model_key: str,
    *,
    universe_id: str | None,
    replay_report_dir: Path,
) -> tuple[_ComparisonSource, ...]:
    if not replay_report_dir.exists():
        return ()
    sources: list[_ComparisonSource] = []
    for path in replay_report_dir.glob("*-full-base-comparison.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if model_key not in text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        inferred_universe_id = _universe_id_from_report_path(path)
        if universe_id and inferred_universe_id != universe_id:
            continue
        rows = [
            row
            for row in payload.get("rows", [])
            if isinstance(row, dict) and row.get("model_key") == model_key
        ]
        if not rows:
            continue
        try:
            source = _comparison_source_from_payload(
                path=path,
                payload=payload,
                universe_id=inferred_universe_id,
                row=rows[0],
            )
        except (KeyError, ValueError, TypeError):
            continue
        sources.append(source)
    return tuple(sources)


def _comparison_source_from_payload(
    *,
    path: Path,
    payload: dict[str, Any],
    universe_id: str | None,
    row: dict[str, Any],
) -> _ComparisonSource:
    return _ComparisonSource(
        path=path,
        run_id=str(payload["run_id"]),
        generated_at=_parse_datetime(
            payload.get("generated_at"),
            fallback=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        ),
        start_date=date.fromisoformat(str(payload["start_date"])),
        end_date=date.fromisoformat(str(payload["end_date"])),
        benchmark=validate_symbol(str(payload.get("benchmark") or "SPY")),
        universe_id=universe_id,
        row=row,
    )


def _select_longest_source(
    sources: tuple[_ComparisonSource, ...],
) -> _ComparisonSource:
    return max(
        sources,
        key=lambda source: (
            (source.end_date - source.start_date).days,
            source.end_date,
            source.generated_at,
            -int(source.row.get("rank") or 999999),
        ),
    )


def _strategy_for_source(
    model_key: str,
    source: _ComparisonSource,
):
    definition = _definition_for_source(model_key, source)
    if definition is not None:
        strategy_id = str(definition.strategy_id)
        factory = default_strategy_factories().get(strategy_id)
        if factory is None:
            raise ValueError(f"no strategy factory registered for {strategy_id}")
        strategy = factory(definition.parameters)
        symbol_universe = tuple(
            validate_symbol(symbol)
            for symbol in definition.universe
            if validate_symbol(symbol) != definition.benchmark
        )
        return (
            strategy,
            str(definition.name),
            symbol_universe,
            validate_symbol(str(definition.benchmark)),
            definition,
        )

    strategy = build_paper_strategy(model_key)
    benchmark = validate_symbol(str(getattr(strategy, "benchmark", source.benchmark)))
    raw_symbols = tuple(
        getattr(strategy, "required_symbols", getattr(strategy, "universe", ()))
    )
    symbol_universe = tuple(
        symbol
        for symbol in (validate_symbol(symbol) for symbol in raw_symbols)
        if symbol != benchmark
    )
    if not symbol_universe:
        raise ValueError(f"model {model_key} has no replay symbol universe")
    strategy_name = str(getattr(strategy, "strategy_id", model_key.split(":", 1)[0]))
    return strategy, strategy_name, symbol_universe, benchmark, None


def _strategy_profile(
    definition,
    symbol_universe: tuple[str, ...],
) -> ModelStrategyProfile | None:
    if definition is None:
        return None
    parameters = {
        key: _parameter_text(value)
        for key, value in definition.parameters.items()
        if key not in ("universe", "benchmark")
    }
    return ModelStrategyProfile(
        hypothesis=str(definition.hypothesis),
        trading_cadence=str(definition.trading_cadence.value),
        holding_period=str(definition.holding_period),
        signal_logic=str(definition.signal_logic),
        sizing_logic=str(definition.sizing_logic),
        exit_logic=str(definition.exit_logic),
        invests_in=symbol_universe,
        failure_modes=tuple(str(mode) for mode in definition.failure_modes),
        parameters=parameters,
    )


def _parameter_text(value: object) -> str:
    if isinstance(value, (tuple, list)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _definition_for_source(model_key: str, source: _ComparisonSource):
    universes = _candidate_universes(source)
    for _universe_id, symbols in universes:
        catalog = _autonomous_catalog(
            symbols=symbols,
            benchmark=source.benchmark,
            mode=AutonomousLearningCycleMode.WEEKLY,
        )
        for definition in catalog.all():
            if f"{definition.strategy_id}:{definition.version}" == model_key:
                return definition
    return None


def _candidate_universes(
    source: _ComparisonSource,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if source.universe_id and source.universe_id in DISCOVERY_UNIVERSES:
        primary = (source.universe_id, DISCOVERY_UNIVERSES[source.universe_id])
        rest = tuple(
            (universe_id, symbols)
            for universe_id, symbols in DISCOVERY_UNIVERSES.items()
            if universe_id != source.universe_id
        )
        return (primary, *rest)
    return tuple(DISCOVERY_UNIVERSES.items())


def _run_replay(
    *,
    model_key: str,
    strategy: object,
    symbol_universe: tuple[str, ...],
    benchmark: str,
    source: _ComparisonSource,
    bar_root: Path,
    generated_at: datetime | None,
):
    data_start = source.start_date - timedelta(days=DEFAULT_WARMUP_CALENDAR_DAYS)
    query = DuckDBBarQuery(bar_root)
    best = None
    best_score = float("inf")
    for feed in (DataFeed.SIP, DataFeed.IEX):
        bars = query.load_daily_bars(
            list(symbol_universe),
            data_start,
            source.end_date,
            feed,
        )
        benchmark_bars = query.load_daily_bars(
            [benchmark],
            data_start,
            source.end_date,
            feed,
        )
        if _missing_symbols(symbol_universe, bars) or _missing_symbols(
            (benchmark,),
            benchmark_bars,
        ):
            continue
        for decision_frequency in _decision_frequency_candidates(source):
            for execution_price in _execution_price_candidates():
                config = ReplayConfig(
                    run_id=f"model-performance-{_slug(model_key)}",
                    start_date=source.start_date,
                    end_date=source.end_date,
                    symbol_universe=symbol_universe,
                    benchmark=benchmark,
                    decision_frequency=decision_frequency,
                    warmup_trading_days=DEFAULT_WARMUP_TRADING_DAYS,
                    starting_cash=DEFAULT_STARTING_CASH,
                    slippage_bps=Decimal("5"),
                    execution_price=execution_price,
                    data_feed=feed,
                )
                result = HistoricalReplayRunner().run(
                    policy=StrategyReplayPolicy(strategy, key=model_key),
                    bars=bars,
                    benchmark_bars=benchmark_bars,
                    config=config,
                    generated_at=generated_at,
                )
                score = _stored_row_fit_score(result.metrics, source.row)
                if score < best_score:
                    best_score = score
                    best = (result, feed, decision_frequency, execution_price)
                if score < 0.000001:
                    return result, feed, decision_frequency, execution_price
    if best is not None:
        return best
    raise ValueError(
        f"stored daily bars are missing for {', '.join((*symbol_universe, benchmark))}"
    )


def _decision_frequency_candidates(
    source: _ComparisonSource,
) -> tuple[ReplayDecisionFrequency, ...]:
    decision_count = _int_or_none(source.row.get("decision_count"))
    if decision_count is not None and decision_count < 500:
        return (
            ReplayDecisionFrequency.MONTH_START,
            ReplayDecisionFrequency.DAILY,
        )
    return (
        ReplayDecisionFrequency.DAILY,
        ReplayDecisionFrequency.MONTH_START,
    )


def _execution_price_candidates() -> tuple[ReplayExecutionPrice, ...]:
    return (ReplayExecutionPrice.CLOSE, ReplayExecutionPrice.OPEN)


def _stored_row_fit_score(metrics: ReplayMetrics, row: dict[str, Any]) -> float:
    score = 0.0
    for attr, key in (
        ("net_total_return", "net_total_return"),
        ("benchmark_total_return", "benchmark_total_return"),
        ("excess_return", "excess_return"),
        ("max_drawdown", "max_drawdown"),
    ):
        expected = _float_or_none(row.get(key))
        if expected is not None:
            score += abs(float(getattr(metrics, attr)) - expected)
    expected_trades = _int_or_none(row.get("trade_count"))
    if expected_trades is not None:
        score += abs(metrics.trade_count - expected_trades) / 1000
    expected_decisions = _int_or_none(row.get("decision_count"))
    if expected_decisions is not None:
        score += abs(metrics.decision_count - expected_decisions) / 1000
    return score


def _performance_points(
    equity_curve,
    starting_cash: Decimal,
) -> tuple[ModelPerformancePoint, ...]:
    points: list[ModelPerformancePoint] = []
    for point in equity_curve:
        model_return = point.equity / starting_cash - Decimal("1")
        benchmark_return = point.benchmark_equity / starting_cash - Decimal("1")
        points.append(
            ModelPerformancePoint(
                trading_date=point.trading_date,
                model_equity=float(point.equity),
                benchmark_equity=float(point.benchmark_equity),
                model_return=float(model_return),
                benchmark_return=float(benchmark_return),
                excess_return=float(model_return - benchmark_return),
            )
        )
    return tuple(points)


def _return_curve_points(
    points: tuple[ModelPerformancePoint, ...],
) -> tuple[ReturnCurvePoint, ...]:
    return tuple(
        ReturnCurvePoint(
            trading_date=point.trading_date,
            model_return=point.model_return,
            benchmark_return=point.benchmark_return,
            excess_return=point.excess_return,
        )
        for point in points
    )


def _recent_window_payloads(
    points: tuple[ModelPerformancePoint, ...],
) -> tuple[ModelPerformanceRecentWindow, ...]:
    assessments = assess_recent_window_concentration(_return_curve_points(points))
    return tuple(
        ModelPerformanceRecentWindow(
            trading_days=assessment.trading_days,
            start_date=assessment.start_date,
            end_date=assessment.end_date,
            model_return_delta=assessment.model_return_delta,
            benchmark_return_delta=assessment.benchmark_return_delta,
            excess_return_delta=assessment.excess_return_delta,
            excess_contribution_share=assessment.excess_contribution_share,
            late_entry_risk=assessment.late_entry_risk,
        )
        for assessment in assessments
    )


def _missing_symbols(symbols: tuple[str, ...], bars) -> tuple[str, ...]:
    present = {bar.symbol for bar in bars}
    return tuple(symbol for symbol in symbols if symbol not in present)


def _universe_id_from_report_path(path: Path) -> str | None:
    suffix = "-full-base-comparison.json"
    name = path.name
    if not name.endswith(suffix):
        return None
    stem = name[: -len(suffix)]
    for universe_id in sorted(DISCOVERY_UNIVERSES, key=len, reverse=True):
        marker = f"-{universe_id}"
        if stem.endswith(marker):
            return universe_id
    return None


def _parse_datetime(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return fallback


def _cache_path(
    *,
    cache_dir: Path,
    model_key: str,
    universe_id: str | None,
    source: _ComparisonSource,
) -> Path:
    fingerprint = "|".join(
        (
            MODEL_PERFORMANCE_CACHE_VERSION,
            model_key,
            universe_id or "",
            source.path.name,
            str(source.path.stat().st_mtime_ns),
            source.start_date.isoformat(),
            source.end_date.isoformat(),
        )
    )
    return cache_dir / f"{sha256(fingerprint.encode()).hexdigest()}.json"


def _read_cached_payload(path: Path) -> ModelPerformancePayload | None:
    if not path.exists():
        return None
    try:
        return ModelPerformancePayload.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return None


def _write_cached_payload(path: Path, payload: ModelPerformancePayload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value)


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
