"""Paper Trading screen.

A Robinhood-grade holdings log for fake-money activity. The hero is the
count of open positions — the single number that orients the operator.
Below it: the same 4-up stat row used elsewhere in the app, a positions
table with per-symbol sparklines, the live activity strip (fills + open
orders), the reconciliation/provenance pair, and a quiet tax footnote.

Composition rules:

- No new CSS classes; only ``surface``, ``stat``, ``row``, ``k_list``,
  ``pill``, ``empty``, ``microcopy``, and ``sparkline`` from
  ``components.py``.
- No nested cards. Stats and surfaces sit flat on the viewport grid.
- Every figure is mono. BUY is positive (green), SELL is negative (red).
- The tax surface is intentionally calm — research estimate only.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from trading_app.dashboard import components as C
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.screens import _helpers as H


def render(snapshot: OperatorDashboardSnapshot) -> str:
    """Render the Paper Trading surface."""

    return f"""
    <section class="screen" data-screen="paper" hidden>
      <div class="screen__head">
        <div>
          <span class="eyebrow">Paper Trading</span>
          <h1>Holdings, fills, and the reconciliation evidence behind them.</h1>
          <p>Paper mode only. Every order, fill, and lot is traceable.</p>
        </div>
      </div>

      {_holdings_hero(snapshot)}
      {_stat_row(snapshot)}

      {_positions(snapshot)}

      <div class="grid-2">
        {_fills(snapshot)}
        {_open_orders(snapshot)}
      </div>

      <div class="grid-2">
        {_statement_review(snapshot)}
        {_audit_trail(snapshot)}
      </div>

      {_tax_estimate(snapshot)}
    </section>"""


# ---------------------------------------------------------------------------
# Hero — Robinhood-style holdings header
# ---------------------------------------------------------------------------


def _holdings_hero(snapshot: OperatorDashboardSnapshot) -> str:
    positions = snapshot.paper_report.ledger_snapshot.positions
    count = len(positions)
    label = "open position" if count == 1 else "open positions"
    headline = f'{count} <span class="hero__delta"><span>{label}</span></span>'
    if count == 0:
        headline = f'0 <span class="hero__delta"><span>open positions</span></span>'

    return f"""
      <section class="hero" aria-label="Paper holdings">
        <div class="hero__lead">
          <span class="hero__label">Holdings</span>
          <div class="hero__value"><span data-field="position-count">{count}</span></div>
          <div class="hero__delta">
            <span>{escape(label)} held</span>
            <span class="delta-divider">·</span>
            <span>fake-money ledger</span>
          </div>
        </div>
        <p class="microcopy">Paper mode only. No live-money actions.</p>
      </section>"""


# ---------------------------------------------------------------------------
# Stat row — Cash · Open Orders · Realized P&L · Positions
# ---------------------------------------------------------------------------


def _stat_row(snapshot: OperatorDashboardSnapshot) -> str:
    positions = snapshot.paper_report.ledger_snapshot.positions
    realized = float(snapshot.realized_pnl)
    pnl_tone = "pos" if realized > 0 else "neg" if realized < 0 else ""

    stats = [
        C.stat(
            label="Cash",
            value=H.money(snapshot.cash),
            detail="Money available to spend",
        ),
        C.stat(
            label=C.glossary("Open orders", key="open_orders"),
            value=str(snapshot.open_orders),
            detail="Sent to the broker, not yet filled",
            tone="ai" if snapshot.open_orders > 0 else "",
        ),
        C.stat(
            label=C.glossary("Realized P&L", key="realized_pnl"),
            value=H.money(snapshot.realized_pnl),
            detail="From positions you've already closed",
            tone=pnl_tone,
        ),
        C.stat(
            label="Positions",
            value=str(len(positions)),
            detail="Different symbols you currently hold",
        ),
    ]
    return (
        '<section class="stat-row" aria-label="Paper portfolio metrics">'
        + "".join(stats)
        + "</section>"
    )


# ---------------------------------------------------------------------------
# Positions — Robinhood holdings list pattern
# ---------------------------------------------------------------------------


def _positions(snapshot: OperatorDashboardSnapshot) -> str:
    positions = snapshot.paper_report.ledger_snapshot.positions
    fills_by_symbol: dict[str, list] = {}
    for fill in snapshot.recent_fills:
        fills_by_symbol.setdefault(fill.symbol, []).append(fill)

    if not positions:
        body = (
            '<div class="row-list" data-position-list>'
            + C.empty("No positions held yet. They will appear here after a buy order fills at the next daily-close window.")
            + "</div>"
        )
        pill_html = C.pill("FLAT", tone="ghost")
    else:
        rows = []
        for position in positions:
            symbol = position.symbol
            qty = position.quantity
            avg = Decimal(str(position.average_cost))
            value = Decimal(str(qty)) * avg
            related_fills = fills_by_symbol.get(symbol, [])
            spark_html = _position_sparkline(position, related_fills)
            primary = f"<strong>{escape(symbol)}</strong>"
            sub = f"avg <span class=\"mono\">{H.money(avg)}</span>"
            meta = f'<span class="mono">{qty} sh</span>{spark_html}'
            rows.append(
                C.row(
                    primary=primary,
                    primary_sub=sub,
                    meta=meta,
                    value=H.money(value),
                )
            )
        body = C.row_list(rows, container_attrs="data-position-list")
        pill_html = C.pill(f"{len(positions)} held", tone="ai")

    return C.surface(
        eyebrow="Holdings ledger",
        title="Positions",
        body_html=body,
        pill_html=pill_html,
    )


def _position_sparkline(position, related_fills) -> str:
    """Render a tiny per-row sparkline from cost basis vs latest fill price.

    Returns empty string when there is no matching fill — the table stays
    calm rather than seeding fake motion.
    """

    if not related_fills:
        return ""
    avg = float(position.average_cost)
    latest = related_fills[-1]
    latest_price = float(latest.price)
    # Synthesize a 5-point series anchored on cost basis and current price
    midpoint = (avg + latest_price) / 2.0
    series = [
        avg,
        (avg + midpoint) / 2.0,
        midpoint,
        (midpoint + latest_price) / 2.0,
        latest_price,
    ]
    positive = latest_price >= avg
    spark = C.sparkline(series, positive=positive, label=f"{position.symbol} trend")
    return f' <span class="mono">{spark}</span>'


# ---------------------------------------------------------------------------
# Activity strip — Recent Fills + Open Orders placeholder
# ---------------------------------------------------------------------------


def _fills(snapshot: OperatorDashboardSnapshot) -> str:
    fills = snapshot.recent_fills
    if not fills:
        body = (
            '<div class="row-list" data-fill-list>'
            + C.empty("No trades placed today. Strategies look for opportunities at market close (4pm ET) and only act when a candidate clears every safety check.")
            + "</div>"
        )
        pill_html = C.pill("0 today", tone="ghost")
    else:
        rows = []
        for fill in fills:
            side = fill.side.value
            tone = "pos" if side == "BUY" else "neg"
            side_pill = C.pill(side, tone="good" if side == "BUY" else "danger")
            value_html = (
                f'<span class="mono">{fill.quantity} @ {H.money(fill.price)}</span>'
            )
            rows.append(
                C.row(
                    primary=f"<strong>{escape(fill.symbol)}</strong>",
                    primary_sub=escape(fill.filled_at.isoformat()),
                    meta=side_pill,
                    value=value_html,
                    value_tone=tone,
                )
            )
        body = C.row_list(rows, container_attrs="data-fill-list")
        pill_html = C.pill(f"{len(fills)} today", tone="ai")

    return C.surface(
        eyebrow="Activity",
        title=f'Recent Fills · <span data-field="fill-count" class="mono">{len(fills)}</span>',
        body_html=body,
        pill_html=pill_html,
    )


def _open_orders(snapshot: OperatorDashboardSnapshot) -> str:
    open_count = snapshot.open_orders
    if open_count == 0:
        body = (
            C.empty("No orders are working right now. Strategies only place orders during the scheduled daily-close window.")
            + C.microcopy(
                "Strategies place orders at the daily close window only."
            )
        )
        pill_html = C.pill("Idle", tone="ghost")
    else:
        body = C.k_list(
            [
                (
                    "Working",
                    f'<span class="mono">{open_count}</span>',
                ),
                ("Authority", "Daily close only"),
                ("Next window", "scheduled"),
            ]
        ) + C.microcopy(
            "Strategies place orders at the daily close window only."
        )
        pill_html = C.pill(f"{open_count} working", tone="ai")

    return C.surface(
        eyebrow="Activity",
        title="Open Orders",
        body_html=body,
        pill_html=pill_html,
    )


# ---------------------------------------------------------------------------
# Reconciliation — Statement Review + Audit Trail
# ---------------------------------------------------------------------------


def _statement_review(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.statement_reconciliation
    if report is None:
        body = f"""
          {C.k_list([
              ("Statement", '<span data-field="statement-id">not loaded</span>'),
              ("Provider", '<span data-field="statement-provider">unknown</span>'),
              ("Issues", '<span data-field="statement-issues" class="mono">unknown</span>'),
              ("Report", '<span data-field="statement-path">not written</span>'),
          ])}
          <div class="row-list" data-statement-issue-list>{C.empty("No statement differences above tolerance.")}</div>
          <p class="microcopy" data-field="statement-caveat">Paper/research-only review. Not filing-grade tax accounting.</p>
        """
        return C.surface(
            eyebrow=C.glossary("Broker statement vs our records", key="statement_review"),
            title='<span data-field="statement-status">Awaiting Statement</span>',
            body_html=body,
            pill_html=f'<span class="pill pill--warn" data-field="statement-chip">Post-run</span>',
        )

    statement = H.field(report, "statement", {})
    reconciled = bool(H.field(report, "reconciled", False))
    tone = "good" if reconciled else "danger"
    chip_text = "Clean" if reconciled else "Review"

    body = f"""
      {C.k_list([
          ("Statement", f'<span data-field="statement-id" class="mono">{escape(H.field(statement, "statement_id", "unknown"))}</span>'),
          ("Provider", f'<span data-field="statement-provider">{escape(H.field(statement, "provider", "unknown"))}</span>'),
          ("Issues", f'<span data-field="statement-issues" class="mono">{len(H.field(report, "issues", ()))}</span>'),
          ("Report", f'<span data-field="statement-path">{escape(snapshot.statement_reconciliation_path or "not written")}</span>'),
      ])}
      <div class="row-list" data-statement-issue-list>
        {_statement_issue_rows(report)}
      </div>
      <p class="microcopy" data-field="statement-caveat">Paper/research-only review. Not filing-grade tax accounting.</p>
    """
    return C.surface(
        eyebrow=C.glossary("Broker statement vs our records", key="statement_review"),
        title=f'<span data-field="statement-status">{"Reconciled" if reconciled else "Mismatch"}</span>',
        body_html=body,
        pill_html=f'<span class="pill pill--{tone}" data-field="statement-chip">{chip_text}</span>',
    )


def _statement_issue_rows(report) -> str:
    issues = H.field(report, "issues", ())
    if not issues:
        return C.empty("No statement differences above tolerance.")
    rows = []
    for issue in tuple(issues)[:4]:
        issue_type = H.enum_value(H.field(issue, "issue_type"), "statement_issue")
        rows.append(
            C.row(
                primary=f"<strong>{escape(H.humanize_code(issue_type.lower()))}</strong>",
                primary_sub=escape(
                    H.field(issue, "message", "Statement mismatch requires review.")
                ),
                meta=escape(H.field(issue, "symbol", None) or "account"),
                tone="danger",
            )
        )
    return "".join(rows)


def _audit_trail(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.daily_report
    metadata = report.report_metadata
    evidence_sources = len(metadata.evidence_sources) if metadata else 0
    traced_orders = sum(1 for trade in report.trade_explanations if trade.ledger_trace)
    body = C.k_list(
        [
            (
                "Fills traced",
                f'<span class="mono">{len(report.fill_report)}</span>',
            ),
            (
                "Operator actions",
                f'<span class="mono">{len(report.operator_actions)}</span>',
            ),
            (
                "Runtime events",
                f'<span class="mono">{len(report.runtime_events)}</span>',
            ),
            (
                "Trace coverage",
                f'<span class="mono">{traced_orders}</span>',
            ),
            ("Benchmark", escape(H.benchmark_status(report))),
        ]
    )
    return C.surface(
        eyebrow=C.glossary("Where the numbers came from", key="audit_trail"),
        title="Audit Trail",
        body_html=body,
        pill_html=C.pill(f"{evidence_sources} sources", tone="ai"),
    )


# ---------------------------------------------------------------------------
# Tax estimate — quiet footnote surface
# ---------------------------------------------------------------------------


def _tax_estimate(snapshot: OperatorDashboardSnapshot) -> str:
    tax = snapshot.daily_report.tax_report
    estimated_tax = (
        H.money(tax.estimated_tax) if tax.tax_estimate_available else "unavailable"
    )
    tone = "good" if tax.tax_estimate_available else "ghost"
    state_text = "available" if tax.tax_estimate_available else "estimate only"
    left = [
        (
            C.glossary("Open lots", key="tax_lots"),
            f'<span data-field="tax-active-lots" class="mono">{tax.active_lot_count}</span>',
        ),
        (
            "Closed lots",
            f'<span data-field="tax-realized-lots" class="mono">{tax.realized_lot_count}</span>',
        ),
        (
            C.glossary("Lot method", key="fifo"),
            f'<span data-field="tax-lot-method" class="mono">{escape(H.enum_value(tax.lot_method, "fifo").upper())}</span>',
        ),
        (
            "Estimated tax",
            f'<span data-field="tax-estimated-tax">{escape(estimated_tax)}</span>',
        ),
    ]
    right = [
        (
            C.glossary("Short-term gains", key="short_long_term"),
            f'<span data-field="tax-short-term-gains">{H.money(tax.short_term_realized_gains)}</span>',
        ),
        (
            "Long-term gains",
            f'<span data-field="tax-long-term-gains">{H.money(tax.long_term_realized_gains)}</span>',
        ),
        (
            "Total gains",
            f'<span data-field="tax-total-gains">{H.money(tax.total_realized_gains)}</span>',
        ),
    ]
    body = f"""
      {C.k_split(left, right)}
      <p class="microcopy">Research estimate only. Not filing-grade tax accounting.</p>
    """
    return C.surface(
        eyebrow="Accounting",
        title=C.glossary("Tax Estimate", key="accounting"),
        body_html=body,
        pill_html=f'<span class="pill pill--{tone}" data-field="tax-estimate-state">{state_text}</span>',
    )
