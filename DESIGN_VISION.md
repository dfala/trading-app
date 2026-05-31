# Design Vision

Last updated: 2026-05-30

## Product Feel

This app should feel like the financial trading platform of the future: calm, intelligent, luminous, fast, and deeply trustworthy.

The design should take inspiration from Robinhood's simplicity and approachability, but it should not copy Robinhood's exact visual identity. The goal is to build something better suited to this project: a trading research cockpit where model behavior, paper trading, risk, and learning loops are beautiful, understandable, and under control.

The app should feel like:

- Robinhood-level clarity.
- Institutional-grade seriousness.
- AI-native intelligence.
- Futuristic neon energy.
- A research lab, not a casino.

## Design Principles

### 1. Clarity Before Flash

The interface can be breathtaking, but it must never obscure risk, model state, cash, positions, or trade history.

Beautiful trading software that hides uncertainty is dangerous. Our design should make uncertainty visible.

### 2. Confidence Without Gambling Energy

The app should feel exciting, but not reckless. Avoid visual patterns that push the user toward impulsive trading.

Good:

- Clear model confidence.
- Risk warnings.
- Calm confirmations.
- Trade explanations.
- Paper-vs-live status that is impossible to miss.

Bad:

- Celebration animations for risky trades.
- Casino-like colors or motion.
- Pressure-based prompts.
- "Hot stock" hype.
- UI that makes losing trades feel trivial.

### 3. AI As Copilot, Not Magician

AI should be visually present as an analyst and governance layer. It should explain, summarize, flag, compare, and recommend.

AI should not be presented as an all-knowing oracle.

The UI should show:

- What the AI reviewed.
- What evidence it used.
- What it recommends.
- How confident it is.
- What still requires human approval.

### 4. Risk Is Always Visible

Risk should have first-class visual treatment. It should not be hidden under advanced settings.

Every major screen should make it easy to see:

- Current risk state.
- Drawdown.
- Daily loss.
- Exposure by model.
- Exposure by symbol.
- Exposure by sector.
- Rejected signals.
- Kill switch state.
- Paper/live mode.

### 5. Model Behavior Should Be Explainable

The user should be able to inspect why a model acted.

Every signal and trade should answer:

- Which model produced this?
- What was the hypothesis?
- What data did it use?
- Why did it buy, sell, hold, or exit?
- Did the risk engine approve or reject it?
- How has this model performed recently?

## Visual Direction

### Overall Style

The app should use a dark, high-contrast base with luminous accents.

Target mood:

- Dark graphite and near-black backgrounds.
- Electric green, cyan, and selective violet accents.
- Sharp, clean typography.
- Dense but calm data layouts.
- Smooth motion used sparingly.
- Financial charts that feel alive but readable.

Avoid:

- Generic SaaS dashboards.
- Beige, tan, or soft lifestyle palettes.
- Overly playful illustrations.
- Decorative gradient blobs.
- Marketing-site hero layouts inside the app.
- UI cards nested inside other cards.
- Visual clutter that reduces trust.

### Palette Direction

Suggested starting palette:

- Background: near-black graphite.
- Primary positive accent: neon green.
- Secondary intelligence accent: electric cyan.
- Caution: amber.
- Danger: red.
- Neutral text: off-white and cool gray.
- Disabled/quiet state: muted slate gray.

Use neon colors as signals and highlights, not as huge background washes.

### Typography

Typography should feel modern, precise, and legible.

Guidelines:

- Use large numbers for portfolio value, P&L, and core metrics.
- Use compact labels for dense model and risk panels.
- Avoid oversized marketing-style headings inside app screens.
- Do not use negative letter spacing.
- Keep financial numbers aligned and easy to scan.

### Motion

Motion should communicate state, not distract.

Good motion:

- Live price updates.
- Model status changes.
- Risk alerts.
- Data stream health.
- Paper order lifecycle.

Avoid:

- Constant ambient animation.
- Celebration effects for profits.
- Flashing elements that create urgency.
- Motion that makes numbers hard to read.

## Product Structure

The eventual app should be organized around the actual system backbone.

### Home Command Center

Purpose: show the whole system at a glance.

Should include:

- Paper portfolio value.
- Daily P&L.
- Total return.
- Cash.
- Active model count.
- Current risk state.
- Kill switch status.
- Latest model decisions.
- Data feed health.
- AI daily summary.

### Models

Purpose: inspect and compare trading models.

Should include:

- Model status.
- Hypothesis.
- Strategy version.
- Performance.
- Drawdown.
- Turnover.
- Recent signals.
- Risk rejections.
- Promotion stage.
- Gross, after-cost, and estimated after-tax results.

### Paper Trading

Purpose: inspect fake-money trading activity.

Should include:

- Open orders.
- Recent fills.
- Positions.
- Cash.
- Trade explanations.
- Ledger reconciliation status.
- Cost and slippage assumptions.

### Risk

Purpose: make risk impossible to ignore.

Should include:

- Portfolio exposure.
- Model exposure.
- Symbol exposure.
- Sector exposure.
- Daily loss.
- Drawdown.
- Rejected signals.
- Risk rules triggered.
- Kill switch.

### Research Lab

Purpose: review backtests, experiments, and candidate models.

Should include:

- Experiment registry.
- Backtest results.
- Champion/challenger comparisons.
- Data feed used.
- Date range.
- Parameters.
- Benchmark comparison.
- Failure notes.

### AI Review

Purpose: show how AI is helping without pretending it is always right.

Should include:

- Daily AI memo.
- Model drift flags.
- Suspicious data alerts.
- Candidate improvement suggestions.
- Filing/news summaries.
- Human approval queue.

## First UI Experience

When we eventually build the first dashboard, the first screen should not be a landing page.

It should open directly into the command center with real system state:

- Paper mode clearly shown.
- Current cash and portfolio state.
- Active models.
- Risk status.
- Latest signals.
- Latest fills.
- Data status.

The app should feel alive because the system is alive, not because the UI is decorative.

## Robinhood Inspiration, With Better Discipline

What to learn from Robinhood:

- Simple onboarding.
- Clean portfolio display.
- Minimal friction.
- Clear charts.
- Mobile-first polish.
- Friendly financial UX.

Where this app should be better:

- Stronger model transparency.
- Better risk visibility.
- Better paper-vs-live separation.
- Better research history.
- Better audit trail.
- Better AI explainability.
- Better after-cost and after-tax reporting.
- Better guardrails against impulsive trading.

## Design Guardrails

The UI should never:

- Hide whether we are in paper or live mode.
- Hide model risk.
- Hide rejected signals.
- Hide costs, slippage, or estimated taxes.
- Encourage day trading by visual pressure.
- Let AI recommendations look like guaranteed truth.
- Make a risky action feel casual.
- Use visual beauty to cover weak evidence.

The UI should always:

- Show the state of the system.
- Make risk visible.
- Explain model behavior.
- Separate research, paper trading, and live trading.
- Make every trade traceable.
- Look beautiful enough that we want to use it every day.

## Design North Star

The app should feel like stepping into a quiet, neon-lit trading lab where every model is observable, every risk is visible, and every decision can be explained.

It should be breathtaking because it is both beautiful and disciplined.

## Copy Guard Rule

Before any new label, eyebrow, button, microcopy, or empty-state string ships, it must pass the 5-second-friend test:

> *"Would a smart non-finance friend understand what this means in 5 seconds, without me explaining it?"*

If the answer is no, one of the following must be true before the label can ship:

1. **Rewrite it** in plain language. The technical term moves into a `C.glossary(...)` tooltip so power users still have it.
2. **Replace it** with a question form ("Ready for real money?" beats "Final Acceptance").
3. **Pair it** with a short microcopy line that explains the term inline.

The rule applies to:

- Every surface eyebrow and title.
- Every stat label.
- Every button label (especially destructive ones).
- Every alert, rejection, or warning message.
- Every empty state string.
- Every status pill text where it isn't a number.

The rule does NOT apply to:

- The technical term displayed inside a glossary popover (that's where the jargon belongs).
- Data values rendered from the snapshot (symbols, paths, IDs).
- Code paths and `data-field` attribute names.

The single source of truth for plain-language replacements is `src/trading_app/dashboard/glossary.py`. New technical terms should be added there with their plain definition, and referenced via `C.glossary("plain label", key="...")`.
