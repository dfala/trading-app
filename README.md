# Trading Research App

## Purpose

This project is a financial research and trading application for developing, testing, comparing, and eventually funding stock-trading models.

The core idea is to begin with real market data and fake money. We will build multiple trading models, run them in a mock trading environment, measure how they perform, and learn which approaches are promising before risking real capital.

The goal is not to rush into live trading. The goal is to get very smart about trading first.

## Market Scope

This project will focus exclusively on U.S. stock markets. We will not trade or invest in non-U.S. markets.

All strategy research, data pipelines, benchmarks, paper-trading simulations, and future real-money funding decisions should stay within this U.S.-only stock market scope.

## Project Vision

We want to create a disciplined system that can:

- Ingest real U.S. stock prices and market data.
- Define different trading models and strategies.
- Simulate trades using paper money.
- Track each model's decisions, positions, returns, risk, and mistakes.
- Compare models against one another and against simple benchmarks.
- Identify models that appear consistently strong under realistic conditions.
- Gradually move selected models toward limited real-money funding only after careful review.

This project should feel more like a research lab than a casino. Every model should have a clear hypothesis, every trade should be explainable, and every result should be measured honestly.

## Guiding Principles

1. Learn before risking capital.
2. Use real market prices, but start with fake money.
3. Compare models with consistent rules and metrics.
4. Prefer explainable strategies over mysterious black boxes.
5. Treat risk management as a first-class feature.
6. Keep detailed records of model behavior and trading outcomes.
7. Fund only the models that show durable, repeatable performance.
8. Assume every promising result may be misleading until tested carefully.

## Initial Phases

### Phase 1: Build Knowledge

Before writing serious trading logic, we will study trading concepts, market mechanics, strategy types, portfolio risk, backtesting pitfalls, paper trading, and evaluation metrics.

The first major deliverable is not code. It is understanding.

### Phase 2: Create the Paper Trading Foundation

We will build a mock trading environment that uses real stock price data while tracking fake cash, positions, orders, and performance. This gives us a safe arena for experimentation.

### Phase 3: Develop Trading Models

We will create multiple models with different hypotheses. Examples may include momentum models, mean-reversion models, trend-following models, volatility-aware models, fundamentals-informed models, or machine-learning-based models.

Each model should be treated as a testable idea, not a guaranteed source of profit.

### Phase 4: Compare and Evaluate

Models will be compared using shared measurements such as total return, benchmark-relative return, drawdown, volatility, win rate, risk-adjusted return, turnover, and behavior during different market conditions.

We will care about how a model earns returns, not just whether it earns them.

### Phase 5: Carefully Consider Funding

Only after a model performs well in mock trading, survives review, and demonstrates acceptable risk behavior should it be considered for real-money funding.

Any real-money deployment should start small, include strict limits, and be monitored closely.

## What This Project Is Not

This project is not a promise of profits. It is not financial advice. It is not a shortcut to trading success.

It is a structured attempt to learn, test, measure, and improve trading ideas before putting real money at risk.

## Current Status

The project now has a Python paper-trading foundation with schemas, an internal ledger, historical data, backtesting, paper broker abstractions, risk controls, reporting, nightly learning scaffolding, a local dashboard, always-on runtime scaffolding, persistence, operator controls, health checks, validation, and local operations guidance.

## Starting The Servers

The production-style local setup uses two servers:

- Next.js operator dashboard: `http://127.0.0.1:3003/`
- Python paper runtime backend/API: `http://127.0.0.1:8765/`

Use the Next.js URL as the dashboard. The Python URL stays alive for API,
health, controls, broker sync, and runtime state. Browser requests to the old
Python dashboard routes redirect to the Next.js dashboard.

If launchd is already installed, check both services with:

```bash
make launchd-status
```

To install or restart both launchd services after code, dependency, or `.env`
changes:

```bash
make launchd-install
```

To stop and remove both launchd services:

```bash
make launchd-uninstall
```

For manual development without launchd, start the Python backend first:

```bash
uv run dev
```

Then start the Next.js dashboard in another terminal:

```bash
make web-dev
```

For production-style manual serving instead of Next dev mode:

```bash
make web-start
```

Do not stop the Python backend just because the UI moved to Next.js. If `8765`
is down, the dashboard at `3003` can load HTML but data and controls will fail.

The backend shortcut loads `.env` when present, keeps any credentials already
exported in your shell, honors the `TRADING_APP_*` runtime defaults from that
file, runs the required monitor-only dry run first, and starts the Python
runtime backend at `http://127.0.0.1:8765`. If the backend port is already in
use, the shortcut automatically tries the next local port and prints the URL it
selected.

The equivalent explicit command is:

```bash
python -m trading_app.runtime.run_alpaca_paper --monitor-only-dry-run-first
```

The combined launchd targets call the Python backend script first and the
Next.js dashboard script second. The Python LaunchAgent uses the fixed backend
URL `http://127.0.0.1:8765/`; if that port is occupied, startup fails loudly
instead of silently choosing another port. The Next LaunchAgent builds `web/`,
starts production Next.js at `http://127.0.0.1:3003/`, and proxies to the Python
backend. Alpaca credentials stay with the Python backend.

The lower-level scripts are still available when you intentionally want to
operate only one service:

```bash
scripts/install_alpaca_paper_launchd.sh
scripts/status_alpaca_paper_launchd.sh
scripts/uninstall_alpaca_paper_launchd.sh
scripts/install_operator_web_launchd.sh
scripts/status_operator_web_launchd.sh
scripts/uninstall_operator_web_launchd.sh
```

## Next.js Frontend

The operator dashboard frontend lives in `web/`. It carries over the Python
dashboard's seven-screen cockpit: Home, Models, Paper Trading, Risk, Research
Lab, AI Review, and Learn. The Python runtime remains the trading authority;
Next.js only renders the UI and proxies browser requests through same-origin
routes to the local Python backend.

Start the Python backend first:

```bash
uv run dev
```

Then start the Next.js UI:

```bash
make web-install
make web-dev
```

The Next app reads `TRADING_APP_BACKEND_URL` on the server side only. The default
matches the Python runtime backend at `http://127.0.0.1:8765`.

Check the frontend before handing it off:

```bash
make web-check
```

For production-style local serving, build and run Next.js on the fixed operator
dashboard port:

```bash
make web-start
```

That serves the React dashboard at `http://127.0.0.1:3003/` and proxies to the
Python backend at `http://127.0.0.1:8765` by default.

Use `.env.example` for local environment setup, keep the dashboard and backend
bound to `127.0.0.1`, and keep all runtime artifacts under ignored
`data/runtime/` folders.
