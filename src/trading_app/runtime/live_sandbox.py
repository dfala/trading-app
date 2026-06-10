"""Bounded live-money sandbox for the active paper champion."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from trading_app.alpaca_credentials import normalize_alpaca_env_value
from trading_app.broker import AlpacaLiveBrokerAdapter, PaperBrokerAdapter
from trading_app.broker.models import (
    BrokerOrderState,
    BrokerPortfolioState,
    BrokerPositionState,
)
from trading_app.live.readiness import LIVE_RISK_CONFIRMATION
from trading_app.market_data import HistoricalBarFetcher, LatestPriceSnapshot
from trading_app.paper import (
    PaperOrderStatus,
    PaperOrderSubmission,
    PaperTradingService,
)
from trading_app.risk import RiskConfig, RiskEngine
from trading_app.schemas import (
    DataFeed,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioSnapshot,
    Position,
    TradingModel,
    validate_symbol,
)
from trading_app.strategies.benchmark_relative import (
    BenchmarkRelativeStrengthETFStrategy,
)
from trading_app.strategies.catalog import StrategyAuthority

LIVE_SANDBOX_MODEL_KEY = "benchmark_relative_strength_etf:grid-l252-t21-n2"
LIVE_SANDBOX_UNIVERSE_ID = "macro-defensive"
LIVE_SANDBOX_ALLOWED_SYMBOLS = (
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
)
LIVE_SANDBOX_BENCHMARK = "SPY"
LIVE_SANDBOX_ORDER_PREFIX = "live-sandbox-"
MARKET_TZ = ZoneInfo("America/New_York")
QUANTITY_INCREMENT = Decimal("0.000001")
MIN_ORDER_NOTIONAL = Decimal("1")


class LiveSandboxStatus(StrEnum):
    DISABLED = "disabled"
    BROKER_UNAVAILABLE = "broker_unavailable"
    PAUSED = "paused"
    KILL_SWITCH = "kill_switch"
    BLOCKED = "blocked"
    ARMED = "armed"
    RUNNING = "running"


class LiveSandboxControlAction(StrEnum):
    ENABLE_LIVE_AUTONOMY = "enable_live_autonomy"
    PAUSE_LIVE_AUTONOMY = "pause_live_autonomy"
    RESUME_LIVE_AUTONOMY = "resume_live_autonomy"
    ENABLE_LIVE_KILL_SWITCH = "enable_live_kill_switch"
    DISABLE_LIVE_KILL_SWITCH = "disable_live_kill_switch"
    FORCE_LIVE_RECONCILIATION = "force_live_reconciliation"


class LiveSandboxConfig(TradingModel):
    enabled: bool = False
    model_key: str = LIVE_SANDBOX_MODEL_KEY
    universe_id: str = LIVE_SANDBOX_UNIVERSE_ID
    allowed_symbols: tuple[str, ...] = LIVE_SANDBOX_ALLOWED_SYMBOLS
    benchmark_symbol: str = LIVE_SANDBOX_BENCHMARK
    max_live_allocation: Decimal = Field(default=Decimal("100"), gt=Decimal("0"))
    max_order_notional: Decimal = Field(default=Decimal("100"), gt=Decimal("0"))
    max_orders_per_day: int = Field(default=4, gt=0)
    max_daily_loss: Decimal = Field(default=Decimal("10"), gt=Decimal("0"))
    min_order_notional: Decimal = Field(default=MIN_ORDER_NOTIONAL, gt=Decimal("0"))
    order_prefix: str = Field(default=LIVE_SANDBOX_ORDER_PREFIX, min_length=1)
    confirmation: str | None = Field(default=None, min_length=1)
    live_account_id: str = Field(default="alpaca-live-sandbox", min_length=1)
    enforce_market_hours: bool = True
    market_open_time: dt_time = dt_time(hour=9, minute=30)
    market_close_time: dt_time = dt_time(hour=16)
    feed: DataFeed = DataFeed.IEX

    @field_validator("allowed_symbols")
    @classmethod
    def _validate_allowed_symbols(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_symbol(symbol) for symbol in symbols)

    @field_validator("benchmark_symbol")
    @classmethod
    def _validate_benchmark_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)

    @model_validator(mode="after")
    def _validate_fixed_live_sandbox(self) -> LiveSandboxConfig:
        if self.model_key != LIVE_SANDBOX_MODEL_KEY:
            raise ValueError("live sandbox is fixed to the approved champion model")
        if self.universe_id != LIVE_SANDBOX_UNIVERSE_ID:
            raise ValueError("live sandbox is fixed to the macro-defensive universe")
        if set(self.allowed_symbols) != set(LIVE_SANDBOX_ALLOWED_SYMBOLS):
            raise ValueError("live sandbox symbols must match the approved universe")
        return self

    @property
    def has_live_confirmation(self) -> bool:
        return self.confirmation == LIVE_RISK_CONFIRMATION


class LiveSandboxControlState(TradingModel):
    live_autonomy_enabled: bool = False
    live_kill_switch_enabled: bool = True
    updated_at: AwareDatetime
    updated_by: str = Field(default="system", min_length=1)
    reason: str = ""


class LiveSandboxControlRequest(TradingModel):
    action: LiveSandboxControlAction
    requested_at: AwareDatetime
    requested_by: str = Field(min_length=1)
    reason: str = ""


class LiveSandboxControlResult(TradingModel):
    request: LiveSandboxControlRequest
    accepted: bool
    message: str = Field(min_length=1)
    control_state: LiveSandboxControlState
    canceled_order_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class LiveSandboxOrderIntent(TradingModel):
    symbol: str
    side: OrderSide
    quantity: Decimal
    estimated_price: Decimal
    estimated_notional: Decimal
    current_value: Decimal
    target_value: Decimal

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, symbol: str) -> str:
        return validate_symbol(symbol)


class LiveSandboxCycleResult(TradingModel):
    as_of: AwareDatetime
    status: LiveSandboxStatus
    orders_submitted: int = Field(ge=0)
    fills_applied: int = Field(ge=0)
    broker_synced: bool = False
    targets: dict[str, Decimal] = Field(default_factory=dict)
    order_intents: tuple[LiveSandboxOrderIntent, ...] = ()
    submitted_order_ids: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    sandbox_cash: Decimal = Decimal("0")
    sandbox_equity: Decimal = Decimal("0")
    cap_deployed: Decimal = Decimal("0")
    external_conflicts: tuple[str, ...] = ()


class LiveSandboxSnapshot(TradingModel):
    generated_at: AwareDatetime
    enabled: bool
    status: LiveSandboxStatus
    model_key: str
    universe_id: str
    allowed_symbols: tuple[str, ...]
    benchmark_symbol: str
    order_prefix: str
    broker_provider: str | None = None
    live_account_id: str | None = None
    max_live_allocation: Decimal
    max_order_notional: Decimal
    max_orders_per_day: int
    max_daily_loss: Decimal
    min_order_notional: Decimal
    control_state: LiveSandboxControlState
    sandbox_cash: Decimal
    sandbox_equity: Decimal
    cap_deployed: Decimal
    positions: tuple[Position, ...] = ()
    broker_positions: tuple[BrokerPositionState, ...] = ()
    open_orders: tuple[BrokerOrderState, ...] = ()
    recent_fills: tuple[Fill, ...] = ()
    latest_cycle: LiveSandboxCycleResult | None = None
    last_control_result: LiveSandboxControlResult | None = None
    blocked_reasons: tuple[str, ...] = ()
    order_intents: tuple[LiveSandboxOrderIntent, ...] = ()
    external_conflicts: tuple[str, ...] = ()
    broker_error: str | None = None


class LiveSandboxRuntime:
    """Run one bounded autonomous live-money sandbox beside paper trading."""

    def __init__(
        self,
        *,
        config: LiveSandboxConfig | None = None,
        service: PaperTradingService | None = None,
        broker_error: str | None = None,
        control_state: LiveSandboxControlState | None = None,
    ) -> None:
        self.config = config or LiveSandboxConfig()
        self.service = service
        self.broker_error = broker_error
        self.control_state = control_state or LiveSandboxControlState(
            updated_at=datetime.now(tz=UTC),
            reason="live sandbox starts with autonomy off and kill switch on",
        )
        self.strategy = build_live_sandbox_strategy(self.config)
        self._latest_cycle: LiveSandboxCycleResult | None = None
        self._last_control_result: LiveSandboxControlResult | None = None

    @classmethod
    def disabled(cls) -> LiveSandboxRuntime:
        return cls(config=LiveSandboxConfig(enabled=False))

    @classmethod
    def from_env(cls) -> LiveSandboxRuntime:
        config = live_sandbox_config_from_env()
        if not config.enabled:
            return cls(config=config)
        if not config.has_live_confirmation:
            return cls(
                config=config,
                broker_error=(
                    "TRADING_APP_LIVE_SANDBOX_CONFIRMATION must equal "
                    f"{LIVE_RISK_CONFIRMATION} before live broker creation."
                ),
            )
        api_key = _live_env("APCA_LIVE_API_KEY_ID", "ALPACA_LIVE_API_KEY")
        secret_key = _live_env("APCA_LIVE_API_SECRET_KEY", "ALPACA_LIVE_SECRET_KEY")
        if not api_key or not secret_key:
            return cls(
                config=config,
                broker_error=(
                    "APCA_LIVE_API_KEY_ID/APCA_LIVE_API_SECRET_KEY are required "
                    "for the live sandbox."
                ),
            )
        try:
            broker = AlpacaLiveBrokerAdapter(
                api_key=api_key,
                secret_key=secret_key,
                live_trading_enabled=True,
                explicit_confirmation=config.confirmation,
            )
        except Exception as error:
            return cls(config=config, broker_error=str(error))
        service = live_sandbox_service(broker=broker, config=config)
        return cls(config=config, service=service)

    @property
    def last_control_result(self) -> LiveSandboxControlResult | None:
        return self._last_control_result

    def restore_state(
        self,
        *,
        control_state: LiveSandboxControlState | None = None,
        submissions: tuple[PaperOrderSubmission, ...] = (),
        order_statuses: tuple[PaperOrderStatus, ...] = (),
        fills: tuple[Fill, ...] = (),
        latest_cycle: LiveSandboxCycleResult | None = None,
    ) -> None:
        if control_state is not None:
            self.control_state = control_state
        if self.service is not None:
            self.service.restore_state(
                submissions=submissions,
                order_statuses=order_statuses,
                fills=fills,
            )
        self._latest_cycle = latest_cycle

    def apply_control(
        self,
        request: LiveSandboxControlRequest | LiveSandboxControlAction | str,
        *,
        requested_by: str = "local-operator",
        reason: str = "",
        requested_at: datetime | None = None,
    ) -> LiveSandboxControlResult:
        if not isinstance(request, LiveSandboxControlRequest):
            request = LiveSandboxControlRequest(
                action=LiveSandboxControlAction(request),
                requested_at=requested_at or datetime.now(tz=UTC),
                requested_by=requested_by,
                reason=reason,
            )

        accepted = True
        message = "Live sandbox control accepted."
        canceled: list[str] = []
        errors: list[str] = []
        updates: dict[str, object] = {
            "updated_at": request.requested_at,
            "updated_by": request.requested_by,
            "reason": request.reason,
        }
        if request.action in {
            LiveSandboxControlAction.ENABLE_LIVE_AUTONOMY,
            LiveSandboxControlAction.RESUME_LIVE_AUTONOMY,
        }:
            if not self.config.enabled:
                accepted = False
                message = "Live sandbox is disabled by configuration."
            elif self.broker_error:
                accepted = False
                message = f"Live sandbox broker unavailable: {self.broker_error}"
            elif not self.config.has_live_confirmation:
                accepted = False
                message = "Live risk confirmation is missing."
            else:
                updates["live_autonomy_enabled"] = True
                updates["live_kill_switch_enabled"] = False
                message = "Live sandbox autonomy armed under the $100 cap."
        elif request.action == LiveSandboxControlAction.PAUSE_LIVE_AUTONOMY:
            updates["live_autonomy_enabled"] = False
            message = "Live sandbox autonomy paused."
        elif request.action == LiveSandboxControlAction.ENABLE_LIVE_KILL_SWITCH:
            updates["live_autonomy_enabled"] = False
            updates["live_kill_switch_enabled"] = True
            canceled, errors = self._cancel_open_sandbox_orders(request.requested_at)
            message = "Live sandbox kill switch enabled; tagged open orders canceled."
        elif request.action == LiveSandboxControlAction.DISABLE_LIVE_KILL_SWITCH:
            updates["live_kill_switch_enabled"] = False
            message = "Live sandbox kill switch disabled; autonomy remains unchanged."
        elif request.action == LiveSandboxControlAction.FORCE_LIVE_RECONCILIATION:
            message = "Live sandbox reconciliation requested."
        else:
            accepted = False
            message = "Unsupported live sandbox control action."

        if accepted:
            self.control_state = self.control_state.model_copy(update=updates)
        result = LiveSandboxControlResult(
            request=request,
            accepted=accepted,
            message=message,
            control_state=self.control_state,
            canceled_order_ids=tuple(canceled),
            errors=tuple(errors),
        )
        self._last_control_result = result
        return result

    def run_once(
        self,
        *,
        as_of: datetime,
        latest_prices: LatestPriceSnapshot | None,
        historical_bar_fetcher: HistoricalBarFetcher,
    ) -> LiveSandboxCycleResult:
        broker_orders: tuple[BrokerOrderState, ...] = ()
        broker_portfolio: BrokerPortfolioState | None = None
        fills_applied = 0
        broker_synced = False
        if self.service is not None:
            try:
                broker_orders = self.service.broker.list_orders(
                    symbols=self.config.allowed_symbols,
                    limit=500,
                )
                broker_portfolio = _filtered_broker_portfolio(
                    self.service.broker.get_portfolio(as_of),
                    self.config.allowed_symbols,
                )
                fills_applied = self._sync_tagged_broker_orders(
                    broker_orders,
                    as_of=as_of,
                )
                broker_synced = True
                self.broker_error = None
            except Exception as error:
                self.broker_error = str(error)

        snapshot = self._ledger_snapshot(as_of)
        latest_price_map = latest_prices.price_map if latest_prices else {}
        targets: dict[str, Decimal] = {}
        intents: tuple[LiveSandboxOrderIntent, ...] = ()
        if latest_prices is not None and latest_prices.all_fresh:
            try:
                targets = self._strategy_targets(
                    as_of=as_of,
                    historical_bar_fetcher=historical_bar_fetcher,
                )
                intents = self._plan_orders(
                    snapshot=snapshot,
                    targets=targets,
                    latest_prices=latest_price_map,
                )
            except Exception as error:
                targets = {}
                intents = ()
                self.broker_error = self.broker_error or str(error)

        external_conflicts = self._external_conflicts(
            broker_orders=broker_orders,
            broker_portfolio=broker_portfolio,
            snapshot=snapshot,
            latest_prices=latest_price_map,
        )
        blocked = self._blocked_reasons(
            as_of=as_of,
            latest_prices=latest_prices,
            broker_orders=broker_orders,
            broker_synced=broker_synced,
            external_conflicts=external_conflicts,
            snapshot=snapshot,
            intents=intents,
        )
        submitted_ids: list[str] = []
        status = self._status(blocked)
        if not blocked:
            submitted_ids = self._submit_intents(
                intents,
                latest_prices=latest_price_map,
                as_of=as_of,
            )
            status = (
                LiveSandboxStatus.RUNNING
                if submitted_ids
                else LiveSandboxStatus.ARMED
            )

        sandbox_equity = _estimated_equity(snapshot, latest_price_map)
        cap_deployed = _cap_deployed(snapshot, latest_price_map)
        cycle = LiveSandboxCycleResult(
            as_of=as_of,
            status=status,
            orders_submitted=len(submitted_ids),
            fills_applied=fills_applied,
            broker_synced=broker_synced,
            targets=targets,
            order_intents=intents,
            submitted_order_ids=tuple(submitted_ids),
            blocked_reasons=tuple(blocked),
            sandbox_cash=snapshot.cash,
            sandbox_equity=sandbox_equity,
            cap_deployed=cap_deployed,
            external_conflicts=external_conflicts,
        )
        self._latest_cycle = cycle
        return cycle

    def snapshot(
        self,
        *,
        as_of: datetime,
        latest_prices: LatestPriceSnapshot | None = None,
    ) -> LiveSandboxSnapshot:
        latest_price_map = latest_prices.price_map if latest_prices else {}
        ledger_snapshot = self._ledger_snapshot(as_of)
        broker_orders: tuple[BrokerOrderState, ...] = ()
        broker_positions: tuple[BrokerPositionState, ...] = ()
        open_orders: tuple[BrokerOrderState, ...] = ()
        if self.service is not None:
            try:
                broker_orders = self.service.broker.list_orders(
                    symbols=self.config.allowed_symbols,
                    limit=500,
                )
                broker_positions = _filtered_broker_portfolio(
                    self.service.broker.get_portfolio(as_of),
                    self.config.allowed_symbols,
                ).positions
                open_orders = tuple(
                    order
                    for order in broker_orders
                    if order.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
                    and _is_live_sandbox_order_id(
                        order.client_order_id,
                        prefix=self.config.order_prefix,
                    )
                )
                self.broker_error = None
            except Exception as error:
                self.broker_error = str(error)
        latest_cycle = self._latest_cycle
        blocked = (
            latest_cycle.blocked_reasons
            if latest_cycle is not None
            else self._baseline_blocked_reasons()
        )
        return LiveSandboxSnapshot(
            generated_at=as_of,
            enabled=self.config.enabled,
            status=latest_cycle.status if latest_cycle else self._status(blocked),
            model_key=self.config.model_key,
            universe_id=self.config.universe_id,
            allowed_symbols=self.config.allowed_symbols,
            benchmark_symbol=self.config.benchmark_symbol,
            order_prefix=self.config.order_prefix,
            broker_provider=self.service.broker.provider if self.service else None,
            live_account_id=self.config.live_account_id,
            max_live_allocation=self.config.max_live_allocation,
            max_order_notional=self.config.max_order_notional,
            max_orders_per_day=self.config.max_orders_per_day,
            max_daily_loss=self.config.max_daily_loss,
            min_order_notional=self.config.min_order_notional,
            control_state=self.control_state,
            sandbox_cash=ledger_snapshot.cash,
            sandbox_equity=_estimated_equity(ledger_snapshot, latest_price_map),
            cap_deployed=_cap_deployed(ledger_snapshot, latest_price_map),
            positions=ledger_snapshot.positions,
            broker_positions=broker_positions,
            open_orders=open_orders,
            recent_fills=tuple(self.service.fills[-10:]) if self.service else (),
            latest_cycle=latest_cycle,
            last_control_result=self._last_control_result,
            blocked_reasons=blocked,
            order_intents=latest_cycle.order_intents if latest_cycle else (),
            external_conflicts=latest_cycle.external_conflicts if latest_cycle else (),
            broker_error=self.broker_error,
        )

    def _sync_tagged_broker_orders(
        self,
        broker_orders: tuple[BrokerOrderState, ...],
        *,
        as_of: datetime,
    ) -> int:
        if self.service is None:
            return 0
        fills_applied = 0
        for broker_order in broker_orders:
            order_id = broker_order.client_order_id
            if not _is_live_sandbox_order_id(order_id, prefix=self.config.order_prefix):
                continue
            if self.service.ledger.get_order(order_id) is None:
                self.service.recover_broker_order(
                    broker_order,
                    strategy_id=self.strategy.strategy_id,
                    as_of=as_of,
                )
            _, fill = self.service.sync_broker_order_state(broker_order, as_of=as_of)
            if fill is not None:
                fills_applied += 1
        return fills_applied

    def _strategy_targets(
        self,
        *,
        as_of: datetime,
        historical_bar_fetcher: HistoricalBarFetcher,
    ) -> dict[str, Decimal]:
        local_date = as_of.astimezone(MARKET_TZ).date()
        symbols = tuple(
            sorted(set(self.config.allowed_symbols) | {self.config.benchmark_symbol})
        )
        history_days = max(
            260,
            max(self.strategy.lookback_days, self.strategy.tracking_window_days) * 3,
        )
        bars = historical_bar_fetcher.fetch_daily_bars(
            list(symbols),
            local_date - timedelta(days=history_days),
            local_date,
            self.config.feed,
        )
        generated = self.strategy.generate_targets(bars, local_date)
        return {
            symbol: weight
            for symbol, weight in generated.items()
            if symbol in self.config.allowed_symbols and weight > 0
        }

    def _plan_orders(
        self,
        *,
        snapshot: PortfolioSnapshot,
        targets: dict[str, Decimal],
        latest_prices: dict[str, Decimal],
    ) -> tuple[LiveSandboxOrderIntent, ...]:
        if not latest_prices:
            return ()
        target_equity = min(
            self.config.max_live_allocation,
            _estimated_equity(snapshot, latest_prices),
        )
        cash = snapshot.cash
        positions = {position.symbol: position for position in snapshot.positions}
        target_values = {
            symbol: target_equity * weight for symbol, weight in targets.items()
        }
        intents: list[LiveSandboxOrderIntent] = []

        for symbol in sorted(set(positions) | set(targets)):
            if symbol not in latest_prices:
                continue
            position = positions.get(symbol)
            if position is None:
                continue
            price = latest_prices[symbol]
            current_value = position.quantity * price
            target_value = target_values.get(symbol, Decimal("0"))
            if current_value <= target_value:
                continue
            quantity = (
                position.quantity
                if target_value == 0
                else (current_value - target_value) / price
            )
            quantity = _round_quantity_down(min(quantity, position.quantity))
            notional = quantity * price
            if quantity <= 0 or notional < self.config.min_order_notional:
                continue
            intents.append(
                LiveSandboxOrderIntent(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=quantity,
                    estimated_price=price,
                    estimated_notional=notional,
                    current_value=current_value,
                    target_value=target_value,
                )
            )
            cash += notional

        for symbol in sorted(targets):
            if symbol not in latest_prices:
                continue
            price = latest_prices[symbol]
            position = positions.get(symbol)
            current_quantity = position.quantity if position else Decimal("0")
            current_value = current_quantity * price
            target_value = target_values[symbol]
            if current_value >= target_value:
                continue
            available_cash = (
                min(cash, self.config.max_live_allocation) * Decimal("0.99")
            )
            quantity = min(
                (target_value - current_value) / price,
                available_cash / price,
            )
            quantity = _round_quantity_down(quantity)
            notional = quantity * price
            if quantity <= 0 or notional < self.config.min_order_notional:
                continue
            intents.append(
                LiveSandboxOrderIntent(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    quantity=quantity,
                    estimated_price=price,
                    estimated_notional=notional,
                    current_value=current_value,
                    target_value=target_value,
                )
            )
            cash -= notional
        return tuple(intents)

    def _blocked_reasons(
        self,
        *,
        as_of: datetime,
        latest_prices: LatestPriceSnapshot | None,
        broker_orders: tuple[BrokerOrderState, ...],
        broker_synced: bool,
        external_conflicts: tuple[str, ...],
        snapshot: PortfolioSnapshot,
        intents: tuple[LiveSandboxOrderIntent, ...],
    ) -> list[str]:
        blocked = list(self._baseline_blocked_reasons())
        if self.config.enabled and self.service is None and not self.broker_error:
            blocked.append("Live sandbox broker is not configured.")
        if self.config.enabled and self.service is not None and not broker_synced:
            blocked.append("Live broker state did not sync.")
        if latest_prices is None:
            blocked.append("Latest prices are unavailable.")
        elif not latest_prices.all_fresh:
            blocked.append("Latest prices are stale or missing.")
        elif missing := sorted(
            symbol
            for symbol in self.config.allowed_symbols
            if symbol not in latest_prices.price_map
        ):
            blocked.append(f"Latest prices missing for: {', '.join(missing)}.")
        if self.config.enforce_market_hours and not _is_market_hours(
            as_of,
            open_time=self.config.market_open_time,
            close_time=self.config.market_close_time,
        ):
            blocked.append("Live sandbox only trades during regular market hours.")
        if external_conflicts:
            blocked.extend(external_conflicts)
        open_tagged_orders = [
            order.client_order_id or order.broker_order_id
            for order in broker_orders
            if order.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
            and _is_live_sandbox_order_id(
                order.client_order_id,
                prefix=self.config.order_prefix,
            )
        ]
        if open_tagged_orders:
            blocked.append(
                "Tagged live sandbox orders are still open: "
                f"{', '.join(open_tagged_orders)}."
            )
        orders_today = self._orders_submitted_today(as_of)
        if orders_today >= self.config.max_orders_per_day:
            blocked.append("Live sandbox max orders per day has been reached.")
        remaining_orders = self.config.max_orders_per_day - orders_today
        if len(intents) > remaining_orders:
            blocked.append(
                "Planned rebalance exceeds remaining live sandbox orders today."
            )
        too_large = [
            intent
            for intent in intents
            if intent.estimated_notional > self.config.max_order_notional
        ]
        if too_large:
            symbols = ", ".join(intent.symbol for intent in too_large)
            blocked.append(f"Planned order exceeds max order notional: {symbols}.")
        latest_price_map = latest_prices.price_map if latest_prices else {}
        sandbox_equity = _estimated_equity(snapshot, latest_price_map)
        if (
            self.config.max_live_allocation - sandbox_equity
            >= self.config.max_daily_loss
        ):
            blocked.append("Live sandbox daily loss stop is breached.")
        return blocked

    def _baseline_blocked_reasons(self) -> tuple[str, ...]:
        blocked: list[str] = []
        if not self.config.enabled:
            blocked.append("Live sandbox is disabled by configuration.")
        if self.broker_error:
            blocked.append(f"Live sandbox broker unavailable: {self.broker_error}")
        if not self.config.has_live_confirmation:
            blocked.append("Live risk confirmation is missing.")
        if not self.control_state.live_autonomy_enabled:
            blocked.append("Live sandbox autonomy is paused.")
        if self.control_state.live_kill_switch_enabled:
            blocked.append("Live sandbox kill switch is enabled.")
        return tuple(blocked)

    def _status(self, blocked: tuple[str, ...] | list[str]) -> LiveSandboxStatus:
        if not self.config.enabled:
            return LiveSandboxStatus.DISABLED
        if self.broker_error:
            return LiveSandboxStatus.BROKER_UNAVAILABLE
        if self.control_state.live_kill_switch_enabled:
            return LiveSandboxStatus.KILL_SWITCH
        if not self.control_state.live_autonomy_enabled:
            return LiveSandboxStatus.PAUSED
        if blocked:
            return LiveSandboxStatus.BLOCKED
        return LiveSandboxStatus.ARMED

    def _submit_intents(
        self,
        intents: tuple[LiveSandboxOrderIntent, ...],
        *,
        latest_prices: dict[str, Decimal],
        as_of: datetime,
    ) -> list[str]:
        if self.service is None:
            return []
        submitted: list[str] = []
        remaining = self.config.max_orders_per_day - self._orders_submitted_today(as_of)
        for intent in intents[:remaining]:
            if intent.estimated_notional > self.config.max_order_notional:
                continue
            order = Order(
                id=self._next_order_id(as_of, intent.symbol, intent.side),
                symbol=intent.symbol,
                side=intent.side,
                order_type=OrderType.MARKET,
                quantity=intent.quantity,
                created_at=as_of,
            )
            submission = self.service.submit_order(
                order,
                strategy_id=self.strategy.strategy_id,
                estimated_price=intent.estimated_price,
                as_of=as_of,
                latest_prices=latest_prices,
            )
            if submission.accepted and submission.broker_submitted:
                submitted.append(order.id)
        return submitted

    def _cancel_open_sandbox_orders(
        self,
        canceled_at: datetime,
    ) -> tuple[list[str], list[str]]:
        canceled: list[str] = []
        errors: list[str] = []
        if self.service is None:
            return canceled, errors
        for status in self.service.order_statuses:
            if status.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
                continue
            if not _is_live_sandbox_order_id(
                status.order_id,
                prefix=self.config.order_prefix,
            ):
                continue
            try:
                self.service.cancel_order(status.order_id, canceled_at=canceled_at)
                canceled.append(status.order_id)
            except Exception as error:
                errors.append(f"{status.order_id}: {error}")
        return canceled, errors

    def _external_conflicts(
        self,
        *,
        broker_orders: tuple[BrokerOrderState, ...],
        broker_portfolio: BrokerPortfolioState | None,
        snapshot: PortfolioSnapshot,
        latest_prices: dict[str, Decimal],
    ) -> tuple[str, ...]:
        conflicts: list[str] = []
        for order in broker_orders:
            if order.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
                continue
            if _is_live_sandbox_order_id(
                order.client_order_id,
                prefix=self.config.order_prefix,
            ):
                continue
            conflicts.append(
                "External open order in sandbox symbol "
                f"{order.symbol}; live sandbox blocked."
            )
        if broker_portfolio is None:
            return tuple(conflicts)
        ledger_positions = {
            position.symbol: position for position in snapshot.positions
        }
        for broker_position in broker_portfolio.positions:
            if broker_position.symbol not in self.config.allowed_symbols:
                continue
            ledger_quantity = ledger_positions.get(broker_position.symbol)
            expected = ledger_quantity.quantity if ledger_quantity else Decimal("0")
            if abs(expected - broker_position.quantity) > QUANTITY_INCREMENT:
                conflicts.append(
                    "External live position or fill mismatch in sandbox symbol "
                    f"{broker_position.symbol}; expected {expected}, broker has "
                    f"{broker_position.quantity}."
                )
        if not conflicts and latest_prices:
            cap_deployed = _cap_deployed(snapshot, latest_prices)
            if cap_deployed > self.config.max_live_allocation + Decimal("0.01"):
                conflicts.append("Live sandbox deployed capital exceeds the hard cap.")
        return tuple(conflicts)

    def _orders_submitted_today(self, as_of: datetime) -> int:
        if self.service is None:
            return 0
        local_date = as_of.astimezone(MARKET_TZ).date()
        return sum(
            1
            for submission in self.service.submissions
            if submission.accepted
            and submission.broker_submitted
            and submission.submitted_at.astimezone(MARKET_TZ).date() == local_date
        )

    def _ledger_snapshot(self, as_of: datetime) -> PortfolioSnapshot:
        if self.service is None:
            return PortfolioSnapshot(
                cash=self.config.max_live_allocation,
                positions=(),
                realized_pnl=Decimal("0"),
                total_fees=Decimal("0"),
                as_of=as_of,
            )
        return self.service.ledger.snapshot(as_of)

    def _next_order_id(self, as_of: datetime, symbol: str, side: OrderSide) -> str:
        suffix = len(self.service.submissions) + 1 if self.service else 1
        timestamp = as_of.astimezone(MARKET_TZ).strftime("%Y%m%d-%H%M%S")
        return (
            f"{self.config.order_prefix}{timestamp}-{symbol}-"
            f"{side.value.lower()}-{suffix}"
        )


def live_sandbox_config_from_env(
    env: dict[str, str] | None = None,
) -> LiveSandboxConfig:
    source = env if env is not None else os.environ
    enabled = _truthy(source.get("TRADING_APP_LIVE_SANDBOX_ENABLED"))
    return LiveSandboxConfig(
        enabled=enabled,
        confirmation=normalize_alpaca_env_value(
            source.get("TRADING_APP_LIVE_SANDBOX_CONFIRMATION")
        ),
        max_live_allocation=_decimal_env(
            source,
            "TRADING_APP_LIVE_SANDBOX_MAX_ALLOCATION",
            Decimal("100"),
        ),
        max_order_notional=_decimal_env(
            source,
            "TRADING_APP_LIVE_SANDBOX_MAX_ORDER_NOTIONAL",
            Decimal("100"),
        ),
        max_orders_per_day=int(
            normalize_alpaca_env_value(
                source.get("TRADING_APP_LIVE_SANDBOX_MAX_ORDERS_PER_DAY")
            )
            or "4"
        ),
        max_daily_loss=_decimal_env(
            source,
            "TRADING_APP_LIVE_SANDBOX_MAX_DAILY_LOSS",
            Decimal("10"),
        ),
        live_account_id=(
            normalize_alpaca_env_value(
                source.get("TRADING_APP_LIVE_SANDBOX_ACCOUNT_ID")
            )
            or "alpaca-live-sandbox"
        ),
    )


def live_sandbox_service(
    *,
    broker: PaperBrokerAdapter,
    config: LiveSandboxConfig | None = None,
) -> PaperTradingService:
    resolved = config or LiveSandboxConfig(enabled=True)
    risk_engine = RiskEngine(
        RiskConfig(
            enforce_market_hours=resolved.enforce_market_hours,
            tradable_symbols=frozenset(resolved.allowed_symbols),
            us_tradable_universe=frozenset(resolved.allowed_symbols),
            max_orders_per_day=resolved.max_orders_per_day,
            max_daily_loss=resolved.max_daily_loss,
            max_portfolio_gross_exposure=Decimal("1"),
        )
    )
    return PaperTradingService(
        broker=broker,
        starting_cash=resolved.max_live_allocation,
        risk_engine=risk_engine,
    )


def build_live_sandbox_strategy(
    config: LiveSandboxConfig | None = None,
) -> BenchmarkRelativeStrengthETFStrategy:
    resolved = config or LiveSandboxConfig()
    strategy = BenchmarkRelativeStrengthETFStrategy(
        universe=resolved.allowed_symbols,
        benchmark=resolved.benchmark_symbol,
        lookback_days=252,
        tracking_window_days=21,
        top_n=2,
    )
    strategy.strategy_version = "grid-l252-t21-n2"
    return strategy


def _filtered_broker_portfolio(
    portfolio: BrokerPortfolioState,
    symbols: tuple[str, ...],
) -> BrokerPortfolioState:
    allowed = set(symbols)
    return portfolio.model_copy(
        update={
            "positions": tuple(
                position
                for position in portfolio.positions
                if position.symbol in allowed
            )
        }
    )


def _estimated_equity(
    snapshot: PortfolioSnapshot,
    latest_prices: dict[str, Decimal],
) -> Decimal:
    equity = snapshot.cash
    for position in snapshot.positions:
        price = latest_prices.get(position.symbol, position.average_cost)
        equity += position.quantity * price
    return equity


def _cap_deployed(
    snapshot: PortfolioSnapshot,
    latest_prices: dict[str, Decimal],
) -> Decimal:
    return sum(
        (
            position.quantity
            * latest_prices.get(position.symbol, position.average_cost)
            for position in snapshot.positions
        ),
        Decimal("0"),
    )


def _round_quantity_down(quantity: Decimal) -> Decimal:
    if quantity <= 0:
        return Decimal("0")
    return quantity.quantize(QUANTITY_INCREMENT, rounding=ROUND_DOWN)


def _is_market_hours(
    as_of: datetime,
    *,
    open_time: dt_time,
    close_time: dt_time,
) -> bool:
    local = as_of.astimezone(MARKET_TZ)
    return local.weekday() < 5 and open_time <= local.time() <= close_time


def _is_live_sandbox_order_id(order_id: str | None, *, prefix: str) -> bool:
    return bool(order_id and order_id.startswith(prefix))


def _truthy(value: str | None) -> bool:
    return (normalize_alpaca_env_value(value) or "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _decimal_env(
    env: dict[str, str],
    name: str,
    default: Decimal,
) -> Decimal:
    value = normalize_alpaca_env_value(env.get(name))
    return Decimal(value) if value else default


def _live_env(*names: str) -> str | None:
    for name in names:
        value = normalize_alpaca_env_value(os.environ.get(name))
        if value:
            return value
    return None


def live_sandbox_policy_summary() -> dict[str, Any]:
    definition = build_live_sandbox_strategy().definition(
        authority=StrategyAuthority.PAPER
    )
    return {
        "model_key": LIVE_SANDBOX_MODEL_KEY,
        "universe_id": LIVE_SANDBOX_UNIVERSE_ID,
        "allowed_symbols": LIVE_SANDBOX_ALLOWED_SYMBOLS,
        "benchmark_symbol": LIVE_SANDBOX_BENCHMARK,
        "order_prefix": LIVE_SANDBOX_ORDER_PREFIX,
        "strategy_name": definition.name,
    }
