# Recommended Stack

Date reviewed: 2026-05-30

## Decision

Use Alpaca as the first-stage trading and market-data provider.

For this project's current stage, Alpaca is the best fit because it combines:

- Paper trading through a broker-style API.
- Real-time stock market data streaming.
- Historical stock bars, quotes, and trades.
- Order, account, position, buying-power, and fill tracking.
- A Python SDK that supports both paper and live environments.

This does not mean Alpaca is perfect or permanently locked in. It means Alpaca is the right first execution/data adapter while this project is focused on learning, paper trading, replay, model comparison, and risk controls.

Robinhood Agentic Trading should not be the first foundation. It is better suited as a later live-execution adapter after the project has strong guardrails.

## Project Scope

This project is limited to U.S. stock markets.

Initial scope:

- U.S.-listed stocks.
- U.S.-listed ETFs used as benchmarks, sector proxies, or lower-risk strategy instruments.
- U.S. regular and extended-hours equity market data, only when the data source and session are clearly recorded.

Out of scope for the first build:

- Non-U.S. exchanges.
- Foreign-listed securities.
- Crypto.
- Futures.
- Options.
- Forex.
- Contracts for difference.
- Any synthetic or leveraged product that we have not explicitly approved as a research instrument.

Every strategy, dataset, benchmark, broker adapter, and funding decision should respect this U.S.-only scope.

## Core Principle

Mock trading must use real market values and real market timing.

That means:

- No invented prices.
- No arbitrary fill timestamps.
- No candle-only backtests pretending to be execution quality.
- Every quote, trade, bar, signal, order, fill, and portfolio update should carry a timestamp.
- Backtests, paper trading, and eventual live trading should share the same strategy and risk-control interfaces.

## Recommended Stack

### Language

Use Python for the core research and trading engine.

Python has the strongest ecosystem for market data, statistics, backtesting, numerical work, and trading APIs.

Recommended baseline:

- Python 3.12 to start. Revisit Python 3.13 or 3.14 only after the core finance, data, and ML dependencies are proven stable for this project.
- `uv` for dependency and environment management
- `ruff` for linting and formatting
- `pytest` for tests
- `pydantic` for typed internal contracts and configuration validation
- `SQLAlchemy` for database models
- `Alembic` for database migrations

### Broker And Paper Trading

Use Alpaca Paper Trading through `alpaca-py`.

Role:

- Paper account
- Simulated orders
- Simulated fills
- Account state
- Positions
- Buying power
- Order status
- Trade history

Important limitation: paper trading is still simulation. Alpaca notes that paper trading does not fully model market impact, information leakage, latency slippage, or queue position for non-marketable limit orders.

The internal project ledger should be the source of truth for research and evaluation. Alpaca's paper account is an execution simulator and broker-style integration target, but every broker-reported order, fill, position, and cash update should be reconciled against our own timestamped audit trail.

Do not let strategy logic depend directly on Alpaca objects. Strategies should emit project-owned signal objects, the risk engine should approve or reject those signals, and broker adapters should translate approved orders into provider-specific API calls.

Official reference: https://docs.alpaca.markets/v1.4.2/docs/paper-trading

### Market Data

Use Alpaca Market Data first.

Development phase:

- Use Alpaca Basic/free data.
- Treat it as useful for building the app only, not for final model confidence or serious model ranking.
- For equities, the free plan is IEX-only, so it does not represent the entire US market.
- Label every result produced from IEX-only data as development-grade.

Serious evaluation phase:

- Upgrade to Alpaca Algo Trader Plus or another full-market SIP provider.
- Use SIP/full-market data before trusting strategy comparisons, model rankings, or funding decisions.
- Store the market-data feed used for each experiment so results are not mixed across IEX, SIP, delayed, or third-party data.
- Record whether the data came from trades, quotes, bars, adjusted bars, raw bars, delayed feeds, or broker-reported fills.

Official references:

- https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
- https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api

### Data Storage

Use three storage layers:

1. PostgreSQL for application state.
2. Parquet files for research datasets and replayable market-data archives.
3. DuckDB as a local analytics/query layer over Parquet.

PostgreSQL should store:

- Strategies
- Model runs
- Signals
- Orders
- Fills
- Positions
- Cash balances
- Risk decisions
- Experiment metadata
- Audit logs
- Data source metadata
- Schema versions

Parquet should store:

- Historical bars
- Quote snapshots
- Trade events
- Feature datasets
- Replay inputs
- Model output snapshots

DuckDB should be used for:

- Querying Parquet files directly.
- Building research datasets from large historical archives.
- Inspecting feature tables without loading everything into memory.
- Reproducible analysis queries.

If market-data volume becomes large or PostgreSQL time-series queries become painful, consider TimescaleDB. Do not start there unless the simpler PostgreSQL plus Parquet plus DuckDB setup becomes limiting.

### Data Quality And Provenance

Data quality is part of the trading system, not a cleanup task.

Track and validate:

- Data vendor.
- Feed type, such as IEX, SIP, delayed SIP, or third-party.
- Symbol and exchange.
- Event timestamp.
- Ingestion timestamp.
- Time zone.
- Session, such as pre-market, regular, after-hours, or overnight.
- Corporate-action adjustment status.
- Missing bars or quote gaps.
- Duplicate events.
- Out-of-order events.
- Suspicious prices or volumes.
- Symbol changes, delistings, splits, and dividends.

Every model run should be reproducible from its recorded data inputs and assumptions.

### Research And Analytics

Use:

- `pandas` for early analysis and broad library compatibility.
- `numpy` for numerical work.
- `scipy` and `statsmodels` for statistics.
- `scikit-learn` for baseline machine-learning models.
- `matplotlib` or `plotly` for charts.
- `duckdb` for querying Parquet-backed research datasets.

Keep model research separate from execution. A model should produce signals; a risk layer should decide whether those signals may become orders.

### Experiment Registry

Every backtest, replay, paper-trading run, and live trial should create an experiment record.

Each experiment should record:

- Strategy name and version.
- Hypothesis being tested.
- Code version or commit hash when available.
- Data source and feed.
- Symbol universe.
- Date range.
- Market session rules.
- Parameters.
- Random seed, if any.
- Starting cash.
- Position sizing rules.
- Risk limits.
- Cost and slippage assumptions.
- Benchmark.
- Output metrics.
- Failure notes or manual review notes.

The system should preserve failed experiments. Failed models are valuable evidence.

### Backtesting And Replay

Build a project-owned event-driven replay engine.

Reason: this project cares about real market timing, order lifecycle, risk gates, and model comparison. A simple custom engine will make assumptions visible instead of hiding them inside a generic backtesting framework.

The replay engine should process events in timestamp order:

1. Market event received.
2. Strategy updates state.
3. Strategy emits signal.
4. Risk engine reviews signal.
5. Portfolio/order engine creates simulated order.
6. Fill model simulates execution from available quote/trade data.
7. Ledger records the result.

For early testing, fills can be conservative:

- Market buy fills near ask.
- Market sell fills near bid.
- Apply configurable slippage.
- Reject fills when data is missing.
- Track partial-fill support as a required future feature.

Do not evaluate serious execution quality using OHLC candles alone.

### Risk Controls

Risk management should be a first-class service, not scattered strategy code.

Minimum controls:

- Max position size per symbol.
- Max portfolio allocation per symbol.
- Max daily loss.
- Max drawdown threshold.
- Max orders per day.
- Max turnover.
- Allowlist of tradable symbols.
- Blocklist of restricted symbols.
- Market-hours rules.
- Manual approval mode before any live-money adapter.
- Kill switch that blocks all new orders.

Every rejected signal should be logged with the rule that rejected it.

### Application Shape

Recommended modules:

- `market_data`: live streams, historical fetches, replay data.
- `strategies`: model logic that emits signals.
- `risk`: pre-trade checks and portfolio limits.
- `broker`: adapter interface for paper/live providers.
- `ledger`: orders, fills, cash, positions, and audit trail.
- `backtest`: historical event replay.
- `paper`: real-time paper-trading runner.
- `analysis`: metrics, charts, reports, and comparisons.
- `experiments`: run registry, hypotheses, parameters, metrics, and review notes.
- `data_quality`: feed validation, gap checks, corporate-action checks, and provenance.
- `schemas`: shared typed contracts for signals, orders, fills, events, and strategy outputs.

Broker adapters should share one interface:

- `AlpacaPaperBroker`
- `AlpacaLiveBroker` later, if appropriate
- `RobinhoodAgenticBroker` later, if appropriate
- `InteractiveBrokersBroker` later, if needed

### User Interface

Start with a small local dashboard after the engine works.

Recommended later options:

- FastAPI for a local API.
- Streamlit for fast internal research views.
- React/Next.js only if the dashboard grows into a serious product UI.

Do not start with the UI. Start with the ledger, market-data ingestion, replay, and risk controls.

## Staged Plan

### Stage 1: Foundation

- Create the internal data model.
- Add typed schemas for market events, signals, orders, fills, positions, and experiment records.
- Add database migrations.
- Add Alpaca paper credentials.
- Fetch historical bars.
- Stream live quotes/trades for a tiny symbol set.
- Record all timestamps.
- Build the ledger.
- Add data provenance fields to every stored event.

### Stage 2: Replay

- Store replayable market data.
- Query replay inputs through DuckDB when using Parquet archives.
- Run simple strategies against historical event streams.
- Produce consistent metrics.
- Compare against benchmarks such as SPY buy-and-hold.
- Record every run in the experiment registry.

### Stage 3: Real-Time Paper Trading

- Run strategies during market hours against live data.
- Submit paper orders through Alpaca.
- Compare expected fills, broker-reported fills, and internal ledger state.
- Track slippage assumptions separately from realized paper fills.
- Reconcile Alpaca paper account state against the internal ledger.

### Stage 4: Better Data

- Upgrade from IEX-only data to SIP/full-market data before trusting results.
- Re-run model comparisons.
- Validate whether earlier results survive better data.
- Promote only results that are reproducible under the better data feed.

### Stage 5: Limited Live Trial

- Only consider live money after a model survives backtesting, real-time paper trading, and review.
- Start with manual approval.
- Start with very small size.
- Keep the kill switch active.
- Add Robinhood or another live broker only as an adapter, not as the core system.

## Current Recommendation

Use Alpaca now.

Use it because it is the strongest first-stage match for real-time paper trading with real market data and broker-style order mechanics.

Do not treat free IEX data as enough for final conclusions, serious model ranking, or funding decisions.

Do not connect Robinhood Agentic Trading until the project has proven strategies, strong risk controls, and a clear live-trading promotion process.

Do not connect any live-money broker until the internal ledger, risk engine, data provenance, and experiment registry are working reliably.
