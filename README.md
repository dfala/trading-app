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

The recommended local paper startup path is:

```bash
python -m trading_app.runtime.run_alpaca_paper --monitor-only-dry-run-first
```

Use `.env.example` for local environment setup, keep the dashboard bound to `127.0.0.1`, and keep all runtime artifacts under ignored `data/runtime/` folders.
