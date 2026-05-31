"""Glossary registry — every technical term, in plain language.

This file is the single source of truth for what the app's jargon means.
Both the design system (``components.py``) and the screen modules read
from here, so changing a definition propagates everywhere.

The pattern: a visible plain-language label appears in the UI, and a
small ``(?)`` button reveals a popover with the **technical term** and a
1–2 sentence definition. The popover content is what a finance beginner
needs in order to understand what they're looking at without leaving
the screen.

Tone rules:

- Speak to the user in plain English. Avoid "the system does X" — say
  "we do X" when it's the app, "you do X" when it's the operator.
- Two sentences is the ceiling. If you can't say it in two, the
  concept is bigger than a tooltip — link it to a Learn page instead.
- Never use a jargon term inside a definition without explaining it.
- No marketing. No exclamation points. No emojis.
"""

from __future__ import annotations


# key -> (technical term, plain-language definition)
GLOSSARY: dict[str, tuple[str, str]] = {
    # ---------- Mode / boundary ----------
    "paper_trading": (
        "Paper Trading",
        "Fake money only. Every dollar you see here is simulated; no real "
        "account is touched.",
    ),
    "paper_boundary": (
        "Paper Boundary",
        "The wall between this app and real money. We literally cannot place "
        "a live-money order from here.",
    ),
    "live_disabled": (
        "Live disabled",
        "Real-money trading is turned off and cannot be turned on from this "
        "screen. Even arming the kill switch the wrong way only affects "
        "paper orders.",
    ),
    # ---------- Portfolio / P&L ----------
    "paper_portfolio": (
        "Paper Portfolio",
        "Your simulated holdings — cash plus the value of any positions. "
        "Treat it as practice, not a track record.",
    ),
    "realized_pnl": (
        "Realized P&L",
        "Profit or loss from positions you've already closed. Open positions "
        "don't count until you sell.",
    ),
    "open_orders": (
        "Open orders",
        "Orders the broker has accepted but not yet filled. For daily-close "
        "strategies, this is usually zero until 4pm ET.",
    ),
    # ---------- Risk ----------
    "risk_state": (
        "Risk State",
        "How worried the safety system is right now. OK means everything's "
        "within limits; ATTENTION means at least one rule fired today.",
    ),
    "drawdown": (
        "Drawdown",
        "The biggest drop from a peak portfolio value. A 10% drawdown means "
        "you fell 10% from your highest point — a normal measure of pain.",
    ),
    "exposure": (
        "Exposure",
        "How much of your money is committed to a single symbol or sector. "
        "Concentrated exposure is riskier — if that one thing tanks, you do too.",
    ),
    "rejected_signals": (
        "Rejected signals",
        "Trades the strategy wanted to place, but the safety system stopped. "
        "Each rejection has a reason — read it before changing settings.",
    ),
    "runtime_alerts": (
        "Runtime Alerts",
        "Real-time warnings about things the system thinks you should know — "
        "data feed problems, rule violations, anything off-normal.",
    ),
    "kill_switch": (
        "Kill switch",
        "The one button that stops all paper trading. Use it freely; it "
        "cannot harm real capital because there is no real capital here.",
    ),
    "rule_max_orders_per_day": (
        "MAX_ORDERS_PER_DAY",
        "A safety rule that caps how many orders the strategy can place in a "
        "single trading day. Prevents a runaway model from spamming the broker.",
    ),
    # ---------- Models ----------
    "active_model": (
        "Active Model",
        "The strategy currently allowed to place paper orders. We only run "
        "one at a time so behavior is easy to audit.",
    ),
    "hypothesis": (
        "Hypothesis",
        "The trading theory the model is built on. Every model starts as a "
        "claim about how markets behave that we then test.",
    ),
    "cadence": (
        "Cadence",
        "How often the model decides whether to trade. \"Daily close\" means "
        "it only acts at the end of each trading day — slow and steady.",
    ),
    "universe": (
        "Universe",
        "The list of symbols the model is allowed to pick from. A small, "
        "well-understood universe is usually safer than a sprawling one.",
    ),
    "benchmark": (
        "Benchmark",
        "An index — usually SPY (the S&P 500) — we measure returns against. "
        "Beating the benchmark over time is the whole game.",
    ),
    "holding_period": (
        "Holding period",
        "How long the model typically keeps a position before selling. "
        "Shorter periods mean more trades, more costs, more taxes.",
    ),
    "signal_logic": (
        "Signal",
        "How the model decides what to buy. Could be a momentum score, a "
        "mean-reversion trigger, anything quantifiable from market data.",
    ),
    "sizing_logic": (
        "Sizing",
        "How much of your cash the model puts into each position. Equal-weight "
        "is the simplest; risk-weighted is more careful.",
    ),
    "exit_logic": (
        "Exit",
        "When the model sells. Could be a calendar rule (\"sell after 30 days\"), "
        "a stop loss, or a rebalance signal.",
    ),
    "champion_challenger": (
        "Champion / Challenger",
        "The current trading model (Champion) versus a candidate we're "
        "testing (Challenger). We never replace one without proving the new "
        "one is meaningfully better.",
    ),
    "shadow_candidate": (
        "Shadow candidate",
        "A model we're watching live but not letting trade. It produces "
        "would-be signals we can grade without risking anything.",
    ),
    "failure_modes": (
        "Known Failure Modes",
        "The specific situations where this model is expected to perform "
        "badly. Documented up front so we're not surprised when they happen.",
    ),
    "ai_role": (
        "AI Role",
        "What the AI copilot is allowed to do for this model. It explains, "
        "summarizes, and recommends — never trades autonomously.",
    ),
    "score": (
        "Score",
        "A single number that ranks how well a model has been doing in our "
        "evaluation system. Higher is better, but the absolute value depends "
        "on the metric.",
    ),
    # ---------- AI / governance ----------
    "ai_governance": (
        "AI Governance",
        "The ledger of what the AI did, what it recommended, and what still "
        "needs your approval. AI never makes irreversible changes on its own.",
    ),
    "ai_confidence": (
        "AI confidence",
        "How sure the AI is about a recommendation, from 0 (no idea) to 1 "
        "(very sure). Always treat as advisory — a high number is not a "
        "guarantee.",
    ),
    "active_mutation": (
        "Active mutation",
        "Whether the currently trading model is in the middle of changing. "
        "We block mutations by default so behavior stays predictable.",
    ),
    # ---------- Compliance / audit ----------
    "reconciliation": (
        "Reconciliation",
        "We compare our internal records to the broker's every day. \"Clean\" "
        "means they match to the penny; \"mismatch\" means something's off and "
        "needs investigating.",
    ),
    "statement_review": (
        "Statement Review",
        "Once the broker sends an official statement, we re-check it against "
        "our daily reconciliation. Catches errors the daily check missed.",
    ),
    "audit_trail": (
        "Audit Trail",
        "Every trade traced back to the raw data and rule that produced it. "
        "If anyone asks \"why did we buy this?\", the answer is one click away.",
    ),
    "functional_readiness": (
        "Functional Readiness",
        "Evidence that every feature in the app has been tested with real "
        "data. A checklist of \"yes, this works\".",
    ),
    "final_acceptance": (
        "Final Acceptance",
        "The final operator signoff before this app could ever be used for "
        "real-money trading. Multiple safety checks must all pass first.",
    ),
    "live_readiness": (
        "Live Readiness",
        "A separate evaluation of whether the app is technically ready to "
        "trade real money. Right now this is always \"disabled\".",
    ),
    "runtime_proof": (
        "Runtime Proof",
        "Evidence that the trading loop actually ran today — prices "
        "refreshed, broker synced, orders submitted, fills applied.",
    ),
    "incident_command": (
        "Incident Command",
        "Active operational problems the system has noticed. Each comes with "
        "a suggested action and a severity level.",
    ),
    # ---------- Data ----------
    "data_quality": (
        "Data Quality Evidence",
        "How trustworthy today's market data is. Warning means the data is "
        "fine for research but not for live trading decisions.",
    ),
    "iex_dev_grade": (
        "IEX development-grade feed",
        "Free market data from the IEX exchange. Good for testing but missing "
        "ticks from other exchanges — don't bet real money on it.",
    ),
    # ---------- Accounting ----------
    "tax_lots": (
        "Tax lots",
        "Each batch of shares you bought is a \"lot\" with its own cost basis. "
        "When you sell, the lot you pick determines the gain or loss.",
    ),
    "fifo": (
        "FIFO",
        "First-In, First-Out — the oldest lot is sold first. The simplest "
        "method and the default for most brokers.",
    ),
    "realized_gains": (
        "Realized gains",
        "Profit (or loss) on shares you've actually sold. Open positions "
        "don't realize anything — only closing trades do.",
    ),
    "short_long_term": (
        "Short-term vs long-term gains",
        "Gains on positions held under 1 year are taxed at higher rates than "
        "those held 1 year or longer. This estimate is research-only.",
    ),
    # ---------- Surface eyebrows / sections ----------
    "daily_report": (
        "Daily Report",
        "The system's summary of every trade decision today — accepted, "
        "rejected, and why. The audit record for one trading day.",
    ),
    "ai_daily_memo": (
        "AI Daily Memo",
        "What the AI thought about today's activity, written for a human "
        "to read. It is advisory; you are still the one who approves changes.",
    ),
    "latest_prices": (
        "Latest Prices",
        "The most recent prices the system has on file for tracked symbols. "
        "Stale prices are flagged so you know not to trust them.",
    ),
    "operator_controls": (
        "Operator Controls",
        "Buttons that let you pause trading, arm the kill switch, force a "
        "broker reconciliation, or save today's report.",
    ),
    "model_arena": (
        "Model Arena",
        "Where current and candidate strategies are scored side by side. "
        "Promotion never happens automatically — the operator decides.",
    ),
    "reports_and_learning": (
        "Reports And Learning",
        "Where today's report was saved and whether nightly learning produced "
        "any new recommendations.",
    ),
    "accounting": (
        "Tax Estimate",
        "A rough estimate of what taxes might look like on closed positions. "
        "Research-only — not filing-grade accounting.",
    ),
    # ---------- Research ----------
    "nightly_learning": (
        "Nightly Learning",
        "After each trading day we re-evaluate candidate models against the "
        "active one. If a candidate is meaningfully better, we'll recommend "
        "it — but never replace anything without your approval.",
    ),
    "walk_forward": (
        "Walk-forward",
        "Testing a model by re-fitting it on rolling windows of history and "
        "scoring it on the next window. More honest than a single backtest "
        "because it can't peek at the future.",
    ),
    "research_memo": (
        "Research memo",
        "The AI's nightly written summary of what it studied, what it found, "
        "and what it recommends. Written to be read by a human, not parsed "
        "by a machine.",
    ),
    "score_delta": (
        "Score delta",
        "How much better (or worse) the challenger scored than the current "
        "champion. Positive means the challenger looks better — but \"better\" "
        "needs more than one number.",
    ),
}


def get(key: str) -> tuple[str, str] | None:
    """Look up (technical term, plain definition) for a glossary key."""

    return GLOSSARY.get(key)


# ---------------------------------------------------------------------------
# Topic index — used by the Learn screen.
#
# A small, ordered mapping from a topic key to (heading, blurb, deep-link,
# [glossary keys]). The Learn screen renders one surface per topic; each
# row inside reuses the (term, definition) data already in ``GLOSSARY`` so
# definitions stay single-sourced.
#
# Topics are intentionally five. More than that and the page stops feeling
# like a reference index.
# ---------------------------------------------------------------------------


# topic key -> (heading, one-line blurb, default deep-link, ordered glossary keys)
TOPICS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "paper": (
        "Paper trading",
        "Fake money only. What that means here, and why it's the only mode.",
        "#paper",
        (
            "paper_trading",
            "paper_boundary",
            "live_disabled",
            "paper_portfolio",
            "realized_pnl",
            "open_orders",
        ),
    ),
    "risk": (
        "Risk",
        "What the safety system watches, what severity means, and the kill switch.",
        "#risk",
        (
            "risk_state",
            "drawdown",
            "exposure",
            "rejected_signals",
            "runtime_alerts",
            "kill_switch",
            "rule_max_orders_per_day",
        ),
    ),
    "models": (
        "Models",
        "Strategy vocabulary — from hypothesis through exit, and how we compare candidates.",
        "#strategies",
        (
            "active_model",
            "hypothesis",
            "cadence",
            "universe",
            "benchmark",
            "holding_period",
            "signal_logic",
            "sizing_logic",
            "exit_logic",
            "champion_challenger",
            "shadow_candidate",
            "failure_modes",
            "ai_role",
            "score",
        ),
    ),
    "ai": (
        "AI",
        "What the copilot does — and what it never does.",
        "#ai",
        (
            "ai_governance",
            "ai_confidence",
            "active_mutation",
            "ai_daily_memo",
        ),
    ),
    "dashboard": (
        "Reading the dashboard",
        "Terms about the dashboard itself — reconciliation, audit trail, readiness.",
        "#home",
        (
            "reconciliation",
            "statement_review",
            "audit_trail",
            "functional_readiness",
            "final_acceptance",
            "live_readiness",
            "runtime_proof",
            "incident_command",
            "data_quality",
            "iex_dev_grade",
            "tax_lots",
            "fifo",
            "realized_gains",
            "short_long_term",
            "nightly_learning",
            "walk_forward",
            "research_memo",
            "score_delta",
            "latest_prices",
            "operator_controls",
            "model_arena",
            "reports_and_learning",
            "accounting",
            "daily_report",
        ),
    ),
}


# Per-term deep-link override. Most terms in a topic share the topic's
# default deep-link; a few belong to a different screen and are pinned
# here. The Learn screen falls back to the topic default when a key is
# absent from this map.
DEEP_LINKS: dict[str, str] = {
    # Compliance / audit bits — best inspected in the AI Review surface.
    "audit_trail": "#ai",
    "functional_readiness": "#ai",
    "final_acceptance": "#ai",
    "live_readiness": "#ai",
    "statement_review": "#ai",
    "incident_command": "#ai",
    "reconciliation": "#paper",
    # Research bits — Research Lab.
    "nightly_learning": "#research",
    "walk_forward": "#research",
    "research_memo": "#research",
    "score_delta": "#research",
    "model_arena": "#strategies",
    # Runtime / home surface bits.
    "runtime_proof": "#home",
    "latest_prices": "#home",
    "data_quality": "#home",
    "operator_controls": "#home",
    "iex_dev_grade": "#home",
    "daily_report": "#home",
    "reports_and_learning": "#home",
    # Accounting bits — Paper Trading surface holds the tax estimate.
    "tax_lots": "#paper",
    "fifo": "#paper",
    "realized_gains": "#paper",
    "short_long_term": "#paper",
    "accounting": "#paper",
}


def deep_link_for(key: str, topic_default: str) -> str:
    """Resolve a deep-link for a glossary key, falling back to the topic default."""

    return DEEP_LINKS.get(key, topic_default)
