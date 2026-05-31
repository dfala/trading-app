"""Shared helpers for screen modules.

These are small, pure functions that adapt the snapshot model into the
strings/values the components need. They were extracted from the legacy
``render.py`` so screen modules can stay focused on layout.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from trading_app.dashboard.models import OperatorDashboardSnapshot


def money(value) -> str:
    """Format a Decimal/float-ish value as USD."""

    return f"${Decimal(str(value)):,.2f}"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def enum_value(value, fallback: str) -> str:
    """Read ``.value`` off enums; fall through for plain values."""

    return getattr(value, "value", value) if value is not None else fallback


def field(value, name: str, default=None):
    """Read a nested field from either an object or a dict."""

    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def join_values(values) -> str:
    rendered = [enum_value(value, str(value)) for value in values or ()]
    return ", ".join(rendered) if rendered else "unavailable"


def humanize_code(value) -> str:
    acronyms = {"iex", "sip", "us", "etf", "pnl"}
    parts = enum_value(value, "quality_issue").split("_")
    return " ".join(
        part.upper() if part in acronyms else part.capitalize() for part in parts
    )


def safe(value) -> str:
    """HTML-escape an arbitrary value to text."""

    return escape("" if value is None else str(value))


# ---------------------------------------------------------------------------
# Cross-screen derivations
# ---------------------------------------------------------------------------


def broker_connection_status(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    cycle = getattr(runtime, "last_cycle", None) if runtime else None
    if cycle is not None:
        return "connected" if getattr(cycle, "broker_synced", False) else "degraded"
    session = snapshot.session_state
    connection_status = (
        getattr(session, "connection_status", None) if session else None
    )
    return enum_value(connection_status, "awaiting")


def active_model_key(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    key = getattr(runtime, "active_model_key", None) if runtime else None
    if key:
        return key
    if snapshot.model_cards:
        card = snapshot.model_cards[0]
        return f"{card.strategy_id}:{card.version}"
    return "unassigned"


def latest_prices(snapshot: OperatorDashboardSnapshot) -> dict:
    """Adapt either runtime.latest_prices or session.market_data into one shape."""

    runtime = snapshot.runtime_state
    latest = getattr(runtime, "latest_prices", None) if runtime else None
    if latest is not None:
        records = [
            {
                "symbol": record.symbol,
                "price": money(record.price),
                "status": record.status.value,
                "tone": "pos" if record.status.value == "fresh" else "warn",
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
                "price": money(price),
                "status": market_data.status.value,
                "tone": "pos" if market_data.status.value == "fresh" else "warn",
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


def health_tone(status: str) -> str:
    if status == "critical":
        return "danger"
    if status == "degraded":
        return "warn"
    if status == "watch":
        return "ai"
    return "good"


def status_tone(status: str) -> str:
    normalized = status.casefold()
    if normalized in {"blocked", "stopped", "critical", "failed"}:
        return "danger"
    if normalized in {"degraded", "warning", "standing by", "awaiting"}:
        return "warn"
    return "good"


def benchmark_status(report) -> str:
    benchmark = report.benchmark_report
    if benchmark is None:
        return "unavailable"
    return "available" if benchmark.comparison_available else "unavailable"


def report_metadata_path(snapshot: OperatorDashboardSnapshot) -> str | None:
    metadata = snapshot.daily_report.report_metadata
    return metadata.markdown_path if metadata else None


def report_heading(snapshot: OperatorDashboardSnapshot) -> str:
    runtime = snapshot.runtime_state
    if runtime and getattr(runtime, "daily_report_path", None):
        return "Written"
    return "Snapshot"


def hero_equity_series(snapshot: OperatorDashboardSnapshot) -> list[float]:
    """A small synthetic series for the initial server render of the hero chart.

    The browser side replaces this on first snapshot fetch with the same shape
    but the client-side renderer; we still need a server-side fallback for
    no-JS smoke tests and for ``write_dashboard``.
    """

    cash = float(snapshot.cash)
    equity = float(snapshot.estimated_equity)
    return [cash, (cash + equity) / 2.0, equity, equity * 0.997, equity]


def hero_delta(snapshot: OperatorDashboardSnapshot) -> tuple[float, float, bool]:
    """Return (absolute_delta, pct, positive?) versus paper baseline (cash)."""

    base = float(snapshot.cash)
    equity = float(snapshot.estimated_equity)
    delta = equity - base
    pct = (delta / base) * 100.0 if base else 0.0
    return delta, pct, delta >= 0
