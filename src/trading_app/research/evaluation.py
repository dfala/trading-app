"""Reproducible research evidence for implemented strategy hypotheses."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, Field

from trading_app.backtest import BacktestConfig, BacktestResult, BacktestRunner
from trading_app.learning import (
    ModelArena,
    ModelComparisonResult,
    ModelEvidenceRecord,
    ModelEvidenceType,
    ModelMetricSet,
    ModelRegistry,
    ModelRegistryState,
    ModelVersionRecord,
)
from trading_app.schemas import DailyBar, TradingModel
from trading_app.strategies import (
    StrategyCatalog,
    StrategyDefinition,
    StrategyImplementationStatus,
    strategy_definition_metadata,
)
from trading_app.strategies.benchmark_relative import (
    BenchmarkRelativeStrengthETFStrategy,
)
from trading_app.strategies.cash_rotation import CashRotationETFStrategy
from trading_app.strategies.defensive_regime import DefensiveRegimeSwitchETFStrategy
from trading_app.strategies.mean_reversion import MeanReversionETFStrategy
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy
from trading_app.strategies.trend_following import TrendFollowingETFStrategy
from trading_app.strategies.volatility_aware import VolatilityAwareETFStrategy

StrategyFactory = Callable[[dict[str, Any]], object]


class StrategyResearchSkippedDefinition(TradingModel):
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class StrategyResearchReport(TradingModel):
    as_of: AwareDatetime
    champion_key: str = Field(min_length=1)
    evaluated_model_keys: tuple[str, ...]
    skipped_definitions: tuple[StrategyResearchSkippedDefinition, ...] = ()
    evidence: tuple[ModelEvidenceRecord, ...]
    comparisons: tuple[ModelComparisonResult, ...]
    active_model_unchanged: bool
    summary: str = Field(min_length=1)


class StrategyResearchEvaluationRunner:
    """Evaluate implemented strategy cards and produce model evidence."""

    def __init__(
        self,
        *,
        factories: dict[str, StrategyFactory] | None = None,
        backtest_runner: BacktestRunner | None = None,
    ) -> None:
        self.factories = factories or default_strategy_factories()
        self.backtest_runner = backtest_runner or BacktestRunner()

    def run(
        self,
        *,
        catalog: StrategyCatalog,
        champion_strategy_id: str,
        champion_version: str,
        bars: tuple[DailyBar, ...] | list[DailyBar],
        benchmark_bars: tuple[DailyBar, ...] | list[DailyBar],
        as_of: datetime,
        config: BacktestConfig | None = None,
    ) -> StrategyResearchReport:
        resolved_config = config or BacktestConfig()
        champion_definition = catalog.get(champion_strategy_id, champion_version)
        registry = ModelRegistry()
        champion = registry.register(
            _model_record(
                champion_definition,
                state=ModelRegistryState.PAPER,
                created_at=as_of,
                is_active=True,
            )
        )
        active_before = registry.snapshot(as_of).active_keys
        arena = ModelArena(registry=registry)
        evidence_records: list[ModelEvidenceRecord] = []
        comparisons: list[ModelComparisonResult] = []
        skipped: list[StrategyResearchSkippedDefinition] = []

        champion_evidence = self._evaluate_definition(
            definition=champion_definition,
            model=champion,
            bars=tuple(bars),
            benchmark_bars=tuple(benchmark_bars),
            as_of=as_of,
            config=resolved_config,
        )
        arena.record_evidence(champion_evidence)
        evidence_records.append(champion_evidence)

        for definition in catalog.all():
            if definition.strategy_id == champion_strategy_id and (
                definition.version == champion_version
            ):
                continue
            if (
                definition.implementation_status
                != StrategyImplementationStatus.IMPLEMENTED
            ):
                skipped.append(
                    StrategyResearchSkippedDefinition(
                        strategy_id=definition.strategy_id,
                        version=definition.version,
                        reason="Strategy card is not implemented yet.",
                    )
                )
                continue
            if definition.strategy_id not in self.factories:
                skipped.append(
                    StrategyResearchSkippedDefinition(
                        strategy_id=definition.strategy_id,
                        version=definition.version,
                        reason="No research evaluation factory is registered.",
                    )
                )
                continue

            candidate = registry.register(
                _model_record(
                    definition,
                    state=ModelRegistryState.BACKTEST,
                    created_at=as_of,
                    is_active=False,
                )
            )
            evidence = self._evaluate_definition(
                definition=definition,
                model=candidate,
                bars=tuple(bars),
                benchmark_bars=tuple(benchmark_bars),
                as_of=as_of,
                config=resolved_config,
            )
            arena.record_evidence(evidence)
            evidence_records.append(evidence)
            comparisons.append(
                arena.compare(
                    champion=champion,
                    challenger=candidate,
                    champion_evidence_id=champion_evidence.id,
                    challenger_evidence_id=evidence.id,
                )
            )

        active_after = registry.snapshot(as_of).active_keys
        evaluated_model_keys = tuple(record.model_key for record in evidence_records)
        return StrategyResearchReport(
            as_of=as_of,
            champion_key=champion.key,
            evaluated_model_keys=evaluated_model_keys,
            skipped_definitions=tuple(skipped),
            evidence=tuple(evidence_records),
            comparisons=tuple(comparisons),
            active_model_unchanged=active_before == active_after,
            summary=_summary(
                champion_key=champion.key,
                evaluated=len(evidence_records),
                skipped=len(skipped),
                comparisons=len(comparisons),
            ),
        )

    def _evaluate_definition(
        self,
        *,
        definition: StrategyDefinition,
        model: ModelVersionRecord,
        bars: tuple[DailyBar, ...],
        benchmark_bars: tuple[DailyBar, ...],
        as_of: datetime,
        config: BacktestConfig,
    ) -> ModelEvidenceRecord:
        factory = self.factories.get(definition.strategy_id)
        if factory is None:
            raise ValueError(f"missing strategy factory: {definition.strategy_id}")
        strategy = factory(definition.parameters)
        result = self.backtest_runner.run(
            strategy=strategy,
            bars=bars,
            benchmark_bars=benchmark_bars,
            config=config,
        )
        return _evidence_from_backtest(
            definition=definition,
            model=model,
            result=result,
            as_of=as_of,
        )


def default_strategy_factories() -> dict[str, StrategyFactory]:
    return {
        "monthly_sector_momentum": _monthly_sector_momentum_factory,
        "trend_following_etf": _trend_following_factory,
        "mean_reversion_etf": _mean_reversion_factory,
        "volatility_aware_etf": _volatility_aware_factory,
        "benchmark_relative_strength_etf": _benchmark_relative_factory,
        "defensive_regime_switch": _defensive_regime_factory,
        "cash_rotation_model": _cash_rotation_factory,
    }


def _monthly_sector_momentum_factory(parameters: dict[str, Any]):
    return MonthlySectorMomentumStrategy(
        universe=tuple(parameters["universe"]),
        lookback_days=int(parameters["lookback_days"]),
        top_n=int(parameters["top_n"]),
    )


def _trend_following_factory(parameters: dict[str, Any]):
    return TrendFollowingETFStrategy(
        universe=tuple(parameters["universe"]),
        trend_window_days=int(parameters["trend_window_days"]),
        top_n=int(parameters["top_n"]),
        min_trend_return=Decimal(str(parameters.get("min_trend_return", "0"))),
    )


def _mean_reversion_factory(parameters: dict[str, Any]):
    return MeanReversionETFStrategy(
        universe=tuple(parameters["universe"]),
        reversion_window_days=int(parameters["reversion_window_days"]),
        trend_filter_days=int(parameters["trend_filter_days"]),
        top_n=int(parameters["top_n"]),
        max_short_return=Decimal(str(parameters.get("max_short_return", "0"))),
    )


def _volatility_aware_factory(parameters: dict[str, Any]):
    max_volatility = parameters.get("max_volatility")
    return VolatilityAwareETFStrategy(
        universe=tuple(parameters["universe"]),
        lookback_days=int(parameters["lookback_days"]),
        volatility_window_days=int(parameters["volatility_window_days"]),
        top_n=int(parameters["top_n"]),
        min_trailing_return=Decimal(str(parameters.get("min_trailing_return", "0"))),
        max_volatility=(
            Decimal(str(max_volatility)) if max_volatility is not None else None
        ),
        volatility_floor=Decimal(str(parameters.get("volatility_floor", "0.000001"))),
    )


def _benchmark_relative_factory(parameters: dict[str, Any]):
    return BenchmarkRelativeStrengthETFStrategy(
        universe=tuple(parameters["universe"]),
        benchmark=str(parameters.get("benchmark", "SPY")),
        lookback_days=int(parameters["lookback_days"]),
        tracking_window_days=int(parameters["tracking_window_days"]),
        top_n=int(parameters["top_n"]),
        min_excess_return=Decimal(str(parameters.get("min_excess_return", "0"))),
        min_absolute_return=Decimal(str(parameters.get("min_absolute_return", "0"))),
        tracking_error_floor=Decimal(
            str(parameters.get("tracking_error_floor", "0.000001"))
        ),
    )


def _defensive_regime_factory(parameters: dict[str, Any]):
    return DefensiveRegimeSwitchETFStrategy(
        universe=tuple(parameters["universe"]),
        defensive_symbols=tuple(parameters["defensive_symbols"]),
        benchmark=str(parameters.get("benchmark", "SPY")),
        regime_lookback_days=int(parameters["regime_lookback_days"]),
        risk_on_top_n=int(parameters["risk_on_top_n"]),
        risk_off_top_n=int(parameters["risk_off_top_n"]),
        max_benchmark_drawdown=Decimal(
            str(parameters.get("max_benchmark_drawdown", "-0.10"))
        ),
        min_benchmark_return=Decimal(str(parameters.get("min_benchmark_return", "0"))),
        min_defensive_return=Decimal(str(parameters.get("min_defensive_return", "0"))),
    )


def _cash_rotation_factory(parameters: dict[str, Any]):
    return CashRotationETFStrategy(
        universe=tuple(parameters["universe"]),
        lookback_days=int(parameters["lookback_days"]),
        top_n=int(parameters["top_n"]),
        min_symbol_return=Decimal(str(parameters.get("min_symbol_return", "0"))),
        min_breadth=Decimal(str(parameters.get("min_breadth", "0.40"))),
        min_average_top_return=Decimal(
            str(parameters.get("min_average_top_return", "0.02"))
        ),
    )


def _model_record(
    definition: StrategyDefinition,
    *,
    state: ModelRegistryState,
    created_at: datetime,
    is_active: bool,
) -> ModelVersionRecord:
    return ModelVersionRecord(
        strategy_id=definition.strategy_id,
        version=definition.version,
        state=state,
        parameters=definition.parameters,
        hypothesis=definition.hypothesis,
        created_at=created_at,
        is_active=is_active,
        metadata=strategy_definition_metadata(definition),
    )


def _evidence_from_backtest(
    *,
    definition: StrategyDefinition,
    model: ModelVersionRecord,
    result: BacktestResult,
    as_of: datetime,
) -> ModelEvidenceRecord:
    return ModelEvidenceRecord(
        id=f"research-{model.strategy_id}-{model.version}-{as_of.date().isoformat()}",
        model_key=model.key,
        evidence_type=ModelEvidenceType.BACKTEST,
        recorded_at=as_of,
        start_date=result.equity_curve[0].trading_date,
        end_date=result.equity_curve[-1].trading_date,
        benchmark=definition.benchmark,
        data_source=",".join(result.data_sources),
        metrics=ModelMetricSet(
            gross_total_return=result.gross_total_return,
            net_total_return=result.net_total_return,
            benchmark_total_return=result.benchmark_total_return,
            max_drawdown=result.max_drawdown,
            annualized_volatility=result.annualized_volatility,
            turnover=result.turnover,
            trade_count=result.trade_count,
            average_holding_period_days=result.average_holding_period_days,
            estimated_after_tax_total_return=(
                result.tax_summary.estimated_after_tax_total_return
            ),
        ),
        cost_assumptions={
            "starting_cash": str(result.cost_assumptions.starting_cash),
            "commission_per_trade": str(result.cost_assumptions.commission_per_trade),
            "slippage_bps": str(result.cost_assumptions.slippage_bps),
            "sell_fee_bps": str(result.cost_assumptions.sell_fee_bps),
        },
        tax_assumptions={
            "short_term_tax_rate": (
                str(result.cost_assumptions.short_term_tax_rate)
                if result.cost_assumptions.short_term_tax_rate is not None
                else None
            ),
            "long_term_tax_rate": (
                str(result.cost_assumptions.long_term_tax_rate)
                if result.cost_assumptions.long_term_tax_rate is not None
                else None
            ),
        },
        risk_settings={
            "constraints": definition.constraints,
            "risk_assumptions": definition.risk_assumptions,
        },
        notes=(
            "Research evidence generated by StrategyResearchEvaluationRunner. "
            "This evidence does not grant paper or live trading authority."
        ),
        failure_modes=definition.failure_modes,
    )


def _summary(
    *,
    champion_key: str,
    evaluated: int,
    skipped: int,
    comparisons: int,
) -> str:
    return (
        f"Evaluated {evaluated} implemented model(s) against champion "
        f"{champion_key}; produced {comparisons} comparison(s) and skipped "
        f"{skipped} research idea(s). Active model unchanged."
    )
