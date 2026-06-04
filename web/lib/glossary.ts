export type GlossaryEntry = {
  term: string;
  definition: string;
  link: ScreenHash;
};

export type GlossaryTopic = {
  heading: string;
  blurb: string;
  defaultLink: ScreenHash;
  terms: string[];
};

export type ScreenHash =
  | "#overview"
  | "#home"
  | "#strategies"
  | "#paper"
  | "#risk"
  | "#research"
  | "#reports"
  | "#ai"
  | "#learn";

export const SCREEN_LABELS: Record<ScreenHash, string> = {
  "#overview": "Overview",
  "#home": "Home",
  "#strategies": "Models",
  "#paper": "Paper Trading",
  "#risk": "Risk",
  "#research": "Research Lab",
  "#reports": "Reports",
  "#ai": "AI Review",
  "#learn": "Learn",
};

export const GLOSSARY: Record<string, GlossaryEntry> = {
  paper_trading: {
    term: "Paper Trading",
    definition:
      "Fake money only. Every dollar you see here is simulated; no real account is touched.",
    link: "#home",
  },
  paper_boundary: {
    term: "Paper Boundary",
    definition:
      "The wall between this app and real money. We literally cannot place a live-money order from here.",
    link: "#home",
  },
  live_disabled: {
    term: "Live disabled",
    definition:
      "Real-money trading is turned off and cannot be turned on from this screen. Even arming the kill switch the wrong way only affects paper orders.",
    link: "#home",
  },
  paper_portfolio: {
    term: "Paper Portfolio",
    definition:
      "Your simulated holdings - cash plus the value of any positions. Treat it as practice, not a track record.",
    link: "#home",
  },
  realized_pnl: {
    term: "Realized P&L",
    definition:
      "Profit or loss from positions you've already closed. Open positions don't count until you sell.",
    link: "#home",
  },
  open_orders: {
    term: "Open orders",
    definition:
      "Orders the broker has accepted but not yet filled. For daily-close strategies, this is usually zero until 4pm ET.",
    link: "#home",
  },
  risk_state: {
    term: "Risk State",
    definition:
      "How worried the safety system is right now. OK means everything's within limits; ATTENTION means at least one rule fired today.",
    link: "#home",
  },
  drawdown: {
    term: "Drawdown",
    definition:
      "The biggest drop from a peak portfolio value. A 10% drawdown means you fell 10% from your highest point - a normal measure of pain.",
    link: "#home",
  },
  max_drawdown: {
    term: "Max DD",
    definition:
      "Maximum drawdown - the deepest peak-to-trough fall the model ever had during the test window. A -25% max DD means it lost 25% from its highest point before recovering. Smaller magnitude = smoother ride.",
    link: "#overview",
  },
  excess_return: {
    term: "Excess return",
    definition:
      "How much the model beat (or trailed) the benchmark over the same window. +15% means the model finished 15 percentage points above the benchmark's return. This is the headline 'beat the market by' number.",
    link: "#overview",
  },
  net_total_return: {
    term: "Net return",
    definition:
      "The model's total return over the test window, after costs. Plus = profit, minus = loss. Cumulative, not annualized.",
    link: "#overview",
  },
  risk_adjusted_score: {
    term: "Research score",
    definition:
      "A composite number the learning engine assigns to each candidate that blends return, drawdown, fold consistency, and risk. Higher = the engine likes it more. Useful for ranking, not for predicting returns.",
    link: "#overview",
  },
  hypothesis_queue: {
    term: "Hypothesis queue",
    definition:
      "The list of experiments the autonomous research worker is running on a schedule. Each hypothesis tests a specific tweak (different lookback, different drawdown rule, different universe) against historical data.",
    link: "#overview",
  },
  exposure: {
    term: "Exposure",
    definition:
      "How much of your money is committed to a single symbol or sector. Concentrated exposure is riskier - if that one thing tanks, you do too.",
    link: "#home",
  },
  rejected_signals: {
    term: "Rejected signals",
    definition:
      "Trades the strategy wanted to place, but the safety system stopped. Each rejection has a reason - read it before changing settings.",
    link: "#home",
  },
  runtime_alerts: {
    term: "Runtime Alerts",
    definition:
      "Real-time warnings about things the system thinks you should know - data feed problems, rule violations, anything off-normal.",
    link: "#home",
  },
  kill_switch: {
    term: "Kill switch",
    definition:
      "The one button that stops all paper trading. Use it freely; it cannot harm real capital because there is no real capital here.",
    link: "#home",
  },
  rule_max_orders_per_day: {
    term: "MAX_ORDERS_PER_DAY",
    definition:
      "A safety rule that caps how many orders the strategy can place in a single trading day. Prevents a runaway model from spamming the broker.",
    link: "#home",
  },
  active_model: {
    term: "Active Model",
    definition:
      "The strategy currently allowed to place paper orders. We only run one at a time so behavior is easy to audit.",
    link: "#home",
  },
  hypothesis: {
    term: "Hypothesis",
    definition:
      "The trading theory the model is built on. Every model starts as a claim about how markets behave that we then test.",
    link: "#home",
  },
  cadence: {
    term: "Cadence",
    definition:
      '"Daily close" means it only acts at the end of each trading day - slow and steady.',
    link: "#home",
  },
  universe: {
    term: "Universe",
    definition:
      "The list of symbols the model is allowed to pick from. A small, well-understood universe is usually safer than a sprawling one.",
    link: "#home",
  },
  benchmark: {
    term: "Benchmark",
    definition:
      "An index - usually SPY (the S&P 500) - we measure returns against. Beating the benchmark over time is the whole game.",
    link: "#home",
  },
  holding_period: {
    term: "Holding period",
    definition:
      "How long the model typically keeps a position before selling. Shorter periods mean more trades, more costs, more taxes.",
    link: "#home",
  },
  signal_logic: {
    term: "Signal",
    definition:
      "How the model decides what to buy. Could be a momentum score, a mean-reversion trigger, anything quantifiable from market data.",
    link: "#home",
  },
  sizing_logic: {
    term: "Sizing",
    definition:
      "How much of your cash the model puts into each position. Equal-weight is the simplest; risk-weighted is more careful.",
    link: "#home",
  },
  exit_logic: {
    term: "Exit",
    definition:
      'When the model sells. Could be a calendar rule ("sell after 30 days"), a stop loss, or a rebalance signal.',
    link: "#home",
  },
  champion_challenger: {
    term: "Champion / Challenger",
    definition:
      "The current trading model (Champion) versus a candidate we're testing (Challenger). We never replace one without proving the new one is meaningfully better.",
    link: "#home",
  },
  shadow_candidate: {
    term: "Shadow candidate",
    definition:
      "A model we're watching live but not letting trade. It produces would-be signals we can grade without risking anything.",
    link: "#home",
  },
  failure_modes: {
    term: "Known Failure Modes",
    definition:
      "The specific situations where this model is expected to perform badly. Documented up front so we're not surprised when they happen.",
    link: "#home",
  },
  ai_role: {
    term: "AI Role",
    definition:
      "What the AI copilot is allowed to do for this model. It explains, summarizes, and recommends - never trades autonomously.",
    link: "#home",
  },
  score: {
    term: "Score",
    definition:
      "A single number that ranks how well a model has been doing in our evaluation system. Higher is better, but the absolute value depends on the metric.",
    link: "#home",
  },
  ai_governance: {
    term: "AI Governance",
    definition:
      "The ledger of what the AI did, what it recommended, and what still needs your approval. AI never makes irreversible changes on its own.",
    link: "#home",
  },
  ai_confidence: {
    term: "AI confidence",
    definition:
      "How sure the AI is about a recommendation, from 0 (no idea) to 1 (very sure). Always treat as advisory - a high number is not a guarantee.",
    link: "#home",
  },
  active_mutation: {
    term: "Active mutation",
    definition:
      "Whether the currently trading model is in the middle of changing. We block mutations by default so behavior stays predictable.",
    link: "#home",
  },
  reconciliation: {
    term: "Reconciliation",
    definition:
      'We compare our internal records to the broker\'s every day. "Clean" means they match to the penny; "mismatch" means something\'s off and needs investigating.',
    link: "#paper",
  },
  statement_review: {
    term: "Statement Review",
    definition:
      "Once the broker sends an official statement, we re-check it against our daily reconciliation. Catches errors the daily check missed.",
    link: "#ai",
  },
  audit_trail: {
    term: "Audit Trail",
    definition:
      'Every trade traced back to the raw data and rule that produced it. If anyone asks "why did we buy this?", the answer is one click away.',
    link: "#ai",
  },
  functional_readiness: {
    term: "Functional Readiness",
    definition:
      'Evidence that every feature in the app has been tested with real data. A checklist of "yes, this works".',
    link: "#ai",
  },
  final_acceptance: {
    term: "Final Acceptance",
    definition:
      "The final operator signoff before this app could ever be used for real-money trading. Multiple safety checks must all pass first.",
    link: "#ai",
  },
  live_readiness: {
    term: "Live Readiness",
    definition:
      'A separate evaluation of whether the app is technically ready to trade real money. Right now this is always "disabled".',
    link: "#ai",
  },
  runtime_proof: {
    term: "Runtime Proof",
    definition:
      "Evidence that the trading loop actually ran today - prices refreshed, broker synced, orders submitted, fills applied.",
    link: "#home",
  },
  incident_command: {
    term: "Incident Command",
    definition:
      "Active operational problems the system has noticed. Each comes with a suggested action and a severity level.",
    link: "#ai",
  },
  data_quality: {
    term: "Data Quality Evidence",
    definition:
      "How trustworthy today's market data is. Warning means the data is fine for research but not for live trading decisions.",
    link: "#home",
  },
  iex_dev_grade: {
    term: "IEX development-grade feed",
    definition:
      "Free market data from the IEX exchange. Good for testing but missing ticks from other exchanges - don't bet real money on it.",
    link: "#home",
  },
  tax_lots: {
    term: "Tax lots",
    definition:
      'Each batch of shares you bought is a "lot" with its own cost basis. When you sell, the lot you pick determines the gain or loss.',
    link: "#paper",
  },
  fifo: {
    term: "FIFO",
    definition:
      "First-In, First-Out - the oldest lot is sold first. The simplest method and the default for most brokers.",
    link: "#paper",
  },
  realized_gains: {
    term: "Realized gains",
    definition:
      "Profit (or loss) on shares you've actually sold. Open positions don't realize anything until you sell.",
    link: "#paper",
  },
  short_long_term: {
    term: "Short-term vs long-term gains",
    definition:
      "Gains on positions held under 1 year are taxed at higher rates than those held 1 year or longer. This estimate is research-only.",
    link: "#paper",
  },
  daily_report: {
    term: "Daily Report",
    definition:
      "The system's summary of every trade decision today - accepted, rejected, and why. The audit record for one trading day.",
    link: "#home",
  },
  ai_daily_memo: {
    term: "AI Daily Memo",
    definition:
      "What the AI thought about today's activity, written for a human to read. It is advisory; you are still the one who approves changes.",
    link: "#home",
  },
  latest_prices: {
    term: "Latest Prices",
    definition:
      "The most recent prices the system has on file for tracked symbols. Stale prices are flagged so you know not to trust them.",
    link: "#home",
  },
  operator_controls: {
    term: "Operator Controls",
    definition:
      "Buttons that let you pause trading, arm the kill switch, force a broker reconciliation, or save today's report.",
    link: "#home",
  },
  model_arena: {
    term: "Model Arena",
    definition:
      "Where current and candidate strategies are scored side by side. Promotion never happens automatically - the operator decides.",
    link: "#strategies",
  },
  reports_and_learning: {
    term: "Reports And Learning",
    definition:
      "Where today's report was saved and whether nightly learning produced any new recommendations.",
    link: "#home",
  },
  accounting: {
    term: "Tax Estimate",
    definition:
      "A rough estimate of what taxes might look like on closed positions. Research-only - not filing-grade accounting.",
    link: "#paper",
  },
  nightly_learning: {
    term: "Nightly Learning",
    definition:
      "After each trading day we re-evaluate candidate models against the active one. If a candidate is meaningfully better, we'll recommend it - but never replace anything without your approval.",
    link: "#research",
  },
  walk_forward: {
    term: "Walk-forward",
    definition:
      "Testing a model by re-fitting it on rolling windows of history and scoring it on the next window. More honest than a single backtest because it can't peek at the future.",
    link: "#research",
  },
  research_memo: {
    term: "Research memo",
    definition:
      "The AI's nightly written summary of what it studied, what it found, and what it recommends. Written to be read by a human, not parsed by a machine.",
    link: "#research",
  },
  score_delta: {
    term: "Score delta",
    definition:
      'How much better (or worse) the challenger scored than the current champion. Positive means the challenger looks better - but "better" needs more than one number.',
    link: "#research",
  },
};

export const TOPICS: Record<string, GlossaryTopic> = {
  paper: {
    heading: "Paper trading",
    blurb: "Fake money only. What that means here, and why it's the only mode.",
    defaultLink: "#paper",
    terms: [
      "paper_trading",
      "paper_boundary",
      "live_disabled",
      "paper_portfolio",
      "realized_pnl",
      "open_orders",
    ],
  },
  risk: {
    heading: "Risk",
    blurb:
      "What the safety system watches, what severity means, and the kill switch.",
    defaultLink: "#risk",
    terms: [
      "risk_state",
      "drawdown",
      "exposure",
      "rejected_signals",
      "runtime_alerts",
      "kill_switch",
      "rule_max_orders_per_day",
    ],
  },
  models: {
    heading: "Models",
    blurb:
      "Strategy vocabulary - from hypothesis through exit, and how we compare candidates.",
    defaultLink: "#strategies",
    terms: [
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
    ],
  },
  ai: {
    heading: "AI",
    blurb: "What the copilot does - and what it never does.",
    defaultLink: "#ai",
    terms: [
      "ai_governance",
      "ai_confidence",
      "active_mutation",
      "ai_daily_memo",
    ],
  },
  dashboard: {
    heading: "Reading the dashboard",
    blurb:
      "Terms about the dashboard itself - reconciliation, audit trail, readiness.",
    defaultLink: "#home",
    terms: [
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
    ],
  },
};

export const DEEP_LINKS: Record<string, ScreenHash> = {
  audit_trail: "#ai",
  functional_readiness: "#ai",
  final_acceptance: "#ai",
  live_readiness: "#ai",
  statement_review: "#ai",
  incident_command: "#ai",
  reconciliation: "#paper",
  nightly_learning: "#research",
  walk_forward: "#research",
  research_memo: "#research",
  score_delta: "#research",
  model_arena: "#strategies",
  runtime_proof: "#home",
  latest_prices: "#home",
  data_quality: "#home",
  operator_controls: "#home",
  iex_dev_grade: "#home",
  daily_report: "#home",
  reports_and_learning: "#home",
  tax_lots: "#paper",
  fifo: "#paper",
  realized_gains: "#paper",
  short_long_term: "#paper",
  accounting: "#paper",
};

export function deepLinkFor(key: string, topicDefault: ScreenHash): ScreenHash {
  return DEEP_LINKS[key] ?? topicDefault;
}
