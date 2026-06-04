"""Point-in-time historical replay for research model evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps
from math import sqrt
from pathlib import Path
from statistics import mean
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import AwareDatetime, Field, field_validator, model_validator

from trading_app.learning import ModelEvidenceRecord, ModelEvidenceType, ModelMetricSet
from trading_app.ledger import Ledger
from trading_app.market_data import MarketDataQualityChecker, MarketDataQualityReport
from trading_app.risk import ProposedOrder, RiskContext, RiskDecision, RiskEngine
from trading_app.schemas import (
    DailyBar,
    DataFeed,
    Fill,
    Order,
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    TradingModel,
    validate_symbol,
)

BPS_DENOMINATOR = Decimal("10000")
QUANTITY_INCREMENT = Decimal("0.000001")
MARKET_TIMEZONE = ZoneInfo("America/New_York")


class ReplayUniverseKind(StrEnum):
    ETF = "etf"
    STOCK = "stock"


class ReplayDecisionFrequency(StrEnum):
    DAILY = "daily"
    MONTH_START = "month_start"


class ReplayExecutionPrice(StrEnum):
    CLOSE = "close"
    OPEN = "open"


class ReplayPolicyKind(StrEnum):
    STRATEGY = "strategy"
    AI_CHALLENGER = "ai_challenger"


class ReplayAuditStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class ReplayLeakageIssueCode(StrEnum):
    FUTURE_VISIBLE_BAR = "future_visible_bar"
    NO_DECISIONS = "no_decisions"
    AI_DATE_UNMASKED = "ai_date_unmasked"
    AI_SYMBOL_UNMASKED = "ai_symbol_unmasked"


class ReplayConfig(TradingModel):
    """Configuration for daily-bar historical replay."""

    run_id: str = Field(min_length=1)
    start_date: date
    end_date: date
    symbol_universe: tuple[str, ...]
    benchmark: str = "SPY"
    universe_kind: ReplayUniverseKind = ReplayUniverseKind.ETF
    point_in_time_universe: bool = False
    decision_frequency: ReplayDecisionFrequency = ReplayDecisionFrequency.DAILY
    warmup_trading_days: int = Field(default=126, ge=1)
    starting_cash: Decimal = Decimal("100000")
    commission_per_trade: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("5")
    sell_fee_bps: Decimal = Decimal("0")
    execution_price: ReplayExecutionPrice = ReplayExecutionPrice.CLOSE
    min_trade_notional: Decimal = Decimal("1")
    min_trade_weight_delta: Decimal = Decimal("0.005")
    outcome_horizons: tuple[int, ...] = (5, 21, 63)
    data_feed: DataFeed = DataFeed.IEX
    mask_ai_dates: bool = True
    mask_ai_symbols: bool = True

    @field_validator("symbol_universe")
    @classmethod
    def _validate_symbol_universe(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        if not symbols:
            raise ValueError("symbol_universe cannot be empty")
        return tuple(validate_symbol(symbol) for symbol in symbols)

    @field_validator("benchmark")
    @classmethod
    def _validate_benchmark(cls, benchmark: str) -> str:
        return validate_symbol(benchmark)

    @field_validator("outcome_horizons")
    @classmethod
    def _validate_outcome_horizons(cls, horizons: tuple[int, ...]) -> tuple[int, ...]:
        if not horizons:
            raise ValueError("outcome_horizons cannot be empty")
        if any(horizon <= 0 for horizon in horizons):
            raise ValueError("outcome_horizons must be positive")
        return tuple(sorted(set(horizons)))

    @model_validator(mode="after")
    def _validate_replay_config(self) -> ReplayConfig:
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if self.universe_kind == ReplayUniverseKind.STOCK and not (
            self.point_in_time_universe
        ):
            raise ValueError(
                "stock replay requires point_in_time_universe=True to avoid "
                "survivorship bias"
            )
        if self.benchmark in self.symbol_universe:
            raise ValueError("benchmark should be supplied separately from universe")
        return self


class ReplayPolicyDecision(TradingModel):
    """Target weights produced by a replay policy."""

    target_weights: dict[str, Decimal] = Field(default_factory=dict)
    explanation: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayFeatureSnapshot(TradingModel):
    as_of: date
    visible_start: date | None
    visible_end: date | None
    symbols: tuple[str, ...]
    features_by_symbol: dict[str, dict[str, Decimal]]
    feature_hash: str = Field(min_length=1)


class ReplayDecisionContext(TradingModel):
    """Policy-visible decision packet with no same-day or future prices."""

    run_id: str = Field(min_length=1)
    sequence_index: int = Field(ge=0)
    as_of: date
    visible_bars: tuple[DailyBar, ...]
    feature_snapshot: ReplayFeatureSnapshot
    portfolio: PortfolioSnapshot
    symbol_aliases: dict[str, str]
    mask_ai_dates: bool
    mask_ai_symbols: bool


class AIReplayDecisionPacket(TradingModel):
    """Masked structured packet for AI challenger experiments."""

    policy_key: str = Field(min_length=1)
    market_day_label: str = Field(min_length=1)
    as_of: date | None = None
    symbols: tuple[str, ...]
    features_by_symbol: dict[str, dict[str, Decimal]]
    portfolio_weights: dict[str, Decimal]
    instructions: str = Field(min_length=1)


class ReplayOrderPlan(TradingModel):
    order_id: str = Field(min_length=1)
    symbol: str
    side: OrderSide
    quantity: Decimal
    estimated_price: Decimal
    estimated_notional: Decimal
    approved: bool
    rejection_rules: tuple[str, ...] = ()

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class ReplayTrade(TradingModel):
    decision_id: str = Field(min_length=1)
    trading_date: date
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fees: Decimal
    gross_value: Decimal
    order_id: str = Field(min_length=1)
    fill_id: str = Field(min_length=1)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class ReplayOutcome(TradingModel):
    symbol: str
    horizon_trading_days: int = Field(gt=0)
    start_price: Decimal
    end_price: Decimal | None = None
    realized_return: float | None = None
    available_on: date | None = None

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class ReplayDecision(TradingModel):
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    sequence_index: int = Field(ge=0)
    as_of: date
    policy_key: str = Field(min_length=1)
    policy_kind: ReplayPolicyKind
    visible_data_start: date | None
    visible_data_end: date | None
    feature_snapshot_hash: str = Field(min_length=1)
    target_weights: dict[str, Decimal]
    order_plans: tuple[ReplayOrderPlan, ...]
    explanation: str = Field(min_length=1)
    outcomes: tuple[ReplayOutcome, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayEquityPoint(TradingModel):
    trading_date: date
    equity: Decimal
    benchmark_equity: Decimal


class ReplayMetrics(TradingModel):
    net_total_return: float
    benchmark_total_return: float
    excess_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    turnover: float
    trade_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)


class ReplayLeakageIssue(TradingModel):
    code: ReplayLeakageIssueCode
    status: ReplayAuditStatus
    message: str = Field(min_length=1)
    decision_id: str | None = None
    as_of: date | None = None
    evidence: tuple[str, ...] = ()


class ReplayLeakageAudit(TradingModel):
    status: ReplayAuditStatus
    passed: bool
    decision_count: int = Field(ge=0)
    max_visible_date: date | None
    issues: tuple[ReplayLeakageIssue, ...] = ()
    summary: str = Field(min_length=1)


class ReplayRunResult(TradingModel):
    run_id: str = Field(min_length=1)
    generated_at: AwareDatetime
    config: ReplayConfig
    policy_key: str = Field(min_length=1)
    policy_kind: ReplayPolicyKind
    decisions: tuple[ReplayDecision, ...]
    trades: tuple[ReplayTrade, ...]
    risk_decisions: tuple[RiskDecision, ...]
    equity_curve: tuple[ReplayEquityPoint, ...]
    metrics: ReplayMetrics
    leakage_audit: ReplayLeakageAudit
    data_quality_report: MarketDataQualityReport
    model_evidence: ModelEvidenceRecord


class ReplayDecisionPolicy(Protocol):
    key: str
    kind: ReplayPolicyKind

    def generate_decision(self, context: ReplayDecisionContext) -> ReplayPolicyDecision:
        """Generate target weights from point-in-time visible data."""


class StrategyReplayPolicy:
    """Replay adapter for existing deterministic strategy implementations."""

    kind = ReplayPolicyKind.STRATEGY

    def __init__(self, strategy, *, key: str | None = None) -> None:
        self.strategy = strategy
        self.key = key or _strategy_key(strategy)

    def generate_decision(self, context: ReplayDecisionContext) -> ReplayPolicyDecision:
        if hasattr(self.strategy, "generate_targets_with_metadata"):
            targets, explanation, metadata = (
                self.strategy.generate_targets_with_metadata(
                    context.visible_bars,
                    context.as_of,
                )
            )
            return ReplayPolicyDecision(
                target_weights=targets,
                explanation=explanation,
                metadata={"adapter": "strategy", **metadata},
            )

        targets = self.strategy.generate_targets(context.visible_bars, context.as_of)
        return ReplayPolicyDecision(
            target_weights=targets,
            explanation=(
                f"Deterministic strategy {self.key} generated point-in-time targets "
                f"using bars before {context.as_of.isoformat()}."
            ),
            metadata={"adapter": "strategy"},
        )


class CallableAIReplayPolicy:
    """AI challenger adapter with mandatory structured packets and masking support."""

    kind = ReplayPolicyKind.AI_CHALLENGER

    def __init__(
        self,
        *,
        key: str,
        decision_fn: Callable[[AIReplayDecisionPacket], ReplayPolicyDecision],
        instructions: str,
    ) -> None:
        self.key = key
        self._decision_fn = decision_fn
        self.instructions = instructions

    def generate_decision(self, context: ReplayDecisionContext) -> ReplayPolicyDecision:
        actual_to_packet = (
            context.symbol_aliases
            if context.mask_ai_symbols
            else {symbol: symbol for symbol in context.feature_snapshot.symbols}
        )
        packet_to_actual = {alias: symbol for symbol, alias in actual_to_packet.items()}
        packet = AIReplayDecisionPacket(
            policy_key=self.key,
            market_day_label=(
                f"replay_day_{context.sequence_index:05d}"
                if context.mask_ai_dates
                else context.as_of.isoformat()
            ),
            as_of=None if context.mask_ai_dates else context.as_of,
            symbols=tuple(
                actual_to_packet[s] for s in context.feature_snapshot.symbols
            ),
            features_by_symbol={
                actual_to_packet[symbol]: values
                for symbol, values in (
                    context.feature_snapshot.features_by_symbol.items()
                )
            },
            portfolio_weights=_portfolio_weights_for_packet(context, actual_to_packet),
            instructions=self.instructions,
        )
        raw = self._decision_fn(packet)
        mapped_targets = {
            packet_to_actual.get(symbol_or_alias, symbol_or_alias): weight
            for symbol_or_alias, weight in raw.target_weights.items()
        }
        return ReplayPolicyDecision(
            target_weights=mapped_targets,
            explanation=raw.explanation,
            metadata={
                **raw.metadata,
                "ai_packet_masked_date": context.mask_ai_dates,
                "ai_packet_masked_symbols": context.mask_ai_symbols,
                "ai_packet_symbol_count": len(packet.symbols),
            },
        )


class HistoricalReplayRunner:
    """Run a leakage-audited historical replay over daily bars."""

    def run(
        self,
        *,
        policy: ReplayDecisionPolicy,
        bars: tuple[DailyBar, ...] | list[DailyBar],
        benchmark_bars: tuple[DailyBar, ...] | list[DailyBar],
        config: ReplayConfig,
        risk_engine: RiskEngine | None = None,
        generated_at: datetime | None = None,
    ) -> ReplayRunResult:
        generated = _aware_generated_at(generated_at)
        universe_bars = tuple(sorted(bars, key=_bar_sort_key))
        benchmark = tuple(sorted(benchmark_bars, key=_bar_sort_key))
        policy_bars = tuple(
            sorted(tuple(universe_bars) + tuple(benchmark), key=_bar_sort_key)
        )
        _require_replay_inputs(universe_bars, benchmark, config)

        active_risk_engine = risk_engine or RiskEngine()
        ledger = Ledger(config.starting_cash)
        bars_by_date = _bars_by_date(universe_bars)
        bars_by_symbol = _bars_by_symbol(tuple(universe_bars) + tuple(benchmark))
        trading_dates = [
            trading_day
            for trading_day in sorted(bars_by_date)
            if config.start_date <= trading_day <= config.end_date
        ]
        if not trading_dates:
            raise ValueError("bars contain no trading dates in the replay range")
        if trading_dates[0] > config.start_date + timedelta(days=7):
            raise ValueError(
                "universe bars do not cover the replay start date: "
                f"requested {config.start_date.isoformat()}, first available "
                f"{trading_dates[0].isoformat()}"
            )

        evaluation_benchmark = tuple(
            bar
            for bar in benchmark
            if trading_dates[0] <= bar.trading_date <= config.end_date
        )
        if not evaluation_benchmark:
            raise ValueError("benchmark_bars contain no replay-range dates")
        benchmark_by_date = _bars_by_date(evaluation_benchmark)
        decision_dates = _decision_dates(
            trading_dates,
            frequency=config.decision_frequency,
        )
        symbol_aliases = _symbol_aliases(config.symbol_universe)

        decisions: list[ReplayDecision] = []
        trades: list[ReplayTrade] = []
        equity_curve: list[ReplayEquityPoint] = []
        last_prices: dict[str, Decimal] = {}
        trade_index = 0

        for trading_day in trading_dates:
            close_prices = {
                symbol: bar.close_price
                for symbol, bar in bars_by_date[trading_day].items()
            }
            execution_prices = {
                symbol: _execution_bar_price(bar, config)
                for symbol, bar in bars_by_date[trading_day].items()
            }
            benchmark_bar = benchmark_by_date.get(trading_day, {}).get(config.benchmark)
            if benchmark_bar is not None:
                close_prices[config.benchmark] = benchmark_bar.close_price
                execution_prices[config.benchmark] = _execution_bar_price(
                    benchmark_bar,
                    config,
                )
            last_prices.update(close_prices)

            if trading_day in decision_dates and _has_warmup(
                universe_bars,
                trading_day,
                config.warmup_trading_days,
            ):
                visible_bars = tuple(
                    bar for bar in policy_bars if bar.trading_date < trading_day
                )
                feature_snapshot = _feature_snapshot(
                    config=config,
                    visible_bars=visible_bars,
                    as_of=trading_day,
                )
                context = ReplayDecisionContext(
                    run_id=config.run_id,
                    sequence_index=len(decisions),
                    as_of=trading_day,
                    visible_bars=visible_bars,
                    feature_snapshot=feature_snapshot,
                    portfolio=ledger.snapshot(_as_dt(trading_day)),
                    symbol_aliases=symbol_aliases,
                    mask_ai_dates=config.mask_ai_dates,
                    mask_ai_symbols=config.mask_ai_symbols,
                )
                policy_decision = policy.generate_decision(context)
                targets = _validated_targets(policy_decision.target_weights, config)
                decision_id = (
                    f"{config.run_id}-{len(decisions):05d}-{trading_day.isoformat()}"
                )
                trade_index, order_plans = _rebalance(
                    ledger=ledger,
                    trades=trades,
                    trade_index=trade_index,
                    decision_id=decision_id,
                    trading_day=trading_day,
                    prices=execution_prices,
                    targets=targets,
                    config=config,
                    policy_key=policy.key,
                    risk_engine=active_risk_engine,
                )
                decisions.append(
                    ReplayDecision(
                        id=decision_id,
                        run_id=config.run_id,
                        sequence_index=len(decisions),
                        as_of=trading_day,
                        policy_key=policy.key,
                        policy_kind=policy.kind,
                        visible_data_start=feature_snapshot.visible_start,
                        visible_data_end=feature_snapshot.visible_end,
                        feature_snapshot_hash=feature_snapshot.feature_hash,
                        target_weights=targets,
                        order_plans=tuple(order_plans),
                        explanation=policy_decision.explanation,
                        outcomes=_decision_outcomes(
                            as_of=trading_day,
                            targets=targets,
                            config=config,
                            bars_by_symbol=bars_by_symbol,
                        ),
                        metadata=policy_decision.metadata,
                    )
                )

            equity_curve.append(
                ReplayEquityPoint(
                    trading_date=trading_day,
                    equity=_mark_to_market(ledger, last_prices, trading_day),
                    benchmark_equity=_benchmark_equity(
                        benchmark_by_date=benchmark_by_date,
                        trading_date=trading_day,
                        starting_cash=config.starting_cash,
                    ),
                )
            )

        metrics = _metrics(
            config=config,
            decisions=tuple(decisions),
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
        )
        leakage_audit = _leakage_audit(
            decisions=tuple(decisions),
            policy_kind=policy.kind,
            config=config,
        )
        all_bars = tuple(universe_bars) + tuple(benchmark)
        data_quality_report = MarketDataQualityChecker().assess_daily_bars(
            all_bars,
            symbols=tuple(config.symbol_universe) + (config.benchmark,),
            start=min(bar.trading_date for bar in all_bars),
            end=max(bar.trading_date for bar in all_bars),
            generated_at=generated,
            expected_feed=config.data_feed,
            as_of_date=config.end_date,
            require_all_symbols=False,
        )
        evidence = _model_evidence(
            generated_at=generated,
            config=config,
            policy=policy,
            metrics=metrics,
            trades=tuple(trades),
            bars=all_bars,
            leakage_audit=leakage_audit,
        )
        return ReplayRunResult(
            run_id=config.run_id,
            generated_at=generated,
            config=config,
            policy_key=policy.key,
            policy_kind=policy.kind,
            decisions=tuple(decisions),
            trades=tuple(trades),
            risk_decisions=active_risk_engine.decision_log,
            equity_curve=tuple(equity_curve),
            metrics=metrics,
            leakage_audit=leakage_audit,
            data_quality_report=data_quality_report,
            model_evidence=evidence,
        )


def render_replay_markdown_report(result: ReplayRunResult) -> str:
    """Render a reviewable historical replay memo."""

    lines = [
        "# Historical Replay Report",
        "",
        "> Historical replay is research evidence only. It does not grant paper or "
        "live trading authority.",
        "",
        "## Summary",
        "",
        f"- Run id: `{result.run_id}`",
        f"- Policy: `{result.policy_key}`",
        f"- Policy kind: `{result.policy_kind.value}`",
        f"- Range: `{result.config.start_date.isoformat()}` to "
        f"`{result.config.end_date.isoformat()}`",
        f"- Universe kind: `{result.config.universe_kind.value}`",
        f"- Decision frequency: `{result.config.decision_frequency.value}`",
        f"- Execution price: `{result.config.execution_price.value}`",
        f"- Decisions: `{result.metrics.decision_count}`",
        f"- Trades: `{result.metrics.trade_count}`",
        "",
        "## Metrics",
        "",
        f"- Net total return: `{result.metrics.net_total_return:.4%}`",
        f"- Benchmark total return: `{result.metrics.benchmark_total_return:.4%}`",
        f"- Excess return: `{result.metrics.excess_return:.4%}`",
        f"- Annualized return: `{result.metrics.annualized_return:.4%}`",
        f"- Annualized volatility: `{result.metrics.annualized_volatility:.4%}`",
        f"- Max drawdown: `{result.metrics.max_drawdown:.4%}`",
        f"- Turnover: `{result.metrics.turnover:.4f}`",
        "",
        "## Leakage Audit",
        "",
        f"- Status: `{result.leakage_audit.status.value}`",
        f"- Passed: `{_yes_no(result.leakage_audit.passed)}`",
        f"- Summary: {result.leakage_audit.summary}",
        "",
    ]
    if result.leakage_audit.issues:
        lines.extend(
            [
                "| Status | Code | Decision | Message |",
                "| --- | --- | --- | --- |",
            ]
        )
        for issue in result.leakage_audit.issues:
            lines.append(
                f"| `{issue.status.value}` | `{issue.code.value}` | "
                f"`{issue.decision_id or ''}` | {_table_text(issue.message)} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Cost Assumptions",
            "",
            f"- Starting cash: `{result.config.starting_cash}`",
            f"- Commission per trade: `{result.config.commission_per_trade}`",
            f"- Slippage bps: `{result.config.slippage_bps}`",
            f"- Sell fee bps: `{result.config.sell_fee_bps}`",
            f"- Execution price: `{result.config.execution_price.value}`",
            f"- Min trade notional: `{result.config.min_trade_notional}`",
            "",
            "## Governance",
            "",
            "- Replay outcomes are revealed only after each logged decision.",
            "- AI challenger policies receive structured packets; date and symbol "
            "masking are enabled by default.",
            "- Stock replay requires point-in-time universe data before it can run.",
            "",
        ]
    )
    return "\n".join(lines)


def write_replay_markdown_report(
    result: ReplayRunResult,
    output_dir: Path | str,
) -> Path:
    """Write a replay memo and return the path."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.run_id}.md"
    path.write_text(render_replay_markdown_report(result), encoding="utf-8")
    return path


def write_replay_decision_log_json(
    result: ReplayRunResult,
    output_dir: Path | str,
) -> Path:
    """Write the full replay decision audit log as JSON."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.run_id}-decisions.json"
    payload = {
        "run_id": result.run_id,
        "policy_key": result.policy_key,
        "generated_at": result.generated_at.isoformat(),
        "start_date": result.config.start_date.isoformat(),
        "end_date": result.config.end_date.isoformat(),
        "benchmark": result.config.benchmark,
        "decision_count": len(result.decisions),
        "decisions": [
            decision.model_dump(mode="json") for decision in result.decisions
        ],
    }
    path.write_text(dumps(payload, indent=2), encoding="utf-8")
    return path


@dataclass(frozen=True)
class _ExecutionPlan:
    order: Order
    fill: Fill
    gross_value: Decimal
    fees: Decimal


def _rebalance(
    *,
    ledger: Ledger,
    trades: list[ReplayTrade],
    trade_index: int,
    decision_id: str,
    trading_day: date,
    prices: dict[str, Decimal],
    targets: dict[str, Decimal],
    config: ReplayConfig,
    policy_key: str,
    risk_engine: RiskEngine,
) -> tuple[int, list[ReplayOrderPlan]]:
    order_plans: list[ReplayOrderPlan] = []
    equity = _mark_to_market(ledger, prices, trading_day)
    target_values = {symbol: equity * weight for symbol, weight in targets.items()}
    current_symbols = {
        position.symbol for position in ledger.snapshot(_as_dt(trading_day)).positions
    }
    symbols_to_consider = sorted(current_symbols | set(targets))

    for symbol in symbols_to_consider:
        if symbol not in prices:
            continue
        position = ledger.get_position(symbol)
        current_quantity = position.quantity if position is not None else Decimal("0")
        current_value = current_quantity * prices[symbol]
        target_value = target_values.get(symbol, Decimal("0"))
        if not _should_trade(current_value, target_value, equity, config):
            continue
        quantity = (
            current_quantity
            if target_value == 0
            else (current_value - target_value) / _sell_price(prices[symbol], config)
        )
        quantity = _round_quantity_down(min(quantity, current_quantity))
        if quantity <= 0:
            continue
        trade_index, plan = _execute_trade(
            ledger=ledger,
            trades=trades,
            trade_index=trade_index,
            decision_id=decision_id,
            trading_day=trading_day,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            raw_close=prices[symbol],
            config=config,
            risk_engine=risk_engine,
            policy_key=policy_key,
            latest_prices=prices,
            orders_today=_orders_today(trades, trading_day),
            notional_traded_today=_notional_traded_today(trades, trading_day),
        )
        order_plans.append(plan)

    for symbol in sorted(targets):
        if symbol not in prices:
            continue
        position = ledger.get_position(symbol)
        current_quantity = position.quantity if position is not None else Decimal("0")
        current_value = current_quantity * prices[symbol]
        target_value = target_values[symbol]
        if not _should_trade(target_value, current_value, equity, config):
            continue

        buy_price = _buy_price(prices[symbol], config)
        desired_quantity = (target_value - current_value) / buy_price
        affordable_quantity = (
            (ledger.cash - config.commission_per_trade) / buy_price
            if ledger.cash > config.commission_per_trade
            else Decimal("0")
        )
        quantity = _round_quantity_down(min(desired_quantity, affordable_quantity))
        if quantity <= 0:
            continue
        trade_index, plan = _execute_trade(
            ledger=ledger,
            trades=trades,
            trade_index=trade_index,
            decision_id=decision_id,
            trading_day=trading_day,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            raw_close=prices[symbol],
            config=config,
            risk_engine=risk_engine,
            policy_key=policy_key,
            latest_prices=prices,
            orders_today=_orders_today(trades, trading_day),
            notional_traded_today=_notional_traded_today(trades, trading_day),
        )
        order_plans.append(plan)

    return trade_index, order_plans


def _execute_trade(
    *,
    ledger: Ledger,
    trades: list[ReplayTrade],
    trade_index: int,
    decision_id: str,
    trading_day: date,
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    raw_close: Decimal,
    config: ReplayConfig,
    risk_engine: RiskEngine,
    policy_key: str,
    latest_prices: dict[str, Decimal],
    orders_today: int,
    notional_traded_today: Decimal,
) -> tuple[int, ReplayOrderPlan]:
    trade_index += 1
    execution = _execution_plan(
        trade_index=trade_index,
        trading_day=trading_day,
        symbol=symbol,
        side=side,
        quantity=quantity,
        raw_close=raw_close,
        config=config,
    )
    proposal = ProposedOrder(
        order=execution.order,
        estimated_price=execution.fill.price,
        estimated_commission=execution.fees,
        strategy_id=policy_key,
        metadata={"decision_id": decision_id, "replay_run_id": config.run_id},
    )
    context = RiskContext(
        as_of=_as_dt(trading_day),
        portfolio=ledger.snapshot(_as_dt(trading_day)),
        latest_prices=latest_prices,
        orders_today=orders_today,
        notional_traded_today=notional_traded_today,
    )
    decision = risk_engine.evaluate_order(proposal, context)
    plan = ReplayOrderPlan(
        order_id=execution.order.id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        estimated_price=execution.fill.price,
        estimated_notional=execution.gross_value,
        approved=decision.approved,
        rejection_rules=tuple(
            rejection.rule.value for rejection in decision.rejections
        ),
    )
    if not decision.approved:
        return trade_index, plan

    ledger.record_order(execution.order)
    ledger.record_fill(execution.fill)
    trades.append(
        ReplayTrade(
            decision_id=decision_id,
            trading_date=trading_day,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=execution.fill.price,
            fees=execution.fees,
            gross_value=execution.gross_value,
            order_id=execution.order.id,
            fill_id=execution.fill.id,
        )
    )
    return trade_index, plan


def _execution_plan(
    *,
    trade_index: int,
    trading_day: date,
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    raw_close: Decimal,
    config: ReplayConfig,
) -> _ExecutionPlan:
    price = (
        _buy_price(raw_close, config)
        if side == OrderSide.BUY
        else _sell_price(raw_close, config)
    )
    gross_value = quantity * price
    fees = config.commission_per_trade
    if side == OrderSide.SELL:
        fees += gross_value * config.sell_fee_bps / BPS_DENOMINATOR

    order_id = f"replay-order-{trade_index}"
    fill_id = f"replay-fill-{trade_index}"
    order = Order(
        id=order_id,
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_at=_as_dt(trading_day),
    )
    fill = Fill(
        id=fill_id,
        order_id=order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        commission=fees,
        filled_at=_as_dt(trading_day),
    )
    return _ExecutionPlan(order=order, fill=fill, gross_value=gross_value, fees=fees)


def _feature_snapshot(
    *,
    config: ReplayConfig,
    visible_bars: tuple[DailyBar, ...],
    as_of: date,
) -> ReplayFeatureSnapshot:
    features = {
        symbol: _features_for_symbol(symbol, visible_bars)
        for symbol in config.symbol_universe
    }
    features = {symbol: values for symbol, values in features.items() if values}
    visible_dates = [bar.trading_date for bar in visible_bars]
    visible_start = min(visible_dates, default=None)
    visible_end = max(visible_dates, default=None)
    payload = {
        "as_of": as_of.isoformat(),
        "visible_start": visible_start.isoformat() if visible_start else None,
        "visible_end": visible_end.isoformat() if visible_end else None,
        "features": {
            symbol: {name: str(value) for name, value in sorted(values.items())}
            for symbol, values in sorted(features.items())
        },
    }
    feature_hash = sha256(dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return ReplayFeatureSnapshot(
        as_of=as_of,
        visible_start=visible_start,
        visible_end=visible_end,
        symbols=tuple(sorted(features)),
        features_by_symbol=features,
        feature_hash=feature_hash,
    )


def _features_for_symbol(
    symbol: str,
    visible_bars: tuple[DailyBar, ...],
) -> dict[str, Decimal]:
    symbol_bars = sorted(
        (bar for bar in visible_bars if bar.symbol == symbol),
        key=lambda bar: bar.trading_date,
    )
    if not symbol_bars:
        return {}
    latest = symbol_bars[-1]
    features: dict[str, Decimal] = {
        "close_price": latest.close_price,
        "volume": latest.volume,
    }
    if len(symbol_bars) >= 2:
        previous = symbol_bars[-2]
        features["daily_return"] = latest.close_price / previous.close_price - Decimal(
            "1"
        )
    for window in (21, 63, 126):
        if len(symbol_bars) > window:
            lookback = symbol_bars[-(window + 1)]
            features[f"return_{window}d"] = (
                latest.close_price / lookback.close_price - Decimal("1")
            )
    if len(symbol_bars) >= 21:
        volumes = [bar.volume for bar in symbol_bars[-21:]]
        features["average_volume_21d"] = sum(volumes, Decimal("0")) / Decimal(
            len(volumes)
        )
        returns = [
            float(symbol_bars[index].close_price / symbol_bars[index - 1].close_price)
            - 1.0
            for index in range(len(symbol_bars) - 20, len(symbol_bars))
        ]
        if returns:
            series = pd.Series(returns)
            features["realized_volatility_21d"] = Decimal(
                str(series.std(ddof=0) * sqrt(252))
            )
    return features


def _decision_outcomes(
    *,
    as_of: date,
    targets: dict[str, Decimal],
    config: ReplayConfig,
    bars_by_symbol: dict[str, list[DailyBar]],
) -> tuple[ReplayOutcome, ...]:
    outcomes: list[ReplayOutcome] = []
    symbols = tuple(sorted(set(targets) | {config.benchmark}))
    for symbol in symbols:
        symbol_bars = bars_by_symbol.get(symbol, [])
        start_index = next(
            (
                index
                for index, bar in enumerate(symbol_bars)
                if bar.trading_date == as_of
            ),
            None,
        )
        if start_index is None:
            continue
        start_price = symbol_bars[start_index].close_price
        for horizon in config.outcome_horizons:
            end_index = start_index + horizon
            if end_index >= len(symbol_bars):
                outcomes.append(
                    ReplayOutcome(
                        symbol=symbol,
                        horizon_trading_days=horizon,
                        start_price=start_price,
                    )
                )
                continue
            end_bar = symbol_bars[end_index]
            outcomes.append(
                ReplayOutcome(
                    symbol=symbol,
                    horizon_trading_days=horizon,
                    start_price=start_price,
                    end_price=end_bar.close_price,
                    realized_return=float(end_bar.close_price / start_price - 1),
                    available_on=end_bar.trading_date,
                )
            )
    return tuple(outcomes)


def _validated_targets(
    target_weights: dict[str, Decimal],
    config: ReplayConfig,
) -> dict[str, Decimal]:
    normalized: dict[str, Decimal] = {}
    for symbol, weight in target_weights.items():
        actual_symbol = validate_symbol(symbol)
        if actual_symbol not in config.symbol_universe and (
            actual_symbol != config.benchmark
        ):
            raise ValueError(
                f"target symbol is outside replay universe: {actual_symbol}"
            )
        if weight < Decimal("0"):
            raise ValueError("target weights cannot be negative")
        if weight == Decimal("0"):
            continue
        normalized[actual_symbol] = weight

    total = sum(normalized.values(), Decimal("0"))
    if total > Decimal("1.000001"):
        raise ValueError("target weights cannot sum above 1.0")
    return dict(sorted(normalized.items()))


def _metrics(
    *,
    config: ReplayConfig,
    decisions: tuple[ReplayDecision, ...],
    trades: tuple[ReplayTrade, ...],
    equity_curve: tuple[ReplayEquityPoint, ...],
) -> ReplayMetrics:
    net_total_return = _total_return(config.starting_cash, equity_curve[-1].equity)
    benchmark_total_return = _total_return(
        config.starting_cash,
        equity_curve[-1].benchmark_equity,
    )
    return ReplayMetrics(
        net_total_return=net_total_return,
        benchmark_total_return=benchmark_total_return,
        excess_return=net_total_return - benchmark_total_return,
        annualized_return=_annualized_return(
            config.starting_cash,
            equity_curve[-1].equity,
            equity_curve[0].trading_date,
            equity_curve[-1].trading_date,
        ),
        annualized_volatility=_annualized_volatility(equity_curve),
        max_drawdown=_max_drawdown(equity_curve),
        turnover=_turnover(trades, equity_curve),
        trade_count=len(trades),
        decision_count=len(decisions),
    )


def _leakage_audit(
    *,
    decisions: tuple[ReplayDecision, ...],
    policy_kind: ReplayPolicyKind,
    config: ReplayConfig,
) -> ReplayLeakageAudit:
    issues: list[ReplayLeakageIssue] = []
    if not decisions:
        issues.append(
            ReplayLeakageIssue(
                code=ReplayLeakageIssueCode.NO_DECISIONS,
                status=ReplayAuditStatus.WARNING,
                message="Replay produced no eligible point-in-time decisions.",
            )
        )
    for decision in decisions:
        if (
            decision.visible_data_end is not None
            and decision.visible_data_end >= decision.as_of
        ):
            issues.append(
                ReplayLeakageIssue(
                    code=ReplayLeakageIssueCode.FUTURE_VISIBLE_BAR,
                    status=ReplayAuditStatus.FAILED,
                    message="Decision-visible data included same-day or future bars.",
                    decision_id=decision.id,
                    as_of=decision.as_of,
                    evidence=(
                        f"visible_data_end={decision.visible_data_end.isoformat()}",
                        f"as_of={decision.as_of.isoformat()}",
                    ),
                )
            )
    if policy_kind == ReplayPolicyKind.AI_CHALLENGER and not config.mask_ai_dates:
        issues.append(
            ReplayLeakageIssue(
                code=ReplayLeakageIssueCode.AI_DATE_UNMASKED,
                status=ReplayAuditStatus.WARNING,
                message="AI challenger received real calendar dates.",
            )
        )
    if policy_kind == ReplayPolicyKind.AI_CHALLENGER and not config.mask_ai_symbols:
        issues.append(
            ReplayLeakageIssue(
                code=ReplayLeakageIssueCode.AI_SYMBOL_UNMASKED,
                status=ReplayAuditStatus.WARNING,
                message="AI challenger received real ticker symbols.",
            )
        )

    status = _audit_status(issues)
    max_visible_date = max(
        (
            decision.visible_data_end
            for decision in decisions
            if decision.visible_data_end is not None
        ),
        default=None,
    )
    return ReplayLeakageAudit(
        status=status,
        passed=status != ReplayAuditStatus.FAILED,
        decision_count=len(decisions),
        max_visible_date=max_visible_date,
        issues=tuple(issues),
        summary=_audit_summary(status, issues),
    )


def _model_evidence(
    *,
    generated_at: datetime,
    config: ReplayConfig,
    policy: ReplayDecisionPolicy,
    metrics: ReplayMetrics,
    trades: tuple[ReplayTrade, ...],
    bars: tuple[DailyBar, ...],
    leakage_audit: ReplayLeakageAudit,
) -> ModelEvidenceRecord:
    return ModelEvidenceRecord(
        id=f"historical-replay-{config.run_id}-{policy.key}",
        model_key=policy.key,
        evidence_type=ModelEvidenceType.HISTORICAL_REPLAY,
        recorded_at=generated_at,
        start_date=config.start_date,
        end_date=config.end_date,
        benchmark=config.benchmark,
        data_source=",".join(sorted({bar.source for bar in bars})),
        metrics=ModelMetricSet(
            gross_total_return=metrics.net_total_return,
            net_total_return=metrics.net_total_return,
            benchmark_total_return=metrics.benchmark_total_return,
            max_drawdown=metrics.max_drawdown,
            annualized_volatility=metrics.annualized_volatility,
            turnover=metrics.turnover,
            trade_count=metrics.trade_count,
            average_holding_period_days=_average_holding_period_days(trades),
            estimated_after_tax_total_return=None,
        ),
        cost_assumptions={
            "starting_cash": str(config.starting_cash),
            "commission_per_trade": str(config.commission_per_trade),
            "slippage_bps": str(config.slippage_bps),
            "sell_fee_bps": str(config.sell_fee_bps),
            "execution_price": config.execution_price.value,
            "min_trade_notional": str(config.min_trade_notional),
            "min_trade_weight_delta": str(config.min_trade_weight_delta),
        },
        tax_assumptions={},
        risk_settings={
            "decision_frequency": config.decision_frequency.value,
            "execution_price": config.execution_price.value,
            "universe_kind": config.universe_kind.value,
            "point_in_time_universe": config.point_in_time_universe,
            "leakage_audit_status": leakage_audit.status.value,
        },
        notes=(
            "Point-in-time historical replay evidence. Policy-visible data was "
            "restricted to bars before each decision date."
        ),
        failure_modes=tuple(issue.message for issue in leakage_audit.issues),
    )


def _portfolio_weights_for_packet(
    context: ReplayDecisionContext,
    actual_to_packet: dict[str, str],
) -> dict[str, Decimal]:
    latest_visible_prices = _latest_visible_prices(context.visible_bars)
    equity = context.portfolio.cash
    for position in context.portfolio.positions:
        equity += position.quantity * latest_visible_prices.get(
            position.symbol,
            position.average_cost,
        )
    if equity <= 0:
        return {}
    weights: dict[str, Decimal] = {}
    for position in context.portfolio.positions:
        symbol = actual_to_packet.get(position.symbol, position.symbol)
        price = latest_visible_prices.get(position.symbol, position.average_cost)
        weights[symbol] = position.quantity * price / equity
    return weights


def _latest_visible_prices(bars: tuple[DailyBar, ...]) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for bar in sorted(bars, key=_bar_sort_key):
        prices[bar.symbol] = bar.close_price
    return prices


def _require_replay_inputs(
    bars: tuple[DailyBar, ...],
    benchmark_bars: tuple[DailyBar, ...],
    config: ReplayConfig,
) -> None:
    if not bars:
        raise ValueError("bars cannot be empty")
    if not benchmark_bars:
        raise ValueError("benchmark_bars cannot be empty")
    symbols = {bar.symbol for bar in bars}
    missing = set(config.symbol_universe) - symbols
    if missing:
        raise ValueError(f"bars missing replay universe symbols: {sorted(missing)}")
    if config.benchmark not in {bar.symbol for bar in benchmark_bars}:
        raise ValueError(f"benchmark_bars missing benchmark: {config.benchmark}")


def _decision_dates(
    trading_dates: list[date],
    *,
    frequency: ReplayDecisionFrequency,
) -> set[date]:
    if frequency == ReplayDecisionFrequency.DAILY:
        return set(trading_dates)
    first_by_month: dict[tuple[int, int], date] = {}
    for trading_day in trading_dates:
        first_by_month.setdefault((trading_day.year, trading_day.month), trading_day)
    return set(first_by_month.values())


def _has_warmup(
    bars: tuple[DailyBar, ...],
    trading_day: date,
    warmup_trading_days: int,
) -> bool:
    prior_dates = {bar.trading_date for bar in bars if bar.trading_date < trading_day}
    return len(prior_dates) >= warmup_trading_days


def _bars_by_date(bars: tuple[DailyBar, ...]) -> dict[date, dict[str, DailyBar]]:
    grouped: dict[date, dict[str, DailyBar]] = {}
    for bar in bars:
        grouped.setdefault(bar.trading_date, {})[bar.symbol] = bar
    return grouped


def _bars_by_symbol(bars: tuple[DailyBar, ...]) -> dict[str, list[DailyBar]]:
    grouped: dict[str, list[DailyBar]] = {}
    for bar in sorted(bars, key=_bar_sort_key):
        grouped.setdefault(bar.symbol, []).append(bar)
    return grouped


def _bar_sort_key(bar: DailyBar) -> tuple[date, str]:
    return (bar.trading_date, bar.symbol)


def _execution_bar_price(bar: DailyBar, config: ReplayConfig) -> Decimal:
    if config.execution_price == ReplayExecutionPrice.OPEN:
        return bar.open_price
    return bar.close_price


def _symbol_aliases(symbols: tuple[str, ...]) -> dict[str, str]:
    return {symbol: f"ASSET_{index + 1:03d}" for index, symbol in enumerate(symbols)}


def _strategy_key(strategy) -> str:
    strategy_id = getattr(strategy, "strategy_id", "unknown_strategy")
    strategy_version = getattr(strategy, "strategy_version", "unversioned")
    return f"{strategy_id}:{strategy_version}"


def _mark_to_market(
    ledger: Ledger,
    prices: dict[str, Decimal],
    trading_day: date,
) -> Decimal:
    equity = ledger.cash
    for position in ledger.snapshot(_as_dt(trading_day)).positions:
        price = prices.get(position.symbol, position.average_cost)
        equity += position.quantity * price
    return equity


def _benchmark_equity(
    *,
    benchmark_by_date: dict[date, dict[str, DailyBar]],
    trading_date: date,
    starting_cash: Decimal,
) -> Decimal:
    available_dates = sorted(day for day in benchmark_by_date if day <= trading_date)
    if not available_dates:
        return starting_cash
    first_date = available_dates[0]
    current_date = available_dates[-1]
    first_bar = next(iter(benchmark_by_date[first_date].values()))
    current_bar = next(iter(benchmark_by_date[current_date].values()))
    return starting_cash * (current_bar.close_price / first_bar.close_price)


def _buy_price(close: Decimal, config: ReplayConfig) -> Decimal:
    return close * (Decimal("1") + config.slippage_bps / BPS_DENOMINATOR)


def _sell_price(close: Decimal, config: ReplayConfig) -> Decimal:
    return close * (Decimal("1") - config.slippage_bps / BPS_DENOMINATOR)


def _round_quantity_down(quantity: Decimal) -> Decimal:
    return quantity.quantize(QUANTITY_INCREMENT, rounding=ROUND_DOWN)


def _should_trade(
    larger_value: Decimal,
    smaller_value: Decimal,
    equity: Decimal,
    config: ReplayConfig,
) -> bool:
    difference = larger_value - smaller_value
    if difference <= 0:
        return False
    if difference < config.min_trade_notional:
        return False
    return not (equity > 0 and difference / equity < config.min_trade_weight_delta)


def _orders_today(trades: list[ReplayTrade], trading_day: date) -> int:
    return sum(1 for trade in trades if trade.trading_date == trading_day)


def _notional_traded_today(trades: list[ReplayTrade], trading_day: date) -> Decimal:
    return sum(
        (trade.gross_value for trade in trades if trade.trading_date == trading_day),
        Decimal("0"),
    )


def _total_return(starting_cash: Decimal, ending_equity: Decimal) -> float:
    return float(ending_equity / starting_cash - Decimal("1"))


def _annualized_return(
    starting_cash: Decimal,
    ending_equity: Decimal,
    start: date,
    end: date,
) -> float:
    days = max((end - start).days, 1)
    return float((float(ending_equity / starting_cash) ** (365 / days)) - 1)


def _annualized_volatility(equity_curve: tuple[ReplayEquityPoint, ...]) -> float:
    if len(equity_curve) < 3:
        return 0.0
    series = pd.Series([float(point.equity) for point in equity_curve])
    returns = series.pct_change().dropna()
    if returns.empty:
        return 0.0
    return float(returns.std(ddof=0) * sqrt(252))


def _max_drawdown(equity_curve: tuple[ReplayEquityPoint, ...]) -> float:
    running_max = Decimal("0")
    max_drawdown = Decimal("0")
    for point in equity_curve:
        running_max = max(running_max, point.equity)
        if running_max > 0:
            drawdown = point.equity / running_max - Decimal("1")
            max_drawdown = min(max_drawdown, drawdown)
    return float(max_drawdown)


def _turnover(
    trades: tuple[ReplayTrade, ...],
    equity_curve: tuple[ReplayEquityPoint, ...],
) -> float:
    if not trades or not equity_curve:
        return 0.0
    traded_value = sum((trade.gross_value for trade in trades), Decimal("0"))
    average_equity = sum(
        (point.equity for point in equity_curve), Decimal("0")
    ) / Decimal(len(equity_curve))
    if average_equity == 0:
        return 0.0
    return float(traded_value / average_equity)


def _average_holding_period_days(trades: tuple[ReplayTrade, ...]) -> float:
    buys: dict[str, list[ReplayTrade]] = {}
    holding_periods: list[int] = []
    for trade in trades:
        if trade.side == OrderSide.BUY:
            buys.setdefault(trade.symbol, []).append(trade)
            continue
        lots = buys.get(trade.symbol, [])
        if lots:
            holding_periods.append((trade.trading_date - lots[0].trading_date).days)
            lots.pop(0)
    return mean(holding_periods) if holding_periods else 0.0


def _audit_status(issues: list[ReplayLeakageIssue]) -> ReplayAuditStatus:
    if any(issue.status == ReplayAuditStatus.FAILED for issue in issues):
        return ReplayAuditStatus.FAILED
    if any(issue.status == ReplayAuditStatus.WARNING for issue in issues):
        return ReplayAuditStatus.WARNING
    return ReplayAuditStatus.PASSED


def _audit_summary(
    status: ReplayAuditStatus,
    issues: list[ReplayLeakageIssue],
) -> str:
    if status == ReplayAuditStatus.PASSED:
        return "No replay leakage issues were detected."
    failures = sum(1 for issue in issues if issue.status == ReplayAuditStatus.FAILED)
    warnings = sum(1 for issue in issues if issue.status == ReplayAuditStatus.WARNING)
    return (
        f"Replay leakage audit found {failures} failure(s) and {warnings} warning(s)."
    )


def _aware_generated_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _as_dt(trading_day: date) -> datetime:
    local_close = datetime.combine(trading_day, time(hour=16), tzinfo=MARKET_TIMEZONE)
    return local_close.astimezone(UTC)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _table_text(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
