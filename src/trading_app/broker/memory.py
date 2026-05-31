"""Deterministic in-memory paper broker for local runs and tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from trading_app.broker.models import (
    BrokerFillEvent,
    BrokerOrderState,
    BrokerPortfolioState,
    BrokerPositionState,
)
from trading_app.schemas import Order, OrderSide, OrderStatus, Position


class PaperBrokerError(ValueError):
    """Raised when the deterministic paper broker rejects an operation."""


class InMemoryPaperBrokerAdapter:
    """Small broker simulator with Alpaca-like adapter semantics."""

    provider = "memory-paper"

    def __init__(self, starting_cash: Decimal = Decimal("100000")) -> None:
        if not isinstance(starting_cash, Decimal):
            raise PaperBrokerError("starting_cash must be a Decimal")
        if starting_cash < Decimal("0"):
            raise PaperBrokerError("starting_cash cannot be negative")

        self._cash = starting_cash
        self._positions: dict[str, Position] = {}
        self._last_prices: dict[str, Decimal] = {}
        self._orders_by_broker_id: dict[str, BrokerOrderState] = {}
        self._broker_id_by_order_id: dict[str, str] = {}
        self._next_order_number = 1
        self._next_fill_number = 1

    @property
    def submitted_orders(self) -> tuple[BrokerOrderState, ...]:
        return tuple(self._orders_by_broker_id.values())

    def submit_order(self, order: Order) -> BrokerOrderState:
        if order.id in self._broker_id_by_order_id:
            raise PaperBrokerError(f"duplicate client order id: {order.id}")

        broker_order_id = f"paper-order-{self._next_order_number}"
        self._next_order_number += 1
        state = BrokerOrderState(
            broker_order_id=broker_order_id,
            client_order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            filled_quantity=Decimal("0"),
            status=OrderStatus.NEW,
            submitted_at=order.created_at,
            limit_price=order.limit_price,
            provider=self.provider,
            provider_status="new",
        )
        self._orders_by_broker_id[broker_order_id] = state
        self._broker_id_by_order_id[order.id] = broker_order_id
        return state

    def get_order(self, broker_order_id: str) -> BrokerOrderState:
        broker_order_id = self._broker_id_by_order_id.get(
            broker_order_id, broker_order_id
        )
        try:
            return self._orders_by_broker_id[broker_order_id]
        except KeyError as error:
            raise PaperBrokerError(
                f"unknown broker order: {broker_order_id}"
            ) from error

    def list_orders(
        self,
        status: OrderStatus | None = None,
        *,
        after: datetime | None = None,
        until: datetime | None = None,
        symbols: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> tuple[BrokerOrderState, ...]:
        orders = tuple(
            sorted(
                self._orders_by_broker_id.values(),
                key=lambda order: order.submitted_at,
            )
        )
        if status is not None:
            orders = tuple(order for order in orders if order.status == status)
        if after is not None:
            orders = tuple(order for order in orders if order.submitted_at >= after)
        if until is not None:
            orders = tuple(order for order in orders if order.submitted_at <= until)
        if symbols is not None:
            allowed = set(symbols)
            orders = tuple(order for order in orders if order.symbol in allowed)
        if limit is not None:
            orders = orders[:limit]
        return orders

    def cancel_order(
        self, broker_order_id: str, canceled_at: datetime | None = None
    ) -> BrokerOrderState:
        broker_order_id = self._broker_id_by_order_id.get(
            broker_order_id, broker_order_id
        )
        state = self.get_order(broker_order_id)
        if state.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
            raise PaperBrokerError("only open paper orders can be canceled")
        updated = state.model_copy(
            update={
                "status": OrderStatus.CANCELED,
                "updated_at": canceled_at or state.updated_at or state.submitted_at,
                "provider_status": "canceled",
            }
        )
        self._orders_by_broker_id[broker_order_id] = updated
        return updated

    def fill_order(
        self,
        order_id: str,
        *,
        price: Decimal,
        filled_at: datetime,
        quantity: Decimal | None = None,
        commission: Decimal = Decimal("0"),
    ) -> BrokerFillEvent:
        broker_order_id = self._broker_id_by_order_id.get(order_id, order_id)
        state = self.get_order(broker_order_id)
        remaining = state.quantity - state.filled_quantity
        fill_quantity = quantity or remaining
        if fill_quantity <= Decimal("0"):
            raise PaperBrokerError("fill quantity must be positive")
        if fill_quantity > remaining:
            raise PaperBrokerError("fill quantity exceeds remaining order quantity")

        if state.side == OrderSide.BUY:
            self._apply_buy_fill(state.symbol, fill_quantity, price, commission)
        else:
            self._apply_sell_fill(state.symbol, fill_quantity, price, commission)
        self._last_prices[state.symbol] = price

        next_filled = state.filled_quantity + fill_quantity
        next_status = (
            OrderStatus.FILLED
            if next_filled == state.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        next_state = state.model_copy(
            update={
                "filled_quantity": next_filled,
                "status": next_status,
                "updated_at": filled_at,
                "average_fill_price": price,
                "provider_status": next_status.value.lower(),
            }
        )
        self._orders_by_broker_id[broker_order_id] = next_state
        fill_id = f"paper-fill-{self._next_fill_number}"
        self._next_fill_number += 1
        return BrokerFillEvent(
            id=fill_id,
            broker_order_id=broker_order_id,
            order_id=state.client_order_id or broker_order_id,
            symbol=state.symbol,
            side=state.side,
            quantity=fill_quantity,
            price=price,
            commission=commission,
            filled_at=filled_at,
            provider=self.provider,
        )

    def get_portfolio(self, as_of: datetime) -> BrokerPortfolioState:
        return BrokerPortfolioState(
            cash=self._cash,
            positions=tuple(
                BrokerPositionState(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    average_entry_price=position.average_cost,
                    market_value=position.quantity
                    * self._last_prices.get(position.symbol, position.average_cost),
                    current_price=self._last_prices.get(
                        position.symbol, position.average_cost
                    ),
                )
                for position in sorted(
                    self._positions.values(), key=lambda item: item.symbol
                )
            ),
            as_of=as_of,
            provider=self.provider,
        )

    def _apply_buy_fill(
        self, symbol: str, quantity: Decimal, price: Decimal, commission: Decimal
    ) -> None:
        total_cost = quantity * price + commission
        if total_cost > self._cash:
            raise PaperBrokerError("broker has insufficient cash for buy fill")

        existing = self._positions.get(symbol)
        if existing is None:
            next_quantity = quantity
            next_average_cost = total_cost / next_quantity
        else:
            next_quantity = existing.quantity + quantity
            next_average_cost = (
                existing.quantity * existing.average_cost + total_cost
            ) / next_quantity

        self._cash -= total_cost
        self._positions[symbol] = Position(
            symbol=symbol,
            quantity=next_quantity,
            average_cost=next_average_cost,
        )

    def _apply_sell_fill(
        self, symbol: str, quantity: Decimal, price: Decimal, commission: Decimal
    ) -> None:
        existing = self._positions.get(symbol)
        if existing is None or quantity > existing.quantity:
            raise PaperBrokerError("broker cannot sell more than held quantity")
        proceeds = quantity * price - commission
        if proceeds < Decimal("0"):
            raise PaperBrokerError("sell commission cannot exceed gross proceeds")

        self._cash += proceeds
        next_quantity = existing.quantity - quantity
        if next_quantity == Decimal("0"):
            del self._positions[symbol]
            return
        self._positions[symbol] = existing.model_copy(
            update={"quantity": next_quantity}
        )
