import pandas as pd
import numpy as np
import quantstats as qs


def run_dynamic_backtest(prices, lookback_months=[3, 6], top_n_sectors=3, core_weight=0.5):

    prices = prices.sort_index()
    # Solves the problem of repeated due to inclusion of etfs mid month.
    prices = prices.resample('ME').last()
    benchmark = 'SPY'
    sectors = [c for c in prices.columns if c != benchmark]
    sectors_set = set(sectors)
    tilt_weight = 1.0 - core_weight
    rebalance_freq = 'QE'

    # --- Config (mirrors momentum-strategy-quantstats.py) ---
    trend_sma_months = 10                 # 10-month SMA
    use_sector_trend = True        # If True: drop sectors below their own 10-month SMA
    cost_per_rebal = 0.0001        # 1bps spread/cost (commission 0 + spread 1bps)

    def is_above_sma(prices, ticker, asof, window_months):
        """True if `ticker` price at `asof` is >= its trailing SMA.
        Returns False if not enough history or price is NaN."""
        # Contains index number of the last month <= asof. If asof is before first date, returns -1.
        # Pad method finds the index of the last date that is less than or equal to the given date (asof).
        end_idx = prices.index.get_indexer([asof], method='pad')[0]
        # If asof is before first date, end_idx will be -1, which is < window_months, so function will return False.
        if end_idx < window_months:
            return False
        window = prices[ticker].iloc[end_idx - window_months + 1:end_idx + 1]
        # If any price in the window is NaN, we can't calculate a valid SMA, so return False.
        # isna() transforms the data into a boolean array where True indicates NaN values.
        # any() checks if there's at least one True in the array, meaning at least one NaN in the window.
        if window.isna().any():
            return False
        current = prices[ticker].iloc[end_idx]
        return current >= window.mean()

    def momentum_score(prices, asof):
        end_idx = prices.index.get_indexer([asof], method='pad')[0]
        end_pos = end_idx - 1  # Use previous month-end price for momentum calculation.
        if end_pos <= 0:  # Not enough history to calculate momentum.
            return pd.Series(dtype=float)
        # End price of all tickers at the end of the previous month.
        # We will compare this to the price N months ago to calculate momentum.
        end_price = prices.iloc[end_pos]

        rank_frames = []
        for m in lookback_months:
            start_pos = end_pos - m
            if start_pos >= 0:
                start_price = prices.iloc[start_pos]
                valid = start_price.notna() & end_price.notna()
                ret = (end_price[valid] / start_price[valid]) - 1.0
                ret = ret[ret.index.isin(sectors_set)]  # Sets are faster than lists for finding elements.
                rank_frames.append(ret.rank(ascending=True))

        # Empty series for when not enough history to calculate the 3-month or 6-month momentum.
        if not rank_frames:
            return pd.Series(dtype=float)
        # Average the ranks across all lookback periods.
        return pd.concat(rank_frames, axis=1).mean(axis=1).dropna()

    def target_weights(prices, asof):
        # Start with benchmark and sector weights at 0.
        weights = pd.Series(0.0, index=[benchmark] + sectors)
        # Calculate momentum scores for all sectors at the given date.
        scores = momentum_score(prices, asof)
        if scores.empty:
            weights[benchmark] = 1.0
            return weights

        # Pick top N by momentum
        candidates = scores.nlargest(min(top_n_sectors, len(scores))).index.tolist()

        # Drop any candidate sector that's below its own SMA.
        if use_sector_trend:
            candidates = [s for s in candidates
                        if is_above_sma(prices, s, asof, trend_sma_months)]

        weights[benchmark] = core_weight
        if candidates:
            per_sector = tilt_weight / len(candidates)
            for s in candidates:
                weights[s] += per_sector
        else:
            # No sector passed trend filter: tilt weight falls back to SPY core.
            weights[benchmark] += tilt_weight

        return weights


    def backtest(prices):
        # Calculate returns.
        rets = prices.pct_change().fillna(0.0)
        # Rebalance on the last day of each quarter, aligned to the price data.
        rebal_dates = [
            prices.index[i]
            for d in pd.date_range(prices.index.min(), prices.index.max(), freq=rebalance_freq)
            # Get_indexer with method='pad' finds the index of the last date in prices.index that is less than or equal to d.
            # Method='pad' means that if d is not exactly in prices.index, it will return the index of the most recent prior date.
            # If d is before the first date in prices.index, it will return -1, which we filter out with the >= 0 condition.
            if (i := prices.index.get_indexer([d], method='pad')[0]) >= 0
        ]
        # Start with 100% in the benchmark at the first date, then apply target_weights at each rebalance date.
        initial_w = pd.Series(0.0, index=prices.columns)
        initial_w[benchmark] = 1.0
        # Build a DataFrame of weights at each rebalance date.
        rebal_rows = {prices.index[0]: initial_w}
        turnover = {}
        prev_w = initial_w
        for d in rebal_dates:
            # Reindex to ensure the new weights align with the price columns.
            new_w = target_weights(prices, d).reindex(prices.columns).fillna(0.0)
            turnover[d] = (new_w - prev_w).abs().sum()
            rebal_rows[d] = new_w
            prev_w = new_w
        # Create a DataFrame where each row corresponds to a rebalance date and each column corresponds to a ticker's weight.
        weight_history = (
            pd.DataFrame(rebal_rows).T
            .reindex(prices.index) # Align the weight history with the price index, filling in any missing dates.
            .ffill()
        )
        # Calculate strategy returns by multiplying the weights by the returns and summing across all assets.
        strat_ret = (weight_history.shift(1).fillna(0.0) * rets).sum(axis=1)
        costs = pd.Series(turnover, dtype=float) * cost_per_rebal
        strat_ret = strat_ret.subtract(costs, fill_value=0.0)

        return {
            'strategy_returns': strat_ret,
            'bmk_returns':      rets[benchmark],
            'turnover':         list(turnover.values()),
            'rebalance_dates':  rebal_dates
        }


    ### Main execution of the backtest and summary generation

    # Run the backtest to get strategy returns, benchmark returns, and turnover.
    result = backtest(prices)

    strat_rets = result['strategy_returns']
    strat_rets.name = 'Strategy'
    bmk_rets = result['bmk_returns']
    bmk_rets.name = benchmark
    active_rets = strat_rets - bmk_rets

    return {
        'labels': [d.strftime('%b %Y') for d in strat_rets.index],
        'cum_data': ((1 + strat_rets).cumprod() * 100).tolist(),
        'bench_data': ((1 + bmk_rets).cumprod() * 100).tolist(),
        'dd_data':       (qs.stats.to_drawdown_series(strat_rets) * 100).tolist(),
        'bench_dd_data': (qs.stats.to_drawdown_series(bmk_rets)   * 100).tolist(),
        'monthly_returns': {
            int(y): [round(v * 100, 2) for v in g.tolist()]
            for y, g in active_rets.groupby(active_rets.index.year)
        },
        'metrics': {
            'Cumulative Return': (f"{(1 + strat_rets).prod() - 1:.2%}",      f"{(1 + bmk_rets).prod() - 1:.2%}"),
            'CAGR':             (f"{qs.stats.cagr(strat_rets, periods=12):.2%}", f"{qs.stats.cagr(bmk_rets, periods=12):.2%}"),
            'Volatility (Ann.)': (f"{qs.stats.volatility(strat_rets, periods=12):.2%}", f"{qs.stats.volatility(bmk_rets, periods=12):.2%}"),
            'Sharpe':           (f"{qs.stats.sharpe(strat_rets, periods=12):.2f}",  f"{qs.stats.sharpe(bmk_rets, periods=12):.2f}"),
            'Sortino':          (f"{qs.stats.sortino(strat_rets, periods=12):.2f}", f"{qs.stats.sortino(bmk_rets, periods=12):.2f}"),
            'VaR (95%)':        (f"{qs.stats.var(strat_rets):.2%}",          f"{qs.stats.var(bmk_rets):.2%}"),
            'CVaR (95%)':       (f"{qs.stats.cvar(strat_rets):.2%}",         f"{qs.stats.cvar(bmk_rets):.2%}"),
            'Max Drawdown':     (f"{qs.stats.max_drawdown(strat_rets):.2%}",        f"{qs.stats.max_drawdown(bmk_rets):.2%}"),
            'Calmar':           (f"{qs.stats.calmar(strat_rets, periods=12):.2f}",              f"{qs.stats.calmar(bmk_rets, periods=12):.2f}"),
            'Avg. Turnover':    (f"{np.mean(list(result['turnover'])):.2%}" if result['turnover'] else "0.00%", "--"),
        }
    }
