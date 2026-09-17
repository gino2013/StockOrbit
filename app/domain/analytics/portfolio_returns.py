"""Shared helper: reconstruct a synthetic historical daily-return series for
the portfolio by applying *today's* holding weights backward over past
prices - the same "current shares/weights, past prices" approximation used
throughout this app (holdings-history, backtest), not a claim that the
portfolio was actually allocated that way historically.
"""

import pandas as pd

from app.infrastructure import market_data


def weighted_portfolio_returns(symbols: list[str], weights: dict[str, float], period: str = "1y") -> pd.Series:
    if not symbols:
        return pd.Series(dtype=float)
    prices = market_data.download_close(symbols, period=period)
    prices = prices.dropna(how="all").ffill()
    returns = prices[symbols].pct_change().dropna()
    w = pd.Series({s: weights.get(s, 0.0) for s in symbols})
    return (returns * w).sum(axis=1)
