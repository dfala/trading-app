"""Render the local operator dashboard."""

# ruff: noqa: E501

from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path

from trading_app.dashboard.models import OperatorDashboardSnapshot


def render_dashboard_html(
    snapshot: OperatorDashboardSnapshot, *, interactive: bool = False
) -> str:
    """Render a self-contained operator dashboard HTML document."""

    refresh_attrs = ' data-refresh-time=""' if interactive else ""
    script = _interactive_script() if interactive else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trading Lab Operator Dashboard</title>
  <style>
{_CSS}
  </style>
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Trading Lab</p>
      <h1>Operator Dashboard</h1>
    </div>
    <div class="status-strip" aria-label="System status">
      <span class="status-pill paper" data-field="mode">{escape(snapshot.mode)}</span>
      <span class="status-pill broker" data-field="broker">{escape(snapshot.broker)}</span>
      <span class="status-pill {"danger" if snapshot.kill_switch_enabled else "calm"}" data-field="kill-switch">
        Kill switch {"ON" if snapshot.kill_switch_enabled else "OFF"}
      </span>
    </div>
  </header>

  <main>
    <section class="metrics-grid" aria-label="Portfolio metrics">
      {_metric_cards(snapshot)}
    </section>

    <section class="dashboard-grid">
      <article class="panel portfolio-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Paper Portfolio</p>
            <h2 data-field="estimated-equity">{_money_text(snapshot.estimated_equity)}</h2>
          </div>
          <span class="chip {"good" if snapshot.paper_report.reconciliation.reconciled else "danger"}" data-field="reconciliation">{"Reconciled" if snapshot.paper_report.reconciliation.reconciled else "Mismatch"}</span>
        </div>
        <div class="equity-visual">
          {_equity_svg(snapshot)}
        </div>
        <div class="split-list">
          <div>
            <span class="label">Cash</span>
            <strong data-field="cash">{_money_text(snapshot.cash)}</strong>
          </div>
          <div>
            <span class="label">Open orders</span>
            <strong data-field="open-orders">{snapshot.open_orders}</strong>
          </div>
          <div>
            <span class="label">Realized P&L</span>
            <strong data-field="realized-pnl">{_money_text(snapshot.realized_pnl)}</strong>
          </div>
        </div>
      </article>

      {_paper_boundary_panel(snapshot)}

      <article class="panel risk-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Risk State</p>
            <h2 data-field="risk-severity">{escape(snapshot.daily_report.risk_report.severity.value)}</h2>
          </div>
          <span class="chip warn">{snapshot.daily_report.risk_report.rejection_count} rejection</span>
        </div>
        <div class="risk-meter" aria-label="Risk meter">
          <span style="height: 18%"></span>
          <span style="height: 28%"></span>
          <span class="active" style="height: 62%"></span>
          <span style="height: 38%"></span>
          <span style="height: 22%"></span>
        </div>
        <ul class="clean-list">
          <li><span>Rules triggered</span><strong>{_rules(snapshot)}</strong></li>
          <li><span>Broker reconciliation</span><strong>{"Clean" if snapshot.paper_report.reconciliation.reconciled else "Issue"}</strong></li>
          <li><span>Data feed</span><strong>{escape(snapshot.data_feed_status)}</strong></li>
        </ul>
      </article>

      {_latest_price_panel(snapshot)}

      {_data_quality_panel(snapshot)}

      {_runtime_proof_panel(snapshot)}

      {_active_model_explanation_panel(snapshot)}

      {_completion_audit_panel(snapshot)}

      {_final_acceptance_panel(snapshot)}

      {_statement_reconciliation_panel(snapshot)}

      {_health_panel(snapshot)}

      {_control_panel(snapshot)}

      {_alerts_panel(snapshot)}

      {_live_readiness_panel(snapshot)}

      {_report_status_panel(snapshot)}

      {_audit_trail_panel(snapshot)}

      {_tax_estimate_panel(snapshot)}

      <article class="panel wide-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Model Arena</p>
            <h2>Champion / Challenger</h2>
          </div>
          <span class="chip info">Active model locked</span>
        </div>
        <div class="model-grid">
          {_model_cards(snapshot)}
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Daily Report</p>
            <h2>AI Governance Summary</h2>
          </div>
        </div>
        <p class="summary">{escape(snapshot.daily_report.ai_summary.summary)}</p>
        <div class="mini-table">
          {_trade_rows(snapshot)}
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Rejected Signals</p>
            <h2>{snapshot.daily_report.risk_report.rejection_count}</h2>
          </div>
          <span class="chip warn">Review</span>
        </div>
        <div class="event-list">
          {_rejection_rows(snapshot)}
        </div>
      </article>

      <article class="panel wide-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Nightly Learning</p>
            <h2>{_learning_heading(snapshot)}</h2>
          </div>
          <span class="chip good">No active mutation</span>
        </div>
        <p class="microcopy">{escape(_learning_review_line(snapshot))}</p>
        <div class="learning-grid">
          <div class="memo">{escape(_learning_memo(snapshot))}</div>
          <div class="comparison-bars">
            {_comparison_svg(snapshot)}
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Positions</p>
            <h2 data-field="position-count">{len(snapshot.paper_report.ledger_snapshot.positions)} open</h2>
          </div>
        </div>
        <div class="mini-table" data-position-list>
          {_position_rows(snapshot)}
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Recent Fills</p>
            <h2 data-field="fill-count">{len(snapshot.recent_fills)}</h2>
          </div>
        </div>
        <div class="event-list" data-fill-list>
          {_fill_rows(snapshot)}
        </div>
      </article>
    </section>
  </main>

  <footer class="footer">
    Generated<span{refresh_attrs}> {escape(snapshot.generated_at.isoformat())}</span>. Paper mode only. No live-money actions are available from this dashboard.
  </footer>
{script}
</body>
</html>
"""


def write_dashboard(
    snapshot: OperatorDashboardSnapshot, output_path: Path | str
) -> Path:
    """Write the dashboard HTML file and return the path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard_html(snapshot), encoding="utf-8")
    return path


def render_interactive_dashboard_html(snapshot: OperatorDashboardSnapshot) -> str:
    """Render the local web-app shell with browser-side JSON refresh."""

    return render_dashboard_html(snapshot, interactive=True)


def _metric_cards(snapshot: OperatorDashboardSnapshot) -> str:
    return "\n".join(
        f"""
      <article class="metric-card {escape(metric.tone)}">
        <span>{escape(metric.label)}</span>
        <strong>{escape(metric.value)}</strong>
        <small>{escape(metric.detail)}</small>
      </article>"""
        for metric in snapshot.metrics
    )


def _model_cards(snapshot: OperatorDashboardSnapshot) -> str:
    cards = []
    for card in snapshot.model_cards:
        cards.append(
            f"""
          <div class="model-card">
            <div>
              <span class="label">{escape(card.label)}</span>
              <strong>{escape(card.version)}</strong>
            </div>
            <p>{escape(card.strategy_id)}</p>
            <div class="score-row"><span>Score</span><b>{card.score:.4f}</b></div>
            <div class="score-row"><span>State</span><b>{escape(card.state)}</b></div>
            <small>{escape(card.detail)}</small>
          </div>"""
        )
    return "\n".join(cards)


def _trade_rows(snapshot: OperatorDashboardSnapshot) -> str:
    rows = []
    for explanation in snapshot.daily_report.trade_explanations:
        rows.append(
            f"""
          <div class="table-row">
            <span>{escape(explanation.order_id)}</span>
            <strong>{escape(explanation.symbol)} {escape(explanation.side.value)}</strong>
            <em>{escape(explanation.status.value)}</em>
          </div>"""
        )
    return "\n".join(rows)


def _rejection_rows(snapshot: OperatorDashboardSnapshot) -> str:
    rejected = snapshot.daily_report.rejected_signal_report.rejected_signals
    if not rejected:
        return '<p class="empty">No rejected signals.</p>'
    return "\n".join(
        f"""
          <div class="event-row warn-border">
            <strong>{escape(item.rule.value)}</strong>
            <span>{escape(item.order_id)} {escape(item.symbol)}</span>
            <small>{escape(item.message)}</small>
          </div>"""
        for item in rejected
    )


def _health_panel(snapshot: OperatorDashboardSnapshot) -> str:
    health = snapshot.health_report
    if health is None:
        return ""
    health_status = _enum_value(_field(health, "status"), "unknown")
    incidents = tuple(_field(health, "incidents", ()) or ())
    tone = _health_tone(health_status)
    return f"""
      <article class="panel wide-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Runtime Health</p>
            <h2 data-field="health-status">{escape(health_status)}</h2>
          </div>
          <span class="chip {tone}" data-field="health-incident-count">{len(incidents)} incident</span>
        </div>
        <p class="summary" data-field="health-summary">{escape(_field(health, "summary", ""))}</p>
        {_health_report_path(snapshot)}
        <div class="health-grid">
          <div class="mini-table" data-health-check-list>
            <span class="label">Health Checks</span>
            {_health_rows(snapshot)}
          </div>
          <div class="event-list" data-incident-list>
            <span class="label">Incident Command</span>
            {_incident_rows(snapshot)}
          </div>
        </div>
      </article>"""


def _health_report_path(snapshot: OperatorDashboardSnapshot) -> str:
    if not snapshot.health_report_path:
        return '<p class="microcopy" data-field="health-report-path">Incident review: not written</p>'
    return (
        '<p class="microcopy" data-field="health-report-path">Incident review: '
        f"{escape(snapshot.health_report_path)}</p>"
    )


def _health_rows(snapshot: OperatorDashboardSnapshot) -> str:
    health = snapshot.health_report
    checks = tuple(_field(health, "checks", ()) or ()) if health is not None else ()
    if health is None or not checks:
        return '<p class="empty">No health checks yet.</p>'
    rows = []
    for check in checks:
        rows.append(
            f"""
          <div class="table-row">
            <span>{escape(_field(check, "name", "unknown"))}</span>
            <strong>{escape(_enum_value(_field(check, "status"), "unknown"))}</strong>
            <em>{escape(_field(check, "message", ""))}</em>
          </div>"""
        )
    return "\n".join(rows)


def _incident_rows(snapshot: OperatorDashboardSnapshot) -> str:
    health = snapshot.health_report
    incidents = (
        tuple(_field(health, "incidents", ()) or ()) if health is not None else ()
    )
    if health is None or not incidents:
        return '<p class="empty">No open incidents.</p>'
    rows = []
    for incident in incidents:
        status = _enum_value(_field(incident, "status"), "unknown")
        tone = (
            "danger-border"
            if status == "critical"
            else "warn-border"
            if status == "degraded"
            else ""
        )
        rows.append(
            f"""
          <div class="event-row {tone}">
            <strong>{escape(_field(incident, "title", "Runtime incident"))}</strong>
            <span>{escape(status)}</span>
            <small>{escape(_field(incident, "summary", ""))}</small>
            <small>{escape(_field(incident, "suggested_action", ""))}</small>
          </div>"""
        )
    return "\n".join(rows)


def _control_panel(snapshot: OperatorDashboardSnapshot) -> str:
    control_state = snapshot.control_state
    paused = bool(control_state and _field(control_state, "paused", False))
    kill_switch = snapshot.kill_switch_enabled
    last_action = (
        _enum_value(
            _field(_field(snapshot.last_control_result, "request", {}), "action"),
            "none",
        )
        if snapshot.last_control_result
        else "none"
    )
    updated_by = _field(control_state, "updated_by", "system")
    raw_updated_at = _field(control_state, "updated_at", "pending")
    updated_at = (
        raw_updated_at.isoformat()
        if hasattr(raw_updated_at, "isoformat")
        else str(raw_updated_at)
    )
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Operator Controls</p>
            <h2 data-field="control-state-heading">{"Paused" if paused else "Armed"}</h2>
          </div>
          <span class="chip {"danger" if kill_switch else "good"}" data-field="paper-kill-switch-state">Kill {"ON" if kill_switch else "OFF"}</span>
        </div>
        <div class="control-grid" data-control-grid>
          {_control_button("resume_runtime", "Resume", not paused)}
          {_control_button("pause_runtime", "Pause", paused)}
          {_control_button("disable_paper_kill_switch", "Kill Off", not kill_switch)}
          {_control_button("enable_paper_kill_switch", "Kill On", kill_switch)}
          {_control_button("force_reconciliation", "Reconcile", False)}
          {_control_button("generate_report", "Report", False)}
        </div>
        <ul class="clean-list">
          <li><span>Last action</span><strong data-field="last-control-action">{escape(last_action)}</strong></li>
          <li><span>Updated by</span><strong data-field="control-updated-by">{escape(updated_by)}</strong></li>
          <li><span>Updated at</span><strong data-field="control-updated-at">{escape(updated_at)}</strong></li>
        </ul>
      </article>"""


def _control_button(action: str, label: str, disabled: bool) -> str:
    disabled_attr = " disabled" if disabled else ""
    return (
        f'<button class="control-button" data-control-action="{escape(action)}"'
        f"{disabled_attr}>{escape(label)}</button>"
    )


def _alerts_panel(snapshot: OperatorDashboardSnapshot) -> str:
    tone = (
        "danger"
        if any(
            _enum_value(_field(alert, "severity"), "") == "error"
            for alert in snapshot.alerts
        )
        else "warn"
        if snapshot.alerts
        else "good"
    )
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Runtime Alerts</p>
            <h2 data-field="alert-count">{len(snapshot.alerts)} active</h2>
          </div>
          <span class="chip {tone}" data-field="alert-tone">{escape(tone.upper())}</span>
        </div>
        <div class="event-list" data-alert-list>
          {_alert_rows(snapshot)}
        </div>
      </article>"""


def _alert_rows(snapshot: OperatorDashboardSnapshot) -> str:
    if not snapshot.alerts:
        return '<p class="empty">No active alerts.</p>'
    rows = []
    for alert in snapshot.alerts:
        severity = _enum_value(_field(alert, "severity"), "warning")
        tone = "danger-border" if severity == "error" else "warn-border"
        evidence = " / ".join(_field(alert, "evidence", ()) or ())
        rows.append(
            f"""
          <div class="event-row {tone}">
            <strong>{escape(_field(alert, "title", "Runtime alert"))}</strong>
            <span>{escape(_enum_value(_field(alert, "code"), "runtime_alert"))}</span>
            <small>{escape(_field(alert, "message", ""))}</small>
            <small>{escape(evidence)}</small>
          </div>"""
        )
    return "\n".join(rows)


def _paper_boundary_panel(snapshot: OperatorDashboardSnapshot) -> str:
    mode = snapshot.mode
    live_status = (
        _enum_value(_field(snapshot.live_readiness, "status"), "disabled")
        if snapshot.live_readiness
        else "disabled"
    )
    return f"""
      <article class="panel boundary-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Paper Boundary</p>
            <h2>Live Disabled</h2>
          </div>
          <span class="chip good">Paper only</span>
        </div>
        <ul class="clean-list">
          <li><span>Runtime mode</span><strong data-field="paper-boundary-mode">{escape(mode)}</strong></li>
          <li><span>Money at risk</span><strong>$0 real capital</strong></li>
          <li><span>Blocked products</span><strong>No margin, shorts, options</strong></li>
          <li><span>Live readiness</span><strong data-field="live-readiness-status">{escape(live_status)}</strong></li>
        </ul>
      </article>"""


def _latest_price_panel(snapshot: OperatorDashboardSnapshot) -> str:
    latest = _latest_prices(snapshot)
    status = latest["status"]
    tone = "good" if status == "fresh" else "warn" if status != "missing" else "danger"
    return f"""
      <article class="panel wide-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Latest Prices</p>
            <h2 data-field="price-freshness">{escape(status)}</h2>
          </div>
          <span class="chip {tone}" data-field="price-feed">{escape(latest["feed"])}</span>
        </div>
        <div class="price-tape" data-latest-price-list>
          {_latest_price_rows(snapshot)}
        </div>
        <p class="microcopy" data-field="price-warning">{escape(latest["warning"])}</p>
      </article>"""


def _latest_price_rows(snapshot: OperatorDashboardSnapshot) -> str:
    latest = _latest_prices(snapshot)
    records = latest["records"]
    if not records:
        return '<p class="empty">No latest prices available yet.</p>'
    rows = []
    for record in records:
        rows.append(
            f"""
          <div class="price-pill {escape(record["tone"])}">
            <span>{escape(record["symbol"])}</span>
            <strong>{escape(record["price"])}</strong>
            <small>{escape(record["status"])}</small>
          </div>"""
        )
    return "\n".join(rows)


def _data_quality_panel(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.daily_report.data_quality_report
    status = _data_quality_status(report)
    tone = _data_quality_tone(status)
    provenance = getattr(report, "provenance", None) if report else None
    return f"""
      <article class="panel wide-panel data-quality-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Data Quality Evidence</p>
            <h2 data-field="data-quality-status">{escape(status)}</h2>
          </div>
          <span class="chip {tone}" data-field="data-quality-chip">{escape(status)}</span>
        </div>
        <p class="summary" data-field="data-quality-summary">{escape(_data_quality_summary(report))}</p>
        <div class="model-explain-grid">
          <ul class="clean-list">
            <li><span>Research usable</span><strong data-field="data-quality-research-usable">{_yes_no(bool(getattr(report, "can_use_for_research", False))) if report else "unknown"}</strong></li>
            <li><span>Trading usable</span><strong data-field="data-quality-trading-usable">{_yes_no(bool(getattr(report, "can_use_for_trading", False))) if report else "unknown"}</strong></li>
            <li><span>Warnings</span><strong data-field="data-quality-warnings">{getattr(report, "warnings", "-") if report else "-"}</strong></li>
            <li><span>Failures</span><strong data-field="data-quality-failures">{getattr(report, "failures", "-") if report else "-"}</strong></li>
          </ul>
          <ul class="clean-list">
            <li><span>Dataset</span><strong data-field="data-quality-dataset">{escape(getattr(provenance, "dataset_type", "unavailable") if provenance else "unavailable")}</strong></li>
            <li><span>Symbols</span><strong data-field="data-quality-symbols">{_data_quality_symbol_count(provenance)}</strong></li>
            <li><span>Sources</span><strong data-field="data-quality-sources">{escape(_join_values(getattr(provenance, "sources", ())))}</strong></li>
            <li><span>Feeds</span><strong data-field="data-quality-feeds">{escape(_join_values(getattr(provenance, "feeds", ())))}</strong></li>
            <li><span>Window</span><strong data-field="data-quality-window">{escape(_data_quality_window(report))}</strong></li>
          </ul>
        </div>
        <div class="event-list" data-data-quality-issue-list>
          <span class="label">Quality Issues</span>
          {_data_quality_issue_rows(report)}
        </div>
      </article>"""


def _data_quality_status(report) -> str:
    return _enum_value(getattr(report, "status", None), "unavailable")


def _data_quality_summary(report) -> str:
    if report is None:
        return "No market-data quality report is attached to this dashboard snapshot."
    return report.summary


def _data_quality_tone(status: str) -> str:
    if status == "failed":
        return "danger"
    if status == "warning" or status == "unavailable":
        return "warn"
    return "good"


def _data_quality_symbol_count(provenance) -> str:
    symbols = getattr(provenance, "symbols", ()) if provenance else ()
    return f"{len(symbols)} tracked" if symbols else "unavailable"


def _data_quality_window(report) -> str:
    if report is None:
        return "unavailable"
    provenance = report.provenance
    if provenance.start and provenance.end:
        return f"{provenance.start.isoformat()} to {provenance.end.isoformat()}"
    return report.generated_at.isoformat()


def _data_quality_issue_rows(report) -> str:
    if report is None:
        return '<p class="empty">No quality report available.</p>'
    if not report.issues:
        return '<p class="empty">No quality issues detected.</p>'
    rows = []
    for issue in report.issues[:4]:
        status = _enum_value(issue.status, "warning")
        tone = "danger-border" if status == "failed" else "warn-border"
        subject = issue.symbol or "dataset"
        if issue.trading_date:
            subject = f"{subject} {issue.trading_date.isoformat()}"
        rows.append(
            f"""
          <div class="event-row {tone}">
            <strong>{escape(_humanize_code(issue.code))}</strong>
            <span>{escape(subject)}</span>
            <small>{escape(issue.message)}</small>
          </div>"""
        )
    return "\n".join(rows)


def _runtime_proof_panel(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    cycle = getattr(runtime, "last_cycle", None) if runtime else None
    status = getattr(runtime, "status", None)
    status_value = _enum_value(status, "awaiting")
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Runtime Proof</p>
            <h2 data-field="runtime-status">{escape(status_value)}</h2>
          </div>
          <span class="chip info">Daily close only</span>
        </div>
        <ul class="clean-list">
          <li><span>Prices refreshed</span><strong data-field="prices-refreshed">{_yes_no(getattr(cycle, "prices_refreshed", False))}</strong></li>
          <li><span>Broker synced</span><strong data-field="broker-synced">{_yes_no(getattr(cycle, "broker_synced", False))}</strong></li>
          <li><span>Broker connection</span><strong data-field="broker-connection">{escape(_broker_connection_status(snapshot))}</strong></li>
          <li><span>Active model</span><strong data-field="active-model-key">{escape(_active_model_key(snapshot))}</strong></li>
          <li><span>Trading authority</span><strong data-field="trading-authority">Daily close only</strong></li>
          <li><span>Orders submitted</span><strong data-field="orders-submitted">{getattr(cycle, "orders_submitted", 0)}</strong></li>
          <li><span>Fills applied</span><strong data-field="fills-applied">{getattr(cycle, "fills_applied", 0)}</strong></li>
        </ul>
      </article>"""


def _active_model_explanation_panel(snapshot: OperatorDashboardSnapshot) -> str:
    definition = snapshot.active_strategy_definition
    if definition is None:
        return ""
    failure_modes = tuple(definition.failure_modes[:3])
    ai_roles = tuple(definition.ai_role[:3])
    return f"""
      <article class="panel wide-panel active-model-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Active Model</p>
            <h2 data-field="active-strategy-name">{escape(definition.name)}</h2>
          </div>
          <span class="chip info" data-field="active-strategy-authority">{escape(definition.authority.value)}</span>
        </div>
        <p class="summary" data-field="active-strategy-hypothesis">{escape(definition.hypothesis)}</p>
        <div class="model-explain-grid">
          <ul class="clean-list">
            <li><span>Model key</span><strong data-field="active-strategy-id">{escape(definition.strategy_id)}:{escape(definition.version)}</strong></li>
            <li><span>Cadence</span><strong data-field="active-strategy-cadence">{escape(definition.trading_cadence.value)}</strong></li>
            <li><span>Benchmark</span><strong data-field="active-strategy-benchmark">{escape(definition.benchmark)}</strong></li>
            <li><span>Universe</span><strong data-field="active-strategy-universe">{len(definition.universe)} U.S. ETF(s)</strong></li>
          </ul>
          <ul class="clean-list">
            <li><span>Signal</span><strong data-field="active-strategy-signal">{escape(definition.signal_logic)}</strong></li>
            <li><span>Sizing</span><strong data-field="active-strategy-sizing">{escape(definition.sizing_logic)}</strong></li>
            <li><span>Exit</span><strong data-field="active-strategy-exit">{escape(definition.exit_logic)}</strong></li>
          </ul>
        </div>
        <div class="model-explain-grid">
          <div class="event-list" data-active-strategy-failure-list>
            <span class="label">Known Failure Modes</span>
            {_plain_rows(failure_modes, empty="No failure modes recorded.")}
          </div>
          <div class="event-list" data-active-strategy-ai-role-list>
            <span class="label">AI Role</span>
            {_plain_rows(ai_roles, empty="No AI role recorded.")}
          </div>
        </div>
      </article>"""


def _plain_rows(values: tuple[str, ...], *, empty: str) -> str:
    if not values:
        return f'<p class="empty">{escape(empty)}</p>'
    return "\n".join(
        f"""
          <div class="event-row">
            <small>{escape(value)}</small>
          </div>"""
        for value in values
    )


def _completion_audit_panel(snapshot: OperatorDashboardSnapshot) -> str:
    audit = snapshot.completion_audit
    if audit is None:
        return """
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Functional Readiness</p>
            <h2 data-field="completion-status">Awaiting Audit</h2>
          </div>
          <span class="chip warn" data-field="completion-chip">Review</span>
        </div>
        <ul class="clean-list">
          <li><span>Proven</span><strong data-field="completion-proven">0</strong></li>
          <li><span>Missing</span><strong data-field="completion-missing">unknown</strong></li>
          <li><span>Failed</span><strong data-field="completion-failed">unknown</strong></li>
          <li><span>External proof</span><strong data-field="completion-external">required</strong></li>
          <li><span>Audit report</span><strong data-field="completion-path">not written</strong></li>
        </ul>
        <p class="microcopy" data-field="completion-summary">Run the functional completion audit after validation and soak evidence exists.</p>
      </article>"""

    status = _enum_value(_field(audit, "status"), "unknown")
    passed = bool(_field(audit, "passed", False))
    failed = int(_field(audit, "failed_count", 0) or 0)
    tone = "good" if passed else "danger" if failed else "warn"
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Functional Readiness</p>
            <h2 data-field="completion-status">{escape(status)}</h2>
          </div>
          <span class="chip {tone}" data-field="completion-chip">{"Ready" if passed else "Evidence"}</span>
        </div>
        <ul class="clean-list">
          <li><span>Proven</span><strong data-field="completion-proven">{_field(audit, "proven_count", 0)}</strong></li>
          <li><span>Missing</span><strong data-field="completion-missing">{_field(audit, "missing_count", 0)}</strong></li>
          <li><span>Failed</span><strong data-field="completion-failed">{_field(audit, "failed_count", 0)}</strong></li>
          <li><span>External proof</span><strong data-field="completion-external">{_field(audit, "external_required_count", 0)}</strong></li>
          <li><span>Audit report</span><strong data-field="completion-path">{escape(_field(audit, "markdown_path", None) or "not written")}</strong></li>
        </ul>
        <p class="microcopy" data-field="completion-summary">{escape(_field(audit, "summary", "Completion audit evidence is available."))}</p>
      </article>"""


def _final_acceptance_panel(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.final_acceptance
    if report is None:
        return """
      <article class="panel final-acceptance-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Final Acceptance</p>
            <h2 data-field="final-acceptance-status">Awaiting Signoff</h2>
          </div>
          <span class="chip warn" data-field="final-acceptance-chip">Not final</span>
        </div>
        <ul class="clean-list">
          <li><span>Accepted</span><strong data-field="final-acceptance-accepted">no</strong></li>
          <li><span>Checks</span><strong data-field="final-acceptance-checks">0/0</strong></li>
          <li><span>Signoff</span><strong data-field="final-acceptance-signoff">missing</strong></li>
          <li><span>Report</span><strong data-field="final-acceptance-path">not written</strong></li>
        </ul>
        <p class="microcopy" data-field="final-acceptance-summary">Run final acceptance after operator signoff and reviewed Alpaca Paper evidence.</p>
      </article>"""

    status = _enum_value(_field(report, "status"), "unknown")
    accepted = bool(_field(report, "accepted_for_functional_paper_app", False))
    checks = tuple(_field(report, "checks", ()) or ())
    passed_checks = sum(
        1 for check in checks if _enum_value(_field(check, "status"), "") == "passed"
    )
    tone = "good" if accepted else "danger"
    return f"""
      <article class="panel final-acceptance-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Final Acceptance</p>
            <h2 data-field="final-acceptance-status">{escape(status)}</h2>
          </div>
          <span class="chip {tone}" data-field="final-acceptance-chip">{"Accepted" if accepted else "Blocked"}</span>
        </div>
        <ul class="clean-list">
          <li><span>Accepted</span><strong data-field="final-acceptance-accepted">{_yes_no(accepted)}</strong></li>
          <li><span>Checks</span><strong data-field="final-acceptance-checks">{passed_checks}/{len(checks)}</strong></li>
          <li><span>Signoff</span><strong data-field="final-acceptance-signoff">{escape(_field(report, "signoff_path", None) or "missing")}</strong></li>
          <li><span>Report</span><strong data-field="final-acceptance-path">{escape(_field(report, "markdown_path", None) or "not written")}</strong></li>
        </ul>
        <p class="microcopy" data-field="final-acceptance-summary">{escape(_field(report, "summary", "Final acceptance evidence is available."))}</p>
      </article>"""


def _statement_reconciliation_panel(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.statement_reconciliation
    if report is None:
        return """
      <article class="panel statement-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Statement Review</p>
            <h2 data-field="statement-status">Awaiting Statement</h2>
          </div>
          <span class="chip warn" data-field="statement-chip">Post-run</span>
        </div>
        <ul class="clean-list">
          <li><span>Statement</span><strong data-field="statement-id">not loaded</strong></li>
          <li><span>Provider</span><strong data-field="statement-provider">unknown</strong></li>
          <li><span>Issues</span><strong data-field="statement-issues">unknown</strong></li>
          <li><span>Report</span><strong data-field="statement-path">not written</strong></li>
        </ul>
        <div class="event-list" data-statement-issue-list>
          <span class="label">Statement Issues</span>
          <p class="empty">Run post-run statement reconciliation.</p>
        </div>
        <p class="microcopy" data-field="statement-caveat">Paper/research-only review. Not filing-grade tax accounting.</p>
      </article>"""

    statement = _field(report, "statement", {})
    reconciled = bool(_field(report, "reconciled", False))
    tone = "good" if reconciled else "danger"
    return f"""
      <article class="panel statement-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Statement Review</p>
            <h2 data-field="statement-status">{"Reconciled" if reconciled else "Mismatch"}</h2>
          </div>
          <span class="chip {tone}" data-field="statement-chip">{"Clean" if reconciled else "Review"}</span>
        </div>
        <ul class="clean-list">
          <li><span>Statement</span><strong data-field="statement-id">{escape(_field(statement, "statement_id", "unknown"))}</strong></li>
          <li><span>Provider</span><strong data-field="statement-provider">{escape(_field(statement, "provider", "unknown"))}</strong></li>
          <li><span>Issues</span><strong data-field="statement-issues">{len(_field(report, "issues", ()))}</strong></li>
          <li><span>Report</span><strong data-field="statement-path">{escape(snapshot.statement_reconciliation_path or "not written")}</strong></li>
        </ul>
        <div class="event-list" data-statement-issue-list>
          <span class="label">Statement Issues</span>
          {_statement_issue_rows(report)}
        </div>
        <p class="microcopy" data-field="statement-caveat">Paper/research-only review. Not filing-grade tax accounting.</p>
      </article>"""


def _statement_issue_rows(report) -> str:
    issues = _field(report, "issues", ())
    if not issues:
        return '<p class="empty">No statement differences above tolerance.</p>'
    rows = []
    for issue in tuple(issues)[:4]:
        issue_type = _enum_value(_field(issue, "issue_type"), "statement_issue")
        rows.append(
            f"""
          <div class="event-row danger-border">
            <strong>{escape(_humanize_code(issue_type.lower()))}</strong>
            <span>{escape(_field(issue, "symbol", None) or "account")}</span>
            <small>{escape(_field(issue, "message", "Statement mismatch requires review."))}</small>
          </div>"""
        )
    return "\n".join(rows)


def _broker_connection_status(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    cycle = getattr(runtime, "last_cycle", None) if runtime else None
    if cycle is not None:
        return "connected" if getattr(cycle, "broker_synced", False) else "degraded"
    session = snapshot.session_state
    connection_status = getattr(session, "connection_status", None) if session else None
    return _enum_value(connection_status, "awaiting")


def _active_model_key(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    active_model_key = getattr(runtime, "active_model_key", None) if runtime else None
    if active_model_key:
        return active_model_key
    if snapshot.model_cards:
        card = snapshot.model_cards[0]
        return f"{card.strategy_id}:{card.version}"
    return "unassigned"


def _report_status_panel(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    daily_report_path = getattr(runtime, "daily_report_path", None) if runtime else None
    nightly = snapshot.nightly_learning
    learning_path = snapshot.nightly_learning_path
    active_model_unchanged = (
        nightly.active_model_unchanged if nightly is not None else True
    )
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Reports And Learning</p>
            <h2 data-field="report-status">{_report_heading(snapshot)}</h2>
          </div>
          <span class="chip {"good" if active_model_unchanged else "danger"}">Model locked</span>
        </div>
        <ul class="clean-list">
          <li><span>Daily report</span><strong data-field="daily-report-state">{escape("written" if daily_report_path else "snapshot")}</strong></li>
          <li><span>Report path</span><strong data-field="daily-report-path">{escape(daily_report_path or _report_metadata_path(snapshot) or "not written")}</strong></li>
          <li><span>Trading day</span><strong data-field="trading-day">{escape(snapshot.daily_report.trading_day.isoformat())}</strong></li>
          <li><span>Nightly learning</span><strong data-field="learning-state">{escape("complete" if nightly else "waiting")}</strong></li>
          <li><span>Learning memo</span><strong data-field="learning-memo-path">{escape(learning_path or "not written")}</strong></li>
          <li><span>Active mutation</span><strong data-field="active-mutation-state">{escape("blocked" if active_model_unchanged else "review")}</strong></li>
        </ul>
      </article>"""


def _audit_trail_panel(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.daily_report
    metadata = report.report_metadata
    evidence_sources = len(metadata.evidence_sources) if metadata else 0
    traced_orders = sum(1 for trade in report.trade_explanations if trade.ledger_trace)
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Audit Trail</p>
            <h2>{traced_orders} trace</h2>
          </div>
          <span class="chip info">{evidence_sources} sources</span>
        </div>
        <ul class="clean-list">
          <li><span>Fills traced</span><strong>{len(report.fill_report)}</strong></li>
          <li><span>Operator actions</span><strong>{len(report.operator_actions)}</strong></li>
          <li><span>Runtime events</span><strong>{len(report.runtime_events)}</strong></li>
          <li><span>Benchmark</span><strong>{_benchmark_status(report)}</strong></li>
        </ul>
      </article>"""


def _tax_estimate_panel(snapshot: OperatorDashboardSnapshot) -> str:
    tax = snapshot.daily_report.tax_report
    estimated_tax = (
        _money_text(tax.estimated_tax) if tax.tax_estimate_available else "unavailable"
    )
    tone = "good" if tax.tax_estimate_available else "warn"
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Accounting</p>
            <h2>Tax Estimate</h2>
          </div>
          <span class="chip {tone}" data-field="tax-estimate-state">{"available" if tax.tax_estimate_available else "estimate only"}</span>
        </div>
        <ul class="clean-list">
          <li><span>Active lots</span><strong data-field="tax-active-lots">{tax.active_lot_count}</strong></li>
          <li><span>Realized lots</span><strong data-field="tax-realized-lots">{tax.realized_lot_count}</strong></li>
          <li><span>Lot method</span><strong data-field="tax-lot-method">{escape(_enum_value(tax.lot_method, "fifo").upper())}</strong></li>
          <li><span>Short-term gains</span><strong data-field="tax-short-term-gains">{_money_text(tax.short_term_realized_gains)}</strong></li>
          <li><span>Long-term gains</span><strong data-field="tax-long-term-gains">{_money_text(tax.long_term_realized_gains)}</strong></li>
          <li><span>Total gains</span><strong data-field="tax-total-gains">{_money_text(tax.total_realized_gains)}</strong></li>
          <li><span>Estimated tax</span><strong data-field="tax-estimated-tax">{escape(estimated_tax)}</strong></li>
        </ul>
        <p class="microcopy">Research estimate only. Not filing-grade tax accounting.</p>
      </article>"""


def _live_readiness_panel(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.live_readiness
    if report is None:
        return ""
    checks = tuple(_field(report, "checks", ()) or ())
    passed = sum(1 for check in checks if _field(check, "passed", False))
    total = len(checks)
    status = _enum_value(_field(report, "status"), "unknown")
    limits = _field(report, "limits", {})
    max_order = _field(limits, "max_order_notional", 0)
    approved = tuple(_field(report, "approved_model_keys", ()) or ())
    return f"""
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Live Readiness</p>
            <h2 data-field="live-readiness-panel-status">{escape(status)}</h2>
          </div>
          <span class="chip warn">Live disabled</span>
        </div>
        <ul class="clean-list">
          <li><span>Checks passed</span><strong data-field="live-readiness-checks">{passed}/{total}</strong></li>
          <li><span>Max order</span><strong data-field="live-max-order">{_money_text(max_order)}</strong></li>
          <li><span>Approved models</span><strong data-field="live-approved-models">{len(approved)}</strong></li>
        </ul>
      </article>"""


def _position_rows(snapshot: OperatorDashboardSnapshot) -> str:
    positions = snapshot.paper_report.ledger_snapshot.positions
    if not positions:
        return '<p class="empty">No positions.</p>'
    return "\n".join(
        f"""
          <div class="table-row">
            <span>{escape(position.symbol)}</span>
            <strong>{position.quantity}</strong>
            <em>{_money_text(position.average_cost)}</em>
          </div>"""
        for position in positions
    )


def _fill_rows(snapshot: OperatorDashboardSnapshot) -> str:
    if not snapshot.recent_fills:
        return '<p class="empty">No fills.</p>'
    return "\n".join(
        f"""
          <div class="event-row">
            <strong>{escape(fill.symbol)} {escape(fill.side.value)}</strong>
            <span>{fill.quantity} @ {_money_text(fill.price)}</span>
            <small>{escape(fill.filled_at.isoformat())}</small>
          </div>"""
        for fill in snapshot.recent_fills
    )


def _rules(snapshot: OperatorDashboardSnapshot) -> str:
    rules = snapshot.daily_report.risk_report.rejection_rules
    if not rules:
        return "None"
    return ", ".join(rule.value for rule in rules)


def _equity_svg(snapshot: OperatorDashboardSnapshot) -> str:
    cash = float(snapshot.cash)
    equity = float(snapshot.estimated_equity)
    points = [cash, (cash + equity) / 2, equity, equity * 0.998, equity]
    return _sparkline(points, "#00e676", "Paper equity curve")


def _comparison_svg(snapshot: OperatorDashboardSnapshot) -> str:
    if snapshot.nightly_learning is None or not snapshot.nightly_learning.comparisons:
        return _sparkline([0, 0.1, 0.05, 0.12, 0.12], "#38d6ff", "Runtime status")
    comparison = snapshot.nightly_learning.comparisons[0]
    values = [comparison.champion_score, comparison.challenger_score]
    labels = ["Champion", "Challenger"]
    min_value = min(values)
    max_value = max(values)
    spread = max(max_value - min_value, 0.0001)
    bars = []
    for index, value in enumerate(values):
        height = 24 + ((value - min_value) / spread) * 70
        x = 30 + index * 120
        y = 118 - height
        bars.append(
            f"""
          <rect x="{x}" y="{y:.2f}" width="54" height="{height:.2f}" rx="4"></rect>
          <text x="{x + 27}" y="138" text-anchor="middle">{labels[index]}</text>"""
        )
    return f"""
        <svg viewBox="0 0 260 150" role="img" aria-label="Champion challenger score comparison">
          <rect class="chart-bg" x="0" y="0" width="260" height="150" rx="8"></rect>
          <g class="bar-chart">{"".join(bars)}</g>
        </svg>"""


def _learning_heading(snapshot: OperatorDashboardSnapshot) -> str:
    if snapshot.nightly_learning is None:
        return "Awaiting Nightly Run"
    return "Shadow Candidate Recommended"


def _learning_memo(snapshot: OperatorDashboardSnapshot) -> str:
    if snapshot.nightly_learning is None:
        return (
            "Nightly learning has not run yet for this always-on session. "
            "The active paper model remains locked."
        )
    return snapshot.nightly_learning.research_memo


def _learning_review_line(snapshot: OperatorDashboardSnapshot) -> str:
    nightly = snapshot.nightly_learning
    if nightly is None or not nightly.recommendations:
        return "AI copilot is waiting for evidence. It cannot trade or promote models."
    recommendation = nightly.recommendations[0]
    return (
        f"AI copilot confidence {recommendation.confidence:.2f}; "
        "manual review is required before any model authority changes."
    )


def _latest_prices(snapshot: OperatorDashboardSnapshot) -> dict:
    runtime = snapshot.runtime_state
    latest = getattr(runtime, "latest_prices", None) if runtime else None
    if latest is not None:
        records = [
            {
                "symbol": record.symbol,
                "price": _money_text(record.price),
                "status": record.status.value,
                "tone": "good" if record.status.value == "fresh" else "warn",
            }
            for record in latest.prices
        ]
        return {
            "status": latest.status.value,
            "feed": latest.feed.value,
            "warning": latest.warning or "Latest prices are available.",
            "records": records,
        }

    session = snapshot.session_state
    market_data = getattr(session, "market_data", None) if session else None
    if market_data is not None:
        records = [
            {
                "symbol": symbol,
                "price": _money_text(price),
                "status": market_data.status.value,
                "tone": "good" if market_data.status.value == "fresh" else "warn",
            }
            for symbol, price in sorted(market_data.prices.items())
        ]
        return {
            "status": market_data.status.value,
            "feed": market_data.feed.value,
            "warning": market_data.warning or "Latest prices are available.",
            "records": records,
        }

    return {
        "status": "missing",
        "feed": "unavailable",
        "warning": "Latest prices have not refreshed yet.",
        "records": [],
    }


def _report_heading(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    if runtime and getattr(runtime, "daily_report_path", None):
        return "Written"
    return "Snapshot"


def _report_metadata_path(snapshot: OperatorDashboardSnapshot) -> str | None:
    metadata = snapshot.daily_report.report_metadata
    return metadata.markdown_path if metadata else None


def _benchmark_status(report) -> str:
    benchmark = report.benchmark_report
    if benchmark is None:
        return "unavailable"
    return "available" if benchmark.comparison_available else "unavailable"


def _enum_value(value, fallback: str) -> str:
    return getattr(value, "value", value) if value is not None else fallback


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _join_values(values) -> str:
    rendered = [_enum_value(value, str(value)) for value in values or ()]
    return ", ".join(rendered) if rendered else "unavailable"


def _humanize_code(value) -> str:
    acronyms = {"iex", "sip", "us", "etf", "pnl"}
    parts = _enum_value(value, "quality_issue").split("_")
    return " ".join(
        part.upper() if part in acronyms else part.capitalize() for part in parts
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _sparkline(points: list[float], color: str, label: str) -> str:
    minimum = min(points)
    maximum = max(points)
    spread = max(maximum - minimum, 0.0001)
    width = 420
    height = 130
    coords = []
    for index, value in enumerate(points):
        x = (index / (len(points) - 1)) * width
        y = height - ((value - minimum) / spread) * (height - 22) - 11
        coords.append(f"{x:.2f},{y:.2f}")
    polyline = " ".join(coords)
    return f"""
        <svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">
          <rect class="chart-bg" x="0" y="0" width="{width}" height="{height}" rx="8"></rect>
          <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="4"></polyline>
          <circle cx="{coords[-1].split(",")[0]}" cy="{coords[-1].split(",")[1]}" r="5"></circle>
        </svg>"""


def _money_text(value) -> str:
    return f"${Decimal(str(value)):,.2f}"


def _health_tone(status: str) -> str:
    if status == "critical":
        return "danger"
    if status == "degraded":
        return "warn"
    if status == "watch":
        return "info"
    return "good"


def _interactive_script() -> str:
    return """
  <script>
    function money(value) {
      const number = Number(value || 0);
      return number.toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD'
      });
    }
    function escapeHtml(value) {
      const text = value === undefined || value === null ? '' : String(value);
      const replacements = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      };
      return text.replace(/[&<>"']/g, (char) => replacements[char]);
    }
    function setText(field, value) {
      document.querySelectorAll(`[data-field="${field}"]`).forEach((node) => {
        node.textContent = value === undefined || value === null ? '' : String(value);
      });
    }
    function setTone(field, baseClass, tone) {
      document.querySelectorAll(`[data-field="${field}"]`).forEach((node) => {
        node.className = `${baseClass} ${tone}`.trim();
      });
    }
    function setControlDisabled(action, disabled) {
      document.querySelectorAll(`[data-control-action="${action}"]`).forEach((node) => {
        node.disabled = disabled;
      });
    }
    function enumValue(value, fallback) {
      if (!value) {
        return fallback;
      }
      if (typeof value === 'object' && value.value) {
        return value.value;
      }
      return value;
    }
    function yesNo(value) {
      return value ? 'yes' : 'no';
    }
    function latestPriceData(snapshot) {
      const runtimeLatest = snapshot.runtime_state && snapshot.runtime_state.latest_prices;
      if (runtimeLatest) {
        return {
          status: enumValue(runtimeLatest.status, 'missing'),
          feed: enumValue(runtimeLatest.feed, 'unavailable'),
          warning: runtimeLatest.warning || 'Latest prices are available.',
          prices: runtimeLatest.prices || []
        };
      }
      const marketData = snapshot.session_state && snapshot.session_state.market_data;
      if (marketData) {
        return {
          status: enumValue(marketData.status, 'missing'),
          feed: enumValue(marketData.feed, 'unavailable'),
          warning: marketData.warning || 'Latest prices are available.',
          prices: Object.entries(marketData.prices || {}).map(([symbol, price]) => ({
            symbol,
            price,
            status: enumValue(marketData.status, 'fresh')
          }))
        };
      }
      return {
        status: 'missing',
        feed: 'unavailable',
        warning: 'Latest prices have not refreshed yet.',
        prices: []
      };
    }
    function renderLatestPrices(snapshot) {
      const target = document.querySelector('[data-latest-price-list]');
      const latest = latestPriceData(snapshot);
      setText('price-freshness', latest.status);
      setText('price-feed', latest.feed);
      setText('price-warning', latest.warning);
      if (!target) {
        return;
      }
      if (!latest.prices.length) {
        target.innerHTML = '<p class="empty">No latest prices available yet.</p>';
        return;
      }
      target.innerHTML = latest.prices.map((record) => {
        const status = enumValue(record.status, 'missing');
        const tone = status === 'fresh' ? 'good' : 'warn';
        return `
          <div class="price-pill ${tone}">
            <span>${escapeHtml(record.symbol)}</span>
            <strong>${money(record.price)}</strong>
            <small>${escapeHtml(status)}</small>
          </div>`;
      }).join('');
    }
    function dataQualityTone(status) {
      if (status === 'failed') {
        return 'danger';
      }
      if (status === 'warning' || status === 'unavailable') {
        return 'warn';
      }
      return 'good';
    }
    function joinValues(values) {
      const rendered = (values || []).map((value) => enumValue(value, value)).filter(Boolean);
      return rendered.length ? rendered.join(', ') : 'unavailable';
    }
    function humanizeCode(value) {
      const acronyms = new Set(['iex', 'sip', 'us', 'etf', 'pnl']);
      return enumValue(value, 'quality_issue').split('_').map((part) => (
        acronyms.has(part) ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)
      )).join(' ');
    }
    function dataQualityWindow(report) {
      if (!report) {
        return 'unavailable';
      }
      const provenance = report.provenance || {};
      if (provenance.start && provenance.end) {
        return `${provenance.start} to ${provenance.end}`;
      }
      return report.generated_at || 'unavailable';
    }
    function renderDataQuality(snapshot) {
      const dailyReport = snapshot.daily_report || {};
      const report = dailyReport.data_quality_report;
      const target = document.querySelector('[data-data-quality-issue-list]');
      if (!report) {
        setText('data-quality-status', 'unavailable');
        setText('data-quality-chip', 'unavailable');
        setTone('data-quality-chip', 'chip', 'warn');
        setText('data-quality-summary', 'No market-data quality report is attached to this dashboard snapshot.');
        setText('data-quality-research-usable', 'unknown');
        setText('data-quality-trading-usable', 'unknown');
        setText('data-quality-warnings', '-');
        setText('data-quality-failures', '-');
        setText('data-quality-dataset', 'unavailable');
        setText('data-quality-symbols', 'unavailable');
        setText('data-quality-sources', 'unavailable');
        setText('data-quality-feeds', 'unavailable');
        setText('data-quality-window', 'unavailable');
        if (target) {
          target.innerHTML = '<span class="label">Quality Issues</span><p class="empty">No quality report available.</p>';
        }
        return;
      }
      const status = enumValue(report.status, 'unavailable');
      const provenance = report.provenance || {};
      setText('data-quality-status', status);
      setText('data-quality-chip', status);
      setTone('data-quality-chip', 'chip', dataQualityTone(status));
      setText('data-quality-summary', report.summary || 'Market-data quality status is unavailable.');
      setText('data-quality-research-usable', yesNo(report.can_use_for_research));
      setText('data-quality-trading-usable', yesNo(report.can_use_for_trading));
      setText('data-quality-warnings', String(report.warnings || 0));
      setText('data-quality-failures', String(report.failures || 0));
      setText('data-quality-dataset', provenance.dataset_type || 'unavailable');
      setText('data-quality-symbols', (provenance.symbols || []).length ? `${provenance.symbols.length} tracked` : 'unavailable');
      setText('data-quality-sources', joinValues(provenance.sources));
      setText('data-quality-feeds', joinValues(provenance.feeds));
      setText('data-quality-window', dataQualityWindow(report));
      if (!target) {
        return;
      }
      const issues = report.issues || [];
      if (!issues.length) {
        target.innerHTML = '<span class="label">Quality Issues</span><p class="empty">No quality issues detected.</p>';
        return;
      }
      target.innerHTML = '<span class="label">Quality Issues</span>' + issues.slice(0, 4).map((issue) => {
        const issueStatus = enumValue(issue.status, 'warning');
        const tone = issueStatus === 'failed' ? 'danger-border' : 'warn-border';
        let subject = issue.symbol || 'dataset';
        if (issue.trading_date) {
          subject = `${subject} ${issue.trading_date}`;
        }
        return `
          <div class="event-row ${tone}">
            <strong>${escapeHtml(humanizeCode(issue.code))}</strong>
            <span>${escapeHtml(subject)}</span>
            <small>${escapeHtml(issue.message)}</small>
          </div>`;
      }).join('');
    }
    function renderAlerts(snapshot) {
      const alerts = snapshot.alerts || [];
      const target = document.querySelector('[data-alert-list]');
      const hasError = alerts.some((alert) => enumValue(alert.severity, '') === 'error');
      const tone = hasError ? 'danger' : alerts.length ? 'warn' : 'good';
      setText('alert-count', `${alerts.length} active`);
      setText('alert-tone', tone.toUpperCase());
      setTone('alert-tone', 'chip', tone);
      if (!target) {
        return;
      }
      if (!alerts.length) {
        target.innerHTML = '<p class="empty">No active alerts.</p>';
        return;
      }
      target.innerHTML = alerts.map((alert) => {
        const severity = enumValue(alert.severity, 'warning');
        const rowTone = severity === 'error' ? 'danger-border' : 'warn-border';
        const code = enumValue(alert.code, 'runtime_alert');
        const evidence = (alert.evidence || []).join(' / ');
        return `
          <div class="event-row ${rowTone}">
            <strong>${escapeHtml(alert.title)}</strong>
            <span>${escapeHtml(code)}</span>
            <small>${escapeHtml(alert.message)}</small>
            <small>${escapeHtml(evidence)}</small>
          </div>`;
      }).join('');
    }
    function renderPositions(snapshot) {
      const positions = (((snapshot.paper_report || {}).ledger_snapshot || {}).positions || []);
      const target = document.querySelector('[data-position-list]');
      setText('position-count', `${positions.length} open`);
      if (!target) {
        return;
      }
      if (!positions.length) {
        target.innerHTML = '<p class="empty">No positions.</p>';
        return;
      }
      target.innerHTML = positions.map((position) => `
          <div class="table-row">
            <span>${escapeHtml(position.symbol)}</span>
            <strong>${escapeHtml(position.quantity)}</strong>
            <em>${money(position.average_cost)}</em>
          </div>`).join('');
    }
    function renderFills(snapshot) {
      const fills = snapshot.recent_fills || [];
      const target = document.querySelector('[data-fill-list]');
      setText('fill-count', String(fills.length));
      if (!target) {
        return;
      }
      if (!fills.length) {
        target.innerHTML = '<p class="empty">No fills.</p>';
        return;
      }
      target.innerHTML = fills.map((fill) => {
        const side = enumValue(fill.side, 'UNKNOWN');
        return `
          <div class="event-row">
            <strong>${escapeHtml(fill.symbol)} ${escapeHtml(side)}</strong>
            <span>${escapeHtml(fill.quantity)} @ ${money(fill.price)}</span>
            <small>${escapeHtml(fill.filled_at)}</small>
          </div>`;
      }).join('');
    }
    function healthTone(status) {
      if (status === 'critical') {
        return 'danger';
      }
      if (status === 'degraded') {
        return 'warn';
      }
      if (status === 'watch') {
        return 'info';
      }
      return 'good';
    }
    function renderHealth(snapshot) {
      const health = snapshot.health_report;
      if (!health) {
        return;
      }
      const status = enumValue(health.status, 'unknown');
      setText('health-status', status);
      setText('health-incident-count', `${(health.incidents || []).length} incident`);
      setText('health-summary', health.summary || 'Runtime health is unavailable.');
      setText('health-report-path', `Incident review: ${snapshot.health_report_path || 'not written'}`);
      setTone('health-incident-count', 'chip', healthTone(status));
      const checksTarget = document.querySelector('[data-health-check-list]');
      if (checksTarget) {
        const checks = health.checks || [];
        checksTarget.innerHTML = '<span class="label">Health Checks</span>' + (
          checks.length ? checks.map((check) => `
          <div class="table-row">
            <span>${escapeHtml(check.name)}</span>
            <strong>${escapeHtml(enumValue(check.status, 'unknown'))}</strong>
            <em>${escapeHtml(check.message)}</em>
          </div>`).join('') : '<p class="empty">No health checks yet.</p>'
        );
      }
      const incidentTarget = document.querySelector('[data-incident-list]');
      if (incidentTarget) {
        const incidents = health.incidents || [];
        incidentTarget.innerHTML = '<span class="label">Incident Command</span>' + (
          incidents.length ? incidents.map((incident) => {
            const incidentStatus = enumValue(incident.status, 'watch');
            const tone = incidentStatus === 'critical' ? 'danger-border' : incidentStatus === 'degraded' ? 'warn-border' : '';
            return `
          <div class="event-row ${tone}">
            <strong>${escapeHtml(incident.title)}</strong>
            <span>${escapeHtml(incidentStatus)}</span>
            <small>${escapeHtml(incident.summary)}</small>
            <small>${escapeHtml(incident.suggested_action)}</small>
          </div>`;
          }).join('') : '<p class="empty">No open incidents.</p>'
        );
      }
    }
    function renderControls(snapshot) {
      const state = snapshot.control_state || {};
      const paused = Boolean(state.paused);
      const killSwitch = Boolean(snapshot.kill_switch_enabled || state.paper_kill_switch_enabled);
      setText('control-state-heading', paused ? 'Paused' : 'Armed');
      setText('paper-kill-switch-state', `Kill ${killSwitch ? 'ON' : 'OFF'}`);
      setTone('paper-kill-switch-state', 'chip', killSwitch ? 'danger' : 'good');
      document.querySelectorAll('[data-field="kill-switch"]').forEach((node) => {
        node.textContent = `Kill switch ${killSwitch ? 'ON' : 'OFF'}`;
        node.className = `status-pill ${killSwitch ? 'danger' : 'calm'}`;
      });
      const lastResult = snapshot.last_control_result || {};
      const request = lastResult.request || {};
      setText('last-control-action', enumValue(request.action, 'none'));
      setText('control-updated-by', state.updated_by || 'system');
      setText('control-updated-at', state.updated_at || 'pending');
      setControlDisabled('resume_runtime', !paused);
      setControlDisabled('pause_runtime', paused);
      setControlDisabled('disable_paper_kill_switch', !killSwitch);
      setControlDisabled('enable_paper_kill_switch', killSwitch);
      setControlDisabled('force_reconciliation', false);
      setControlDisabled('generate_report', false);
    }
    function renderReports(snapshot) {
      const runtime = snapshot.runtime_state || {};
      const dailyReport = snapshot.daily_report || {};
      const metadata = dailyReport.report_metadata || {};
      const dailyReportPath = runtime.daily_report_path || metadata.markdown_path || 'not written';
      const nightly = snapshot.nightly_learning;
      const learningPath = snapshot.nightly_learning_path || runtime.nightly_learning_path || 'not written';
      const activeModelUnchanged = !nightly || nightly.active_model_unchanged !== false;
      setText('report-status', dailyReportPath === 'not written' ? 'Snapshot' : 'Written');
      setText('daily-report-state', dailyReportPath === 'not written' ? 'snapshot' : 'written');
      setText('daily-report-path', dailyReportPath);
      setText('trading-day', dailyReport.trading_day || 'unknown');
      setText('learning-state', nightly ? 'complete' : 'waiting');
      setText('learning-memo-path', learningPath);
      setText('active-mutation-state', activeModelUnchanged ? 'blocked' : 'review');
    }
    function renderFinalAcceptance(snapshot) {
      const report = snapshot.final_acceptance;
      if (!report) {
        setText('final-acceptance-status', 'Awaiting Signoff');
        setText('final-acceptance-chip', 'Not final');
        setTone('final-acceptance-chip', 'chip', 'warn');
        setText('final-acceptance-accepted', 'no');
        setText('final-acceptance-checks', '0/0');
        setText('final-acceptance-signoff', 'missing');
        setText('final-acceptance-path', 'not written');
        setText('final-acceptance-summary', 'Run final acceptance after operator signoff and reviewed Alpaca Paper evidence.');
        return;
      }
      const accepted = Boolean(report.accepted_for_functional_paper_app);
      const checks = report.checks || [];
      const passed = checks.filter((check) => enumValue(check.status, 'failed') === 'passed').length;
      setText('final-acceptance-status', enumValue(report.status, 'unknown'));
      setText('final-acceptance-chip', accepted ? 'Accepted' : 'Blocked');
      setTone('final-acceptance-chip', 'chip', accepted ? 'good' : 'danger');
      setText('final-acceptance-accepted', accepted ? 'yes' : 'no');
      setText('final-acceptance-checks', `${passed}/${checks.length}`);
      setText('final-acceptance-signoff', report.signoff_path || 'missing');
      setText('final-acceptance-path', report.markdown_path || 'not written');
      setText('final-acceptance-summary', report.summary || 'Final acceptance evidence is available.');
    }
    function renderStatementReview(snapshot) {
      const report = snapshot.statement_reconciliation;
      const target = document.querySelector('[data-statement-issue-list]');
      if (!report) {
        setText('statement-status', 'Awaiting Statement');
        setText('statement-chip', 'Post-run');
        setTone('statement-chip', 'chip', 'warn');
        setText('statement-id', 'not loaded');
        setText('statement-provider', 'unknown');
        setText('statement-issues', 'unknown');
        setText('statement-path', 'not written');
        setText('statement-caveat', 'Paper/research-only review. Not filing-grade tax accounting.');
        if (target) {
          target.innerHTML = '<span class="label">Statement Issues</span><p class="empty">Run post-run statement reconciliation.</p>';
        }
        return;
      }
      const statement = report.statement || {};
      const issues = report.issues || [];
      const reconciled = Boolean(report.reconciled);
      setText('statement-status', reconciled ? 'Reconciled' : 'Mismatch');
      setText('statement-chip', reconciled ? 'Clean' : 'Review');
      setTone('statement-chip', 'chip', reconciled ? 'good' : 'danger');
      setText('statement-id', statement.statement_id || 'unknown');
      setText('statement-provider', statement.provider || 'unknown');
      setText('statement-issues', String(issues.length));
      setText('statement-path', snapshot.statement_reconciliation_path || 'not written');
      setText('statement-caveat', 'Paper/research-only review. Not filing-grade tax accounting.');
      if (!target) {
        return;
      }
      if (!issues.length) {
        target.innerHTML = '<span class="label">Statement Issues</span><p class="empty">No statement differences above tolerance.</p>';
        return;
      }
      target.innerHTML = '<span class="label">Statement Issues</span>' + issues.slice(0, 4).map((issue) => {
        const issueType = enumValue(issue.issue_type, 'statement_issue');
        return `
          <div class="event-row danger-border">
            <strong>${escapeHtml(humanizeCode(issueType.toLowerCase()))}</strong>
            <span>${escapeHtml(issue.symbol || 'account')}</span>
            <small>${escapeHtml(issue.message || 'Statement mismatch requires review.')}</small>
          </div>`;
      }).join('');
    }
    function renderLiveReadiness(snapshot) {
      const live = snapshot.live_readiness;
      if (!live) {
        setText('live-readiness-status', 'disabled');
        setText('live-readiness-panel-status', 'disabled');
        return;
      }
      const status = enumValue(live.status, 'blocked');
      const checks = live.checks || [];
      const passed = checks.filter((check) => check.passed).length;
      const limits = live.limits || {};
      setText('live-readiness-status', status);
      setText('live-readiness-panel-status', status);
      setText('live-readiness-checks', `${passed}/${checks.length}`);
      setText('live-max-order', money(limits.max_order_notional));
      setText('live-approved-models', String((live.approved_model_keys || []).length));
    }
    function renderRuntimeProof(snapshot) {
      const runtime = snapshot.runtime_state || {};
      const cycle = runtime.last_cycle || {};
      const session = snapshot.session_state || {};
      const modelCards = snapshot.model_cards || [];
      const fallbackModel = modelCards.length ? `${modelCards[0].strategy_id}:${modelCards[0].version}` : 'unassigned';
      let brokerConnection = 'awaiting';
      if (runtime.last_cycle) {
        brokerConnection = cycle.broker_synced ? 'connected' : 'degraded';
      } else if (session.connection_status) {
        brokerConnection = enumValue(session.connection_status, 'awaiting');
      }
      setText('runtime-status', enumValue(runtime.status, 'awaiting'));
      setText('prices-refreshed', yesNo(cycle.prices_refreshed));
      setText('broker-synced', yesNo(cycle.broker_synced));
      setText('broker-connection', brokerConnection);
      setText('active-model-key', runtime.active_model_key || fallbackModel);
      setText('trading-authority', 'Daily close only');
      setText('orders-submitted', String(cycle.orders_submitted || 0));
      setText('fills-applied', String(cycle.fills_applied || 0));
    }
    function renderPlainRows(target, label, values, emptyText) {
      if (!target) {
        return;
      }
      target.innerHTML = `<span class="label">${escapeHtml(label)}</span>` + (
        values.length ? values.map((value) => `
          <div class="event-row">
            <small>${escapeHtml(value)}</small>
          </div>`).join('') : `<p class="empty">${escapeHtml(emptyText)}</p>`
      );
    }
    function renderActiveStrategy(snapshot) {
      const definition = snapshot.active_strategy_definition;
      if (!definition) {
        return;
      }
      setText('active-strategy-name', definition.name);
      setText('active-strategy-authority', enumValue(definition.authority, 'paper'));
      setText('active-strategy-hypothesis', definition.hypothesis);
      setText('active-strategy-id', `${definition.strategy_id}:${definition.version}`);
      setText('active-strategy-cadence', enumValue(definition.trading_cadence, 'daily_close'));
      setText('active-strategy-benchmark', definition.benchmark);
      setText('active-strategy-universe', `${(definition.universe || []).length} U.S. ETF(s)`);
      setText('active-strategy-signal', definition.signal_logic);
      setText('active-strategy-sizing', definition.sizing_logic);
      setText('active-strategy-exit', definition.exit_logic);
      renderPlainRows(
        document.querySelector('[data-active-strategy-failure-list]'),
        'Known Failure Modes',
        (definition.failure_modes || []).slice(0, 3),
        'No failure modes recorded.'
      );
      renderPlainRows(
        document.querySelector('[data-active-strategy-ai-role-list]'),
        'AI Role',
        (definition.ai_role || []).slice(0, 3),
        'No AI role recorded.'
      );
    }
    function applySnapshot(snapshot) {
      setText('mode', snapshot.mode);
      setText('broker', snapshot.broker);
      setText('paper-boundary-mode', snapshot.mode);
      setText('estimated-equity', money(snapshot.estimated_equity));
      setText('cash', money(snapshot.cash));
      setText('realized-pnl', money(snapshot.realized_pnl));
      setText('open-orders', String(snapshot.open_orders));
      const reconciled = snapshot.paper_report && snapshot.paper_report.reconciliation && snapshot.paper_report.reconciliation.reconciled;
      setText('reconciliation', reconciled ? 'Reconciled' : 'Mismatch');
      const risk = snapshot.daily_report && snapshot.daily_report.risk_report;
      if (risk) {
        setText('risk-severity', enumValue(risk.severity, 'unknown'));
      }
      const completion = snapshot.completion_audit;
      if (completion) {
        setText('completion-status', enumValue(completion.status, 'unknown'));
        setText('completion-chip', completion.passed ? 'Ready' : 'Evidence');
        setText('completion-proven', String(completion.proven_count || 0));
        setText('completion-missing', String(completion.missing_count || 0));
        setText('completion-failed', String(completion.failed_count || 0));
        setText('completion-external', String(completion.external_required_count || 0));
        setText('completion-path', completion.markdown_path || 'not written');
        setText('completion-summary', completion.summary || 'Completion audit evidence is available.');
      }
      const tax = snapshot.daily_report && snapshot.daily_report.tax_report;
      if (tax) {
        setText('tax-active-lots', String(tax.active_lot_count || 0));
        setText('tax-realized-lots', String(tax.realized_lot_count || 0));
        setText('tax-lot-method', enumValue(tax.lot_method, 'fifo').toUpperCase());
        setText('tax-short-term-gains', money(tax.short_term_realized_gains));
        setText('tax-long-term-gains', money(tax.long_term_realized_gains));
        setText('tax-total-gains', money(tax.total_realized_gains));
        setText('tax-estimated-tax', tax.tax_estimate_available ? money(tax.estimated_tax) : 'unavailable');
        setText('tax-estimate-state', tax.tax_estimate_available ? 'available' : 'estimate only');
      }
      renderRuntimeProof(snapshot);
      renderActiveStrategy(snapshot);
      renderLatestPrices(snapshot);
      renderDataQuality(snapshot);
      renderAlerts(snapshot);
      renderPositions(snapshot);
      renderFills(snapshot);
      renderHealth(snapshot);
      renderControls(snapshot);
      renderReports(snapshot);
      renderFinalAcceptance(snapshot);
      renderStatementReview(snapshot);
      renderLiveReadiness(snapshot);
    }
    async function refreshDashboardSnapshot() {
      try {
        const response = await fetch('/api/snapshot', { cache: 'no-store' });
        if (!response.ok) {
          return;
        }
        const snapshot = await response.json();
        const generated = document.querySelector('[data-refresh-time]');
        if (generated) {
          generated.textContent = ` ${snapshot.generated_at}`;
        }
        applySnapshot(snapshot);
        document.documentElement.dataset.dashboardMode = snapshot.mode;
      } catch (_error) {
        document.documentElement.dataset.dashboardMode = 'refresh-error';
      }
    }
    async function sendOperatorControl(action) {
      const response = await fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          requested_by: 'local-dashboard',
          reason: 'dashboard control'
        })
      });
      if (response.ok) {
        window.location.reload();
      }
    }
    document.querySelectorAll('[data-control-action]').forEach((button) => {
      button.addEventListener('click', () => {
        sendOperatorControl(button.dataset.controlAction);
      });
    });
    refreshDashboardSnapshot();
    window.setInterval(refreshDashboardSnapshot, 5000);
  </script>"""


_CSS = """
:root {
  color-scheme: dark;
  --bg: #05070a;
  --surface: #0b1014;
  --surface-2: #10171d;
  --line: #23303a;
  --text: #ecf8f2;
  --muted: #8fa19a;
  --green: #00e676;
  --cyan: #38d6ff;
  --amber: #ffcf5a;
  --magenta: #ff4fd8;
  --red: #ff5d73;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
  color: var(--text);
  background:
    linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px),
    var(--bg);
  background-size: 34px 34px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 22px clamp(18px, 4vw, 48px);
  border-bottom: 1px solid var(--line);
  background: rgba(5, 7, 10, 0.92);
  position: sticky;
  top: 0;
  z-index: 5;
}

.eyebrow,
.label,
small,
.table-row span,
.event-row span {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: clamp(28px, 4vw, 48px);
  font-weight: 720;
}

h2 {
  font-size: clamp(20px, 2vw, 30px);
  font-weight: 700;
}

main {
  padding: 22px clamp(18px, 4vw, 48px) 40px;
}

.status-strip,
.metrics-grid,
.dashboard-grid,
.split-list,
.model-grid,
.model-explain-grid,
.learning-grid,
.health-grid,
.control-grid {
  display: grid;
  gap: 14px;
}

.status-strip {
  grid-template-columns: repeat(3, max-content);
}

.status-pill,
.chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--line);
  font-size: 12px;
  color: var(--text);
  background: var(--surface-2);
}

.paper,
.good {
  border-color: rgba(0, 230, 118, 0.7);
  color: var(--green);
}

.broker,
.info {
  border-color: rgba(56, 214, 255, 0.7);
  color: var(--cyan);
}

.warn {
  border-color: rgba(255, 207, 90, 0.75);
  color: var(--amber);
}

.danger {
  border-color: rgba(255, 93, 115, 0.8);
  color: var(--red);
}

.calm {
  border-color: rgba(0, 230, 118, 0.5);
  color: var(--green);
}

.metrics-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 16px;
}

.metric-card,
.panel,
.model-card {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(11, 16, 20, 0.94);
}

.metric-card {
  display: grid;
  min-height: 112px;
  padding: 16px;
  gap: 8px;
}

.metric-card strong {
  font-size: clamp(24px, 3vw, 36px);
}

.metric-card.good {
  box-shadow: inset 0 0 0 1px rgba(0, 230, 118, 0.14);
}

.metric-card.warn {
  box-shadow: inset 0 0 0 1px rgba(255, 207, 90, 0.18);
}

.metric-card.info {
  box-shadow: inset 0 0 0 1px rgba(56, 214, 255, 0.16);
}

.dashboard-grid {
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.8fr);
  align-items: start;
}

.panel {
  padding: 18px;
  min-height: 220px;
}

.wide-panel {
  grid-column: 1 / -1;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.equity-visual {
  min-height: 130px;
}

svg {
  width: 100%;
  height: auto;
  display: block;
}

.chart-bg {
  fill: #070b0e;
  stroke: #1f2b34;
}

circle {
  fill: var(--green);
}

.bar-chart rect {
  fill: var(--cyan);
}

.bar-chart rect + text,
.bar-chart text {
  fill: var(--muted);
  font-size: 12px;
}

.split-list {
  grid-template-columns: repeat(3, 1fr);
  margin-top: 14px;
}

.split-list div,
.table-row,
.event-row,
.memo {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-2);
}

.split-list div {
  display: grid;
  gap: 5px;
  padding: 12px;
}

.risk-meter {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  align-items: end;
  gap: 10px;
  height: 110px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #070b0e;
}

.risk-meter span {
  border-radius: 6px;
  background: #20313a;
}

.risk-meter .active {
  background: var(--amber);
}

.clean-list {
  list-style: none;
  padding: 0;
  margin: 14px 0 0;
  display: grid;
  gap: 10px;
}

.clean-list li,
.score-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
}

.clean-list strong,
.score-row b {
  color: var(--text);
  text-align: right;
}

.model-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.model-explain-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.active-model-panel .clean-list {
  align-self: start;
}

.active-model-panel .clean-list li {
  display: grid;
  grid-template-columns: minmax(92px, 0.35fr) minmax(0, 1fr);
}

.active-model-panel .clean-list strong {
  text-align: left;
}

.active-model-panel .event-row small {
  color: #c9d7d1;
  font-size: 13px;
  text-transform: none;
}

.data-quality-panel .event-row small {
  color: #c9d7d1;
  font-size: 13px;
  text-transform: none;
}

.model-card {
  min-height: 164px;
  padding: 16px;
  display: grid;
  gap: 10px;
}

.model-card strong {
  display: block;
  margin-top: 4px;
  font-size: 28px;
}

.model-card p,
.summary,
.memo {
  color: #c9d7d1;
  line-height: 1.55;
}

.mini-table,
.event-list {
  display: grid;
  gap: 10px;
}

.table-row,
.event-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
}

.event-row {
  grid-template-columns: 1fr 1fr;
}

.event-row small {
  grid-column: 1 / -1;
}

.warn-border {
  border-color: rgba(255, 207, 90, 0.7);
}

.danger-border {
  border-color: rgba(255, 93, 115, 0.78);
}

.control-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.control-button {
  min-height: 42px;
  border: 1px solid rgba(56, 214, 255, 0.45);
  border-radius: 8px;
  color: var(--text);
  background: #10171d;
  font: inherit;
  cursor: pointer;
}

.control-button:hover:not(:disabled) {
  border-color: var(--cyan);
  box-shadow: 0 0 0 1px rgba(56, 214, 255, 0.18);
}

.control-button:disabled {
  color: var(--muted);
  border-color: var(--line);
  cursor: not-allowed;
}

.learning-grid {
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.7fr);
}

.health-grid {
  grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr);
}

.memo {
  padding: 16px;
  min-height: 150px;
}

.boundary-panel {
  border-color: rgba(0, 230, 118, 0.35);
}

.price-tape {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.price-pill {
  min-height: 82px;
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-2);
}

.price-pill strong {
  font-size: 22px;
}

.price-pill.good {
  border-color: rgba(0, 230, 118, 0.45);
}

.price-pill.warn {
  border-color: rgba(255, 207, 90, 0.55);
}

.microcopy {
  margin-top: 12px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
}

.footer {
  padding: 22px clamp(18px, 4vw, 48px);
  color: var(--muted);
  border-top: 1px solid var(--line);
}

.empty {
  color: var(--muted);
}

@media (max-width: 900px) {
  .topbar,
  .panel-header {
    display: grid;
  }

  .status-strip,
  .metrics-grid,
    .dashboard-grid,
    .split-list,
    .model-grid,
    .model-explain-grid,
    .learning-grid,
    .health-grid,
    .control-grid,
    .price-tape {
    grid-template-columns: 1fr;
  }
}
"""
