"""In-memory ledger for paper/research accounting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from trading_app.schemas import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    PortfolioSnapshot,
    Position,
)


class LedgerError(ValueError):
    """Raised when a ledger operation would create invalid accounting state."""


class Ledger:
    """Source of truth for fake cash, orders, fills, and long-only positions."""

    def __init__(self, starting_cash: Decimal) -> None:
        if not isinstance(starting_cash, Decimal):
            raise LedgerError("starting_cash must be a Decimal")
        if starting_cash < Decimal("0"):
            raise LedgerError("starting_cash cannot be negative")

        self._cash = starting_cash
        self._realized_pnl = Decimal("0")
        self._total_fees = Decimal("0")
        self._orders: dict[str, Order] = {}
        self._fills: dict[str, Fill] = {}
        self._positions: dict[str, Position] = {}
        self._filled_quantities: dict[str, Decimal] = {}

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def realized_pnl(self) -> Decimal:
        return self._realized_pnl

    @property
    def total_fees(self) -> Decimal:
        return self._total_fees

    def record_order(self, order: Order) -> Order:
        if order.id in self._orders:
            raise LedgerError(f"order already exists: {order.id}")
        if order.status != OrderStatus.NEW:
            raise LedgerError("new ledger orders must start with NEW status")

        self._orders[order.id] = order
        self._filled_quantities[order.id] = Decimal("0")
        return order

    def record_fill(self, fill: Fill) -> Fill:
        if fill.id in self._fills:
            raise LedgerError(f"fill already exists: {fill.id}")

        order = self._orders.get(fill.order_id)
        if order is None:
            raise LedgerError(f"unknown order: {fill.order_id}")
        if order.status in {
            OrderStatus.CANCELED,
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
        }:
            raise LedgerError(f"order is not open: {fill.order_id}")
        if fill.symbol != order.symbol:
            raise LedgerError("fill symbol does not match order symbol")
        if fill.side != order.side:
            raise LedgerError("fill side does not match order side")

        current_filled = self._filled_quantities[order.id]
        next_filled = current_filled + fill.quantity
        if next_filled > order.quantity:
            raise LedgerError("fill quantity exceeds remaining order quantity")

        if fill.side == OrderSide.BUY:
            self._apply_buy_fill(fill)
        else:
            self._apply_sell_fill(fill)

        self._fills[fill.id] = fill
        self._filled_quantities[order.id] = next_filled
        status = (
            OrderStatus.FILLED
            if next_filled == order.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        self._orders[order.id] = order.model_copy(
            update={"status": status, "updated_at": fill.filled_at}
        )
        return fill

    def cancel_order(self, order_id: str, canceled_at: datetime) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise LedgerError(f"unknown order: {order_id}")
        if order.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
            raise LedgerError(f"order is not open: {order_id}")
        if canceled_at.tzinfo is None or canceled_at.utcoffset() is None:
            raise LedgerError("canceled_at must be timezone-aware")

        canceled = order.model_copy(
            update={"status": OrderStatus.CANCELED, "updated_at": canceled_at}
        )
        self._orders[order_id] = canceled
        return canceled

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_fill(self, fill_id: str) -> Fill | None:
        return self._fills.get(fill_id)

    def filled_quantity(self, order_id: str) -> Decimal:
        return self._filled_quantities.get(order_id, Decimal("0"))

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def snapshot(self, as_of: datetime) -> PortfolioSnapshot:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise LedgerError("as_of must be timezone-aware")

        return PortfolioSnapshot(
            cash=self._cash,
            positions=tuple(
                sorted(self._positions.values(), key=lambda position: position.symbol)
            ),
            realized_pnl=self._realized_pnl,
            total_fees=self._total_fees,
            as_of=as_of,
        )

    def _apply_buy_fill(self, fill: Fill) -> None:
        total_cost = fill.quantity * fill.price + fill.commission
        if total_cost > self._cash:
            raise LedgerError("insufficient cash for buy fill")

        existing = self._positions.get(fill.symbol)
        if existing is None:
            next_quantity = fill.quantity
            next_average_cost = total_cost / next_quantity
            realized_pnl = Decimal("0")
        else:
            existing_cost = existing.quantity * existing.average_cost
            next_quantity = existing.quantity + fill.quantity
            next_average_cost = (existing_cost + total_cost) / next_quantity
            realized_pnl = existing.realized_pnl

        self._cash -= total_cost
        self._total_fees += fill.commission
        self._positions[fill.symbol] = Position(
            symbol=fill.symbol,
            quantity=next_quantity,
            average_cost=next_average_cost,
            realized_pnl=realized_pnl,
        )

    def _apply_sell_fill(self, fill: Fill) -> None:
        existing = self._positions.get(fill.symbol)
        if existing is None or fill.quantity > existing.quantity:
            raise LedgerError("cannot sell more than the current long position")

        proceeds = fill.quantity * fill.price - fill.commission
        if proceeds < Decimal("0"):
            raise LedgerError("sell commission cannot exceed gross proceeds")

        realized = (
            fill.price - existing.average_cost
        ) * fill.quantity - fill.commission
        next_quantity = existing.quantity - fill.quantity

        self._cash += proceeds
        self._realized_pnl += realized
        self._total_fees += fill.commission

        if next_quantity == Decimal("0"):
            del self._positions[fill.symbol]
            return

        self._positions[fill.symbol] = Position(
            symbol=fill.symbol,
            quantity=next_quantity,
            average_cost=existing.average_cost,
            realized_pnl=existing.realized_pnl + realized,
        )
