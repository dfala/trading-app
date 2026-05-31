"""AI Review screen — the AI governance ledger.

This surface is not a marketing page for the copilot. It is a quiet
regulator's record: what the AI reviewed, what evidence it relied on,
what it recommended, and — most importantly — every place a human still
has to approve. The hero is calm, not loud: a single posture line, a
confidence strip, and the daily memo. Below it, four compliance-style
records (functional readiness, final acceptance, reports and learning,
live readiness). Cyan is reserved for AI affordances. The "Live"
section is amber, not green, because we are explicitly *not* live-ready.
"""

from __future__ import annotations

from html import escape

from trading_app.dashboard import components as C
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.screens import _helpers as H


def render(snapshot: OperatorDashboardSnapshot) -> str:
    return f"""
    <section class="screen" data-screen="ai" hidden>
      {_hero(snapshot)}
      {_daily_memo(snapshot)}

      <div class="grid-2">
        {_completion_audit(snapshot)}
        {_final_acceptance(snapshot)}
      </div>

      <div class="grid-2">
        {_reports_and_learning(snapshot)}
        {_live_readiness(snapshot)}
      </div>

      {C.microcopy(
          "AI cannot trade, promote models, or change risk limits. "
          "Every change requires human approval."
      )}
    </section>"""


# ---------------------------------------------------------------------------
# Hero — the governance posture line
# ---------------------------------------------------------------------------


def _hero(snapshot: OperatorDashboardSnapshot) -> str:
    """A calm posture line. No big numbers, no celebration."""

    nightly = snapshot.nightly_learning
    if nightly is not None and nightly.active_model_unchanged:
        headline = "Copilot active · operator-approved"
    else:
        headline = "Pending operator review"

    if nightly is not None and nightly.recommendations:
        confidence = nightly.recommendations[0].confidence
    else:
        confidence = None
    dots = C.confidence_dots(confidence)
    confidence_text = f"{confidence:.2f}" if confidence is not None else "—"

    return f"""
      <div class="screen__head" aria-label="AI Governance posture">
        <div>
          <span class="eyebrow">AI Governance</span>
          <h1>{escape(headline)}</h1>
          <p>
            {dots}
            <span class="ai-c mono">&nbsp;{confidence_text}</span>
            &nbsp;·&nbsp;
            The copilot explains, summarizes, and recommends. Nothing here is autonomous.
          </p>
        </div>
      </div>"""


# ---------------------------------------------------------------------------
# Daily memo — the centerpiece
# ---------------------------------------------------------------------------


def _daily_memo(snapshot: OperatorDashboardSnapshot) -> str:
    nightly = snapshot.nightly_learning
    if nightly is not None:
        memo_text = escape(nightly.research_memo)
    else:
        memo_text = (
            "Nightly learning has not produced a memo for this trading day yet."
        )

    body = f"""
      <div class="memo">
        {memo_text}
        <small>Reviewed by operator · paper authority only · no autonomous changes</small>
      </div>"""
    return C.surface(
        eyebrow="AI Daily Memo",
        title="Reviewed, paper-only",
        body_html=body,
        pill_html=C.pill("REVIEWED", tone="ai"),
    )


# ---------------------------------------------------------------------------
# Functional Readiness (completion_audit)
# ---------------------------------------------------------------------------


def _completion_audit(snapshot: OperatorDashboardSnapshot) -> str:
    audit = snapshot.completion_audit
    if audit is None:
        body = f"""
          {C.k_list([
              ("Proven", '<span data-field="completion-proven" class="mono">0</span>'),
              ("Missing", '<span data-field="completion-missing">unknown</span>'),
              ("Failed", '<span data-field="completion-failed">unknown</span>'),
              ("External proof", '<span data-field="completion-external">required</span>'),
              ("Report path", '<span data-field="completion-path">not written</span>'),
          ])}
          <p class="microcopy" data-field="completion-summary">Run the functional completion audit after validation and soak evidence exists.</p>
        """
        return C.surface(
            eyebrow="Functional Readiness",
            title='<span data-field="completion-status">Awaiting Audit</span>',
            body_html=body,
            pill_html='<span class="pill pill--warn" data-field="completion-chip">Review</span>',
        )

    status = H.enum_value(H.field(audit, "status"), "unknown")
    passed = bool(H.field(audit, "passed", False))
    failed = int(H.field(audit, "failed_count", 0) or 0)
    tone = "good" if passed else "danger" if failed else "warn"
    chip_text = "Ready" if passed else "Evidence"
    summary = H.field(audit, "summary", "Completion audit evidence is available.")
    path = H.field(audit, "markdown_path", None) or "not written"

    body = f"""
      {C.k_list([
          ("Proven", f'<span data-field="completion-proven" class="mono">{H.field(audit, "proven_count", 0)}</span>'),
          ("Missing", f'<span data-field="completion-missing" class="mono">{H.field(audit, "missing_count", 0)}</span>'),
          ("Failed", f'<span data-field="completion-failed" class="mono">{H.field(audit, "failed_count", 0)}</span>'),
          ("External proof", f'<span data-field="completion-external" class="mono">{H.field(audit, "external_required_count", 0)}</span>'),
          ("Report path", f'<span data-field="completion-path">{escape(path)}</span>'),
      ])}
      <p class="microcopy" data-field="completion-summary">{escape(summary)}</p>
    """
    return C.surface(
        eyebrow="Functional Readiness",
        title=f'<span data-field="completion-status">{escape(status)}</span>',
        body_html=body,
        pill_html=f'<span class="pill pill--{tone}" data-field="completion-chip">{chip_text}</span>',
    )


# ---------------------------------------------------------------------------
# Final Acceptance
# ---------------------------------------------------------------------------


def _final_acceptance(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.final_acceptance
    if report is None:
        body = f"""
          {C.k_list([
              ("Accepted", '<span data-field="final-acceptance-accepted">no</span>'),
              ("Checks", '<span data-field="final-acceptance-checks" class="mono">0/0</span>'),
              ("Signoff", '<span data-field="final-acceptance-signoff">missing</span>'),
              ("Report path", '<span data-field="final-acceptance-path">not written</span>'),
          ])}
          <p class="microcopy" data-field="final-acceptance-summary">Run final acceptance after operator signoff and reviewed Alpaca Paper evidence.</p>
        """
        return C.surface(
            eyebrow="Final Acceptance",
            title='<span data-field="final-acceptance-status">Awaiting Signoff</span>',
            body_html=body,
            pill_html='<span class="pill pill--warn" data-field="final-acceptance-chip">Not final</span>',
        )

    status = H.enum_value(H.field(report, "status"), "unknown")
    accepted = bool(H.field(report, "accepted_for_functional_paper_app", False))
    checks = tuple(H.field(report, "checks", ()) or ())
    passed_checks = sum(
        1 for check in checks if H.enum_value(H.field(check, "status"), "") == "passed"
    )
    tone = "good" if accepted else "danger"
    chip_text = "Accepted" if accepted else "Blocked"
    summary = H.field(report, "summary", "Final acceptance evidence is available.")
    signoff = H.field(report, "signoff_path", None) or "missing"
    path = H.field(report, "markdown_path", None) or "not written"

    body = f"""
      {C.k_list([
          ("Accepted", f'<span data-field="final-acceptance-accepted">{H.yes_no(accepted)}</span>'),
          ("Checks", f'<span data-field="final-acceptance-checks" class="mono">{passed_checks}/{len(checks)}</span>'),
          ("Signoff", f'<span data-field="final-acceptance-signoff">{escape(signoff)}</span>'),
          ("Report path", f'<span data-field="final-acceptance-path">{escape(path)}</span>'),
      ])}
      <p class="microcopy" data-field="final-acceptance-summary">{escape(summary)}</p>
    """
    return C.surface(
        eyebrow="Final Acceptance",
        title=f'<span data-field="final-acceptance-status">{escape(status)}</span>',
        body_html=body,
        pill_html=f'<span class="pill pill--{tone}" data-field="final-acceptance-chip">{chip_text}</span>',
    )


# ---------------------------------------------------------------------------
# Reports & Learning
# ---------------------------------------------------------------------------


def _reports_and_learning(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    daily_report_path = getattr(runtime, "daily_report_path", None) if runtime else None
    resolved_path = (
        daily_report_path or H.report_metadata_path(snapshot) or "not written"
    )
    nightly = snapshot.nightly_learning
    learning_path = snapshot.nightly_learning_path
    active_model_unchanged = (
        nightly.active_model_unchanged if nightly is not None else True
    )

    body = C.k_list(
        [
            (
                "Daily report",
                f'<span data-field="daily-report-state">{escape("written" if daily_report_path else "snapshot")}</span>',
            ),
            (
                "Report path",
                f'<span data-field="daily-report-path">{escape(resolved_path)}</span>',
            ),
            (
                "Trading day",
                f'<span data-field="trading-day" class="mono">{escape(snapshot.daily_report.trading_day.isoformat())}</span>',
            ),
            (
                "Nightly learning",
                f'<span data-field="learning-state">{escape("complete" if nightly else "waiting")}</span>',
            ),
            (
                "Learning memo",
                f'<span data-field="learning-memo-path">{escape(learning_path or "not written")}</span>',
            ),
            (
                "Active mutation",
                f'<span data-field="active-mutation-state">{escape("blocked" if active_model_unchanged else "review")}</span>',
            ),
        ]
    )
    return C.surface(
        eyebrow="Reports And Learning",
        title=f'<span data-field="report-status">{H.report_heading(snapshot)}</span>',
        body_html=body,
        pill_html=C.pill(
            "Model locked" if active_model_unchanged else "Mutation pending",
            tone="ai" if active_model_unchanged else "warn",
        ),
    )


# ---------------------------------------------------------------------------
# Live Readiness — amber, never green
# ---------------------------------------------------------------------------


def _live_readiness(snapshot: OperatorDashboardSnapshot) -> str:
    report = snapshot.live_readiness
    if report is None:
        body = C.k_list(
            [
                (
                    "Checks passed",
                    '<span data-field="live-readiness-checks" class="mono">0/0</span>',
                ),
                ("Max order", '<span data-field="live-max-order">unavailable</span>'),
                (
                    "Approved models",
                    '<span data-field="live-approved-models" class="mono">0</span>',
                ),
            ]
        )
        return C.surface(
            eyebrow="Live Readiness",
            title='<span data-field="live-readiness-panel-status">disabled</span>',
            body_html=body,
            pill_html=C.pill("Live disabled", tone="warn"),
            foot_html=(
                "Live trading is intentionally off. The copilot has no path to "
                "enable it."
            ),
        )

    checks = tuple(H.field(report, "checks", ()) or ())
    passed = sum(1 for check in checks if H.field(check, "passed", False))
    status = H.enum_value(H.field(report, "status"), "unknown")
    limits = H.field(report, "limits", {})
    max_order = H.field(limits, "max_order_notional", 0)
    approved = tuple(H.field(report, "approved_model_keys", ()) or ())

    body = C.k_list(
        [
            (
                "Checks passed",
                f'<span data-field="live-readiness-checks" class="mono">{passed}/{len(checks)}</span>',
            ),
            (
                "Max order",
                f'<span data-field="live-max-order" class="mono">{H.money(max_order)}</span>',
            ),
            (
                "Approved models",
                f'<span data-field="live-approved-models" class="mono">{len(approved)}</span>',
            ),
        ]
    )
    return C.surface(
        eyebrow="Live Readiness",
        title=f'<span data-field="live-readiness-panel-status">{escape(status)}</span>',
        body_html=body,
        pill_html=C.pill("Live disabled", tone="warn"),
        foot_html=(
            "Live trading is intentionally off. The copilot has no path to "
            "enable it."
        ),
    )
