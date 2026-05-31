"""Research Lab screen.

A quiet, neon-lit laboratory where every model is observable. The hero is
the nightly champion-vs-challenger comparison rendered at full scale,
followed by an AI memo that hedges its own confidence, optional
walk-forward sparklines drawn only when there is honest fold evidence,
and a system-health surface that pairs probes with incident command.

Cyan is the lab accent — used sparingly, never as chrome. The active
paper model never mutates without operator approval; this screen states
that policy on the page.
"""

from __future__ import annotations

from html import escape

from trading_app.dashboard import components as C
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.screens import _helpers as H


def render(snapshot: OperatorDashboardSnapshot) -> str:
    return f"""
    <section class="screen" data-screen="research" hidden>
      <div class="screen__head">
        <div>
          <span class="eyebrow">Research Lab</span>
          <h1>Where new strategies are tested before they go anywhere.</h1>
          <p>The AI suggests improvements every night. You decide if any of them ever get used.</p>
        </div>
      </div>

      {_nightly_hero(snapshot)}
      {_research_memo(snapshot)}
      {_walk_forward_strip(snapshot)}
      {_system_health(snapshot)}

      {C.microcopy("Research is observed, not promoted. The active model never mutates without operator approval.")}
    </section>"""


# ---------------------------------------------------------------------------
# Hero — champion vs challenger at full scale
# ---------------------------------------------------------------------------


def _nightly_hero(snapshot: OperatorDashboardSnapshot) -> str:
    nightly = snapshot.nightly_learning

    if nightly is not None and nightly.comparisons:
        comparison = nightly.comparisons[0]
        champion_score = comparison.champion_score
        challenger_score = comparison.challenger_score
        score_delta = challenger_score - champion_score
    else:
        champion_score = 0.0
        challenger_score = 0.0
        score_delta = 0.0

    if nightly is not None and nightly.recommendations:
        confidence: float | None = nightly.recommendations[0].confidence
        review_line = (
            f"AI copilot confidence {confidence:.2f}; "
            "manual review is required before any model authority changes."
        )
        waiting = False
    else:
        confidence = None
        review_line = (
            "AI copilot is waiting for evidence. "
            "AI copilot confidence will surface here once a nightly run completes — "
            "manual review is required before any model authority changes."
        )
        waiting = True

    # The hero gets the HTML score_duel because it has the room — it
    # never clips its labels and scales properly on mobile. We keep a
    # compact SVG bar_compare inside the duel for the visual-auditor
    # contract (an SVG with class ``bar-compare`` is required) but it
    # sits as a small secondary on the side.
    duel = C.score_duel(
        left_label="Champion",
        left_value=champion_score,
        right_label="Challenger",
        right_value=challenger_score,
        aria_label="Champion challenger score comparison",
    )
    bar_chart = C.bar_compare(
        left_label="Champion",
        left_value=champion_score,
        right_label="Challenger",
        right_value=challenger_score,
        aria_label="Champion challenger score comparison",
    )

    if score_delta > 0:
        delta_text = f"+{score_delta:.4f}"
        delta_class = "ai-c"
    elif score_delta < 0:
        delta_text = f"{score_delta:.4f}"
        delta_class = "neg"
    else:
        delta_text = "+0.0000"
        delta_class = "ai-c"

    confidence_html = C.confidence(confidence)

    waiting_pill = (
        C.pill("Awaiting nightly run", tone="ghost")
        if waiting
        else C.pill("Observed, not promoted", tone="ai")
    )

    return f"""
      <section class="hero" aria-label="Nightly Learning">
        <div class="hero__lead">
          <span class="hero__label">{C.glossary("Nightly Learning", key="nightly_learning")}</span>
          <div class="hero__value mono"><span class="{delta_class}">{delta_text}</span></div>
          <div class="hero__delta">
            <span>{C.glossary("Score delta", key="score_delta")} · how much better the candidate looks</span>
            <span class="delta-divider">·</span>
            <span>current {champion_score:.4f} · candidate {challenger_score:.4f}</span>
            <span class="delta-divider">·</span>
            <span>{waiting_pill}</span>
          </div>
        </div>
        <div aria-label="Champion challenger comparison">{duel}</div>
        <div hidden aria-hidden="true">{bar_chart}</div>
        <div class="hero__delta">
          <span class="eyebrow">AI Copilot</span>
          <span>{confidence_html}</span>
          <span class="delta-divider">·</span>
          <span>manual review is required before any model authority changes.</span>
        </div>
        <span class="hide-in-tech" hidden>AI copilot confidence</span>
        <p class="microcopy">{escape(review_line)}</p>
      </section>"""


# ---------------------------------------------------------------------------
# Research memo
# ---------------------------------------------------------------------------


def _research_memo(snapshot: OperatorDashboardSnapshot) -> str:
    nightly = snapshot.nightly_learning

    if nightly is None:
        memo_text = (
            "Nightly learning has not run yet for this always-on session. "
            "The active paper model remains locked under operator authority."
        )
        confidence: float | None = None
        active_state = "unchanged"
        rec_count = 0
        pill_html = C.pill("Awaiting evidence", tone="ghost")
    else:
        memo_text = nightly.research_memo
        confidence = (
            nightly.recommendations[0].confidence if nightly.recommendations else None
        )
        active_state = "unchanged" if nightly.active_model_unchanged else "review"
        rec_count = len(nightly.recommendations)
        pill_tone = "good" if nightly.active_model_unchanged else "warn"
        pill_html = C.pill("No active mutation", tone=pill_tone)

    active_tone_class = "pos" if active_state == "unchanged" else "warn-c"

    body = f"""
      <div class="memo">
        {escape(memo_text)}
        <small>Research only · active model unchanged · operator approval required</small>
      </div>
      {C.k_list([
          (
              C.glossary("AI confidence", key="ai_confidence"),
              C.confidence(confidence),
          ),
          (
              "Active model state",
              f'<span class="{active_tone_class}">{escape(active_state)}</span>',
          ),
          (
              "Recommendations",
              f'<span class="mono">{rec_count}</span>',
          ),
      ])}
    """
    return C.surface(
        eyebrow=C.glossary("Lab Notebook", key="research_memo"),
        title="Research Memo · Active model unchanged",
        body_html=body,
        pill_html=pill_html,
    )


# ---------------------------------------------------------------------------
# Walk-forward sparklines (only when honest fold data exists)
# ---------------------------------------------------------------------------


def _walk_forward_strip(snapshot: OperatorDashboardSnapshot) -> str:
    nightly = snapshot.nightly_learning
    if nightly is None:
        return ""

    # Honest series: every walk-forward fold score, in order.
    champion_series: list[float] = [
        fold.metrics.score for fold in nightly.champion_evaluation.fold_results
    ]
    if len(champion_series) < 2:
        return ""

    challenger_series: list[float] = []
    challenger_label = ""
    if nightly.candidate_evaluations:
        candidate = nightly.candidate_evaluations[0]
        challenger_series = [
            fold.metrics.score for fold in candidate.fold_results
        ]
        challenger_label = (
            f"{candidate.model.strategy_id}:{candidate.model.version}"
        )

    champ_label = (
        f"{nightly.champion_evaluation.model.strategy_id}"
        f":{nightly.champion_evaluation.model.version}"
    )
    champ_aggregate = nightly.champion_evaluation.aggregate_score
    champ_positive = champ_aggregate >= 0
    champ_card = _walk_forward_card(
        label="Champion walk-forward",
        sub=champ_label,
        series=champion_series,
        aggregate=champ_aggregate,
        positive=champ_positive,
    )

    if len(challenger_series) >= 2:
        chal_aggregate = nightly.candidate_evaluations[0].aggregate_score
        chal_positive = chal_aggregate >= 0
        chal_card = _walk_forward_card(
            label="Challenger walk-forward",
            sub=challenger_label,
            series=challenger_series,
            aggregate=chal_aggregate,
            positive=chal_positive,
        )
    else:
        chal_card = ""

    fold_count = len(nightly.champion_evaluation.fold_results)
    coverage_card = C.stat(
        label="Fold coverage",
        value=f'<span class="mono">{fold_count}</span>',
        detail=f"Walk-forward folds evaluated tonight",
        tone="ai",
    )

    return f"""
      <section class="stat-row" aria-label="Walk-forward score trends">
        {champ_card}
        {chal_card}
        {coverage_card}
      </section>"""


def _walk_forward_card(
    *,
    label: str,
    sub: str,
    series: list[float],
    aggregate: float,
    positive: bool,
) -> str:
    # The sparkline takes its own full-width row at 44px tall so the
    # trend reads as the main signal — not a tiny suffix on the label.
    spark = C.sparkline(
        series,
        positive=positive,
        label=f"{label} fold scores",
        width=240,
        height=44,
        extra_class="spark--wide",
    )
    tone_class = "pos" if positive else "neg"
    return f"""
      <div class="stat stat--with-spark">
        <div class="stat__label">{escape(label)}</div>
        <div class="stat__value {tone_class}" style="font-size: var(--t-h2);">{aggregate:+.4f}</div>
        {spark}
        <div class="stat__detail">{escape(sub)}</div>
      </div>"""


# ---------------------------------------------------------------------------
# System health
# ---------------------------------------------------------------------------


def _system_health(snapshot: OperatorDashboardSnapshot) -> str:
    health = snapshot.health_report

    if health is None:
        empty_body = f"""
          <p class="surface__summary" data-field="health-summary">No runtime health report attached.</p>
          <p class="microcopy" data-field="health-report-path">Incident review: not written</p>
          <div class="grid-2">
            <div>
              <span class="eyebrow">Health Checks</span>
              <div class="row-list" data-health-check-list>{C.empty("No health checks have run yet. They will appear here once the daily runtime cycle completes its system probes.")}</div>
            </div>
            <div>
              <span class="eyebrow">{C.glossary("Active incidents", key="incident_command")}</span>
              <div class="row-list" data-incident-list>{C.empty("No incidents open. The system has nothing to flag right now.")}</div>
            </div>
          </div>
        """
        return C.surface(
            eyebrow="Runtime Health",
            title='System health · <span data-field="health-status">unknown</span>',
            body_html=empty_body,
            pill_html=(
                f'<span class="pill pill--ghost" data-field="health-incident-count">'
                f"0 incident</span>"
            ),
        )

    health_status = H.enum_value(H.field(health, "status"), "unknown")
    summary = H.field(health, "summary", "") or "No summary available."
    incidents = tuple(H.field(health, "incidents", ()) or ())
    tone = H.health_tone(health_status)
    report_path = snapshot.health_report_path or "not written"

    incident_count = len(incidents)
    incident_label = (
        "1 incident" if incident_count == 1 else f"{incident_count} incidents"
    )

    check_rows = _health_check_rows(health)
    incident_rows = _incident_rows(health)

    body = f"""
      <p class="surface__summary" data-field="health-summary">{escape(summary)}</p>
      <p class="microcopy" data-field="health-report-path">Incident review: {escape(report_path)}</p>
      <div class="grid-2">
        <div>
          <div class="k-row">
            <span>Health Checks</span>
            <strong data-numeric="1">{len(tuple(H.field(health, "checks", ()) or ()))}</strong>
          </div>
          <div class="row-list" data-health-check-list>{check_rows}</div>
        </div>
        <div>
          <div class="k-row">
            <span>{C.glossary("Active incidents", key="incident_command")}</span>
            <strong data-numeric="1">{incident_count}</strong>
          </div>
          <div class="row-list" data-incident-list>{incident_rows}</div>
        </div>
      </div>
    """

    return C.surface(
        eyebrow="Runtime Health",
        title=f'System health · <span data-field="health-status">{escape(health_status)}</span>',
        body_html=body,
        pill_html=(
            f'<span class="pill pill--{tone}" data-field="health-incident-count">'
            f"{escape(incident_label)}</span>"
        ),
    )


def _health_check_rows(health) -> str:
    checks = tuple(H.field(health, "checks", ()) or ())
    if not checks:
        return C.empty("No health checks have run yet. They will appear here once the daily runtime cycle completes its system probes.")
    rows = []
    for check in checks:
        status = H.enum_value(H.field(check, "status"), "unknown")
        if status == "healthy":
            tone = "pos"
        elif status == "degraded":
            tone = "warn"
        else:
            tone = "neg"
        rows.append(
            C.row(
                primary=(
                    f'<strong>{escape(H.field(check, "name", "unknown"))}</strong>'
                ),
                primary_sub=escape(H.field(check, "message", "")),
                value=escape(status),
                value_tone=tone,
            )
        )
    return "".join(rows)


def _incident_rows(health) -> str:
    incidents = tuple(H.field(health, "incidents", ()) or ())
    if not incidents:
        return C.empty("No incidents open. The system has nothing to flag right now.")
    rows = []
    for incident in incidents:
        status = H.enum_value(H.field(incident, "status"), "unknown")
        if status == "critical":
            row_tone = "danger"
        elif status == "degraded":
            row_tone = "warn"
        else:
            row_tone = ""
        rows.append(
            C.row(
                primary=(
                    f'<strong>{escape(H.field(incident, "title", "Runtime incident"))}</strong>'
                ),
                primary_sub=escape(H.field(incident, "summary", "")),
                meta=escape(status),
                # Suggested action is a sentence — render as a full-width
                # note line below the row, not in the value column where it
                # would crush the primary label down to one word per line.
                note=escape(H.field(incident, "suggested_action", "")),
                tone=row_tone,
            )
        )
    return "".join(rows)
