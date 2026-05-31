"""Home / Command Center screen.

The hero is the single visual anchor: paper equity, day change, the area
chart. Everything else on this surface is calm, dense, and traceable —
the user should land here and instantly understand the state of the
system without scrolling.
"""

from __future__ import annotations

from html import escape

from trading_app.dashboard import components as C
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.screens import _helpers as H


def render(snapshot: OperatorDashboardSnapshot) -> str:
    """Render the Home / Command Center surface."""

    return f"""
    <section class="screen" data-screen="home" hidden>
      <div class="screen__head">
        <div>
          <span class="eyebrow">{C.glossary("Paper Command Center", key="paper_trading")}</span>
          <h1>Real-money actions are turned off. Your strategy only acts on its schedule.</h1>
          <p class="microcopy">Live-money actions are disabled. Strategy authority remains schedule-bound.</p>
        </div>
      </div>

      {_hero(snapshot)}
      {_today_summary(snapshot)}
      {_stat_row(snapshot)}

      <div class="grid-2-1">
        {_latest_decisions(snapshot)}
        {_ai_summary(snapshot)}
      </div>

      <div class="grid-2">
        {_system_status(snapshot)}
        {_paper_boundary(snapshot)}
      </div>

      {_data_feed(snapshot)}
    </section>"""


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------


def _hero(snapshot: OperatorDashboardSnapshot) -> str:
    equity = H.money(snapshot.estimated_equity)
    delta_abs, delta_pct, positive = H.hero_delta(snapshot)
    delta_class = "delta-pos" if positive else "delta-neg"
    sign = "+" if positive else "−"
    delta_text = f"{sign}${abs(delta_abs):,.2f}"
    series = H.hero_equity_series(snapshot)
    chart = C.area_chart(
        series,
        positive=positive,
        label="Paper equity curve",
        width=1200,
        height=300,
    )
    return f"""
      <section class="hero" aria-label="Paper Portfolio">
        <div class="hero__lead">
          <span class="hero__label">{C.glossary("Your portfolio", key="paper_portfolio")}</span>
          <div class="hero__value" data-field="estimated-equity" data-tour-anchor="hero">{equity}</div>
          <div class="hero__delta">
            <span class="{delta_class}">{delta_text}</span>
            <span class="delta-divider">·</span>
            <span>{delta_pct:+.2f}% today</span>
            <span class="delta-divider">·</span>
            <span>since market open</span>
          </div>
        </div>
        <div class="hero__chart" data-hero-chart>{chart}</div>
        <div class="hero__periods" role="tablist" aria-label="Time range">
          <button class="period" data-period="1D" aria-pressed="true">1D</button>
          <button class="period" data-period="1W" aria-pressed="false">1W</button>
          <button class="period" data-period="1M" aria-pressed="false">1M</button>
          <button class="period" data-period="3M" aria-pressed="false">3M</button>
          <button class="period" data-period="YTD" aria-pressed="false">YTD</button>
          <button class="period" data-period="ALL" aria-pressed="false">ALL</button>
        </div>
      </section>"""


# ---------------------------------------------------------------------------
# "What happened today?" — beginner orientation card (Phase B3)
# ---------------------------------------------------------------------------


def _today_summary(snapshot: OperatorDashboardSnapshot) -> str:
    """Three plain-English bullets that orient a beginner to today's activity.

    Power users skim past it. Beginners read this first and discover the rest
    of the dashboard with context. Skipped entirely on the technical-vocab
    setting so it doesn't add noise for power users.
    """

    explanations = snapshot.daily_report.trade_explanations
    reviewed = len(explanations)
    filled = [e for e in explanations if e.status.value == "FILLED"]
    rejected = [e for e in explanations if e.status.value == "REJECTED"]

    # Bullet 1 — what got looked at
    if reviewed == 0:
        bullet_reviewed = "No trades were considered yet today. Strategies act at the daily close."
    elif reviewed == 1:
        bullet_reviewed = "We reviewed 1 possible trade today."
    else:
        bullet_reviewed = f"We reviewed {reviewed} possible trades today."

    # Bullet 2 — what went through and what didn't
    filled_text = ""
    if filled:
        details = ", ".join(
            f"{e.symbol} {e.side.value.lower()} ×{_extract_qty(e)}"
            for e in filled[:3]
        )
        more = f" (and {len(filled) - 3} more)" if len(filled) > 3 else ""
        filled_text = (
            f"{len(filled)} {'was' if len(filled) == 1 else 'were'} placed ({details}{more})."
        )
    rejected_text = ""
    if rejected:
        reasons = sorted({_rejection_reason(e) for e in rejected})
        reasons_text = ", ".join(reasons)
        rejected_text = (
            f"{len(rejected)} {'was' if len(rejected) == 1 else 'were'} blocked by {reasons_text}."
        )
    if filled_text and rejected_text:
        bullet_activity = f"{filled_text} {rejected_text}"
    elif filled_text:
        bullet_activity = filled_text
    elif rejected_text:
        bullet_activity = rejected_text
    elif reviewed:
        bullet_activity = "Nothing was placed and nothing was blocked."
    else:
        bullet_activity = "No orders sent to the broker yet."

    # Bullet 3 — what the AI is up to
    nightly = snapshot.nightly_learning
    if nightly is None:
        bullet_ai = (
            "The AI hasn't published a memo yet today — it's still gathering evidence."
        )
    elif not nightly.recommendations:
        bullet_ai = (
            "The AI didn't ask to change anything today — it's still gathering evidence."
        )
    else:
        n = len(nightly.recommendations)
        bullet_ai = (
            f"The AI flagged {n} candidate {'model' if n == 1 else 'models'} for your review. "
            "Nothing changes without your approval."
        )

    bullets_html = (
        '<ul class="today-bullets">'
        f'<li><span class="today-bullets__dot"></span>{escape(bullet_reviewed)}</li>'
        f'<li><span class="today-bullets__dot"></span>{escape(bullet_activity)}</li>'
        f'<li><span class="today-bullets__dot"></span>{escape(bullet_ai)}</li>'
        "</ul>"
    )

    return C.surface(
        eyebrow="What happened today",
        title="A plain-English summary",
        body_html=bullets_html,
        pill_html=C.pill("for beginners", tone="ai"),
        extra_class="surface--today hide-in-tech",
    )


def _extract_qty(explanation) -> str:
    """Best-effort quantity extractor for the today bullets."""

    for attr in ("quantity", "qty", "size"):
        value = getattr(explanation, attr, None)
        if value is not None:
            return str(value)
    return ""


def _rejection_reason(explanation) -> str:
    """Map a rejected explanation onto plain-English reason text."""

    rule = getattr(explanation, "rule", None) or getattr(explanation, "rule_name", None)
    rule_value = getattr(rule, "value", rule) if rule is not None else None
    rewrites = {
        "MAX_ORDERS_PER_DAY": "your daily order limit",
    }
    if rule_value in rewrites:
        return rewrites[rule_value]
    if rule_value:
        return f"a safety rule ({rule_value})"
    return "a safety rule"


# ---------------------------------------------------------------------------
# Stat row
# ---------------------------------------------------------------------------


def _stat_row(snapshot: OperatorDashboardSnapshot) -> str:
    risk_severity = H.enum_value(
        snapshot.daily_report.risk_report.severity, "calm"
    )
    rejections = snapshot.daily_report.risk_report.rejection_count
    risk_tone = "warn" if risk_severity.lower() in {"attention", "warning"} else "danger" if risk_severity.lower() in {"critical"} else "good"
    risk_detail = f"{rejections} rejection" if rejections == 1 else f"{rejections} rejections"

    realized = float(snapshot.realized_pnl)
    pnl_tone = "pos" if realized > 0 else "neg" if realized < 0 else ""

    active_count = sum(
        1 for card in snapshot.model_cards if card.state.lower() == "paper"
    ) or len(snapshot.model_cards)

    stats = [
        C.stat(
            label="Cash",
            value=f'<span data-field="cash">{H.money(snapshot.cash)}</span>',
            detail="Available to spend",
        ),
        C.stat(
            label="Day P&L",
            value=f'<span data-field="realized-pnl">{H.money(snapshot.realized_pnl)}</span>',
            detail=f'Open orders: <span data-field="open-orders">{snapshot.open_orders}</span>',
            tone=pnl_tone,
        ),
        C.stat(
            label="Risk",
            value=f'<span data-field="risk-severity">{escape(risk_severity)}</span>',
            detail=risk_detail,
            tone=risk_tone,
        ),
        C.stat(
            label="Running strategies",
            value=f"{active_count}",
            detail="fake-money only",
            tone="ai",
        ),
    ]
    return f'<section class="stat-row" aria-label="Portfolio metrics">{"".join(stats)}</section>'


# ---------------------------------------------------------------------------
# Latest decisions / AI summary
# ---------------------------------------------------------------------------


def _latest_decisions(snapshot: OperatorDashboardSnapshot) -> str:
    explanations = snapshot.daily_report.trade_explanations
    if not explanations:
        body = C.empty("No trade decisions reviewed yet today. They appear here after the daily runtime cycle scores each candidate.")
    else:
        rows = []
        for explanation in explanations[:6]:
            status = explanation.status.value
            tone_attr = {
                "FILLED": "pos",
                "REJECTED": "neg",
            }.get(status.upper(), "")
            row_klass = "" if tone_attr in ("pos", "") else "warn" if status.upper() != "REJECTED" else "danger"
            rows.append(
                C.row(
                    primary=f"<strong>{escape(explanation.symbol)} {escape(explanation.side.value)}</strong>",
                    primary_sub=escape(explanation.order_id),
                    meta=escape(status),
                    value=tone_attr.upper() if tone_attr else "",
                    value_tone=tone_attr,
                    tone=row_klass,
                )
            )
        body = C.row_list(rows)

    return C.surface(
        eyebrow=C.glossary("Today's decisions", key="daily_report"),
        title="What the strategy did today",
        body_html=body,
        pill_html=C.pill(f"{len(explanations)} reviewed", tone="ghost"),
    )


def _ai_summary(snapshot: OperatorDashboardSnapshot) -> str:
    summary = escape(snapshot.daily_report.ai_summary.summary)
    nightly = snapshot.nightly_learning
    if nightly and nightly.recommendations:
        confidence = nightly.recommendations[0].confidence
    else:
        confidence = None
    confidence_html = C.confidence(confidence)
    body = f"""
      <div class="memo">
        {summary}
        <small>AI copilot · explainable · paper authority only</small>
      </div>
      <div class="k-list">
        <div class="k-row">
          <span>Confidence</span>
          <strong>{confidence_html}</strong>
        </div>
        <div class="k-row">
          <span>Authority</span>
          <strong>paper · manual approval</strong>
        </div>
      </div>"""
    return C.surface(
        eyebrow=C.glossary("What the AI did", key="ai_daily_memo"),
        title="AI is a copilot, not an oracle",
        body_html=body,
        pill_html=C.pill("REVIEWED", tone="ai"),
    )


# ---------------------------------------------------------------------------
# System status & Paper boundary
# ---------------------------------------------------------------------------


def _system_status(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    cycle = getattr(runtime, "last_cycle", None) if runtime else None
    runtime_status = H.enum_value(getattr(runtime, "status", None), "awaiting")
    body = C.k_list(
        [
            (
                "Runtime",
                f'<span data-field="runtime-status">{escape(runtime_status)}</span>',
            ),
            (
                "Trading authority",
                '<span data-field="trading-authority">Daily close only</span>',
            ),
            (
                "Prices refreshed",
                f'<span data-field="prices-refreshed">{H.yes_no(getattr(cycle, "prices_refreshed", False))}</span>',
            ),
            (
                "Broker synced",
                f'<span data-field="broker-synced">{H.yes_no(getattr(cycle, "broker_synced", False))}</span>',
            ),
            (
                "Broker connection",
                f'<span data-field="broker-connection">{escape(H.broker_connection_status(snapshot))}</span>',
            ),
            (
                "Active model",
                f'<span data-field="active-model-key">{escape(H.active_model_key(snapshot))}</span>',
            ),
            (
                "Orders submitted",
                f'<span data-field="orders-submitted">{getattr(cycle, "orders_submitted", 0)}</span>',
            ),
            (
                "Fills applied",
                f'<span data-field="fills-applied">{getattr(cycle, "fills_applied", 0)}</span>',
            ),
            (
                "Reconciliation",
                _reconciliation_pill(snapshot),
            ),
        ]
    )
    return C.surface(
        eyebrow=C.glossary("System status", key="runtime_proof"),
        title="What ran today",
        body_html=body,
        pill_html=C.pill("Trades once a day", tone="ai"),
    )


def _reconciliation_pill(snapshot: OperatorDashboardSnapshot) -> str:
    reconciled = snapshot.paper_report.reconciliation.reconciled
    text = "Reconciled" if reconciled else "Mismatch"
    return (
        f'<span data-field="reconciliation" class="{"pos" if reconciled else "neg"}">'
        f"{text}</span>"
    )


def _paper_boundary(snapshot: OperatorDashboardSnapshot) -> str:
    live_status = (
        H.enum_value(H.field(snapshot.live_readiness, "status"), "disabled")
        if snapshot.live_readiness
        else "disabled"
    )
    body = C.k_list(
        [
            (
                "Runtime mode",
                f'<span data-field="paper-boundary-mode">{escape(snapshot.mode)}</span>',
            ),
            ("Money at risk", '<span class="pos">$0 real capital</span>'),
            ("Blocked products", "No margin, shorts, options"),
            (
                "Live readiness",
                f'<span data-field="live-readiness-status">{escape(live_status)}</span>',
            ),
        ]
    )
    return C.surface(
        eyebrow=C.glossary("This is fake money", key="paper_boundary"),
        title=C.glossary("Live disabled", key="live_disabled"),
        body_html=body,
        pill_html=C.pill("Paper only", tone="good"),
    )


# ---------------------------------------------------------------------------
# Data feed & data quality
# ---------------------------------------------------------------------------


def _data_feed(snapshot: OperatorDashboardSnapshot) -> str:
    latest = H.latest_prices(snapshot)
    pill_tone = "good" if latest["status"] == "fresh" else "warn"

    if latest["records"]:
        rows = [
            C.row(
                primary=f'<strong>{escape(record["symbol"])}</strong>',
                primary_sub=escape(record["status"]),
                value=record["price"],
                value_tone=record["tone"],
            )
            for record in latest["records"]
        ]
        prices_body = C.row_list(rows, container_attrs="data-latest-price-list")
    else:
        prices_body = (
            '<div class="row-list" data-latest-price-list>'
            + C.empty("No live prices yet. Quotes appear once the market-data feed delivers its first snapshot of the day.")
            + "</div>"
        )

    feed_status = (
        f'<span data-field="price-feed">{escape(latest["feed"])}</span>'
    )
    freshness = (
        f'<span data-field="price-freshness" class="mono">{escape(latest["status"])}</span>'
    )
    warning = f"""<p class="microcopy" data-field="price-warning">{escape(latest["warning"])}</p>"""

    prices_surface = C.surface(
        eyebrow=C.glossary("Latest Prices", key="latest_prices"),
        title=f"Market data · {feed_status}",
        body_html=f"""
          <div class="k-row">
            <span>Freshness</span><strong>{freshness}</strong>
          </div>
          {prices_body}
          {warning}
          <p class="microcopy">{escape(snapshot.data_feed_status)}</p>
        """,
        pill_html=C.pill(latest["status"].upper(), tone=pill_tone),
    )

    quality_surface = _data_quality(snapshot)
    return f'<div class="grid-2">{prices_surface}{quality_surface}</div>'


def _data_quality(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.daily_report.data_quality_report
    if report is None:
        body = C.empty("No data-quality report yet. It will arrive after the next runtime cycle verifies the market data.")
        return C.surface(
            eyebrow=C.glossary("How good is the data?", key="data_quality"),
            title='<span data-field="data-quality-status">unavailable</span>',
            body_html=body,
            pill_html=f'<span class="pill pill--warn" data-field="data-quality-chip">unavailable</span>',
        )
    status = H.enum_value(report.status, "unavailable")
    provenance = report.provenance
    summary = report.summary or "Market-data quality status is unavailable."
    tone = "warn" if status in ("warning", "unavailable") else "danger" if status == "failed" else "good"

    left_rows = [
        (
            "Research usable",
            f'<span data-field="data-quality-research-usable">{H.yes_no(report.can_use_for_research)}</span>',
        ),
        (
            "Trading usable",
            f'<span data-field="data-quality-trading-usable">{H.yes_no(report.can_use_for_trading)}</span>',
        ),
        (
            "Warnings",
            f'<span data-field="data-quality-warnings" class="mono">{report.warnings}</span>',
        ),
        (
            "Failures",
            f'<span data-field="data-quality-failures" class="mono">{report.failures}</span>',
        ),
    ]
    right_rows = [
        (
            "Dataset",
            f'<span data-field="data-quality-dataset">{escape(getattr(provenance, "dataset_type", "unavailable"))}</span>',
        ),
        (
            "Symbols",
            f'<span data-field="data-quality-symbols">{escape(_symbol_count(provenance))}</span>',
        ),
        (
            "Sources",
            f'<span data-field="data-quality-sources">{escape(H.join_values(getattr(provenance, "sources", ())))}</span>',
        ),
        (
            "Feeds",
            f'<span data-field="data-quality-feeds">{escape(H.join_values(getattr(provenance, "feeds", ())))}</span>',
        ),
        (
            "Window",
            f'<span data-field="data-quality-window">{escape(_quality_window(report))}</span>',
        ),
    ]
    body = f"""
      <p class="surface__summary" data-field="data-quality-summary">{escape(summary)}</p>
      {C.k_split(left_rows, right_rows)}
      <div class="k-row"><span>Quality Issues</span><strong>{report.warnings} warning · {report.failures} failure</strong></div>
      <div class="row-list" data-data-quality-issue-list>
        {_quality_issue_rows(report)}
      </div>"""
    return C.surface(
        eyebrow=C.glossary("How good is the data?", key="data_quality"),
        title=f'<span data-field="data-quality-status">{escape(status)}</span>',
        body_html=body,
        pill_html=f'<span class="pill pill--{tone}" data-field="data-quality-chip">{escape(status)}</span>',
    )


def _symbol_count(provenance) -> str:
    symbols = getattr(provenance, "symbols", ()) if provenance else ()
    return f"{len(symbols)} tracked" if symbols else "unavailable"


def _quality_window(report) -> str:
    provenance = report.provenance
    if provenance.start and provenance.end:
        return f"{provenance.start.isoformat()} to {provenance.end.isoformat()}"
    return report.generated_at.isoformat()


def _quality_issue_rows(report) -> str:
    if not report.issues:
        return C.empty("No data-quality issues today. The market data passed every check.")
    rows = []
    for issue in report.issues[:4]:
        status = H.enum_value(issue.status, "warning")
        row_tone = "danger" if status == "failed" else "warn"
        subject = issue.symbol or "dataset"
        if issue.trading_date:
            subject = f"{subject} {issue.trading_date.isoformat()}"
        rows.append(
            C.row(
                primary=f"<strong>{escape(H.humanize_code(issue.code))}</strong>",
                primary_sub=escape(issue.message),
                meta=escape(subject),
                tone=row_tone,
            )
        )
    return "".join(rows)
