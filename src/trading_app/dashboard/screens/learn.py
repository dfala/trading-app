"""Learn screen — the dashboard's own glossary index.

A focused, scannable reference organized by topic. Each entry shows the
technical term, a plain-language definition, and a small deep-link to
where the concept appears in the app. The content is sourced from
``glossary.py`` so definitions stay single-sourced across tooltips and
this page.

Tone follows DESIGN_VISION: calm, two sentences max per entry, no
marketing. Robinhood Learn is the reference for cadence — a beginner
should be able to scan a topic in under a minute without leaving the
dashboard.
"""

from __future__ import annotations

from html import escape

from trading_app.dashboard import components as C
from trading_app.dashboard import glossary as G
from trading_app.dashboard.models import OperatorDashboardSnapshot


# Screen-name labels for the small "Where to see this" tail.
_SCREEN_LABELS: dict[str, str] = {
    "#home": "Home",
    "#strategies": "Models",
    "#paper": "Paper Trading",
    "#risk": "Risk",
    "#research": "Research Lab",
    "#ai": "AI Review",
}


def render(snapshot: OperatorDashboardSnapshot) -> str:
    """Render the Learn surface."""

    head = _head()
    index = _topic_index()
    sections = "".join(_topic_surface(key) for key in G.TOPICS)
    footer = C.microcopy(
        "Definitions are also available as ? tooltips next to any technical "
        "term in the app. Plain / Technical switches the label; the meaning "
        "is unchanged."
    )

    return f"""
    <section class="screen" data-screen="learn" hidden>
      {head}
      {index}
      {sections}
      {footer}
    </section>"""


# ---------------------------------------------------------------------------
# Head
# ---------------------------------------------------------------------------


def _head() -> str:
    return """
      <div class="screen__head">
        <div>
          <span class="eyebrow">Learn</span>
          <h1>How to read this dashboard.</h1>
          <p>A plain-language reference for every technical term in the app. Pick a topic — each entry links to the screen where you'll see it in use.</p>
        </div>
      </div>"""


# ---------------------------------------------------------------------------
# Topic index — small chip strip anchoring to each section
# ---------------------------------------------------------------------------


def _topic_index() -> str:
    chips = []
    for key, (heading, _blurb, _link, _terms) in G.TOPICS.items():
        chips.append(
            f'<a class="pill pill--ghost" href="#learn-{escape(key)}" '
            f'style="text-decoration: none;">{escape(heading)}</a>'
        )
    return (
        '<nav aria-label="Topic index" '
        'style="display: flex; flex-wrap: wrap; gap: 8px;">'
        + "".join(chips)
        + "</nav>"
    )


# ---------------------------------------------------------------------------
# Per-topic surface
# ---------------------------------------------------------------------------


def _topic_surface(topic_key: str) -> str:
    heading, blurb, default_link, term_keys = G.TOPICS[topic_key]

    rows = []
    for term_key in term_keys:
        entry = G.get(term_key)
        if entry is None:
            continue
        term, definition = entry
        deep_link = G.deep_link_for(term_key, default_link)
        rows.append(_term_row(term, definition, deep_link))

    body = (
        f'<p class="surface__summary">{escape(blurb)}</p>'
        f'{C.row_list(rows) if rows else C.empty("No terms in this topic yet.")}'
    )

    # The surface lives inside a wrapper that carries the in-page anchor.
    # We do this with a thin span (not a nested surface) so the design rule
    # against card-in-card stays intact.
    anchor = f'<span id="learn-{escape(topic_key)}"></span>'
    return anchor + C.surface(
        eyebrow=heading,
        title="Terms you'll see in this topic.",
        body_html=body,
        pill_html=_topic_pill(default_link),
    )


def _topic_pill(default_link: str) -> str:
    """Show a single ghost pill pointing to the topic's primary screen."""

    label = _SCREEN_LABELS.get(default_link, "Dashboard")
    # An anchor styled to look like a pill — keeps the design system happy
    # without introducing a new top-level class.
    return (
        f'<a class="pill pill--ghost" href="{escape(default_link)}" '
        f'style="text-decoration: none;">See on {escape(label)} →</a>'
    )


def _term_row(term: str, definition: str, deep_link: str) -> str:
    """One row: mono term on the left, plain definition, deep-link tail."""

    label = _SCREEN_LABELS.get(deep_link, "Dashboard")
    primary = (
        f'<span class="mono" style="font-size: 13px; color: var(--fg);">'
        f"{escape(term)}</span>"
    )
    meta = (
        f'<a href="{escape(deep_link)}" '
        f'style="color: var(--ai); text-decoration: none; font-size: 12px;">'
        f"See on {escape(label)} →</a>"
    )
    return C.row(
        primary=primary,
        primary_sub=escape(definition),
        meta=meta,
    )
