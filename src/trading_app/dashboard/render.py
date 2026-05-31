"""Operator dashboard renderer.

This file is intentionally thin — it produces the shell HTML and composes
the six screens. The visual design system lives in ``styles.py``,
client behavior in ``script.py``, primitives in ``components.py``, and
each screen's layout in ``screens/<name>.py``.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from trading_app.dashboard import components as C
from trading_app.dashboard import glossary as _glossary
from trading_app.dashboard.models import OperatorDashboardSnapshot
from trading_app.dashboard.screens import (
    ai_review,
    home,
    learn,
    paper,
    research,
    risk,
    strategies,
)
from trading_app.dashboard.script import script as _client_script
from trading_app.dashboard.styles import stylesheet as _stylesheet


def render_dashboard_html(
    snapshot: OperatorDashboardSnapshot, *, interactive: bool = False
) -> str:
    """Render a self-contained operator dashboard HTML document.

    Single-page architecture: all six screens are rendered into the DOM and
    hash-routing swaps which is visible. This keeps every required
    data-field present on first paint, and avoids any server round-trip
    when the user navigates between surfaces.
    """

    generated_at = snapshot.generated_at.isoformat()
    body_script = _client_script() if interactive else ""

    screens = "".join(
        [
            home.render(snapshot),
            strategies.render(snapshot),
            paper.render(snapshot),
            risk.render(snapshot),
            research.render(snapshot),
            ai_review.render(snapshot),
            learn.render(snapshot),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trading Lab Operator Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">
  <style>
{_stylesheet()}
  </style>
</head>
<body>
  <div class="app">
    {C.left_rail(broker=snapshot.broker, kill_switch_armed=snapshot.kill_switch_enabled)}
    <div>
      {C.top_bar(mode=snapshot.mode, generated_at=generated_at)}
      <main class="viewport">
        {screens}
        <footer class="footer">
          Generated<span data-refresh-time> {escape(generated_at)}</span>. Paper mode only. No live-money actions are available from this dashboard.
        </footer>
      </main>
    </div>
  </div>
  {C.tour()}
  {C.whats_this_panel()}
  {C.command_palette()}
  {C.shortcuts_help()}
  <script id="cmd-index-data" type="application/json">{_command_index_json()}</script>
{body_script}
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


def _command_index_json() -> str:
    """Static search index for the ⌘K palette.

    Symbols/positions come from the snapshot at refresh time via JS; the
    static list here covers screens, glossary terms, and quick actions.
    """

    screens = [
        {"id": "home", "label": "Home", "sub": "Command Center"},
        {"id": "strategies", "label": "Models", "sub": "Active strategy + arena"},
        {"id": "paper", "label": "Paper Trading", "sub": "Positions · fills · taxes"},
        {"id": "risk", "label": "Risk", "sub": "Severity · exposures · kill switch"},
        {"id": "research", "label": "Research Lab", "sub": "Nightly learning · health"},
        {"id": "ai", "label": "AI Review", "sub": "Governance · readiness"},
        {"id": "learn", "label": "Learn", "sub": "Plain-language reference"},
    ]
    terms = [
        {
            "key": key,
            "term": term,
            "definition": definition,
            "topic_link": _glossary.deep_link_for(key, "#home")
            if hasattr(_glossary, "deep_link_for")
            else "#home",
        }
        for key, (term, definition) in _glossary.GLOSSARY.items()
    ]
    actions = [
        {"id": "toggle-vocab", "label": "Toggle Plain / Technical"},
        {"id": "start-tour", "label": "Take the dashboard tour"},
        {"id": "open-whats-this", "label": "Open What's-this for current screen"},
        {"id": "show-shortcuts", "label": "Show keyboard shortcuts"},
    ]
    return json.dumps(
        {"screens": screens, "terms": terms, "actions": actions},
        separators=(",", ":"),
    )
