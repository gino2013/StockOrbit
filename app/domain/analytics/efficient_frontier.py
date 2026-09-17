"""Markowitz mean-variance efficient frontier - pure information display,
not an optimizer telling the user what to buy or an investment
recommendation. Random-samples a large number of long-only (no leverage,
no short selling) weight combinations across the given symbols, returns
each as a (volatility, return) point, and marks where the *actual current*
allocation sits relative to that cloud so the user can see for themselves
whether it's near the frontier or well inside it.
"""

import numpy as np
import pandas as pd

from app.infrastructure import market_data

TRADING_DAYS_PER_YEAR = 252
_MIN_HISTORY_DAYS = 30


def _annualized_stats(returns: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    return returns.mean() * TRADING_DAYS_PER_YEAR, returns.cov() * TRADING_DAYS_PER_YEAR


def _portfolio_stats(weights: np.ndarray, mean_returns: pd.Series, cov_matrix: pd.DataFrame) -> tuple[float, float]:
    port_return = float(weights @ mean_returns.to_numpy())
    port_vol = float(np.sqrt(max(0.0, weights @ cov_matrix.to_numpy() @ weights)))
    return port_return, port_vol


def build_efficient_frontier(
    symbols: list[str], current_weights: dict[str, float], n_portfolios: int = 2000, seed: int = 42
) -> dict:
    """`current_weights` need not sum to 1 (e.g. cash left out, or it's the
    raw dollar market values) - it's normalized to the given `symbols`
    subset before plotting its point. Raises ValueError for too few symbols
    or too little shared price history, rather than returning a degenerate
    single-point "frontier"."""
    if len(symbols) < 2:
        raise ValueError("至少需要 2 檔標的才能畫效率前緣")

    prices = market_data.download_close(symbols, period="1y")
    prices = prices.dropna(how="all").ffill().dropna()
    if len(prices) < _MIN_HISTORY_DAYS:
        raise ValueError("歷史資料不足，無法計算效率前緣")
    returns = prices[symbols].pct_change().dropna()

    mean_returns, cov_matrix = _annualized_stats(returns)

    rng = np.random.default_rng(seed)
    n = len(symbols)
    # Dirichlet(1,...,1) samples uniformly over the simplex - long-only
    # weight vectors (no leverage, no shorting) that always sum to exactly 1.
    random_weights = rng.dirichlet(np.ones(n), size=n_portfolios)
    points = [
        dict(zip(("return", "volatility"), _portfolio_stats(w, mean_returns, cov_matrix)))
        for w in random_weights
    ]

    held_total = sum(current_weights.get(s, 0.0) for s in symbols)
    current_point = None
    if held_total:
        normalized = np.array([current_weights.get(s, 0.0) / held_total for s in symbols])
        current_return, current_vol = _portfolio_stats(normalized, mean_returns, cov_matrix)
        current_point = {"return": current_return, "volatility": current_vol}

    return {"symbols": symbols, "points": points, "current": current_point}
