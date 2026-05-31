"""Strategy research catalog and strategy cards."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from trading_app.schemas import TradingModel, validate_symbol

SECTOR_ETF_UNIVERSE = (
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
)


class StrategyFamily(StrEnum):
    MOMENTUM = "momentum"
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    VOLATILITY_AWARE = "volatility_aware"
    BENCHMARK_RELATIVE = "benchmark_relative"
    DEFENSIVE_REGIME = "defensive_regime"
    CASH_ROTATION = "cash_rotation"
    FUNDAMENTAL = "fundamental"
    AI_EVENT_CLASSIFICATION = "ai_event_classification"


class StrategyImplementationStatus(StrEnum):
    IMPLEMENTED = "implemented"
    RESEARCH_IDEA = "research_idea"
    SHADOW_ONLY = "shadow_only"
    RETIRED = "retired"


class StrategyCadence(StrEnum):
    DAILY_CLOSE = "daily_close"
    WEEKLY_CLOSE = "weekly_close"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class StrategyAuthority(StrEnum):
    RESEARCH_ONLY = "research_only"
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE_DISABLED = "live_disabled"


class StrategyDefinition(TradingModel):
    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    family: StrategyFamily
    implementation_status: StrategyImplementationStatus
    authority: StrategyAuthority
    hypothesis: str = Field(min_length=1)
    universe: tuple[str, ...]
    benchmark: str
    data_requirements: tuple[str, ...]
    feature_names: tuple[str, ...]
    trading_cadence: StrategyCadence
    holding_period: str = Field(min_length=1)
    signal_logic: str = Field(min_length=1)
    sizing_logic: str = Field(min_length=1)
    exit_logic: str = Field(min_length=1)
    risk_assumptions: tuple[str, ...]
    failure_modes: tuple[str, ...]
    constraints: tuple[str, ...]
    ai_role: tuple[str, ...]
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("universe")
    @classmethod
    def _validate_universe(cls, universe: tuple[str, ...]) -> tuple[str, ...]:
        if not universe:
            raise ValueError("universe cannot be empty")
        return tuple(validate_symbol(symbol) for symbol in universe)

    @field_validator("benchmark")
    @classmethod
    def _validate_benchmark(cls, benchmark: str) -> str:
        return validate_symbol(benchmark)

    @field_validator(
        "data_requirements",
        "feature_names",
        "risk_assumptions",
        "failure_modes",
        "constraints",
        "ai_role",
    )
    @classmethod
    def _require_non_empty_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("value cannot be empty")
        if any(not value.strip() for value in values):
            raise ValueError("tuple values must be non-empty strings")
        return values


class StrategyCatalog:
    """In-memory catalog of strategy cards and research hypotheses."""

    def __init__(self, definitions: tuple[StrategyDefinition, ...] = ()) -> None:
        self._definitions: dict[str, StrategyDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: StrategyDefinition) -> StrategyDefinition:
        key = _definition_key(definition.strategy_id, definition.version)
        if key in self._definitions:
            raise ValueError(f"strategy definition already registered: {key}")
        self._definitions[key] = definition
        return definition

    def get(self, strategy_id: str, version: str) -> StrategyDefinition:
        key = _definition_key(strategy_id, version)
        try:
            return self._definitions[key]
        except KeyError as error:
            raise ValueError(f"unknown strategy definition: {key}") from error

    def all(self) -> tuple[StrategyDefinition, ...]:
        return tuple(
            sorted(
                self._definitions.values(),
                key=lambda definition: (definition.strategy_id, definition.version),
            )
        )

    def implemented(self) -> tuple[StrategyDefinition, ...]:
        return tuple(
            definition
            for definition in self.all()
            if definition.implementation_status
            == StrategyImplementationStatus.IMPLEMENTED
        )


def monthly_sector_momentum_definition(
    *,
    version: str = "1.0.0",
    universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    lookback_days: int = 126,
    top_n: int = 3,
    authority: StrategyAuthority = StrategyAuthority.PAPER,
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="monthly_sector_momentum",
        version=version,
        name="Monthly Sector ETF Momentum",
        family=StrategyFamily.MOMENTUM,
        implementation_status=StrategyImplementationStatus.IMPLEMENTED,
        authority=authority,
        hypothesis=(
            "U.S. sector ETFs with stronger trailing momentum may continue "
            "outperforming over the next monthly holding window."
        ),
        universe=universe,
        benchmark="SPY",
        data_requirements=(
            "Adjusted daily OHLCV bars for every sector ETF in the universe.",
            "Daily SPY benchmark bars for comparison.",
            "Latest Alpaca paper prices for paper order sizing.",
        ),
        feature_names=("trailing_close_to_close_momentum", "rank", "month_key"),
        trading_cadence=StrategyCadence.DAILY_CLOSE,
        holding_period="Approximately one month between rebalance checks.",
        signal_logic=(
            "Rank symbols by trailing adjusted close-to-close return using only "
            "bars before the execution date."
        ),
        sizing_logic=f"Equal weight the top {top_n} selected ETF(s).",
        exit_logic=(
            "Sell removed or overweight holdings first, then buy underweight "
            "target holdings."
        ),
        risk_assumptions=(
            "Long-only U.S.-listed ETF exposure.",
            "No margin, no shorts, no options, no intraday authority.",
            "Risk engine, stale-price checks, and reconciliation gates remain final.",
        ),
        failure_modes=(
            "Momentum reversals after sector leadership changes.",
            "High correlation across sectors during broad market stress.",
            "Overfitting lookback/top-N parameters to recent history.",
            "Development-grade IEX data may understate production data issues.",
        ),
        constraints=(
            "U.S.-listed stocks and ETFs only.",
            "Paper trading only until live-readiness gates are explicitly passed.",
            "Daily-close schedule only.",
        ),
        ai_role=(
            "Explain rank changes and trade rationale.",
            "Compare candidate parameters overnight.",
            "Recommend shadow candidates without changing the active model.",
        ),
        parameters={
            "lookback_days": lookback_days,
            "top_n": top_n,
            "universe": universe,
        },
    )


def trend_following_etf_definition(
    *,
    version: str = "0.1.0",
    universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    trend_window_days: int = 63,
    top_n: int = 3,
    min_trend_return: str = "0",
    authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="trend_following_etf",
        version=version,
        name="ETF Trend Following",
        family=StrategyFamily.TREND_FOLLOWING,
        implementation_status=StrategyImplementationStatus.IMPLEMENTED,
        authority=authority,
        hypothesis=(
            "U.S. sector ETFs in persistent positive trends may offer better "
            "risk-adjusted exposure than staying fully invested in every regime."
        ),
        universe=universe,
        benchmark="SPY",
        data_requirements=(
            "Adjusted daily OHLCV bars for every ETF in the universe.",
            "Daily SPY benchmark bars for comparison.",
            "No intraday data or news data required for v0.1 research.",
        ),
        feature_names=("trend_return", "rolling_average_close", "trend_rank"),
        trading_cadence=StrategyCadence.MONTHLY,
        holding_period="Approximately one month between rebalance checks.",
        signal_logic=(
            "Use only completed bars before execution. Rank ETFs by trailing "
            "trend return and require the latest close to be above the trailing "
            "average close."
        ),
        sizing_logic=f"Equal weight the top {top_n} qualifying ETF(s).",
        exit_logic=(
            "Exit symbols that no longer qualify or fall out of the top trend "
            "rank before buying new qualifying leaders."
        ),
        risk_assumptions=(
            "Long-only U.S.-listed ETF exposure.",
            "No margin, no shorts, no options, no intraday authority.",
            "Trend signals may hold cash when no symbol qualifies.",
        ),
        failure_modes=(
            "Whipsaw during sideways markets.",
            "Late exits after gap-down reversals.",
            "Underexposure during sharp V-shaped recoveries.",
            "Overfitting trend windows to recent market regimes.",
        ),
        constraints=(
            "Research-only by default.",
            "U.S.-listed stocks and ETFs only.",
            "Must pass backtest, shadow, risk, and manual promotion gates.",
        ),
        ai_role=(
            "Explain trend qualification and disqualification.",
            "Compare trend windows against the active paper champion.",
            "Flag whipsaw, drawdown, and cash-drag risks in recommendations.",
        ),
        parameters={
            "trend_window_days": trend_window_days,
            "top_n": top_n,
            "min_trend_return": min_trend_return,
            "universe": universe,
        },
    )


def mean_reversion_etf_definition(
    *,
    version: str = "0.1.0",
    universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    reversion_window_days: int = 5,
    trend_filter_days: int = 63,
    top_n: int = 3,
    max_short_return: str = "0",
    authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="mean_reversion_etf",
        version=version,
        name="ETF Mean Reversion",
        family=StrategyFamily.MEAN_REVERSION,
        implementation_status=StrategyImplementationStatus.IMPLEMENTED,
        authority=authority,
        hypothesis=(
            "Liquid U.S. sector ETFs that pull back over a short window while "
            "remaining in a constructive longer-term trend may rebound enough "
            "to justify research-only allocation."
        ),
        universe=universe,
        benchmark="SPY",
        data_requirements=(
            "Adjusted daily OHLCV bars for every ETF in the universe.",
            "Daily SPY benchmark bars for comparison.",
            "No intraday order authority or event data required for v0.1 research.",
        ),
        feature_names=(
            "short_term_return",
            "trend_filter_average_close",
            "oversold_rank",
        ),
        trading_cadence=StrategyCadence.DAILY_CLOSE,
        holding_period="Short research holding window, normally days to weeks.",
        signal_logic=(
            "Use only completed bars before execution. Rank ETFs by most negative "
            "short-term return, but require the latest close to remain above the "
            "longer-term average close."
        ),
        sizing_logic=f"Equal weight the top {top_n} qualifying oversold ETF(s).",
        exit_logic=(
            "Exit symbols that stop qualifying, recover out of the oversold set, "
            "or lose the longer-term trend filter."
        ),
        risk_assumptions=(
            "Long-only U.S.-listed ETF exposure.",
            "No margin, no shorts, no options, no intraday authority.",
            (
                "Research-only until backtest, shadow, risk, and manual "
                "promotion gates pass."
            ),
        ),
        failure_modes=(
            "Catching falling knives during real regime breaks.",
            "Repeated small losses during persistent downtrends.",
            "Transaction costs overwhelming short-horizon rebounds.",
            "Overfitting the reversion and trend-filter windows.",
        ),
        constraints=(
            "Research-only by default.",
            "U.S.-listed stocks and ETFs only.",
            "Must pass data-quality and promotion gates before paper authority.",
        ),
        ai_role=(
            "Explain why a pullback is treated as mean-reversion research.",
            "Flag falling-knife and regime-break risks.",
            "Compare candidate parameters without changing the active paper model.",
        ),
        parameters={
            "reversion_window_days": reversion_window_days,
            "trend_filter_days": trend_filter_days,
            "top_n": top_n,
            "max_short_return": max_short_return,
            "universe": universe,
        },
    )


def volatility_aware_etf_definition(
    *,
    version: str = "0.1.0",
    universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    lookback_days: int = 63,
    volatility_window_days: int = 21,
    top_n: int = 3,
    min_trailing_return: str = "0",
    max_volatility: str | None = None,
    volatility_floor: str = "0.000001",
    authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="volatility_aware_etf",
        version=version,
        name="Volatility-Aware ETF Allocation",
        family=StrategyFamily.VOLATILITY_AWARE,
        implementation_status=StrategyImplementationStatus.IMPLEMENTED,
        authority=authority,
        hypothesis=(
            "U.S. sector ETFs with positive returns and lower recent realized "
            "volatility may provide a smoother research allocation than raw "
            "momentum alone."
        ),
        universe=universe,
        benchmark="SPY",
        data_requirements=(
            "Adjusted daily OHLCV bars for every ETF in the universe.",
            "Daily SPY benchmark bars for comparison.",
            "No intraday order authority or event data required for v0.1 research.",
        ),
        feature_names=(
            "trailing_return",
            "average_absolute_daily_return_volatility_proxy",
            "risk_adjusted_return_score",
            "inverse_volatility_weight",
        ),
        trading_cadence=StrategyCadence.DAILY_CLOSE,
        holding_period="Research holding window, normally days to one month.",
        signal_logic=(
            "Use only completed bars before execution. Require positive trailing "
            "return, optionally exclude high-volatility ETFs, and rank remaining "
            "symbols by trailing return divided by recent average absolute daily "
            "return."
        ),
        sizing_logic=(
            f"Select the top {top_n} qualifying ETF(s) and weight them by inverse "
            "recent volatility."
        ),
        exit_logic=(
            "Exit symbols that no longer qualify, exceed volatility constraints, "
            "or fall out of the top risk-adjusted rank before buying replacements."
        ),
        risk_assumptions=(
            "Long-only U.S.-listed ETF exposure.",
            "No margin, no shorts, no options, no intraday authority.",
            "Volatility proxy is a research simplification, not a VaR model.",
            (
                "Research-only until backtest, shadow, risk, and manual "
                "promotion gates pass."
            ),
        ),
        failure_modes=(
            "Volatility can spike after positions are already sized.",
            "Inverse-volatility weights may underexpose strong recoveries.",
            "Recent low volatility can precede sharp regime changes.",
            "Overfitting lookback or volatility-window parameters.",
        ),
        constraints=(
            "Research-only by default.",
            "U.S.-listed stocks and ETFs only.",
            "Must pass data-quality and promotion gates before paper authority.",
        ),
        ai_role=(
            "Explain how volatility changed candidate ranks and weights.",
            "Flag low-volatility traps and regime-break risks.",
            "Compare candidate parameters without changing the active paper model.",
        ),
        parameters={
            "lookback_days": lookback_days,
            "volatility_window_days": volatility_window_days,
            "top_n": top_n,
            "min_trailing_return": min_trailing_return,
            "max_volatility": max_volatility,
            "volatility_floor": volatility_floor,
            "universe": universe,
        },
    )


def benchmark_relative_strength_etf_definition(
    *,
    version: str = "0.1.0",
    universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    benchmark: str = "SPY",
    lookback_days: int = 63,
    tracking_window_days: int = 21,
    top_n: int = 3,
    min_excess_return: str = "0",
    min_absolute_return: str = "0",
    tracking_error_floor: str = "0.000001",
    authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="benchmark_relative_strength_etf",
        version=version,
        name="Benchmark-Relative ETF Strength",
        family=StrategyFamily.BENCHMARK_RELATIVE,
        implementation_status=StrategyImplementationStatus.IMPLEMENTED,
        authority=authority,
        hypothesis=(
            "Sector ETFs outperforming SPY on a risk-adjusted relative basis "
            "may be better research candidates than raw momentum leaders."
        ),
        universe=universe,
        benchmark=benchmark,
        data_requirements=(
            "Adjusted daily OHLCV bars for every ETF in the universe.",
            f"Adjusted daily {benchmark} benchmark bars for relative strength.",
            "No intraday order authority or event data required for v0.1 research.",
        ),
        feature_names=(
            "symbol_trailing_return",
            "benchmark_trailing_return",
            "excess_return_vs_benchmark",
            "average_absolute_daily_excess_return",
            "relative_strength_score",
        ),
        trading_cadence=StrategyCadence.DAILY_CLOSE,
        holding_period="Research holding window, normally days to one month.",
        signal_logic=(
            "Use only completed bars before execution. Require positive excess "
            "return versus the benchmark and rank by excess return divided by "
            "recent average absolute daily excess return."
        ),
        sizing_logic=f"Equal weight the top {top_n} qualifying ETF(s).",
        exit_logic=(
            "Exit symbols that no longer beat the benchmark, fall below absolute "
            "return thresholds, or fall out of the top relative-strength rank."
        ),
        risk_assumptions=(
            "Long-only U.S.-listed ETF exposure.",
            "No margin, no shorts, no options, no intraday authority.",
            "Relative winners can still lose absolute money.",
            (
                "Research-only until backtest, shadow, risk, and manual "
                "promotion gates pass."
            ),
        ),
        failure_modes=(
            "Benchmark-relative winners can still decline in broad selloffs.",
            "Crowded relative-strength rotations may unwind quickly.",
            "Tracking-error proxy can understate gap and liquidity risk.",
            "Overfitting lookback or relative-strength windows.",
        ),
        constraints=(
            "Research-only by default.",
            "U.S.-listed stocks and ETFs only.",
            "Must pass data-quality and promotion gates before paper authority.",
        ),
        ai_role=(
            "Explain whether returns are absolute or benchmark-relative.",
            "Flag cases where a candidate beats SPY while still losing money.",
            "Compare candidate parameters without changing the active paper model.",
        ),
        parameters={
            "benchmark": benchmark,
            "lookback_days": lookback_days,
            "tracking_window_days": tracking_window_days,
            "top_n": top_n,
            "min_excess_return": min_excess_return,
            "min_absolute_return": min_absolute_return,
            "tracking_error_floor": tracking_error_floor,
            "universe": universe,
        },
    )


def defensive_regime_switch_definition(
    *,
    version: str = "0.1.0",
    universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    defensive_symbols: tuple[str, ...] = ("XLP", "XLU", "XLV"),
    benchmark: str = "SPY",
    regime_lookback_days: int = 126,
    risk_on_top_n: int = 3,
    risk_off_top_n: int = 2,
    max_benchmark_drawdown: str = "-0.10",
    min_benchmark_return: str = "0",
    min_defensive_return: str = "0",
    authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="defensive_regime_switch",
        version=version,
        name="Defensive Regime Switch",
        family=StrategyFamily.DEFENSIVE_REGIME,
        implementation_status=StrategyImplementationStatus.IMPLEMENTED,
        authority=authority,
        hypothesis=(
            "A SPY trend and drawdown regime filter may improve research "
            "resilience by rotating from broad sector momentum into defensive "
            "sector ETFs, or cash, during unfavorable market conditions."
        ),
        universe=universe,
        benchmark=benchmark,
        data_requirements=(
            "Adjusted daily OHLCV bars for every ETF in the universe.",
            f"Adjusted daily {benchmark} benchmark bars for regime detection.",
            "No intraday order authority or event data required for v0.1 research.",
        ),
        feature_names=(
            "benchmark_trailing_return",
            "benchmark_average_close",
            "benchmark_drawdown",
            "sector_trailing_return",
            "defensive_candidate_rank",
        ),
        trading_cadence=StrategyCadence.DAILY_CLOSE,
        holding_period="Research holding window, normally weeks to one month.",
        signal_logic=(
            "Use only completed bars before execution. Treat the regime as weak "
            "when SPY has negative trailing return, closes below its trailing "
            "average, or breaches the configured drawdown threshold. In strong "
            "regimes, rank all sector ETFs by trailing return. In weak regimes, "
            "rank only defensive ETFs and require positive defensive return."
        ),
        sizing_logic=(
            f"Risk-on: equal weight the top {risk_on_top_n} ETF(s). "
            f"Risk-off: equal weight up to {risk_off_top_n} defensive ETF(s); "
            "hold cash when no defensive candidate qualifies."
        ),
        exit_logic=(
            "Exit risk-on holdings when the benchmark regime turns weak. Exit "
            "defensive holdings when they no longer qualify or the regime recovers."
        ),
        risk_assumptions=(
            "Long-only U.S.-listed ETF exposure.",
            "No margin, no shorts, no options, no intraday authority.",
            "Cash is allowed as an explicit defensive research state.",
            (
                "Research-only until backtest, shadow, risk, and manual "
                "promotion gates pass."
            ),
        ),
        failure_modes=(
            "False defensive signals can create cash drag during bull markets.",
            "Regime filters can react late after sharp market gaps.",
            "Defensive sectors can fall with the market during liquidity shocks.",
            "Overfitting drawdown and lookback thresholds to recent crises.",
        ),
        constraints=(
            "Research-only by default.",
            "U.S.-listed stocks and ETFs only.",
            "Must pass data-quality and promotion gates before paper authority.",
        ),
        ai_role=(
            "Explain why the model is risk-on, defensive, or cash.",
            "Compare drawdown avoided against opportunity cost.",
            "Flag false-positive regime switches and cash-drag risk.",
        ),
        parameters={
            "benchmark": benchmark,
            "defensive_symbols": defensive_symbols,
            "regime_lookback_days": regime_lookback_days,
            "risk_on_top_n": risk_on_top_n,
            "risk_off_top_n": risk_off_top_n,
            "max_benchmark_drawdown": max_benchmark_drawdown,
            "min_benchmark_return": min_benchmark_return,
            "min_defensive_return": min_defensive_return,
            "universe": universe,
        },
    )


def cash_rotation_model_definition(
    *,
    version: str = "0.1.0",
    universe: tuple[str, ...] = SECTOR_ETF_UNIVERSE,
    lookback_days: int = 63,
    top_n: int = 3,
    min_symbol_return: str = "0",
    min_breadth: str = "0.40",
    min_average_top_return: str = "0.02",
    authority: StrategyAuthority = StrategyAuthority.RESEARCH_ONLY,
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="cash_rotation_model",
        version=version,
        name="Cash Rotation Model",
        family=StrategyFamily.CASH_ROTATION,
        implementation_status=StrategyImplementationStatus.IMPLEMENTED,
        authority=authority,
        hypothesis=(
            "Cash can be a deliberate research allocation when too few U.S. "
            "sector ETFs show positive opportunity, rather than forcing "
            "capital into weak signals."
        ),
        universe=universe,
        benchmark="SPY",
        data_requirements=(
            "Adjusted daily OHLCV bars for every ETF in the universe.",
            "Daily SPY benchmark bars for comparison.",
            "No intraday order authority or event data required for v0.1 research.",
        ),
        feature_names=(
            "symbol_trailing_return",
            "positive_opportunity_breadth",
            "average_top_candidate_return",
            "cash_gate",
        ),
        trading_cadence=StrategyCadence.DAILY_CLOSE,
        holding_period="Research holding window, normally days to one month.",
        signal_logic=(
            "Use only completed bars before execution. Compute trailing returns "
            "for every eligible ETF, require enough positive breadth, and require "
            "the average top candidate return to clear the configured cash gate."
        ),
        sizing_logic=(
            f"Equal weight the top {top_n} qualifying ETF(s) when opportunity is "
            "strong; otherwise hold cash."
        ),
        exit_logic=(
            "Exit holdings when the opportunity gate fails or when symbols fall "
            "out of the top qualifying set."
        ),
        risk_assumptions=(
            "Long-only U.S.-listed ETF exposure.",
            "No margin, no shorts, no options, no intraday authority.",
            "Cash is an explicit research state, not an execution failure.",
            (
                "Research-only until backtest, shadow, risk, and manual "
                "promotion gates pass."
            ),
        ),
        failure_modes=(
            "Too much idle cash in persistent bull markets.",
            "Breadth thresholds can be overfit to recent regimes.",
            "Rapid recoveries can happen before the opportunity gate reopens.",
            "Cash drag can hide model weakness if benchmark comparison is ignored.",
        ),
        constraints=(
            "Research-only by default.",
            "U.S.-listed stocks and ETFs only.",
            "Must pass data-quality and promotion gates before paper authority.",
        ),
        ai_role=(
            "Explain why the model is invested or in cash.",
            "Compare cash drag against avoided drawdown.",
            "Flag opportunity-threshold overfitting.",
        ),
        parameters={
            "lookback_days": lookback_days,
            "top_n": top_n,
            "min_symbol_return": min_symbol_return,
            "min_breadth": min_breadth,
            "min_average_top_return": min_average_top_return,
            "universe": universe,
        },
    )


def build_default_strategy_catalog() -> StrategyCatalog:
    return StrategyCatalog(
        (
            monthly_sector_momentum_definition(),
            trend_following_etf_definition(),
            mean_reversion_etf_definition(),
            volatility_aware_etf_definition(),
            benchmark_relative_strength_etf_definition(),
            defensive_regime_switch_definition(),
            cash_rotation_model_definition(),
            _research_definition(
                strategy_id="fundamentals_informed_momentum",
                name="Fundamentals-Informed Momentum",
                family=StrategyFamily.FUNDAMENTAL,
                hypothesis=(
                    "Momentum signals filtered by improving fundamentals may avoid "
                    "some low-quality price moves."
                ),
                features=("momentum", "earnings_revision", "quality_score"),
                failure_modes=(
                    "Fundamental data latency or restatement risk.",
                    "Sparse updates compared with daily price movement.",
                ),
            ),
            _research_definition(
                strategy_id="ai_event_classification_overlay",
                name="AI Event Classification Overlay",
                family=StrategyFamily.AI_EVENT_CLASSIFICATION,
                hypothesis=(
                    "AI-labeled events may improve explanations and risk flags "
                    "when used as research metadata rather than direct trade authority."
                ),
                features=("event_label", "source_confidence", "market_reaction"),
                failure_modes=(
                    "Misclassified events or hallucinated significance.",
                    "News and filings may arrive after market reaction.",
                ),
            ),
        )
    )


def strategy_definition_metadata(definition: StrategyDefinition) -> dict[str, Any]:
    return {"strategy_definition": definition.model_dump(mode="json")}


def _research_definition(
    *,
    strategy_id: str,
    name: str,
    family: StrategyFamily,
    hypothesis: str,
    features: tuple[str, ...],
    failure_modes: tuple[str, ...],
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id=strategy_id,
        version="0.1.0",
        name=name,
        family=family,
        implementation_status=StrategyImplementationStatus.RESEARCH_IDEA,
        authority=StrategyAuthority.RESEARCH_ONLY,
        hypothesis=hypothesis,
        universe=SECTOR_ETF_UNIVERSE,
        benchmark="SPY",
        data_requirements=(
            "Timestamp-safe adjusted daily U.S. market data.",
            "SPY benchmark data.",
            "Explicit cost, slippage, and data-quality assumptions.",
        ),
        feature_names=features,
        trading_cadence=StrategyCadence.DAILY_CLOSE,
        holding_period="Research-defined; must be specified before activation.",
        signal_logic="Research hypothesis only; no paper authority yet.",
        sizing_logic="Research hypothesis only; no paper authority yet.",
        exit_logic="Research hypothesis only; no paper authority yet.",
        risk_assumptions=(
            "Long-only until separately approved.",
            "No margin, no shorts, no options.",
            "Must pass risk engine, data quality, and promotion gates.",
        ),
        failure_modes=failure_modes,
        constraints=(
            "U.S.-listed stocks and ETFs only.",
            "No live-money authority.",
            "No automatic promotion from AI recommendations.",
        ),
        ai_role=(
            "Research and explain candidate behavior.",
            "Flag data-quality or overfitting concerns.",
            "Draft review memos for human approval.",
        ),
    )


def _definition_key(strategy_id: str, version: str) -> str:
    return f"{strategy_id}:{version}"
