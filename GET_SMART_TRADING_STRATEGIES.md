# Get Smart Phase: Trading Strategy Research Guide

Last updated: 2026-05-30

## Purpose of This Document

This is the research foundation for the trading project. The goal of the "get smart" phase is to become careful, skeptical, and well-informed before we build trading models or risk real money.

We are not trying to become gamblers with better dashboards. We are trying to build a disciplined trading research lab that can test hypotheses with real market data, fake money, honest measurement, and strong risk controls.

This document summarizes credible strategy categories, trading horizons, AI-era opportunities, major risks, and model hypotheses we can later convert into paper-trading experiments.

Nothing in this document is financial advice. It is a research plan for educational and software-development purposes.

## Source Standards

For this phase, we should treat credibility as a feature of the system.

Preferred sources:

- Regulators and investor-protection organizations, especially the SEC, Investor.gov, and FINRA.
- Peer-reviewed or widely cited academic finance papers.
- Established research organizations and index providers with transparent methodology.
- Practitioner books from serious quantitative investors, academics, or market-structure experts.
- Primary source data, such as exchange data, SEC filings, company fundamentals, corporate actions, and broker execution logs.

Sources to avoid as decision drivers:

- Social media claims about easy money.
- Unverified trading influencers.
- Courses or newsletters that profit from selling certainty.
- Screenshots of returns without audited statements, risk metrics, drawdowns, or survivorship context.
- AI-generated investment claims that are not tied back to primary sources.

The SEC, FINRA, and NASAA specifically warn that AI can be used in investment fraud and that AI-generated information can be false or misleading. We should use AI as a research and engineering tool, not as an oracle.

## First Principles

### 1. Markets Are Competitive

Every trade has someone on the other side. In liquid stocks, that counterparty may be a market maker, hedge fund, quant fund, institution, or another trader with better data, lower latency, lower costs, or more experience.

This does not mean trading is impossible. It means we must assume any edge is small, unstable, and expensive to prove.

### 2. Costs Matter

Trading performance is not gross return. It is return after:

- Bid-ask spread.
- Slippage.
- Commissions and fees.
- Market impact.
- Borrow costs for shorting.
- Margin interest.
- Taxes in taxable accounts.
- Data and infrastructure costs.

Many strategies that look strong before costs disappear after realistic costs.

### 3. Risk Is Not a Side Feature

Good trading research measures how returns are earned. A model with high return and catastrophic drawdowns is not robust. A model that survives many market regimes may be more valuable than one that wins spectacularly in a single period.

Important risk dimensions:

- Maximum drawdown.
- Volatility.
- Downside volatility.
- Tail loss.
- Time under water.
- Exposure concentration.
- Leverage.
- Liquidity.
- Turnover.
- Correlation to the market.
- Correlation to our other models.
- Performance during market stress.

### 4. Backtests Lie Unless We Force Them to Tell the Truth

Backtests are necessary, but dangerous. Common failure modes include:

- Look-ahead bias.
- Survivorship bias.
- Overfitting.
- Data snooping.
- Ignoring delisted stocks.
- Ignoring corporate actions.
- Using closing prices that would not have been tradable.
- Ignoring slippage and spread.
- Re-optimizing too often.
- Testing thousands of ideas and reporting only the winner.

Bailey and Lopez de Prado's work on the Deflated Sharpe Ratio highlights a central issue: when many strategies are tested, the best backtest can easily be a statistical fluke. Harvey, Liu, and Zhu similarly argue that new factors in financial research need much higher statistical hurdles because so many have been tested.

### 5. Paper Trading Comes Before Funding

Our default path should be:

1. Form a hypothesis.
2. Define the data needed.
3. Backtest with realistic assumptions.
4. Run walk-forward validation.
5. Paper trade with real prices and fake money.
6. Compare against benchmarks and other models.
7. Review risk, explainability, and failure modes.
8. Fund only small, controlled allocations if evidence is strong.

## Trading Horizons

Different horizons are almost different sports. The shorter the horizon, the more execution quality, costs, latency, and noise dominate.

| Horizon | Typical holding period | Main appeal | Main difficulty | Suitability for us |
| --- | --- | --- | --- | --- |
| High-frequency trading | milliseconds to seconds | Market-making and microstructure edges | Requires specialized infrastructure, low latency, exchange connectivity, and deep market microstructure expertise | Avoid |
| Scalping | seconds to minutes | Many small opportunities | Very high cost sensitivity, emotional pressure, execution dependence | Avoid initially |
| Day trading | minutes to same day | No overnight risk, fast feedback | Low signal-to-noise, leverage temptation, costs, stress, competition | Study, but do not start here |
| Swing trading | days to weeks | More signal time, less execution pressure | Gap risk, regime changes, news risk | Good first research area |
| Position trading | weeks to months | Can use fundamentals, trend, macro, and factor data | Slower feedback, drawdowns require patience | Strong first research area |
| Long-term systematic investing | months to years | Lower turnover, more tax and cost efficient | Requires patience and benchmark discipline | Strong baseline and benchmark |
| Event-driven trading | hours to weeks around events | Clear catalysts such as earnings or guidance | Hard event interpretation, crowded trades, gap risk | Useful later |
| Statistical arbitrage | intraday to weeks | Market-neutral potential | Requires strong statistics, stable relationships, cost control | Study after core system works |

## Day Trading vs Longer-Term Trading

### Day Trading

Day trading means buying and selling the same security within the same trading day. The SEC warns that day trading is highly risky, stressful, expensive, and often dependent on borrowed money. Academic evidence from Barber, Lee, Liu, and Odean found that less than 1% of day traders in their Taiwan dataset were able to reliably earn positive abnormal returns net of fees.

Day trading can be attractive because it gives fast feedback and avoids overnight exposure. But the same properties make it dangerous:

- Decisions happen under pressure.
- Small errors compound quickly.
- Costs matter enormously.
- Leverage can magnify losses.
- The trader competes against highly optimized professionals.
- Short-term price movement is extremely noisy.

As of 2026-05-30, U.S. day-trading margin rules are also in transition. FINRA has adopted new intraday margin requirements effective 2026-06-04, with a permitted broker transition period through 2027-10-20. These replace the older pattern day trader framework for firms that migrate. Broker-specific implementation may vary, so any real trading system must check the active broker's current rules before live use.

Project stance: day trading is not our first build target. We can study it and eventually paper trade intraday models, but we should first build a longer-horizon research engine where signals are easier to evaluate and costs are less dominant.

### Swing and Position Trading

Swing and position trading are better initial targets because they allow:

- Daily or hourly data rather than tick-level data.
- More time for signals to play out.
- More explainable hypotheses.
- Easier integration of fundamentals, news, sentiment, and macro context.
- Lower turnover and lower cost drag.
- More manageable engineering complexity.

This does not make them easy. It just makes them a better place to learn.

### Long-Term Systematic Investing

Long-term systematic investing should serve as our baseline. If an active model cannot beat a simple benchmark on a risk-adjusted, after-cost basis, then the model is not adding value.

Useful baselines:

- Buy-and-hold S&P 500 ETF proxy.
- Equal-weighted U.S. stock basket.
- 60/40 stock/bond benchmark.
- Sector ETF rotation benchmark.
- Cash or Treasury bill return.
- Low-cost factor ETF proxy.

## Strategy Families Worth Studying

### 1. Momentum and Trend Following

Hypothesis: assets that have performed well recently may continue to perform well over intermediate horizons because of underreaction, investor behavior, institutional flows, or slow information diffusion.

Evidence base:

- Jegadeesh and Titman documented relative-strength profits over 3- to 12-month horizons in U.S. equities.
- Momentum has been studied widely across equities and other asset classes.

Possible implementation ideas:

- Rank stocks by 3-, 6-, or 12-month returns, excluding the most recent month.
- Buy the top-ranked liquid stocks.
- Apply volatility scaling.
- Exit when rank deteriorates or trend breaks.
- Compare sector-neutral vs unconstrained momentum.

Risks:

- Momentum crashes during sharp reversals.
- Crowding.
- High turnover.
- Trend signals can chase overextended names.
- Works differently across regimes.

Good for us: yes, especially as a first systematic model family.

### 2. Mean Reversion

Hypothesis: prices sometimes overreact in the short term and partially reverse, especially for liquid stocks or ETFs where panic, forced selling, or temporary liquidity imbalances occur.

Possible implementation ideas:

- Buy liquid stocks after unusually large down moves if broader trend remains healthy.
- Use RSI-like or z-score signals, but test them rigorously.
- Focus on ETFs first to reduce single-name news risk.
- Use strict stop-loss and time-stop rules.
- Avoid mean-reverting stocks with major negative news, earnings shocks, fraud allegations, or liquidity collapse.

Risks:

- "Cheap" can get much cheaper.
- Mean reversion can fight real information.
- Small losses can become large losses without exits.
- Averaging down is dangerous if not rule-based.

Good for us: yes, but only with strict risk controls.

### 3. Value, Quality, Profitability, and Investment Factors

Hypothesis: companies with attractive valuations, strong profitability, conservative investment, and quality balance sheets may earn better long-term risk-adjusted returns than expensive, low-quality, speculative companies.

Evidence base:

- Fama and French's three-factor and five-factor models formalized market, size, value, profitability, and investment factors.
- Factor investing has a large research base, but many claimed factors fail under stricter testing.

Possible implementation ideas:

- Rank stocks by value, quality, profitability, and balance-sheet strength.
- Combine fundamentals with price momentum to avoid value traps.
- Use sector-relative rankings.
- Rebalance monthly or quarterly.
- Penalize low liquidity, extreme leverage, and poor earnings quality.

Risks:

- Factors can underperform for years.
- Accounting data can be stale or misleading.
- Value traps.
- Factor crowding.
- Model complexity can hide overfitting.

Good for us: yes, especially for longer-horizon paper portfolios.

### 4. Quality Momentum Blend

Hypothesis: the best candidates may be companies with both strong business quality and positive price momentum. Momentum helps avoid stagnant value traps; quality helps avoid fragile hype stocks.

Possible implementation ideas:

- Score each stock on quality, profitability, debt, earnings stability, and momentum.
- Select stocks with high composite scores.
- Use sector and position caps.
- Rebalance monthly.
- Require liquidity and minimum market cap.

Risks:

- Composite scores can be overfit.
- Strong historical factors can become crowded.
- Quality metrics differ by industry.

Good for us: very strong candidate for early experiments.

### 5. Earnings and Event-Driven Models

Hypothesis: markets may underreact or overreact to earnings surprises, guidance changes, analyst revisions, corporate actions, and other events.

Possible implementation ideas:

- Post-earnings announcement drift model.
- Gap-and-hold model after strong earnings surprise.
- Avoid trading before earnings unless explicitly modeling event risk.
- Use analyst revision data if available.
- Compare reaction strength against volume and historical volatility.

Risks:

- Large overnight gaps.
- Data availability and cost.
- Event definitions can leak future information if not handled carefully.
- Crowded event trades.

Good for us: useful after basic price and fundamentals pipeline exists.

### 6. Sentiment and News Models

Hypothesis: financial text can contain useful information about market expectations, corporate tone, risk, and surprise.

AI relevance:

- Domain-specific language models such as FinBERT were designed for financial sentiment analysis because general language models often miss finance-specific meaning.
- LLMs can help summarize filings, classify news, extract catalysts, and generate structured labels.

Possible implementation ideas:

- Score news sentiment by company and event type.
- Compare sentiment surprise to price reaction.
- Use SEC filing changes, earnings call tone, and management guidance.
- Detect contradiction between positive price trend and deteriorating text signals.
- Use LLMs to produce structured features, not direct buy/sell commands.

Risks:

- News timestamps can be messy.
- Text data can be expensive.
- Sentiment can be backward-looking.
- LLM outputs can hallucinate.
- Social media sentiment is noisy and manipulation-prone.

Good for us: high potential, but only with strong source control and timestamp discipline.

### 7. Statistical Arbitrage and Pairs Trading

Hypothesis: related securities may temporarily diverge and later converge.

Possible implementation ideas:

- ETF pairs or sector pairs before single-stock pairs.
- Cointegration or spread z-score models.
- Market-neutral long/short baskets.
- Beta-neutral pair construction.

Risks:

- Historical relationships break.
- Borrow costs and shorting constraints matter.
- Crowding.
- Requires careful execution and position sizing.
- Correlation is not cointegration.

Good for us: later, after we have solid backtesting and risk systems.

### 8. Regime-Aware Risk Models

Hypothesis: model performance depends on market regime. A strategy that works in calm bull markets may fail in crisis, high-volatility, or sideways markets.

Possible implementation ideas:

- Detect regimes using volatility, trend, breadth, credit spreads, rates, or macro indicators.
- Reduce exposure during high-risk regimes.
- Allocate among strategy models based on regime.
- Build "risk-off" and "risk-on" states.

Risks:

- Regime labels can be obvious only after the fact.
- Too many regime rules can overfit.
- Risk-off models can miss strong rebounds.

Good for us: essential as a risk layer, not necessarily as a standalone alpha model.

### 9. Portfolio Allocation and Model Ensemble

Hypothesis: multiple imperfect models may combine into a more robust system if their errors are not highly correlated.

Possible implementation ideas:

- Run several model portfolios side by side.
- Allocate fake capital based on rolling risk-adjusted performance, drawdown, and correlation.
- Cap exposure to any one model, stock, sector, or factor.
- Use a meta-model to decide model weights.
- Penalize models with high turnover or unstable signals.

Risks:

- The meta-model can overfit even more than the base models.
- Recent winners may mean-revert.
- Correlations rise during market stress.

Good for us: central to the long-term project vision.

### 10. Options Strategies

Hypothesis: options can express views on volatility, direction, skew, and event risk.

Examples:

- Covered calls.
- Cash-secured puts.
- Protective puts.
- Vertical spreads.
- Volatility event trades.

Risks:

- Options are path-dependent.
- Greeks are complex.
- Liquidity and spreads can be poor.
- Short options can create large tail losses.
- Assignment and margin rules matter.
- Backtesting options accurately is much harder than backtesting stocks.

Project stance: study later. Avoid short options, naked options, and leveraged options until the core equity system is mature.

## Risky Strategies to Avoid Initially

We should explicitly avoid these during early development:

- Leveraged day trading.
- Trading on margin with real money.
- Naked short selling.
- Naked options.
- Penny stocks and illiquid microcaps.
- Meme-stock momentum without risk controls.
- Martingale or averaging-down systems.
- "Double down until it works" strategies.
- Strategies based on unverified social media tips.
- High-frequency strategies.
- Strategies that require perfect execution assumptions.
- Strategies with large overnight gap exposure and no plan.
- Models that cannot explain why they entered a trade.
- Models that only work before costs.
- Models optimized across thousands of parameter combinations without multiple-testing correction.

These are not forbidden forever as research topics, but they should not be first-wave candidates for real funding.

## How AI Changes the Opportunity

AI does not make markets easy. It changes what we can build.

### AI Can Help With Research Scale

AI can help us:

- Read and summarize SEC filings.
- Extract structured data from earnings calls.
- Classify news by event type.
- Detect sentiment and tone changes.
- Generate research hypotheses.
- Explain model decisions.
- Identify data-quality anomalies.
- Build test harnesses and simulation tools faster.

### AI Can Help With Prediction, But Must Be Constrained

Machine learning research in asset pricing shows that flexible models such as trees and neural networks can find nonlinear relationships that linear models miss. But the same flexibility increases overfitting risk.

Practical implication: we should use AI and ML, but with:

- Strict train/test separation.
- Walk-forward validation.
- Purged and embargoed cross-validation where labels overlap.
- Multiple-testing correction.
- Realistic trading costs.
- Feature importance and explanation checks.
- Model drift monitoring.
- Out-of-sample paper trading before funding.

### AI Should Create Features, Not Magical Certainty

Good AI uses:

- "The filing language became more cautious."
- "Earnings sentiment improved while guidance worsened."
- "This move is unusually large compared with recent volatility."
- "This model's current drawdown is outside historical expectations."

Bad AI uses:

- "Buy this stock because the chatbot says it will go up."
- "Guaranteed low-risk high return."
- "This strategy worked in a backtest, so it is proven."

### AI Can Power a Model Governance Layer

One of our strongest opportunities is not just building AI traders. It is building an AI-assisted governance system around the traders:

- Every model has a hypothesis card.
- Every trade has an explanation.
- Every paper-trading result is reviewed.
- Every model gets risk limits.
- Every model can be paused automatically.
- Every live-funding decision requires evidence.
- The system watches for drift, overtrading, abnormal losses, and broken assumptions.

This is where we can be genuinely strong: not just smarter models, but smarter supervision.

## Model Hypotheses to Test

The following are candidate hypotheses for future paper-trading experiments.

| ID | Hypothesis | Data needed | Horizon | First test |
| --- | --- | --- | --- | --- |
| H001 | Intermediate-term momentum can outperform a benchmark after costs when applied to liquid large-cap stocks with volatility scaling. | Daily prices, volume, corporate actions | 1-3 months | Top-decile momentum vs S&P 500 |
| H002 | Sector momentum is more robust than single-stock momentum because sector trends persist and single-name risk is lower. | Sector ETF prices, market benchmark | 1-6 months | Rotate among sector ETFs monthly |
| H003 | Short-term mean reversion works better in broad ETFs than individual stocks because single-name news risk is lower. | ETF prices, volatility, volume | 2-10 days | Buy oversold liquid ETFs with time stop |
| H004 | Combining quality and momentum beats either factor alone on a risk-adjusted basis. | Fundamentals, prices, sectors | 1-6 months | Composite score model |
| H005 | Earnings surprises followed by strong price-volume confirmation continue drifting for several weeks. | Earnings dates, estimates, actuals, prices, volume | 2-8 weeks | Post-earnings drift paper portfolio |
| H006 | Negative filing or earnings-call tone predicts underperformance, especially when price momentum is already weakening. | Filings, transcripts, NLP sentiment, prices | 1-6 months | Sentiment plus trend filter |
| H007 | A regime detector can reduce drawdowns by lowering exposure during high-volatility downtrends. | Prices, volatility index, breadth, rates if available | Daily to monthly | Risk-on/risk-off overlay |
| H008 | Pair spreads in highly related ETFs mean-revert more reliably than single-stock pairs. | ETF prices, spreads, volatility | Days to weeks | Cointegration or z-score ETF pairs |
| H009 | A model ensemble can outperform individual models by allocating more to models with strong recent risk-adjusted performance and low correlation. | All model returns, drawdowns, correlations | Monthly | Paper allocation engine |
| H010 | LLM-generated event labels improve news-based models when the labels are tied to verified sources and timestamps. | News, filings, timestamps, prices | Days to weeks | Human-audited event classifier |
| H011 | Avoiding low-quality speculative stocks improves momentum model drawdowns. | Fundamentals, prices | 1-6 months | Momentum with quality exclusion |
| H012 | Volatility-adjusted position sizing improves survival more than fixed-dollar sizing. | Prices, volatility, portfolio returns | All horizons | Same signals, different sizing |

## Evaluation Metrics

Every model should be evaluated with the same basic scorecard.

Return metrics:

- Total return.
- Annualized return.
- Excess return vs benchmark.
- Hit rate.
- Average win and average loss.
- Profit factor.

Risk metrics:

- Volatility.
- Maximum drawdown.
- Downside deviation.
- Sharpe ratio.
- Sortino ratio.
- Calmar ratio.
- Tail loss.
- Time under water.

Trading behavior:

- Number of trades.
- Turnover.
- Average holding period.
- Exposure by stock, sector, and strategy.
- Cash usage.
- Slippage sensitivity.
- Capacity estimate.

Robustness:

- Out-of-sample performance.
- Walk-forward performance.
- Performance by market regime.
- Performance by year.
- Parameter sensitivity.
- Performance after higher cost assumptions.
- Correlation to benchmark.
- Correlation to other models.

Explainability:

- Why did the model enter?
- Why did it size the position this way?
- What would make it exit?
- What assumption would invalidate the trade?
- Did the trade match the model's stated hypothesis?

## Research and Backtesting Rules

We should make these rules part of the project's culture.

1. Every model starts with a written hypothesis.
2. No model is judged only by total return.
3. Every backtest includes costs and slippage.
4. Every model is compared against a simple benchmark.
5. Every strategy has train, validation, and test periods.
6. Do not tune on the final test set.
7. Track every experiment, including failures.
8. Penalize complexity unless it clearly improves robustness.
9. Prefer fewer parameters.
10. Require paper trading before funding.
11. Require a maximum loss limit before funding.
12. Assume a model will eventually break.

## Suggested Learning Path

### Stage 1: Market Basics

Learn:

- How stocks trade.
- Order types.
- Bid-ask spreads.
- Market vs limit orders.
- Liquidity.
- Volatility.
- Corporate actions.
- Dividends and splits.
- Settlement.
- Margin basics.

### Stage 2: Risk and Portfolio Basics

Learn:

- Diversification.
- Position sizing.
- Drawdowns.
- Correlation.
- Rebalancing.
- Benchmarking.
- Risk-adjusted returns.

### Stage 3: Strategy Research

Learn:

- Momentum.
- Mean reversion.
- Factor investing.
- Event-driven trading.
- Trend following.
- Statistical arbitrage.
- Regime detection.

### Stage 4: Quantitative Testing

Learn:

- Backtesting mechanics.
- Walk-forward validation.
- Survivorship bias.
- Look-ahead bias.
- Slippage modeling.
- Multiple-testing correction.
- Deflated Sharpe Ratio.
- Paper trading.

### Stage 5: AI and Financial Machine Learning

Learn:

- Feature engineering.
- Regularization.
- Tree-based models.
- Neural networks.
- Time-series validation.
- Financial NLP.
- Model drift.
- Meta-labeling.
- Ensemble methods.
- Explainability.

## Recommended Reading and Source List

### Regulator and Investor-Protection Sources

- [SEC: Day Trading: Your Dollars at Risk](https://www.sec.gov/about/reports-publications/investorpubsdaytipshtm)
- [Investor.gov: Margin Rules for Day Trading](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/margin)
- [FINRA: Understanding the New Intraday Margin Requirements](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements)
- [FINRA: Know What Triggers a Margin Call](https://www.finra.org/investors/insights/margin-calls)
- [Investor.gov: Asset Allocation and Diversification](https://www.investor.gov/introduction-investing/getting-started/asset-allocation)
- [Investor.gov: Artificial Intelligence and Investment Fraud](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/artificial-intelligence-fraud)

### Academic and Research Sources

- Barber and Odean, [Trading is Hazardous to Your Wealth](https://faculty.haas.berkeley.edu/odean/papers/returns/individual_investor_performance_4-99.pdf)
- Barber, Lee, Liu, and Odean, [The Cross-Section of Speculator Skill: Evidence from Day Trading](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=529063)
- Jegadeesh and Titman, [Returns to Buying Winners and Selling Losers](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf)
- Fama and French, [Common Risk Factors in the Returns on Stocks and Bonds](https://terpconnect.umd.edu/~wermers/ftpsite/FAME/Fama_French_%281993%29.pdf)
- Fama and French, [A Five-Factor Asset Pricing Model](https://www.aea.ru/data/pdf/fama2015.pdf)
- Gu, Kelly, and Xiu, [Empirical Asset Pricing via Machine Learning](https://academic.oup.com/rfs/article/33/5/2223/5758276)
- Bailey and Lopez de Prado, [The Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- Harvey, Liu, and Zhu, [... and the Cross-Section of Expected Returns](https://academic.oup.com/rfs/article/29/1/5/1843824)
- Araci, [FinBERT: Financial Sentiment Analysis with Pre-trained Language Models](https://arxiv.org/abs/1908.10063)
- S&P Dow Jones Indices, [SPIVA Scorecards](https://www.spglobal.com/spdji/en/research-insights/spiva/)

### Books Worth Studying

- Benjamin Graham, *The Intelligent Investor*
- Benjamin Graham and David Dodd, *Security Analysis*
- Ernest P. Chan, *Quantitative Trading*
- Ernest P. Chan, *Algorithmic Trading: Winning Strategies and Their Rationale*
- Marcos Lopez de Prado, *Advances in Financial Machine Learning*
- David Aronson, *Evidence-Based Technical Analysis*
- Andrew Lo, *Adaptive Markets*
- Grinold and Kahn, *Active Portfolio Management*
- John J. Murphy, *Technical Analysis of the Financial Markets*

Book selection principle: read books that teach process, risk, testing, and market mechanics. Be cautious with books that mainly sell confidence, secret patterns, or motivational trading psychology without evidence.

## Initial Project Recommendation

Our first models should not be high-speed or high-leverage. The strongest starting path is:

1. Build a clean historical price and portfolio simulation system.
2. Create benchmark portfolios.
3. Implement daily or weekly momentum models.
4. Implement simple mean-reversion models on liquid ETFs.
5. Implement a quality/momentum composite model.
6. Add realistic costs and slippage.
7. Build a model comparison dashboard.
8. Paper trade all models with fake money.
9. Add AI-assisted news and filing features only after the core engine is trustworthy.
10. Build a governance layer that tracks hypotheses, risks, and model drift.

The first real edge we should seek is not a prediction edge. It is a discipline edge: better testing, better records, better risk controls, and better skepticism than the average trader.
