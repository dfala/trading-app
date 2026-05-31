"""Reusable dashboard primitives.

These are the *only* components screens should compose with. No new card
shapes, no ad-hoc gradients. If a screen wants a new shape, add the
primitive here so all screens stay consistent.

Anatomy:

- ``surface(eyebrow, title, body, pill_html=...)`` — the only card.
- ``stat(label, value, detail, tone=...)`` — KPI tile.
- ``pill(text, tone=...)`` — single status badge.
- ``k_list(rows)`` — label/value key list.
- ``row_list(rows)`` — uniform 1-col/value rows for tables.
- ``mode_badge(mode)`` — paper-vs-live ever-present badge.
- ``confidence_dots(score)`` — 5-dot AI confidence indicator.
- ``area_chart(values, ...)`` — hero-scale equity area chart (SVG).
- ``sparkline(values, ...)`` — small inline trend line (SVG).
- ``bar_compare(left, right, ...)`` — champion vs challenger SVG.
- ``h_bar(label, value, max_value, ...)`` — horizontal exposure bar.
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

from trading_app.dashboard import glossary as _glossary


Tone = str  # "good" | "warn" | "danger" | "ai" | "ghost"


_TONE_TO_PILL = {
    "good": "pill--good",
    "warn": "pill--warn",
    "danger": "pill--danger",
    "ai": "pill--ai",
    "ghost": "pill--ghost",
}

_TONE_TO_STAT = {
    "good": "stat--pos",
    "pos": "stat--pos",
    "warn": "stat--warn",
    "danger": "stat--neg",
    "neg": "stat--neg",
    "ai": "stat--ai",
}


def surface(
    *,
    eyebrow: str,
    title: str,
    body_html: str,
    pill_html: str = "",
    foot_html: str = "",
    extra_class: str = "",
    extra_attrs: str = "",
) -> str:
    """Render the single card primitive. No nested surfaces allowed."""

    klass = f"surface {extra_class}".strip()
    # ``eyebrow`` accepts raw HTML so glossary() spans can be embedded.
    # Callers passing plain text don't need to escape — none of the labels
    # in this app contain HTML-sensitive characters.
    head = f"""
        <div class="surface__head">
          <div class="surface__title">
            <span class="eyebrow">{eyebrow}</span>
            <h2>{title}</h2>
          </div>
          {pill_html}
        </div>"""
    foot = f'<div class="surface__foot">{foot_html}</div>' if foot_html else ""
    return f"""
      <article class="{klass}" {extra_attrs}>
        {head}
        <div class="surface__body">
          {body_html}
        </div>
        {foot}
      </article>"""


def stat(
    *,
    label: str,
    value: str,
    detail: str = "",
    tone: Tone = "",
    value_attrs: str = "",
) -> str:
    """A single KPI tile in the stat row."""

    klass = f"stat {_TONE_TO_STAT.get(tone, '')}".strip()
    detail_html = f'<div class="stat__detail">{detail}</div>' if detail else ""
    # ``label`` accepts raw HTML so glossary() spans can be embedded.
    return f"""
      <div class="{klass}">
        <div class="stat__label">{label}</div>
        <div class="stat__value" {value_attrs}>{value}</div>
        {detail_html}
      </div>"""


def pill(text: str, tone: Tone = "ghost", *, attrs: str = "", armed: bool = False) -> str:
    """Single status badge. Maximum one per region."""

    klass_parts = ["pill", _TONE_TO_PILL.get(tone, "pill--ghost")]
    if armed:
        klass_parts.append("pill--armed")
    klass = " ".join(part for part in klass_parts if part)
    return f'<span class="{klass}" {attrs}>{escape(text)}</span>'


def mode_badge(mode: str) -> str:
    """The ever-present paper-vs-live badge. Sits in the top bar.

    A glossary ``?`` sits beside the badge so a beginner can find out what
    "paper trading" means without leaving the screen. The JS layer rewrites
    the badge's text on snapshot refresh; the sibling ``?`` survives.
    """

    is_paper = "paper" in mode.casefold()
    klass = "mode mode--paper" if is_paper else "mode mode--live"
    return (
        f'<span style="display: inline-flex; align-items: center; gap: 6px;">'
        f'<span class="{klass}" data-field="mode">{escape(mode)}</span>'
        f"{glossary_icon(key='paper_trading')}"
        f"</span>"
    )


def confidence_dots(score: float | None) -> str:
    """5-dot confidence indicator. Cyan for filled, faint for empty."""

    if score is None:
        filled = 0
    else:
        filled = max(0, min(5, round(float(score) * 5)))
    dots = "".join(
        f'<span class="{"on" if i < filled else ""}"></span>' for i in range(5)
    )
    return f'<span class="conf-dots" aria-label="confidence">{dots}</span>'


def k_list(rows: Iterable[tuple[str, str]], *, numeric: bool = False) -> str:
    """Label/value list. ``numeric=True`` switches the value to mono font."""

    parts = []
    for label, value in rows:
        num_attr = ' data-numeric="1"' if numeric else ""
        # Labels accept raw HTML so callers can embed glossary() spans.
        parts.append(
            f"""
        <div class="k-row">
          <span>{label}</span>
          <strong{num_attr}>{value}</strong>
        </div>"""
        )
    return f'<div class="k-list">{"".join(parts)}</div>'


def k_split(left: Iterable[tuple[str, str]], right: Iterable[tuple[str, str]]) -> str:
    """Two-column key list, used for dense model/data inspector panels."""

    return f"""
      <div class="k-split">
        {k_list(left)}
        {k_list(right)}
      </div>"""


def row_list(rows: Iterable[str], *, container_attrs: str = "") -> str:
    """Wrap a sequence of pre-rendered ``row(...)`` strings in a row-list."""

    inner = "".join(rows)
    return f'<div class="row-list" {container_attrs}>{inner}</div>'


def row(
    *,
    primary: str,
    primary_sub: str = "",
    meta: str = "",
    value: str = "",
    value_tone: str = "",
    tone: str = "",
) -> str:
    """A single row in a row-list. ``tone`` adds left-rail accent."""

    klass = f"row {('row--' + tone) if tone else ''}".strip()
    sub = f"<small>{primary_sub}</small>" if primary_sub else ""
    meta_html = f'<div class="row__meta">{meta}</div>' if meta else ""
    value_html = (
        f'<div class="row__value {value_tone}">{value}</div>' if value else ""
    )
    return f"""
      <div class="{klass}">
        <div class="row__primary">{primary}{sub}</div>
        {meta_html}
        {value_html}
      </div>"""


def empty(text: str) -> str:
    """Empty-state placeholder."""

    return f'<p class="empty">{escape(text)}</p>'


def microcopy(text: str, *, attrs: str = "") -> str:
    """Footnote-style text."""

    return f'<p class="microcopy" {attrs}>{escape(text)}</p>'


# ---------------------------------------------------------------------------
# Glossary — plain language with a ringed `?` tooltip
# ---------------------------------------------------------------------------


def glossary(
    text: str = "",
    *,
    key: str | None = None,
    definition: str | None = None,
    term: str | None = None,
) -> str:
    """Render ``text`` followed by a ringed ``?`` button that reveals a popover.

    The popover shows the *technical term* in cyan small caps over the *plain
    definition*. Two common patterns:

    - ``glossary("Where your money is", key="exposure")`` — the visible label is
      plain English; the technical term ("Exposure") appears in the tooltip.
    - ``glossary("Drawdown", key="drawdown")`` — the visible label is the
      technical term itself; the tooltip just defines it.

    If ``key`` is None, pass ``term`` and ``definition`` directly for one-off
    explanations.

    With ``text=""`` the helper renders a standalone ``?`` icon (used in places
    like the kill-switch pill where the label is owned by the JS layer).
    """

    if key:
        entry = _glossary.get(key)
        if entry is None:
            term_value, def_value = "", ""
        else:
            term_value, def_value = entry
    else:
        term_value = term or ""
        def_value = definition or ""

    if not def_value:
        return escape(text) if text else ""

    term_html = (
        f'<strong>{escape(term_value)}</strong>' if term_value else ""
    )
    def_html = f"<span>{escape(def_value)}</span>"
    aria_label = (
        f"What does {term_value or text} mean?".strip() if (term_value or text) else "Definition"
    )
    label_html = escape(text) if text else ""
    icon_class = "glossary__btn" if text else "glossary__btn glossary__btn--solo"

    return (
        f'<span class="glossary">'
        f"{label_html}"
        f'<button type="button" class="{icon_class}" '
        f'aria-label="{escape(aria_label)}" tabindex="0">?</button>'
        f'<span class="glossary__pop" role="tooltip">{term_html}{def_html}</span>'
        f"</span>"
    )


def glossary_icon(*, key: str | None = None, definition: str | None = None, term: str | None = None) -> str:
    """Standalone ``?`` icon — same popover, no visible label."""

    return glossary("", key=key, definition=definition, term=term)


# ---------------------------------------------------------------------------
# Charts (raw SVG, dependency-free)
# ---------------------------------------------------------------------------


def area_chart(
    values: list[float],
    *,
    width: int = 800,
    height: int = 280,
    label: str = "chart",
    positive: bool | None = None,
    series_id: str = "fill-pos",
) -> str:
    """A hero-scale area chart with gradient fill and a single line stroke.

    ``positive`` controls color: green if True, red if False, cyan if None.
    """

    if not values:
        return f'<svg class="area-chart" viewBox="0 0 {width} {height}" aria-label="{escape(label)}"></svg>'

    pad_l, pad_r, pad_t, pad_b = 16, 16, 14, 28
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b
    minimum = min(values)
    maximum = max(values)
    spread = max(maximum - minimum, 0.0001)
    points = []
    for index, value in enumerate(values):
        x = pad_l + (index / max(len(values) - 1, 1)) * inner_w
        y = pad_t + inner_h - ((value - minimum) / spread) * inner_h
        points.append((x, y))
    baseline_y = pad_t + inner_h

    line_path = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)
    area_path = (
        line_path
        + f" L {points[-1][0]:.2f} {baseline_y:.2f}"
        + f" L {points[0][0]:.2f} {baseline_y:.2f} Z"
    )

    if positive is True:
        line_class, fill_class, dot_class = "line-pos", "fill-pos", "end-dot"
        fill_id = "fill-pos"
        line_color, fill_color = "#2bd576", "#2bd576"
    elif positive is False:
        line_class, fill_class, dot_class = "line-neg", "fill-neg", "end-dot neg"
        fill_id = "fill-neg"
        line_color, fill_color = "#ff4d5e", "#ff4d5e"
    else:
        line_class, fill_class, dot_class = "line-ai", "fill-ai", "end-dot ai"
        fill_id = "fill-ai"
        line_color, fill_color = "#5ee3ff", "#5ee3ff"

    # Light grid lines, then area, then line
    grid_lines = "".join(
        f'<line class="grid-line" x1="{pad_l}" x2="{pad_l + inner_w}" '
        f'y1="{pad_t + inner_h * frac:.1f}" y2="{pad_t + inner_h * frac:.1f}" />'
        for frac in (0.25, 0.5, 0.75)
    )

    return f"""
        <svg class="area-chart" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" aria-label="{escape(label)}">
          <defs>
            <linearGradient id="{fill_id}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="{line_color}" stop-opacity="0.28" />
              <stop offset="100%" stop-color="{fill_color}" stop-opacity="0" />
            </linearGradient>
          </defs>
          {grid_lines}
          <path d="{area_path}" class="{fill_class}" />
          <path d="{line_path}" class="{line_class}" />
          <circle class="{dot_class}" cx="{points[-1][0]:.2f}" cy="{points[-1][1]:.2f}" r="3.5" />
        </svg>"""


def sparkline(values: list[float], *, positive: bool = True, label: str = "trend") -> str:
    """A tiny inline trend line used inside dense tables."""

    if not values:
        return f'<svg class="spark" viewBox="0 0 80 28" aria-label="{escape(label)}"></svg>'
    minimum = min(values)
    maximum = max(values)
    spread = max(maximum - minimum, 0.0001)
    pts = []
    for index, value in enumerate(values):
        x = (index / max(len(values) - 1, 1)) * 78 + 1
        y = 26 - ((value - minimum) / spread) * 24 - 1
        pts.append(f"{x:.1f},{y:.1f}")
    klass = "pos" if positive else "neg"
    path = "M " + " L ".join(pts)
    return f"""<svg class="spark" viewBox="0 0 80 28" role="img" aria-label="{escape(label)}"><path d="{path}" class="{klass}" /></svg>"""


def bar_compare(
    *,
    left_label: str,
    left_value: float,
    right_label: str,
    right_value: float,
    aria_label: str = "Champion challenger comparison",
) -> str:
    """Side-by-side bar comparison for champion vs challenger scoring."""

    values = [left_value, right_value]
    minimum = min(values)
    maximum = max(values)
    spread = max(maximum - minimum, 0.0001)
    bars = []
    for index, (label, value) in enumerate(
        ((left_label, left_value), (right_label, right_value))
    ):
        height = 30 + ((value - minimum) / spread) * 90
        x = 40 + index * 130
        y = 130 - height
        klass = "bar bar-champ" if index == 0 else "bar bar-chal"
        bars.append(
            f"""
          <rect class="{klass}" x="{x}" y="{y:.1f}" width="60" height="{height:.1f}" rx="3" />
          <text x="{x + 30}" y="148" text-anchor="middle">{escape(label)}</text>
          <text x="{x + 30}" y="{y - 6:.1f}" text-anchor="middle" fill="#f4f6f8">{value:.4f}</text>"""
        )
    return f"""
        <svg class="bar-compare" viewBox="0 0 290 160" role="img" aria-label="{escape(aria_label)}">
          <rect class="bg" x="0.5" y="0.5" width="289" height="159" rx="10" />
          {"".join(bars)}
        </svg>"""


def h_bar(label: str, value: float, max_value: float, *, tone: str = "") -> str:
    """A horizontal exposure bar — used by the Risk screen."""

    safe_max = max(max_value, 0.0001)
    pct = max(0.0, min(100.0, (value / safe_max) * 100.0))
    tone_class = f" {tone}" if tone else ""
    return f"""
      <div class="h-bar">
        <span>{escape(label)}</span>
        <div class="h-bar__track"><div class="h-bar__fill{tone_class}" style="width: {pct:.1f}%"></div></div>
        <span class="h-bar__amt">{value:,.0f}</span>
      </div>"""


# ---------------------------------------------------------------------------
# Top bar + left rail (shell)
# ---------------------------------------------------------------------------


_NAV = [
    ("home", "Home", "•"),
    ("strategies", "Models", "M"),
    ("paper", "Paper", "P"),
    ("risk", "Risk", "R"),
    ("research", "Research", "L"),
    ("ai", "AI Review", "AI"),
]


def left_rail(*, broker: str, kill_switch_armed: bool) -> str:
    """Persistent left rail navigation."""

    items = []
    for key, label, glyph in _NAV:
        items.append(
            f"""
          <button class="nav-item" data-screen-link="{key}" type="button">
            <span class="nav-item__icon">{escape(glyph)}</span>
            <span>{escape(label)}</span>
          </button>"""
        )
    kill_label = "Kill switch ARMED" if kill_switch_armed else "Kill switch OFF"
    kill_class = "pill pill--danger" if kill_switch_armed else "pill pill--good pill--armed"
    return f"""
      <aside class="rail" aria-label="Primary navigation">
        <div>
          <div class="rail__brand">
            <span class="rail__mark">TL</span>
            <span class="rail__brand-text">
              <strong>Trading Lab</strong>
              <small>Paper Cockpit</small>
            </span>
          </div>
          <nav class="rail__nav">
            {"".join(items)}
          </nav>
        </div>
        <div></div>
        <div class="rail__foot">
          <strong data-field="broker">{escape(broker)}</strong>
          <span style="display: inline-flex; align-items: center; gap: 6px;">
            <span data-field="kill-switch" class="{kill_class}">{kill_label}</span>
            {glossary_icon(key='kill_switch')}
          </span>
        </div>
      </aside>"""


def top_bar(*, mode: str, generated_at: str) -> str:
    """Sticky top bar with mode badge, generated time, paper-mode microcopy."""

    return f"""
      <header class="topbar">
        <div class="topbar__title">
          <small>Operator Dashboard</small>
          <span data-screen-title
            data-title_home="Command Center"
            data-title_strategies="Models"
            data-title_paper="Paper Trading"
            data-title_risk="Risk"
            data-title_research="Research Lab"
            data-title_ai="AI Review">Command Center</span>
        </div>
        <div class="topbar__strip">
          {mode_badge(mode)}
          <span class="topbar__time"><span data-refresh-time> {escape(generated_at)}</span></span>
        </div>
      </header>"""
