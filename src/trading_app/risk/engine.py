"""Pre-trade risk checks and rejection logging."""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, field_validator

from trading_app.schemas import (
    NonNegativeDecimal,
    Order,
    OrderSide,
    PortfolioSnapshot,
    Price,
    TradingModel,
    validate_symbol,
)

Allocation = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
PositiveInt = Annotated[int, Field(gt=0)]


class RiskRule(StrEnum):
    KILL_SWITCH = "KILL_SWITCH"
    MANUAL_APPROVAL = "MANUAL_APPROVAL"
    US_TRADABLE_UNIVERSE = "US_TRADABLE_UNIVERSE"
    SYMBOL_ALLOWLIST = "SYMBOL_ALLOWLIST"
    SYMBOL_BLOCKLIST = "SYMBOL_BLOCKLIST"
    MARKET_HOURS = "MARKET_HOURS"
    MIN_PRICE = "MIN_PRICE"
    MIN_AVERAGE_DAILY_VOLUME = "MIN_AVERAGE_DAILY_VOLUME"
    MAX_ORDERS_PER_DAY = "MAX_ORDERS_PER_DAY"
    CASH_AVAILABLE = "CASH_AVAILABLE"
    NO_SHORT_SELLING = "NO_SHORT_SELLING"
    MAX_POSITION_QUANTITY = "MAX_POSITION_QUANTITY"
    MAX_POSITION_NOTIONAL = "MAX_POSITION_NOTIONAL"
    MAX_SYMBOL_ALLOCATION = "MAX_SYMBOL_ALLOCATION"
    MAX_SECTOR_ALLOCATION = "MAX_SECTOR_ALLOCATION"
    MAX_STRATEGY_ALLOCATION = "MAX_STRATEGY_ALLOCATION"
    MAX_PORTFOLIO_GROSS_EXPOSURE = "MAX_PORTFOLIO_GROSS_EXPOSURE"
    MAX_TURNOVER = "MAX_TURNOVER"
    MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"


class ProposedOrder(TradingModel):
    """Order plus pre-trade metadata needed by risk checks."""

    order: Order
    estimated_price: Price
    estimated_commission: NonNegativeDecimal = Decimal("0")
    strategy_id: str = Field(min_length=1)
    sector: str | None = None
    average_daily_volume: NonNegativeDecimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskConfig(TradingModel):
    """Configurable pre-trade guardrails."""

    kill_switch_enabled: bool = False
    manual_approval_required: bool = False
    enforce_market_hours: bool = True
    market_timezone: str = "America/New_York"
    market_open_time: time = time(hour=9, minute=30)
    market_close_time: time = time(hour=16)
    us_tradable_universe: frozenset[str] | None = None
    tradable_symbols: frozenset[str] | None = None
    blocked_symbols: frozenset[str] = frozenset()
    max_position_quantity_by_symbol: dict[str, NonNegativeDecimal] = Field(
        default_factory=dict
    )
    max_position_notional_by_symbol: dict[str, NonNegativeDecimal] = Field(
        default_factory=dict
    )
    max_symbol_allocation: Allocation | None = None
    max_sector_allocation: Allocation | None = None
    max_strategy_allocation: Allocation | None = None
    max_portfolio_gross_exposure: Allocation | None = Decimal("1")
    max_daily_loss: NonNegativeDecimal | None = None
    max_drawdown: Allocation | None = None
    max_orders_per_day: PositiveInt | None = None
    max_turnover: NonNegativeDecimal | None = None
    minimum_price: Price | None = None
    minimum_average_daily_volume: NonNegativeDecimal | None = None
    symbol_to_sector: dict[str, str] = Field(default_factory=dict)

    @field_validator("market_timezone")
    @classmethod
    def _validate_market_timezone(cls, market_timezone: str) -> str:
        try:
            ZoneInfo(market_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("market_timezone must be a valid IANA timezone") from error
        return market_timezone

    @field_validator("us_tradable_universe")
    @classmethod
    def _validate_us_tradable_universe(
        cls, symbols: frozenset[str] | None
    ) -> frozenset[str] | None:
        if symbols is None:
            return None
        return frozenset(validate_symbol(symbol) for symbol in symbols)

    @field_validator("tradable_symbols")
    @classmethod
    def _validate_tradable_symbols(
        cls, symbols: frozenset[str] | None
    ) -> frozenset[str] | None:
        if symbols is None:
            return None
        return frozenset(validate_symbol(symbol) for symbol in symbols)

    @field_validator("blocked_symbols")
    @classmethod
    def _validate_blocked_symbols(cls, symbols: frozenset[str]) -> frozenset[str]:
        return frozenset(validate_symbol(symbol) for symbol in symbols)

    @field_validator(
        "max_position_quantity_by_symbol",
        "max_position_notional_by_symbol",
    )
    @classmethod
    def _validate_symbol_limit_keys(
        cls, limits: dict[str, Decimal]
    ) -> dict[str, Decimal]:
        return {validate_symbol(symbol): limit for symbol, limit in limits.items()}

    @field_validator("symbol_to_sector")
    @classmethod
    def _validate_symbol_to_sector(cls, sectors: dict[str, str]) -> dict[str, str]:
        return {
            validate_symbol(symbol): sector
            for symbol, sector in sectors.items()
            if sector
        }


class RiskContext(TradingModel):
    """Current portfolio and session state for risk evaluation."""

    as_of: AwareDatetime
    portfolio: PortfolioSnapshot
    latest_prices: dict[str, Price] = Field(default_factory=dict)
    orders_today: int = Field(default=0, ge=0)
    notional_traded_today: NonNegativeDecimal = Decimal("0")
    realized_pnl_today: Decimal = Decimal("0")
    start_of_day_equity: Price | None = None
    peak_equity: Price | None = None
    manual_approval: bool = False
    average_daily_volume_by_symbol: dict[str, NonNegativeDecimal] = Field(
        default_factory=dict
    )
    strategy_exposure: dict[str, NonNegativeDecimal] = Field(default_factory=dict)

    @field_validator("latest_prices", "average_daily_volume_by_symbol")
    @classmethod
    def _validate_symbol_keys(cls, values: dict[str, Decimal]) -> dict[str, Decimal]:
        return {validate_symbol(symbol): value for symbol, value in values.items()}


class RiskRuleResult(TradingModel):
    rule: RiskRule
    passed: bool
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskRejection(TradingModel):
    rule: RiskRule
    message: str
    order_id: str
    signal_id: str | None = None
    symbol: str
    checked_at: AwareDatetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskDecision(TradingModel):
    approved: bool
    order_id: str
    signal_id: str | None = None
    symbol: str
    checked_at: AwareDatetime
    rule_results: tuple[RiskRuleResult, ...]
    rejections: tuple[RiskRejection, ...]


class RiskRejectedError(ValueError):
    """Raised when a caller requires approval but risk rejects the order."""

    def __init__(self, decision: RiskDecision) -> None:
        self.decision = decision
        messages = "; ".join(rejection.message for rejection in decision.rejections)
        super().__init__(messages or "risk rejected order")


class RiskEngine:
    """Evaluate proposed orders against configured pre-trade guardrails."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()
        self._decision_log: list[RiskDecision] = []

    @property
    def decision_log(self) -> tuple[RiskDecision, ...]:
        return tuple(self._decision_log)

    @property
    def rejection_log(self) -> tuple[RiskRejection, ...]:
        return tuple(
            rejection
            for decision in self._decision_log
            for rejection in decision.rejections
        )

    def evaluate_order(
        self, proposal: ProposedOrder, context: RiskContext
    ) -> RiskDecision:
        rule_results = self._evaluate_rules(proposal, context)
        rejections = tuple(
            RiskRejection(
                rule=result.rule,
                message=result.message,
                order_id=proposal.order.id,
                signal_id=proposal.order.signal_id,
                symbol=proposal.order.symbol,
                checked_at=context.as_of,
                metadata=result.metadata,
            )
            for result in rule_results
            if not result.passed
        )
        decision = RiskDecision(
            approved=not rejections,
            order_id=proposal.order.id,
            signal_id=proposal.order.signal_id,
            symbol=proposal.order.symbol,
            checked_at=context.as_of,
            rule_results=tuple(rule_results),
            rejections=rejections,
        )
        self._decision_log.append(decision)
        return decision

    def require_approval(self, proposal: ProposedOrder, context: RiskContext) -> Order:
        decision = self.evaluate_order(proposal, context)
        if not decision.approved:
            raise RiskRejectedError(decision)
        return proposal.order

    def _evaluate_rules(
        self, proposal: ProposedOrder, context: RiskContext
    ) -> list[RiskRuleResult]:
        order = proposal.order
        current = _PortfolioState.from_context(context, proposal)
        projected = current.project(proposal)
        equity = current.equity
        projected_equity = projected.equity
        order_notional = proposal.order.quantity * proposal.estimated_price
        results = [
            self._check_kill_switch(),
            self._check_manual_approval(context),
            self._check_us_tradable_universe(order.symbol),
            self._check_allowlist(order.symbol),
            self._check_blocklist(order.symbol),
            self._check_market_hours(context),
            self._check_minimum_price(proposal),
            self._check_minimum_average_daily_volume(proposal, context),
            self._check_max_orders_per_day(context),
            self._check_cash_available(proposal, context),
            self._check_no_short_selling(order, current),
            self._check_max_position_quantity(order, projected),
            self._check_max_position_notional(order, projected),
            self._check_max_symbol_allocation(order, projected, projected_equity),
            self._check_max_sector_allocation(proposal, projected, projected_equity),
            self._check_max_strategy_allocation(
                proposal, context, order_notional, projected_equity
            ),
            self._check_max_portfolio_gross_exposure(projected, projected_equity),
            self._check_max_turnover(context, order_notional, equity),
            self._check_max_daily_loss(context),
            self._check_max_drawdown(context, equity),
        ]
        return results

    def _pass(self, rule: RiskRule, message: str, **metadata: Any) -> RiskRuleResult:
        return RiskRuleResult(
            rule=rule,
            passed=True,
            message=message,
            metadata=metadata,
        )

    def _fail(self, rule: RiskRule, message: str, **metadata: Any) -> RiskRuleResult:
        return RiskRuleResult(
            rule=rule,
            passed=False,
            message=message,
            metadata=metadata,
        )

    def _check_kill_switch(self) -> RiskRuleResult:
        if self.config.kill_switch_enabled:
            return self._fail(RiskRule.KILL_SWITCH, "kill switch is enabled")
        return self._pass(RiskRule.KILL_SWITCH, "kill switch is disabled")

    def _check_manual_approval(self, context: RiskContext) -> RiskRuleResult:
        if self.config.manual_approval_required and not context.manual_approval:
            return self._fail(
                RiskRule.MANUAL_APPROVAL,
                "manual approval is required",
            )
        return self._pass(RiskRule.MANUAL_APPROVAL, "manual approval requirement met")

    def _check_us_tradable_universe(self, symbol: str) -> RiskRuleResult:
        if self.config.us_tradable_universe is None:
            return self._pass(
                RiskRule.US_TRADABLE_UNIVERSE,
                "U.S. tradable universe check disabled",
            )
        if symbol not in self.config.us_tradable_universe:
            return self._fail(
                RiskRule.US_TRADABLE_UNIVERSE,
                f"{symbol} is not in the configured U.S. tradable universe",
            )
        return self._pass(
            RiskRule.US_TRADABLE_UNIVERSE,
            "symbol is in the configured U.S. tradable universe",
        )

    def _check_allowlist(self, symbol: str) -> RiskRuleResult:
        if (
            self.config.tradable_symbols is not None
            and symbol not in self.config.tradable_symbols
        ):
            return self._fail(
                RiskRule.SYMBOL_ALLOWLIST,
                f"{symbol} is not in the tradable symbol allowlist",
            )
        return self._pass(RiskRule.SYMBOL_ALLOWLIST, "symbol is tradable")

    def _check_blocklist(self, symbol: str) -> RiskRuleResult:
        if symbol in self.config.blocked_symbols:
            return self._fail(
                RiskRule.SYMBOL_BLOCKLIST,
                f"{symbol} is blocked",
            )
        return self._pass(RiskRule.SYMBOL_BLOCKLIST, "symbol is not blocked")

    def _check_market_hours(self, context: RiskContext) -> RiskRuleResult:
        if not self.config.enforce_market_hours:
            return self._pass(RiskRule.MARKET_HOURS, "market-hours check disabled")

        checked_at_market = context.as_of.astimezone(
            ZoneInfo(self.config.market_timezone)
        )
        checked_time = checked_at_market.time()
        is_weekday = checked_at_market.weekday() < 5
        is_open = (
            is_weekday
            and self.config.market_open_time <= checked_time
            and checked_time <= self.config.market_close_time
        )
        if not is_open:
            return self._fail(
                RiskRule.MARKET_HOURS,
                "order is outside configured market hours",
                checked_at_market=checked_at_market.isoformat(),
                market_timezone=self.config.market_timezone,
            )
        return self._pass(RiskRule.MARKET_HOURS, "order is inside market hours")

    def _check_minimum_price(self, proposal: ProposedOrder) -> RiskRuleResult:
        if self.config.minimum_price is None:
            return self._pass(RiskRule.MIN_PRICE, "minimum price check disabled")
        if proposal.estimated_price < self.config.minimum_price:
            return self._fail(
                RiskRule.MIN_PRICE,
                "estimated price is below minimum",
                estimated_price=str(proposal.estimated_price),
                minimum_price=str(self.config.minimum_price),
            )
        return self._pass(RiskRule.MIN_PRICE, "estimated price is acceptable")

    def _check_minimum_average_daily_volume(
        self, proposal: ProposedOrder, context: RiskContext
    ) -> RiskRuleResult:
        if self.config.minimum_average_daily_volume is None:
            return self._pass(
                RiskRule.MIN_AVERAGE_DAILY_VOLUME,
                "minimum average daily volume check disabled",
            )
        volume = (
            proposal.average_daily_volume
            or context.average_daily_volume_by_symbol.get(proposal.order.symbol)
        )
        if volume is None:
            return self._fail(
                RiskRule.MIN_AVERAGE_DAILY_VOLUME,
                "average daily volume is missing",
            )
        if volume < self.config.minimum_average_daily_volume:
            return self._fail(
                RiskRule.MIN_AVERAGE_DAILY_VOLUME,
                "average daily volume is below minimum",
                average_daily_volume=str(volume),
                minimum_average_daily_volume=str(
                    self.config.minimum_average_daily_volume
                ),
            )
        return self._pass(
            RiskRule.MIN_AVERAGE_DAILY_VOLUME,
            "average daily volume is acceptable",
        )

    def _check_max_orders_per_day(self, context: RiskContext) -> RiskRuleResult:
        if self.config.max_orders_per_day is None:
            return self._pass(
                RiskRule.MAX_ORDERS_PER_DAY,
                "max orders per day check disabled",
            )
        if context.orders_today >= self.config.max_orders_per_day:
            return self._fail(
                RiskRule.MAX_ORDERS_PER_DAY,
                "max orders per day would be exceeded",
                orders_today=context.orders_today,
                max_orders_per_day=self.config.max_orders_per_day,
            )
        return self._pass(RiskRule.MAX_ORDERS_PER_DAY, "order count is acceptable")

    def _check_cash_available(
        self, proposal: ProposedOrder, context: RiskContext
    ) -> RiskRuleResult:
        if proposal.order.side != OrderSide.BUY:
            return self._pass(RiskRule.CASH_AVAILABLE, "cash check not needed for sell")
        required_cash = (
            proposal.order.quantity * proposal.estimated_price
            + proposal.estimated_commission
        )
        if required_cash > context.portfolio.cash:
            return self._fail(
                RiskRule.CASH_AVAILABLE,
                "insufficient cash for proposed buy",
                required_cash=str(required_cash),
                cash=str(context.portfolio.cash),
            )
        return self._pass(RiskRule.CASH_AVAILABLE, "cash is available")

    def _check_no_short_selling(
        self, order: Order, current: _PortfolioState
    ) -> RiskRuleResult:
        if order.side != OrderSide.SELL:
            return self._pass(RiskRule.NO_SHORT_SELLING, "not a sell order")
        current_quantity = current.quantities.get(order.symbol, Decimal("0"))
        if order.quantity > current_quantity:
            return self._fail(
                RiskRule.NO_SHORT_SELLING,
                "sell quantity exceeds current long position",
                sell_quantity=str(order.quantity),
                current_quantity=str(current_quantity),
            )
        return self._pass(RiskRule.NO_SHORT_SELLING, "sell stays long-only")

    def _check_max_position_quantity(
        self, order: Order, projected: _PortfolioState
    ) -> RiskRuleResult:
        limit = self.config.max_position_quantity_by_symbol.get(order.symbol)
        if limit is None:
            return self._pass(
                RiskRule.MAX_POSITION_QUANTITY,
                "position quantity check disabled",
            )
        projected_quantity = projected.quantities.get(order.symbol, Decimal("0"))
        if projected_quantity > limit:
            return self._fail(
                RiskRule.MAX_POSITION_QUANTITY,
                "projected position quantity exceeds limit",
                projected_quantity=str(projected_quantity),
                limit=str(limit),
            )
        return self._pass(
            RiskRule.MAX_POSITION_QUANTITY,
            "projected position quantity is acceptable",
        )

    def _check_max_position_notional(
        self, order: Order, projected: _PortfolioState
    ) -> RiskRuleResult:
        limit = self.config.max_position_notional_by_symbol.get(order.symbol)
        if limit is None:
            return self._pass(
                RiskRule.MAX_POSITION_NOTIONAL,
                "position notional check disabled",
            )
        projected_notional = projected.position_values.get(order.symbol, Decimal("0"))
        if projected_notional > limit:
            return self._fail(
                RiskRule.MAX_POSITION_NOTIONAL,
                "projected position notional exceeds limit",
                projected_notional=str(projected_notional),
                limit=str(limit),
            )
        return self._pass(
            RiskRule.MAX_POSITION_NOTIONAL,
            "projected position notional is acceptable",
        )

    def _check_max_symbol_allocation(
        self,
        order: Order,
        projected: _PortfolioState,
        projected_equity: Decimal,
    ) -> RiskRuleResult:
        if self.config.max_symbol_allocation is None:
            return self._pass(
                RiskRule.MAX_SYMBOL_ALLOCATION,
                "symbol allocation check disabled",
            )
        allocation = _allocation(
            projected.position_values.get(order.symbol, Decimal("0")),
            projected_equity,
        )
        if allocation > self.config.max_symbol_allocation:
            return self._fail(
                RiskRule.MAX_SYMBOL_ALLOCATION,
                "projected symbol allocation exceeds limit",
                allocation=str(allocation),
                limit=str(self.config.max_symbol_allocation),
            )
        return self._pass(
            RiskRule.MAX_SYMBOL_ALLOCATION,
            "projected symbol allocation is acceptable",
        )

    def _check_max_sector_allocation(
        self,
        proposal: ProposedOrder,
        projected: _PortfolioState,
        projected_equity: Decimal,
    ) -> RiskRuleResult:
        if self.config.max_sector_allocation is None:
            return self._pass(
                RiskRule.MAX_SECTOR_ALLOCATION,
                "sector allocation check disabled",
            )
        sector = proposal.sector or self.config.symbol_to_sector.get(
            proposal.order.symbol
        )
        if sector is None:
            return self._fail(
                RiskRule.MAX_SECTOR_ALLOCATION,
                "sector is required for sector allocation checks",
            )
        sector_value = Decimal("0")
        for symbol, value in projected.position_values.items():
            if self.config.symbol_to_sector.get(symbol) == sector:
                sector_value += value
        if self.config.symbol_to_sector.get(proposal.order.symbol) is None:
            sector_value += projected.position_values.get(
                proposal.order.symbol, Decimal("0")
            )
        allocation = _allocation(sector_value, projected_equity)
        if allocation > self.config.max_sector_allocation:
            return self._fail(
                RiskRule.MAX_SECTOR_ALLOCATION,
                "projected sector allocation exceeds limit",
                sector=sector,
                allocation=str(allocation),
                limit=str(self.config.max_sector_allocation),
            )
        return self._pass(
            RiskRule.MAX_SECTOR_ALLOCATION,
            "projected sector allocation is acceptable",
        )

    def _check_max_strategy_allocation(
        self,
        proposal: ProposedOrder,
        context: RiskContext,
        order_notional: Decimal,
        projected_equity: Decimal,
    ) -> RiskRuleResult:
        if self.config.max_strategy_allocation is None:
            return self._pass(
                RiskRule.MAX_STRATEGY_ALLOCATION,
                "strategy allocation check disabled",
            )
        current_exposure = context.strategy_exposure.get(
            proposal.strategy_id, Decimal("0")
        )
        projected_exposure = current_exposure
        if proposal.order.side == OrderSide.BUY:
            projected_exposure += order_notional
        else:
            projected_exposure = max(projected_exposure - order_notional, Decimal("0"))
        allocation = _allocation(projected_exposure, projected_equity)
        if allocation > self.config.max_strategy_allocation:
            return self._fail(
                RiskRule.MAX_STRATEGY_ALLOCATION,
                "projected strategy allocation exceeds limit",
                strategy_id=proposal.strategy_id,
                allocation=str(allocation),
                limit=str(self.config.max_strategy_allocation),
            )
        return self._pass(
            RiskRule.MAX_STRATEGY_ALLOCATION,
            "projected strategy allocation is acceptable",
        )

    def _check_max_portfolio_gross_exposure(
        self, projected: _PortfolioState, projected_equity: Decimal
    ) -> RiskRuleResult:
        if self.config.max_portfolio_gross_exposure is None:
            return self._pass(
                RiskRule.MAX_PORTFOLIO_GROSS_EXPOSURE,
                "portfolio exposure check disabled",
            )
        gross_exposure = _allocation(
            sum(projected.position_values.values(), Decimal("0")),
            projected_equity,
        )
        if gross_exposure > self.config.max_portfolio_gross_exposure:
            return self._fail(
                RiskRule.MAX_PORTFOLIO_GROSS_EXPOSURE,
                "projected portfolio gross exposure exceeds limit",
                gross_exposure=str(gross_exposure),
                limit=str(self.config.max_portfolio_gross_exposure),
            )
        return self._pass(
            RiskRule.MAX_PORTFOLIO_GROSS_EXPOSURE,
            "projected portfolio gross exposure is acceptable",
        )

    def _check_max_turnover(
        self,
        context: RiskContext,
        order_notional: Decimal,
        equity: Decimal,
    ) -> RiskRuleResult:
        if self.config.max_turnover is None:
            return self._pass(RiskRule.MAX_TURNOVER, "turnover check disabled")
        projected_turnover = _allocation(
            context.notional_traded_today + order_notional,
            equity,
        )
        if projected_turnover > self.config.max_turnover:
            return self._fail(
                RiskRule.MAX_TURNOVER,
                "projected turnover exceeds limit",
                projected_turnover=str(projected_turnover),
                limit=str(self.config.max_turnover),
            )
        return self._pass(RiskRule.MAX_TURNOVER, "projected turnover is acceptable")

    def _check_max_daily_loss(self, context: RiskContext) -> RiskRuleResult:
        if self.config.max_daily_loss is None:
            return self._pass(RiskRule.MAX_DAILY_LOSS, "daily loss check disabled")
        current_loss = max(-context.realized_pnl_today, Decimal("0"))
        if current_loss >= self.config.max_daily_loss:
            return self._fail(
                RiskRule.MAX_DAILY_LOSS,
                "max daily loss threshold has been reached",
                current_loss=str(current_loss),
                limit=str(self.config.max_daily_loss),
            )
        return self._pass(RiskRule.MAX_DAILY_LOSS, "daily loss is acceptable")

    def _check_max_drawdown(
        self, context: RiskContext, equity: Decimal
    ) -> RiskRuleResult:
        if self.config.max_drawdown is None:
            return self._pass(RiskRule.MAX_DRAWDOWN, "drawdown check disabled")
        peak_equity = context.peak_equity
        if peak_equity is None or peak_equity == Decimal("0"):
            return self._pass(RiskRule.MAX_DRAWDOWN, "peak equity unavailable")
        drawdown = max((peak_equity - equity) / peak_equity, Decimal("0"))
        if drawdown >= self.config.max_drawdown:
            return self._fail(
                RiskRule.MAX_DRAWDOWN,
                "max drawdown threshold has been reached",
                drawdown=str(drawdown),
                limit=str(self.config.max_drawdown),
            )
        return self._pass(RiskRule.MAX_DRAWDOWN, "drawdown is acceptable")


class _PortfolioState:
    def __init__(
        self,
        *,
        cash: Decimal,
        quantities: dict[str, Decimal],
        prices: dict[str, Decimal],
    ) -> None:
        self.cash = cash
        self.quantities = quantities
        self.prices = prices
        self.position_values = {
            symbol: quantity * self.prices[symbol]
            for symbol, quantity in self.quantities.items()
            if quantity > 0
        }
        self.equity = self.cash + sum(self.position_values.values(), Decimal("0"))

    @classmethod
    def from_context(
        cls, context: RiskContext, proposal: ProposedOrder
    ) -> _PortfolioState:
        quantities = {
            position.symbol: position.quantity
            for position in context.portfolio.positions
        }
        prices = {
            position.symbol: context.latest_prices.get(
                position.symbol, position.average_cost
            )
            for position in context.portfolio.positions
        }
        prices[proposal.order.symbol] = proposal.estimated_price
        return cls(cash=context.portfolio.cash, quantities=quantities, prices=prices)

    def project(self, proposal: ProposedOrder) -> _PortfolioState:
        quantities = dict(self.quantities)
        prices = dict(self.prices)
        order = proposal.order
        prices[order.symbol] = proposal.estimated_price
        if order.side == OrderSide.BUY:
            quantities[order.symbol] = (
                quantities.get(order.symbol, Decimal("0")) + order.quantity
            )
            cash = (
                self.cash
                - order.quantity * proposal.estimated_price
                - proposal.estimated_commission
            )
        else:
            next_quantity = quantities.get(order.symbol, Decimal("0")) - order.quantity
            if next_quantity > 0:
                quantities[order.symbol] = next_quantity
            else:
                quantities.pop(order.symbol, None)
            cash = (
                self.cash
                + order.quantity * proposal.estimated_price
                - proposal.estimated_commission
            )
        return _PortfolioState(cash=cash, quantities=quantities, prices=prices)


def _allocation(value: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        return Decimal("Infinity")
    return value / equity
