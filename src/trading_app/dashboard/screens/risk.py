"""Risk screen — first-class risk surface.

Design intent (see DESIGN_VISION.md, "Risk Is Always Visible"):
risk should hit the operator the moment this screen opens. Severity is
the hero (mono, hero-scale, color-toned). The kill switch sits beside
it, breathing cyan while armed-and-off so the operator can see at a
glance that there is one button to stop everything, and that pressing
it cannot harm real capital.

The body is laid out flat — stat row, exposure bars, rejected signals,
runtime alerts, operator controls — with destructive controls visually
separated from safe ones. No card-in-card nesting.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from trading_app.dashboard import components as C
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.screens import _helpers as H


# ---------------------------------------------------------------------------
# Severity → tone mapping
# ---------------------------------------------------------------------------
#
# ReportSeverity values are OK / ATTENTION / BLOCKED. Map them onto the
# design system's neutral / warn / danger tones. "good" looks like a
# trophy on a risk screen, so OK is rendered with the calm cyan "ai"
# tone instead — signal, not celebration.

_SEVERITY_TONE = {
    "OK": "ai",
    "CALM": "ai",
    "ATTENTION": "warn",
    "WARNING": "warn",
    "BLOCKED": "danger",
    "CRITICAL": "danger",
}

_SEVERITY_HERO_COLOR = {
    "ai": "var(--ai)",
    "warn": "var(--warn)",
    "danger": "var(--neg)",
}

# Known risk-rule names mapped to their glossary keys. Rules not in this map
# render with the raw name and no popover — better an honest "unknown" than
# a wrong definition.
_RULE_GLOSSARY_KEYS: dict[str, str] = {
    "MAX_ORDERS_PER_DAY": "rule_max_orders_per_day",
}


def _humanize_rejection(rule_name: str, raw_message: str) -> str:
    """Two-sentence plain-language rewrite of a rejection message.

    Sentence 1: what happened (in user terms). Sentence 2: what it means.
    Unknown rules pass through the raw message unchanged.
    """

    rewrites = {
        "MAX_ORDERS_PER_DAY": (
            "We didn't place this trade — you've already hit today's order "
            "limit. This is a safety rule that prevents a runaway strategy "
            "from spamming the broker."
        ),
    }
    return rewrites.get(rule_name, raw_message)


def render(snapshot: OperatorDashboardSnapshot) -> str:
    return f"""
    <section class="screen" data-screen="risk" hidden>
      <div class="screen__head">
        <div>
          <span class="eyebrow">Risk</span>
          <h1>Your safety net, in one place.</h1>
          <p>How risky things are right now, what trades were blocked, where your money is, and the one button that stops it all.</p>
        </div>
      </div>

      {_severity_hero(snapshot)}
      {_stat_row(snapshot)}
      {_exposure(snapshot)}

      <div class="grid-2">
        {_rejected_signals(snapshot)}
        {_alerts(snapshot)}
      </div>

      {_operator_controls(snapshot)}
    </section>"""


# ---------------------------------------------------------------------------
# Hero — severity + kill switch
# ---------------------------------------------------------------------------


def _severity_hero(snapshot: OperatorDashboardSnapshot) -> str:
    risk = snapshot.daily_report.risk_report
    severity_raw = H.enum_value(risk.severity, "OK")
    severity_text = str(severity_raw).upper()
    tone = _SEVERITY_TONE.get(severity_text, "ai")
    color = _SEVERITY_HERO_COLOR[tone]

    kill_switch_on = snapshot.kill_switch_enabled
    # "Armed and OFF" = kill switch is off, runtime is armed to trade.
    # That state pulses cyan so the operator can see it from across the
    # room. When the kill switch is ON, the breath stops and the pill
    # turns red — the trading floor knows it is halted.
    #
    # NOTE: the canonical ``data-field="paper-kill-switch-state"`` lives
    # in the Operator Controls surface below; the JS overwrites that
    # node's className on every snapshot refresh, which would strip the
    # ``pill--armed`` cyan breath. Keeping the hero pill un-bound lets
    # the breath survive refreshes while the controls pill stays in sync
    # with the live runtime flag.
    if kill_switch_on:
        kill_label = "Kill switch ON"
        kill_class = "pill pill--danger"
    else:
        kill_label = "Kill switch OFF"
        kill_class = "pill pill--ai pill--armed"
    kill_pill_html = (
        f'<span class="{kill_class}" aria-label="{escape(kill_label)}">'
        f"{escape(kill_label)}</span>"
    )

    rejections = risk.rejection_count
    rejection_text = (
        f"1 rejection today" if rejections == 1 else f"{rejections} rejections today"
    )
    rules = ", ".join(rule.value for rule in risk.rejection_rules) or "no rules firing"

    return f"""
      <section class="hero" aria-label="Risk severity">
        <div class="hero__lead">
          <span class="hero__label">{C.glossary("Risk State", key="risk_state")}</span>
          <div class="hero__value" style="color: {color};">
            <span data-field="risk-severity">{escape(severity_text)}</span>
          </div>
          <div class="hero__delta">
            <span>{escape(rejection_text)}</span>
            <span class="delta-divider">·</span>
            <span class="mono">{escape(rules)}</span>
            <span class="delta-divider">·</span>
            {kill_pill_html}
          </div>
        </div>
        <p class="microcopy">
          The {C.glossary("kill switch", key="kill_switch")} is the one button that stops all paper trading. Press it whenever you want — it cannot affect real money.
        </p>
      </section>"""


# ---------------------------------------------------------------------------
# 4-up stat row
# ---------------------------------------------------------------------------


def _stat_row(snapshot: OperatorDashboardSnapshot) -> str:
    risk = snapshot.daily_report.risk_report
    severity_raw = H.enum_value(risk.severity, "OK")
    severity_text = str(severity_raw).upper()
    severity_tone = _SEVERITY_TONE.get(severity_text, "ai")
    severity_stat_tone = {
        "ai": "ai",
        "warn": "warn",
        "danger": "neg",
    }.get(severity_tone, "ai")

    rejections = risk.rejection_count
    rejection_tone = "warn" if rejections > 0 else ""
    rejection_detail = (
        "Paper orders refused today" if rejections else "All paper orders cleared"
    )

    alerts = snapshot.alerts
    alert_count = len(alerts)
    has_error = any(
        H.enum_value(H.field(alert, "severity"), "") == "error" for alert in alerts
    )
    alert_tone = "neg" if has_error else "warn" if alert_count else ""
    alert_detail = (
        "Operator review needed" if alert_count else "Runtime is quiet"
    )

    stats = [
        C.stat(
            label="How worried we are",
            value=escape(severity_text),
            detail=f"{risk.risk_decisions} trades checked today",
            tone=severity_stat_tone,
        ),
        C.stat(
            label=C.glossary("Trades blocked", key="rejected_signals"),
            value=f"{rejections}",
            detail=rejection_detail,
            tone=rejection_tone,
        ),
        C.stat(
            label="Active warnings",
            value=f"{alert_count}",
            detail=alert_detail,
            tone=alert_tone,
        ),
        C.stat(
            label=C.glossary("Drawdown", key="drawdown"),
            value="—",
            detail="No history yet",
        ),
    ]
    return (
        f'<section class="stat-row" aria-label="Risk metrics">{"".join(stats)}</section>'
    )


# ---------------------------------------------------------------------------
# Exposure by symbol
# ---------------------------------------------------------------------------


def _exposure(snapshot: OperatorDashboardSnapshot) -> str:
    positions = snapshot.paper_report.ledger_snapshot.positions
    exposures: list[tuple[str, float]] = []
    for position in positions:
        try:
            exposure = float(Decimal(str(position.quantity)) * Decimal(str(position.average_cost)))
        except (ValueError, TypeError):
            exposure = 0.0
        exposures.append((position.symbol, abs(exposure)))

    if not exposures:
        body = C.empty("No open positions, so there is no symbol exposure to draw.")
        return C.surface(
            eyebrow="Per-Symbol",
            title="Exposure by symbol",
            body_html=body,
            pill_html=C.pill("flat", tone="ghost"),
        )

    exposures.sort(key=lambda item: item[1], reverse=True)
    max_value = exposures[0][1] or 1.0
    total = sum(value for _, value in exposures)

    bars = []
    for symbol, value in exposures:
        share = (value / total) * 100.0 if total else 0.0
        # Tone the largest position(s) warmer so the bar reads as signal.
        if share >= 60.0:
            tone = "warn"
        elif share >= 30.0:
            tone = ""
        else:
            tone = "pos"
        bars.append(C.h_bar(symbol, value, max_value, tone=tone))

    body = f"""
      <div class="k-list">{"".join(bars)}</div>
      <p class="microcopy">
        Largest position anchors the scale. Cost basis = quantity × average cost. Live mark-to-market arrives with the next snapshot.
      </p>"""
    largest_share = (exposures[0][1] / total) * 100.0 if total else 0.0
    pill_tone = "warn" if largest_share >= 60.0 else "ai"
    return C.surface(
        eyebrow=C.glossary("Where your money is", key="exposure"),
        title="Exposure by symbol",
        body_html=body,
        pill_html=C.pill(f"top {largest_share:.0f}%", tone=pill_tone),
    )


# ---------------------------------------------------------------------------
# Rejected signals
# ---------------------------------------------------------------------------


def _rejected_signals(snapshot: OperatorDashboardSnapshot) -> str:
    rejected = snapshot.daily_report.rejected_signal_report.rejected_signals
    severity_raw = str(
        H.enum_value(snapshot.daily_report.risk_report.severity, "OK")
    ).upper()
    severity_tone = _SEVERITY_TONE.get(severity_raw, "ai")
    row_tone = "danger" if severity_tone == "danger" else "warn"

    if not rejected:
        body = C.empty("No trades were blocked today. The safety system is quiet.")
        pill_html = C.pill("clean", tone="good")
    else:
        rows = []
        for item in rejected:
            rule_name = item.rule.value
            # Wrap known rule names with their glossary explanation
            glossary_key = _RULE_GLOSSARY_KEYS.get(rule_name)
            rule_html = (
                C.glossary(rule_name, key=glossary_key)
                if glossary_key
                else escape(rule_name)
            )
            plain_message = _humanize_rejection(rule_name, item.message)
            rows.append(
                C.row(
                    primary=f'<strong class="mono">{rule_html}</strong>',
                    primary_sub=escape(plain_message),
                    meta=f'<span class="mono">{escape(item.order_id)}</span> · {escape(item.symbol)}',
                    tone=row_tone,
                )
            )
        body = C.row_list(rows)
        pill_html = C.pill(
            f"{len(rejected)} blocked",
            tone="danger" if severity_tone == "danger" else "warn",
        )

    return C.surface(
        eyebrow=C.glossary("Trades the safety system blocked", key="rejected_signals"),
        title="Rejected Signals",
        body_html=body,
        pill_html=pill_html,
    )


# ---------------------------------------------------------------------------
# Runtime alerts
# ---------------------------------------------------------------------------


def _alerts(snapshot: OperatorDashboardSnapshot) -> str:
    alerts = snapshot.alerts
    has_error = any(
        H.enum_value(H.field(alert, "severity"), "") == "error" for alert in alerts
    )
    tone = "danger" if has_error else "warn" if alerts else "good"
    tone_text = "ERROR" if has_error else "WARN" if alerts else "CLEAR"

    if not alerts:
        rows_html = C.empty("No active alerts. The runtime is quiet.")
    else:
        rows = []
        for alert in alerts:
            severity = H.enum_value(H.field(alert, "severity"), "warning")
            row_tone = "danger" if severity == "error" else "warn"
            evidence = " / ".join(H.field(alert, "evidence", ()) or ())
            rows.append(
                C.row(
                    primary=(
                        f'<strong>{escape(H.field(alert, "title", "Runtime alert"))}</strong>'
                    ),
                    primary_sub=escape(H.field(alert, "message", "")),
                    meta=escape(
                        H.enum_value(H.field(alert, "code"), "runtime_alert")
                    ),
                    value=escape(evidence),
                    value_tone="warn",
                    tone=row_tone,
                )
            )
        rows_html = "".join(rows)

    body = f"""
      <div class="row-list" data-alert-list>{rows_html}</div>
      <p class="microcopy">
        Alerts surface from the runtime journal. They never auto-dismiss — close the underlying condition first.
      </p>"""
    return C.surface(
        eyebrow=C.glossary("System warnings", key="runtime_alerts"),
        title=f'<span data-field="alert-count">{len(alerts)} active</span>',
        body_html=body,
        pill_html=(
            f'<span class="pill pill--{tone}" data-field="alert-tone">{tone_text}</span>'
        ),
    )


# ---------------------------------------------------------------------------
# Operator controls
# ---------------------------------------------------------------------------


def _operator_controls(snapshot: OperatorDashboardSnapshot) -> str:
    control_state = snapshot.control_state
    paused = bool(control_state and H.field(control_state, "paused", False))
    kill_switch = snapshot.kill_switch_enabled
    last_action = (
        H.enum_value(
            H.field(H.field(snapshot.last_control_result, "request", {}), "action"),
            "none",
        )
        if snapshot.last_control_result
        else "none"
    )
    updated_by = H.field(control_state, "updated_by", "system")
    raw_updated_at = H.field(control_state, "updated_at", "pending")
    updated_at = (
        raw_updated_at.isoformat()
        if hasattr(raw_updated_at, "isoformat")
        else str(raw_updated_at)
    )

    state_text = "Paused" if paused else "Armed"
    state_tone = "warn" if paused else "ai"
    kill_pill_tone = "danger" if kill_switch else "ai"
    kill_label = "Kill ON" if kill_switch else "Kill OFF"
    kill_class = (
        "pill pill--danger" if kill_switch else "pill pill--ai pill--armed"
    )

    def _btn(
        action: str,
        label: str,
        *,
        disabled: bool,
        danger: bool = False,
    ) -> str:
        klass = "btn btn--danger" if danger else "btn"
        attrs = " disabled" if disabled else ""
        return (
            f'<button class="{klass}" data-control-action="{escape(action)}"'
            f"{attrs}>{escape(label)}</button>"
        )

    # Group A — safe runtime controls.
    safe_buttons = [
        _btn("resume_runtime", "Resume trading", disabled=not paused),
        _btn("pause_runtime", "Pause trading", disabled=paused),
        _btn("force_reconciliation", "Re-check vs broker", disabled=False),
        _btn("generate_report", "Save today's summary", disabled=False),
    ]
    # Group B — destructive, visually separated.
    destructive_buttons = [
        _btn(
            "enable_paper_kill_switch",
            "Stop all paper trading",
            disabled=kill_switch,
            danger=True,
        ),
        _btn(
            "disable_paper_kill_switch",
            "Re-enable trading",
            disabled=not kill_switch,
        ),
    ]

    # ``data-control-grid`` wraps the union so tests + JS can locate every
    # action; inside, we split into two visual rows so the destructive
    # cluster sits apart from the safe one.
    grid_html = f"""
      <div data-control-grid>
        <div class="btn-row">{"".join(safe_buttons)}</div>
        <p class="microcopy" style="margin-top: 12px;">
          Stopping paper trading halts every order. It's safe and reversible — no real money can be affected.
        </p>
        <div class="btn-row" style="margin-top: 8px;">{"".join(destructive_buttons)}</div>
      </div>"""

    meta_body = C.k_list(
        [
            (
                "Last action",
                f'<span data-field="last-control-action" class="mono">{escape(last_action)}</span>',
            ),
            (
                "Updated by",
                f'<span data-field="control-updated-by">{escape(updated_by)}</span>',
            ),
            (
                "Updated at",
                f'<span data-field="control-updated-at" class="mono">{escape(updated_at)}</span>',
            ),
        ]
    )

    body = f"""
      <div class="k-row">
        <span>Runtime</span>
        <strong>
          <span class="pill pill--{state_tone}" data-field="control-state-heading">{escape(state_text)}</span>
        </strong>
      </div>
      <div class="k-row">
        <span>Kill switch</span>
        <strong><span class="{kill_class}" data-field="paper-kill-switch-state">{escape(kill_label)}</span></strong>
      </div>
      {grid_html}
      {meta_body}"""

    # Headline pill mirrors the runtime state; the kill-switch field lives
    # in the body grid so it sits next to its arming controls.
    return C.surface(
        eyebrow=C.glossary("What you can do", key="operator_controls"),
        title="Operator Controls",
        body_html=body,
        pill_html=(
            f'<span class="pill pill--{kill_pill_tone}">{escape(kill_label)}</span>'
        ),
    )
