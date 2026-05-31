"""Models screen — the model inspector.

This surface answers the question every trader asks of a system that is
about to commit capital on their behalf: *what is the model thinking,
how do we know, and what could go wrong?*

The hero is the active model's thesis statement — its hypothesis given
room to breathe. Below it, a four-up stat row prints the scannable
identity card (score, cadence, universe, benchmark). Then the Model
Arena: champion versus challenger as a single bar comparison — the
honest answer to "is this model still the best one we have?". Below
that, a three-column logic strip walks the lifecycle (Signal · Sizing ·
Exit) so a reviewer can audit *how* the model decides without reading
code. Finally, two paired lists hold the parts of the system we choose
not to hide: known failure modes and the AI copilot's role.
"""

from __future__ import annotations

from html import escape

from trading_app.dashboard import components as C
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.screens import _helpers as H


def render(snapshot: OperatorDashboardSnapshot) -> str:
    return f"""
    <section class="screen" data-screen="strategies" hidden>
      <div class="screen__head">
        <div>
          <span class="eyebrow">Your strategies</span>
          <h1>What's trading on your behalf — and why.</h1>
          <p>Every trade can be traced back to the strategy that fired it, the data it used, and whether the safety system let it through.</p>
        </div>
      </div>

      {_active_strategy_hero(snapshot)}
      {_stat_row(snapshot)}
      {_model_arena(snapshot)}
      {_logic_strip(snapshot)}
      {_failure_and_ai(snapshot)}
    </section>"""


# ---------------------------------------------------------------------------
# Hero — the active model's thesis
# ---------------------------------------------------------------------------


def _active_strategy_hero(snapshot: OperatorDashboardSnapshot) -> str:
    definition = snapshot.active_strategy_definition
    if definition is None:
        return C.surface(
            eyebrow="Active Model",
            title="No active strategy assigned",
            body_html=C.empty("Assign a strategy to begin paper trading."),
        )

    authority = H.enum_value(definition.authority, "paper")
    cadence = H.enum_value(definition.trading_cadence, "daily_close")
    model_key = f"{escape(definition.strategy_id)}:{escape(definition.version)}"

    body = f"""
      <div class="hero__lead">
        <span class="hero__label">{C.glossary("Hypothesis", key="hypothesis")}</span>
        <p class="surface__summary" data-field="active-strategy-hypothesis">{escape(definition.hypothesis)}</p>
      </div>
      <div class="k-list">
        <div class="k-row">
          <span>Strategy ID</span>
          <strong data-numeric="1"><span data-field="active-strategy-id" class="mono">{model_key}</span></strong>
        </div>
        <div class="k-row">
          <span>{C.glossary("Cadence", key="cadence")}</span>
          <strong><span data-field="active-strategy-cadence">{escape(cadence)}</span></strong>
        </div>
      </div>"""

    return C.surface(
        eyebrow=C.glossary("Active Model", key="active_model"),
        title=f'<span data-field="active-strategy-name">{escape(definition.name)}</span>',
        body_html=body,
        pill_html=f'<span class="pill pill--ai" data-field="active-strategy-authority">{escape(authority)}</span>',
    )


# ---------------------------------------------------------------------------
# Stat row — model identity card
# ---------------------------------------------------------------------------


def _stat_row(snapshot: OperatorDashboardSnapshot) -> str:
    definition = snapshot.active_strategy_definition
    if definition is None:
        return ""

    score_value, score_tone = _champion_score(snapshot)
    cadence = H.enum_value(definition.trading_cadence, "daily_close")
    universe_count = len(definition.universe)

    stats = [
        C.stat(
            label=C.glossary("Score", key="score"),
            value=f'<span class="mono">{score_value}</span>',
            detail="Higher is better",
            tone=score_tone,
        ),
        C.stat(
            label=C.glossary("Cadence", key="cadence"),
            value=f'<span class="mono">{escape(cadence)}</span>',
            detail=f"Holds positions for {escape(definition.holding_period)}",
        ),
        C.stat(
            label=C.glossary("Universe", key="universe"),
            value=(
                f'<span data-field="active-strategy-universe" class="mono">'
                f"{universe_count} U.S. ETFs</span>"
            ),
            detail="What it can pick from",
            tone="ai",
        ),
        C.stat(
            label=C.glossary("Benchmark", key="benchmark"),
            value=(
                f'<span data-field="active-strategy-benchmark" class="mono">'
                f"{escape(definition.benchmark)}</span>"
            ),
            detail="Returns compared to this index",
        ),
    ]
    return f'<section class="stat-row" aria-label="Active model metrics">{"".join(stats)}</section>'


def _champion_score(snapshot: OperatorDashboardSnapshot) -> tuple[str, str]:
    """Pull the champion's score out of the arena snapshot, if available."""

    arena = snapshot.model_arena
    comparisons = getattr(arena, "comparisons", ()) if arena else ()
    if comparisons:
        score = float(comparisons[0].champion_score)
        tone = "pos" if score >= 0 else "neg"
        return f"{score:.4f}", tone
    # Fall back to first model card
    if snapshot.model_cards:
        score = float(snapshot.model_cards[0].score)
        tone = "pos" if score >= 0 else "neg"
        return f"{score:.4f}", tone
    return "—", ""


# ---------------------------------------------------------------------------
# Model Arena — champion vs challenger
# ---------------------------------------------------------------------------


def _model_arena(snapshot: OperatorDashboardSnapshot) -> str:
    arena = snapshot.model_arena
    comparisons = getattr(arena, "comparisons", ()) if arena else ()

    if comparisons:
        comparison = comparisons[0]
        champ = comparison.champion
        chal = comparison.challenger
        champ_score = float(comparison.champion_score)
        chal_score = float(comparison.challenger_score)
        delta = float(comparison.score_delta)
        delta_tone = "pos" if delta >= 0 else "neg"
        delta_sign = "+" if delta >= 0 else "−"
        recommendation = H.enum_value(comparison.recommendation, "hold")
        rationale = comparison.rationale

        chart = C.bar_compare(
            left_label="Champion",
            left_value=champ_score,
            right_label="Challenger",
            right_value=chal_score,
            aria_label="Champion versus challenger score comparison",
        )

        body = f"""
          {chart}
          {C.k_split(
              [
                  ("Champion", f'<span class="mono">{escape(champ.strategy_id)}:{escape(champ.version)}</span>'),
                  ("Champion score", f'<span class="mono ai-c">{champ_score:.4f}</span>'),
                  ("State", f'<span>{escape(H.enum_value(champ.state, "paper"))}</span>'),
              ],
              [
                  ("Challenger", f'<span class="mono">{escape(chal.strategy_id)}:{escape(chal.version)}</span>'),
                  ("Challenger score", f'<span class="mono pos">{chal_score:.4f}</span>'),
                  ("State", f'<span>{escape(H.enum_value(chal.state, "validated"))}</span>'),
              ],
          )}
          <div class="k-row">
            <span>Score delta</span>
            <strong data-numeric="1"><span class="mono {delta_tone}">{delta_sign}{abs(delta):.4f}</span></strong>
          </div>
          <p class="surface__summary">{escape(rationale)}</p>
          {C.microcopy("Promotion requires manual approval. Challenger remains in research authority until reviewed.")}"""

        return C.surface(
            eyebrow=C.glossary("Model Arena", key="model_arena"),
            title=C.glossary("Champion / Challenger", key="champion_challenger"),
            body_html=body,
            pill_html=C.pill(f"recommend · {recommendation}", tone="ai"),
        )

    # Fallback: two surfaces side-by-side from model_cards
    cards_html = []
    for card in snapshot.model_cards[:2]:
        is_champion = card.label.lower() == "champion"
        tone = "good" if is_champion else "ai"
        score_tone = "pos" if float(card.score) >= 0 else "neg"
        cards_html.append(
            C.surface(
                eyebrow=card.label,
                title=f'<span class="mono">{escape(card.strategy_id)}:{escape(card.version)}</span>',
                body_html=f"""
                  <p class="surface__summary">{escape(card.detail)}</p>
                  {C.k_list([
                      ("Score", f'<span class="mono {score_tone}">{float(card.score):.4f}</span>'),
                      ("State", escape(card.state)),
                  ])}
                """,
                pill_html=C.pill(card.state.upper(), tone=tone),
            )
        )
    body = f'<div class="grid-2">{"".join(cards_html)}</div>' if cards_html else C.empty(
        "No arena comparisons recorded."
    )
    return C.surface(
        eyebrow="Model Arena",
        title="Champion / Challenger",
        body_html=body,
        pill_html=C.pill("active model locked", tone="ai"),
    )


# ---------------------------------------------------------------------------
# Signal / Sizing / Exit — lifecycle logic strip
# ---------------------------------------------------------------------------


def _logic_strip(snapshot: OperatorDashboardSnapshot) -> str:
    definition = snapshot.active_strategy_definition
    if definition is None:
        return ""

    cells = (
        C.surface(
            eyebrow=C.glossary("Signal", key="signal_logic"),
            title="How it picks what to buy",
            body_html=(
                f'<p class="surface__summary" data-field="active-strategy-signal">'
                f"{escape(definition.signal_logic)}</p>"
            ),
        ),
        C.surface(
            eyebrow=C.glossary("Sizing", key="sizing_logic"),
            title="How much it buys",
            body_html=(
                f'<p class="surface__summary" data-field="active-strategy-sizing">'
                f"{escape(definition.sizing_logic)}</p>"
            ),
        ),
        C.surface(
            eyebrow=C.glossary("Exit", key="exit_logic"),
            title="When it sells",
            body_html=(
                f'<p class="surface__summary" data-field="active-strategy-exit">'
                f"{escape(definition.exit_logic)}</p>"
            ),
        ),
    )
    return f'<div class="grid-3" aria-label="Trade lifecycle logic">{"".join(cells)}</div>'


# ---------------------------------------------------------------------------
# Known failure modes + AI role
# ---------------------------------------------------------------------------


def _failure_and_ai(snapshot: OperatorDashboardSnapshot) -> str:
    definition = snapshot.active_strategy_definition
    if definition is None:
        return ""

    failure_modes = tuple(definition.failure_modes[:3])
    ai_roles = tuple(definition.ai_role[:3])

    failures = C.surface(
        eyebrow=C.glossary("Known Failure Modes", key="failure_modes"),
        title="When this strategy misses",
        body_html=_honest_rows(
            failure_modes,
            empty="No failure modes recorded.",
            attrs="data-active-strategy-failure-list",
            tone="warn",
        ),
        pill_html=C.pill(f"{len(failure_modes)} documented", tone="warn"),
    )
    ai = C.surface(
        eyebrow=C.glossary("AI Role", key="ai_role"),
        title="What the copilot helps with",
        body_html=_honest_rows(
            ai_roles,
            empty="No AI role recorded.",
            attrs="data-active-strategy-ai-role-list",
            tone="ai",
        ),
        pill_html=C.pill("advisory only", tone="ai"),
    )
    return f'<div class="grid-2">{failures}{ai}</div>'


def _honest_rows(
    values: tuple[str, ...],
    *,
    empty: str,
    attrs: str,
    tone: str = "",
) -> str:
    """Render a row-list of plain string entries with a quiet tone rail."""

    if not values:
        return f'<div class="row-list" {attrs}>{C.empty(empty)}</div>'
    rendered = "".join(
        C.row(primary=f"<small>{escape(value)}</small>", tone=tone)
        for value in values
    )
    return f'<div class="row-list" {attrs}>{rendered}</div>'
