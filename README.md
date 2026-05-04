# Momentum Sector Rotation Strategy
## Documentation, Methodology and Implementation Review

**Repository:** `github.com/mpusta/flask-app`
**Benchmark:** S&P 500 (proxy: SPY)
**Implementation:** Flask web app + monthly EOD pipeline + quarterly-rebalanced backtest engine
**Dependencies (libraries, APIs):** flask, gunicorn, pandas, numpy, requests, quantstats, python-dotenv, EODHD API

This document describes the strategy and its implementation. Open questions and recommended next steps for institutional deployment are listed in the appendix.

---

## 1. Executive Summary and Strategy Genesis

### 1.1 Concept

The strategy is a long-only tactical overlay on US equities. It holds a  core position in the S&P 500 (SPY) and tilts the residual capital toward the sector ETFs that are exhibiting the strongest cross-sectional price momentum. The default weight split is 50% core / 50% tilt, with the tilt distributed equally among the top three sectors that pass both a momentum rank and an absolute trend filter. Rebalances happen quarterly, and the underlying signals are recomputed on month-end prices. The universe covers all 11 GICS sectors: Energy, Materials, Industrials, Consumer Discretionary, Consumer Staples, Health Care, Financials, Information Technology, Communication Services, Utilities, and Real Estate. 

The thesis is two-fold:
1. **Cross-sectional momentum persists at the sector level.** Sectors that have outperformed over the past three to six months tend to continue outperforming over the subsequent quarter. This is a well-documented anomaly in US equities (Moskowitz, Grinblatt, 1999).
2. **A simple time-series trend filter materially improves the drawdown profile.** Holding momentum winners during regime breaks (2008, Q1 2020, late 2022 in places) destroys most of the cross-sectional alpha. A 10-month moving-average filter, applied per-sector, avoids the worst regime transitions without requiring a forecasting model.

The project idea was to keep the signal explainable, the parameter set small, and the implementation auditable.

The scope of the project was to cover the following topics, based on initial conversation:
- Dynamic Asset Allocation
- Market Regime
- Backtesting
- Time-series analysis
- Risk-rating
- Dashboarding & Visualization

### 1.2 Ideation

The strategy combines three sources: a podcast I listened to, a book I read, and a paper I came across while researching sectors I was interested in.

#### Core Components

**The Trend Filter (Meb Faber):** Utilizes a 10-month moving average to act as a risk-off switch. This filter aims to mitigate deep drawdowns by exiting positions when the price falls below its long-term average, preserving capital during extended bear markets.

**The Structural Framework (Gary Antonacci)**: Employs Dual Momentum, which combines relative momentum (ranking assets against each other) with absolute momentum (ensuring the asset is actually gaining value). This prevents the portfolio from rotating into the "best of a bad bunch" during market-wide declines.

**The Trading Unit (Moskowitz & Grinblatt)**: Based on their 1999 research, the strategy targets Sector ETFs rather than individual stocks. The paper demonstrates that momentum is primarily an industry-level phenomenon, making sectors the most efficient vehicle for capturing these returns.

The strategy is not novel but becomes a reproductible test of a specific hypothesis: that momentum is best captured at the industry level, gated by an absolute trend check, and protected by a long-term moving average. The goal is to demonstrate a clear process of sourcing academic and practitioner insights to build a disciplined, code-based investment framework.

#### Academic inspiration

**Moskowitz, T. J., & Grinblatt, M. (1999):** "Do Industries Explain Momentum?" The Journal of Finance.
This paper argues that "momentum" (the tendency of winning stocks to keep winning) is largely driven by industries, not just individual stocks. For instance, if tech stocks are doing well, a specific tech stock isn't just rising on its own. It’s riding an industry-wide wave. They found that buying winning industries and selling losing industries was more profitable than picking individual stocks based on price history alone.

**Faber, M. (2007):** "A Quantitative Approach to Tactical Asset Allocation." Journal of Wealth Management.
Meb Faber’s paper introduced a simple, rule-based system to avoid major market crashes like the 2000 dot-com bust. Look at the 10-month average. If the price of an asset is above the average, you buy it. If it falls below, you sell and move to cash.
It’s not necessarily about making more money than the market, but about avoiding major drawdowns. By exiting when the trend turns negative, you protect your capital during bear markets.

**Antonacci, G. (2014):** "Dual Momentum Investing". McGraw-Hill.
Gary Antonacci combined Faber’s approach with a peer-comparison logic. He argued that you should combined two types of momentum.
Relative Momentum: Compare assets against each other and pick the "winner" of the two.
Absolute Momentum: Compare that "winner" against a "risk-free" asset like Treasury bills. If the winner is performing worse than cash, you stay in cash.
The Result: You are always invested in the best-performing sector, but you have an emergency brake that pulls you out of the market entirely if everything starts crashing.

### 1.4 Market Regime Detection

**Plain statement of what is implemented:** the model implements a trend filter first. If a candidate sector's last close is below its trailing 10-month SMA, that sector is dropped from the tilt allocation regardless of its momentum rank.

The function `is_above_sma(prices, ticker, asof, window_months)` handles this. It returns `False` when there is insufficient history, when there is any NaN inside the lookback window, or when the current close is below the window mean. The conservative-on-NaN behavior prevents a recently-listed sector ETF, such as Real Estated listed in October 2015, from receiving allocation before it has 10 months of history.

When the sector trend filter eliminates every candidate, the tilt weight does not stay invested in the failed candidates. It falls back to the SPY core position.

S&P 500 Select Sector SPDR ETFs:
XLC: Communication Services
XLY: Consumer Discretionary
XLP: Consumer Staples
XLE: Energy
XLF: Financials
XLV: Health Care
XLI: Industrials
XLB: Materials
XLRE: Real Estate
XLK: Technology
XLU: Utilities

---

## 2. Quantitative Methodology

### 2.1 Universe and rebalance calendar

| Parameter | Value | Source |
|---|---|---|
| Benchmark | SPY | `strategy_logic.py` |
| Sector universe | XLK, XLV, XLF, XLY, XLP, XLE, XLI, XLB, XLU, XLRE, XLC | `update_csv.py` |
| Data frequency | Monthly (period='m' from EODHD; resampled to month-end) | `update_csv.py`, `strategy_logic.py` |
| Price field | Adjusted close (dividend-adjusted) | `update_csv.py` |
| Rebalance frequency | Quarter-end (`QE` in pandas) | `strategy_logic.py` |
| Initial allocation | 100% SPY at the first observation | `strategy_logic.py` |

The full sector universe (eleven SPDRs) covers the GICS 11-sector partition of the S&P 500 from 2018 onward. Earlier periods have a smaller effective universe because XLRE and XLC did not yet exist. The rebalance is quarterly to limit turnover.

### 2.2 Multi-horizon momentum signal

For each rebalance date `asof`, the procedure is:

1. Locate the index position of the previous month-end. This is the explicit anti-look-ahead step: the signal is computed off prices that were observable strictly before the rebalance.
2. For each lookback `m` in `[3, 6]` (default), compute the ratio `end_price / start_price - 1` for every ticker that has non-null prices at both endpoints.
3. Rank these returns ascending across the sector universe. Rank is the unit of signal: a sector that is +18% over 6 months when every other sector is +25% gets a low rank.
4. Average the per-horizon rank tables, drop the missing values, and select the top N (default 3).

Why ranks instead of raw returns:

- Rank composites are robust to fat tails. A single huge outlier month does not dominate the score the way it would in a return-weighted ranking.
- Averaging across 3M and 6M reduces the sensitivity to the choice of any single lookback. Some production deployments typically extend to four (1M, 3M, 6M, 12M).

### 2.3 Trend filter mechanics

The 10-month SMA is computed inclusively over the trailing 10 months ending at `asof`. The implementation:

- Locates `end_idx`, the integer position of the last index value at or before `asof`.
- Returns `False` if `end_idx < window_months`, which guards the early-history NaN region.
- Returns `False` if any value in the window is NaN.
- Otherwise returns whether the current close is greater than or equal to the window mean.

### 2.4 Dynamic allocation construction (core-tilt)

The portfolio is built as:

```
weight[SPY]      = core_weight                          (default 0.5)
weight[sector_i] = (1 - core_weight) / N_passing        for each sector that
                                                        clears both rank and trend
```

If zero sectors pass the trend filter, the tilt allocation collapses back into the core: `weight[SPY] = core_weight + (1 - core_weight) = 1.0`. The user-facing API exposes four parameters (`l1`, `l2`, `n`, `c`) covering the two lookback months, the top-N count, and the core weight. All four flow from URL query string into `run_dynamic_backtest` without server-side defaults that override the user input, except for the `default=` clauses in the Flask layer.

## 3. Backtesting and Performance Analysis

### 3.1 Engine architecture

The backtest engine is implemented in `strategy_logic.py::backtest()`. Its structure:

1. Build a percent-return matrix from `prices.pct_change().fillna(0.0)`.
2. Generate a calendar of quarter-end rebalance timestamps, projected onto the actual price index using `get_indexer(method='pad')` so that dates which fall on non-trading days are mapped to the last available trading day.
3. Initialize the holdings book at 100% SPY at the first observation.
4. Iterate the rebalance dates. At each one, compute target weights, record turnover (`abs(new - old).sum()`), and store the new vector.
5. Forward-fill the quarter-end weight vectors across the daily (here, monthly) index to produce a continuous holdings panel.
6. Apply a one-period lag (`weight_history.shift(1)`) before multiplying with returns. This is the second anti-look-ahead control: weights set at the close of period t cannot earn the period t return.
7. Subtract turnover times `cost_per_rebal` (default 1 bp) from the strategy return series on rebalance months.

### 3.2 Cost and slippage assumptions

Costs are modelled as a flat 0.0001 (1 bp) charge per unit of turnover at each rebalance, with `turnover = sum(abs(new_weights - prev_weights))`.

 What is **not** modelled:

- **Market impact at scale.** A 1% portfolio shift on a $5bn book is roughly $50m of ETF rotation, which, while still small relative to ADV in the major sector SPDRs, is not free.
- **Tax drag.** Not modelled. A taxable account running quarterly rotation will produce short-term capital gains.
- **Tracking-difference and ETF expense ratios.** SPDR sector ETFs charge ~0.10%; this is implicitly inside the adjusted-close series and does not need a separate accrual.

The 1 bp assumption should be raised to 3-5 bps for any document that an institutional allocator will diligence, or supported with a TCA study from a prime broker.

### 3.3 Look-ahead bias controls

Two explicit anti-look-ahead steps are present:

1. **Signal lag in `momentum_score`.** `end_pos = end_idx - 1` ensures momentum is computed using prices strictly before `asof`.
2. **Holdings lag in `backtest`.** `weight_history.shift(1)` ensures the return for period t is multiplied against the weights that were already in place at the start of period t.

There is one residual subtlety. The trend filter uses the close at `asof` itself, not the prior close. In a strict sense this is acceptable when `asof` is the rebalance date, but a stricter implementation would use the prior bar for the trend filter as well. However, the realized impact on results is small because the SMA is over 10 months.

### 3.4 Risk-adjusted metrics

The output panel emits the following statistics for both the strategy and the benchmark, computed by `quantstats`:

| Metric | Formula sketch | Notes |
|---|---|---|
| Cumulative return | `(1+r).prod() - 1` | Geometric |
| CAGR | annualized geometric return | `periods=12` (monthly) |
| Volatility (annualized) | `r.std() * sqrt(12)` | |
| Sharpe | excess CAGR / annualized vol | risk-free rate left at quantstats default |
| Sortino | excess CAGR / downside deviation | |
| VaR (95%) | historical 5th percentile | monthly |
| CVaR (95%) | mean of returns below VaR | monthly |
| Max Drawdown | min of `cum / cummax - 1` | |
| Calmar | CAGR / abs(MaxDD) | |
| Avg. Turnover | mean of `abs(Δw).sum()` per rebalance | |

The active monthly returns (`strat - bmk`) are also broken out by calendar year.

### 3.5 Visual validation surface

The JSON returned from `/api/refresh` carries the inputs needed for four standard tearsheet visuals:

| JSON key | What it drives |
|---|---|
| `cum_data`, `bench_data`, `labels` | Equity curves, base 100 |
| `dd_data`, `bench_dd_data` | Drawdown chart |
| `monthly_returns` | Active-return heatmap, year-by-month |
| `metrics` | Side-by-side strategy vs benchmark metric table |

The Flask layer (`app.py`) preserves key order in the JSON response (`app.json.sort_keys = False`), which is a small but deliberate UX detail: the metrics table on the front end appears in the order the engine emits them, not alphabetically.

---

## 4. Technical Implementation

### 4.1 Architecture overview

```
EODHD API  ->  update_csv.py  ->  prices.csv  ->  strategy_logic.py
                                                       |
                                                       v
                                              app.py (Flask) ---> tearsheet.html
                                                       |               |
                                                       +<--------------+
                                                       /api/refresh?l1=&l2=&n=&c=
```

The split between `update_csv.py` (offline, run on a schedule) and `app.py` (online, serves user requests) is a deliberate separation of the slow data-acquisition path from the fast computation path. This avoids the web request never blocks on a third-party API.

### 4.2 Data pipeline (`update_csv.py`)

- **Source:** EODHD `/api/eod` endpoint, queried per ticker.
- **Auth:** `EODHD_API_KEY` from environment, loaded via `python-dotenv`.
- **Frequency:** monthly, adjusted close.
- **Universe:** SPY plus eleven sector SPDRs.
- **Date range:** 2000-01-01 to today.
- **Output:** wide CSV with `date` index and one column per ticker.
- **Forward-fill:** `ffill(limit=1)` is applied so that a single missing month does not propagate, but a multi-month gap (which would indicate a real data issue) is preserved as NaN.

### 4.3 Calculation engine (`strategy_logic.py`)

The engine is a single-file pure-pandas implementation. It accepts a price DataFrame and returns a JSON-serializable dict. This allows it tpo be invoked from a Flask request, a Jupyter notebook, a unit test, or a batch job without modification.

### 4.4 Front-end layer (`app.py, tearsheet.html`)

`app.py` mounts two routes:

```
GET /              -> renders tearsheet.html with fund_name, date_range, benchmark
GET /api/refresh   -> runs the backtest with user-supplied parameters
                      query: l1 (int, default 3), l2 (int, default 6),
                             n (int, default 3),  c (float, default 0.5)
                      returns: JSON payload as documented in 3.6
```

The front end is a single Jinja-rendered HTML template (`templates/tearsheet.html`) backed by Chart.js loaded from the jsDelivr CDN. The whole document is one server-rendered page, which means it can be opened, audited, and modified by anyone.

**Interaction model.**

```javascript
document.addEventListener('DOMContentLoaded', () => {
  initCharts();
  runBacktest();          // automatic run on first page load
});
document.getElementById('refreshBtn').addEventListener('click', runBacktest);
```

`runBacktest()` reads the four parameter inputs, calls `/api/refresh?l1=&l2=&n=&c=`, and on receipt updates four UI elements in turn: the KPI grid, the stats table, the heatmap, and both charts. While the request is in flight the button text flips to "Running..." and the button is disabled to prevent re-entry.

**What is loaded once vs per request.** `prices.csv` is parsed once at Flask process startup (`app.py` top level). Each `/api/refresh` call only pays for the backtest computation itself. With ~25 years of monthly data across 12 tickers, a full backtest runs in well under a second on a single core, which is why the application can afford to re-run the entire backtest on every user click rather than caching results.

### 4.5 Deployment (`render.yaml`)

Render.com web service, gunicorn-fronted, Python 3.12.0. Production-safe because Flask's dev server (`app.run(debug=True)` at the bottom of `app.py`) is only invoked when the file is run directly, not when imported by gunicorn.

### 4.6 Code excerpts

**Excerpt 1: the trend filter.** Contains the early-history guard, NaN guard, and inclusive comparison.

```python
def is_above_sma(prices, ticker, asof, window_months):
    """True if `ticker` price at `asof` is >= its trailing SMA.
    Returns False if not enough history or price is NaN."""
    end_idx = prices.index.get_indexer([asof], method='pad')[0]
    if end_idx < window_months:
        return False
    window = prices[ticker].iloc[end_idx - window_months + 1:end_idx + 1]
    if window.isna().any():
        return False
    current = prices[ticker].iloc[end_idx]
    return current >= window.mean()
```

**Excerpt 2: the allocation kernel.** Builds the rank composite and applies the trend filter.

```python
def target_weights(prices, asof):
    weights = pd.Series(0.0, index=[benchmark] + sectors)
    if use_portfolio_trend and not is_above_sma(prices, benchmark, asof, trend_sma_months):
        return weights

    scores = momentum_score(prices, asof)
    if scores.empty:
        weights[benchmark] = 1.0
        return weights

    candidates = scores.nlargest(min(top_n_sectors, len(scores))).index.tolist()

    if use_sector_trend:
        candidates = [s for s in candidates
                      if is_above_sma(prices, s, asof, trend_sma_months)]

    weights[benchmark] = core_weight
    if candidates:
        per_sector = tilt_weight / len(candidates)
        for s in candidates:
            weights[s] += per_sector
    else:
        weights[benchmark] += tilt_weight
    return weights
```

**Excerpt 3: the backtest loop.** Notice the `shift(1)` on the holdings panel and the cost subtraction.

```python
def backtest(prices):
    rets = prices.pct_change().fillna(0.0)
    rebal_dates = [
        prices.index[i]
        for d in pd.date_range(prices.index.min(), prices.index.max(), freq=rebalance_freq)
        if (i := prices.index.get_indexer([d], method='pad')[0]) >= 0
    ]
    initial_w = pd.Series(0.0, index=prices.columns)
    initial_w[benchmark] = 1.0
    rebal_rows = {prices.index[0]: initial_w}
    turnover = {}
    prev_w = initial_w
    for d in rebal_dates:
        new_w = target_weights(prices, d).reindex(prices.columns).fillna(0.0)
        turnover[d] = (new_w - prev_w).abs().sum()
        rebal_rows[d] = new_w
        prev_w = new_w

    weight_history = (pd.DataFrame(rebal_rows).T
                      .reindex(prices.index).ffill())

    strat_ret = (weight_history.shift(1).fillna(0.0) * rets).sum(axis=1)
    costs = pd.Series(turnover, dtype=float) * cost_per_rebal
    strat_ret = strat_ret.subtract(costs, fill_value=0.0)
    return {'strategy_returns': strat_ret,
            'bmk_returns': rets[benchmark],
            'turnover': list(turnover.values()),
            'rebalance_dates': rebal_dates}
```

---


## 5. Challenges, Solutions, and Evolution

### 5.1 Universe survivorship and listing dates

**Hurdle.** XLRE was listed October 2015. XLC was listed June 2018. Including them in a 2000-2025 backtest produces NaN columns for the early years.

**Solution.** Three places in the code handle this:
- `valid = start_price.notna() & end_price.notna()` in the momentum function masks out tickers without two endpoints.
- `if window.isna().any(): return False` in the SMA function refuses to mark a young ETF as in-trend before it has a full lookback window.
- The fallback in `target_weights` reroutes unfilled tilt weight back to SPY rather than leaving the portfolio underinvested.

### 5.2 Mid-month ETF additions and irregular calendars

**Hurdle.** Sector ETFs can be added to the universe partway through a month. If the price panel is built naively, this introduces phantom one-period returns of `(price / 0)` or large jumps from NaN-fill behavior.

**Solution.** Two layers. First, `update_csv.py` requests monthly data directly from EODHD rather than resampling daily data, avoiding partial-month rows. Second, `strategy_logic.py` calls `prices.resample('ME').last()` defensively, so even if the input file gained an irregular row, it is collapsed to a single month-end value.

### 5.3 Cost realism

**Hurdle.** A 1 bp cost is on the optimistic edge for any institutional context.

**Solution.** Accepted as a v1 tradeoff for simplicity. The cost coefficient is a single named constant (`cost_per_rebal`); it is one line to change. A v2 should add a per-sector spread table and either a fixed-impact or a square-root-impact term for capacity studies.

### 5.4 Single-pass overfitting risk

**Hurdle.** The default parameters (3M / 6M lookbacks, top 3, 10-month SMA, 50% core) are reasonable but were not arrived at via walk-forward optimization that is visible in the repo. Any allocator will ask whether they were chosen with hindsight.

**Solution proposed (not yet implemented).** A walk-forward harness around `run_dynamic_backtest` that, for each year t, refits the parameter grid on data through year t-1 and applies the chosen parameters to year t. The Flask UI's parameter controls already provide the manual analogue; the automation is the v2 deliverable.



### 5.6 Version evolution


---


## Appendix: Limitations and Next Steps for Deployment

The following items are gaps that can be improved between a working prototype and the document.

1. **Walk-forward parameter validation.** The current backtest is a single in-sample pass. Required: rolling out-of-sample evaluation with parameters re-selected on each in-sample window.
2. **Factor attribution.** Regress monthly strategy excess returns onto FF5 + UMD (or AQR's Quality-Minus-Junk for completeness). Report residual alpha and t-statistic, not just Sharpe.
3. **Transaction-cost realism.** Replace the flat 1 bp with a realistic cost and show sensitivity of CAGR and Sharpe across the 0-10 bp range.
5. **Regime stress.** Re-run the backtest sliced into 2000-2002, 2007-2009, 2020 Q1, 2022 separately and report the strategy's behavior conditional on these stressed windows.
6. **Risk-rating module.** Replace the missing automated risk classifier with a formal definition (rolling 36M vol, max drawdown, beta to SPY) and a categorical mapping appropriate for the audience.
8. **Look-ahead audit on the trend filter.** Use the prior bar's close for the SMA comparison, not the current bar's, for full strictness.


---






The idea of this project was to 

First of all 


- Dynamic Asset Allocation
- Market Regime
- Regressions
- Backtesting
- Time-series analysis
Time-series and cross-sectional analysis are the two dimensions of data. Time-series tracks one subject over a period (history), while cross-sectional compares many subjects at one moment (peers).
- Risk-rating
- Dashboarding & Visualization

- `requirements.txt`: runtime dependencies
- `render.yaml`: deployment configuration



## Strategy considerations





Academic inspipration

Moskowitz & Grinblatt (1999)
Do Industries Explain Momentum? — Journal of Finance
Demonstrates that momentum is primarily a sector-level phenomenon rather than a stock-picking one. Industries that performed well over the prior 3–12 months continue to outperform in subsequent periods. The foundation for ranking sectors by prior returns and rotating into the top performers.

Faber (2007)
A Quantitative Approach to Tactical Asset Allocation — Journal of Wealth Management
Introduces the 10-month simple moving average as a binary trend filter: hold an asset when it trades above its SMA, move to cash otherwise. Applied across asset classes, this mechanical rule significantly reduced drawdowns relative to buy-and-hold with minimal drag on long-run returns.

Antonacci (2014)
Dual Momentum Investing — McGraw-Hill
Formalises the combination of cross-sectional momentum (ranking assets against each other) with absolute momentum (confirming each asset is in an uptrend before allocating). This dual filter is the direct ancestor of this strategy's approach: rank sectors by momentum, then gate each one through a trend filter before any capital is deployed.


## Back end and front implementation

## Code examples

## Challenges & Solutions

## Changes in versions


## Time management in hours

### Planning (finding a strategy to test)

### Implementation

### Iterations

### Documentation




Can you help me write a documentation on a trading strategy I developed to present it to a hedge fund?


Before starting the project, the ask was to touch the following points:

Dynamic Asset Allocation
Market Regime
Regressions
Backtesting
Time-series modeling
Risk-rating
Dashboarding & Visualization

The final result was: 

https://github.com/mpusta/flask-app


After they saw the app, the follow up was to write a documentation including how I came up with the strategy, back and front end implementation, code examples, challenging and solutions during my work, improvement in version


