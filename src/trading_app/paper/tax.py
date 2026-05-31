"""Paper tax-lot accounting scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_app.paper.models import (
    PaperRealizedTaxLot,
    PaperTaxLot,
    PaperTaxLotMethod,
    PaperTaxSummary,
    PaperTaxTerm,
)
from trading_app.schemas import Fill, OrderSide

LONG_TERM_HOLDING_PERIOD_DAYS = 365


class PaperTaxLotError(ValueError):
    """Raised when paper tax-lot state would become inconsistent."""


@dataclass
class _MutableTaxLot:
    id: str
    symbol: str
    opened_at: datetime
    source_fill_id: str
    remaining_quantity: Decimal
    cost_basis_per_share: Decimal


class PaperTaxLotTracker:
    """Tax-lot tracker for paper/research reporting.

    This is intentionally an estimate scaffold. It does not model wash sales,
    dividends, state taxes, or broker filing reconciliation.
    """

    def __init__(
        self, *, lot_method: PaperTaxLotMethod = PaperTaxLotMethod.FIFO
    ) -> None:
        self.lot_method = lot_method
        self._active_lots: dict[str, list[_MutableTaxLot]] = {}
        self._realized_lots: list[PaperRealizedTaxLot] = []
        self._processed_fill_ids: set[str] = set()

    @property
    def active_lots(self) -> tuple[PaperTaxLot, ...]:
        lots = [
            _paper_tax_lot(lot)
            for symbol_lots in self._active_lots.values()
            for lot in symbol_lots
            if lot.remaining_quantity > 0
        ]
        return tuple(sorted(lots, key=lambda lot: (lot.opened_at, lot.symbol, lot.id)))

    @property
    def realized_lots(self) -> tuple[PaperRealizedTaxLot, ...]:
        return tuple(
            sorted(
                self._realized_lots,
                key=lambda lot: (lot.closed_at, lot.symbol, lot.id),
            )
        )

    def apply_fill(self, fill: Fill) -> None:
        if fill.id in self._processed_fill_ids:
            return
        if fill.side == OrderSide.BUY:
            self._apply_buy_fill(fill)
        else:
            self._apply_sell_fill(fill)
        self._processed_fill_ids.add(fill.id)

    def summary(
        self,
        *,
        as_of: datetime,
        short_term_tax_rate: Decimal | None = None,
        long_term_tax_rate: Decimal | None = None,
    ) -> PaperTaxSummary:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise PaperTaxLotError("as_of must be timezone-aware")
        short_term = sum(
            (
                lot.realized_gain
                for lot in self._realized_lots
                if lot.term == PaperTaxTerm.SHORT_TERM
            ),
            Decimal("0"),
        )
        long_term = sum(
            (
                lot.realized_gain
                for lot in self._realized_lots
                if lot.term == PaperTaxTerm.LONG_TERM
            ),
            Decimal("0"),
        )
        estimated_tax = None
        estimated_after_tax = None
        if short_term_tax_rate is not None and long_term_tax_rate is not None:
            estimated_tax = (
                max(short_term, Decimal("0")) * short_term_tax_rate
                + max(long_term, Decimal("0")) * long_term_tax_rate
            )
            estimated_after_tax = short_term + long_term - estimated_tax

        return PaperTaxSummary(
            as_of=as_of,
            lot_method=self.lot_method,
            active_lots=self.active_lots,
            realized_lots=self.realized_lots,
            short_term_realized_gains=short_term,
            long_term_realized_gains=long_term,
            total_realized_gains=short_term + long_term,
            estimated_tax=estimated_tax,
            estimated_after_tax_realized_gains=estimated_after_tax,
            tax_estimate_available=estimated_tax is not None,
        )

    def _apply_buy_fill(self, fill: Fill) -> None:
        total_cost = fill.quantity * fill.price + fill.commission
        lot = _MutableTaxLot(
            id=f"lot:{fill.id}",
            symbol=fill.symbol,
            opened_at=fill.filled_at,
            source_fill_id=fill.id,
            remaining_quantity=fill.quantity,
            cost_basis_per_share=total_cost / fill.quantity,
        )
        self._active_lots.setdefault(fill.symbol, []).append(lot)

    def _apply_sell_fill(self, fill: Fill) -> None:
        remaining = fill.quantity
        lots = self._active_lots.get(fill.symbol, [])
        proceeds_per_share = fill.price - fill.commission / fill.quantity
        while remaining > 0 and lots:
            lot_index = _lot_index(lots, self.lot_method)
            lot = lots[lot_index]
            matched_quantity = min(remaining, lot.remaining_quantity)
            holding_days = (fill.filled_at.date() - lot.opened_at.date()).days
            term = (
                PaperTaxTerm.LONG_TERM
                if holding_days >= LONG_TERM_HOLDING_PERIOD_DAYS
                else PaperTaxTerm.SHORT_TERM
            )
            realized_gain = (
                proceeds_per_share - lot.cost_basis_per_share
            ) * matched_quantity
            self._realized_lots.append(
                PaperRealizedTaxLot(
                    id=f"realized:{fill.id}:{lot.id}:{len(self._realized_lots) + 1}",
                    symbol=fill.symbol,
                    side=fill.side,
                    opened_at=lot.opened_at,
                    closed_at=fill.filled_at,
                    acquired_on=lot.opened_at.date(),
                    sold_on=fill.filled_at.date(),
                    source_lot_id=lot.id,
                    source_fill_id=fill.id,
                    quantity=matched_quantity,
                    cost_basis_per_share=lot.cost_basis_per_share,
                    proceeds_per_share=proceeds_per_share,
                    realized_gain=realized_gain,
                    holding_period_days=holding_days,
                    term=term,
                )
            )
            lot.remaining_quantity -= matched_quantity
            remaining -= matched_quantity
            if lot.remaining_quantity == 0:
                lots.pop(lot_index)

        if remaining > 0:
            raise PaperTaxLotError("cannot sell more tax-lot quantity than held")


def _paper_tax_lot(lot: _MutableTaxLot) -> PaperTaxLot:
    return PaperTaxLot(
        id=lot.id,
        symbol=lot.symbol,
        opened_at=lot.opened_at,
        acquired_on=lot.opened_at.date(),
        source_fill_id=lot.source_fill_id,
        remaining_quantity=lot.remaining_quantity,
        cost_basis_per_share=lot.cost_basis_per_share,
    )


def _lot_index(lots: list[_MutableTaxLot], method: PaperTaxLotMethod) -> int:
    if method == PaperTaxLotMethod.FIFO:
        return min(range(len(lots)), key=lambda index: (lots[index].opened_at, index))
    if method == PaperTaxLotMethod.LIFO:
        return max(range(len(lots)), key=lambda index: (lots[index].opened_at, index))
    if method == PaperTaxLotMethod.HIFO:
        return max(
            range(len(lots)),
            key=lambda index: (lots[index].cost_basis_per_share, lots[index].opened_at),
        )
    raise PaperTaxLotError(f"unsupported tax lot method: {method}")
