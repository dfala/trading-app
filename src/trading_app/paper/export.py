"""Reviewable exports for paper accounting artifacts."""

from __future__ import annotations

import csv
from io import StringIO

from trading_app.paper.models import PaperTaxSummary


def render_tax_lot_csv(summary: PaperTaxSummary) -> str:
    """Render active and realized paper tax lots as accountant-friendly CSV."""

    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "record_type",
            "lot_method",
            "lot_id",
            "symbol",
            "source_fill_id",
            "source_lot_id",
            "quantity",
            "acquired_on",
            "sold_on",
            "cost_basis_per_share",
            "proceeds_per_share",
            "realized_gain",
            "term",
            "note",
        ),
    )
    writer.writeheader()
    for lot in summary.active_lots:
        writer.writerow(
            {
                "record_type": "active",
                "lot_method": summary.lot_method.value,
                "lot_id": lot.id,
                "symbol": lot.symbol,
                "source_fill_id": lot.source_fill_id,
                "source_lot_id": "",
                "quantity": str(lot.remaining_quantity),
                "acquired_on": lot.acquired_on.isoformat(),
                "sold_on": "",
                "cost_basis_per_share": str(lot.cost_basis_per_share),
                "proceeds_per_share": "",
                "realized_gain": "",
                "term": "",
                "note": "research estimate",
            }
        )
    for lot in summary.realized_lots:
        writer.writerow(
            {
                "record_type": "realized",
                "lot_method": summary.lot_method.value,
                "lot_id": lot.id,
                "symbol": lot.symbol,
                "source_fill_id": lot.source_fill_id,
                "source_lot_id": lot.source_lot_id,
                "quantity": str(lot.quantity),
                "acquired_on": lot.acquired_on.isoformat(),
                "sold_on": lot.sold_on.isoformat(),
                "cost_basis_per_share": str(lot.cost_basis_per_share),
                "proceeds_per_share": str(lot.proceeds_per_share),
                "realized_gain": str(lot.realized_gain),
                "term": lot.term.value,
                "note": "research estimate, not filing-grade tax accounting",
            }
        )
    return output.getvalue()
