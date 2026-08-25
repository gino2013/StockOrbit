"""Rebalanced-portfolio backtest against a benchmark, using yfinance price
history. No fees/taxes/slippage modeled — a research approximation, not a
trading simulator.
"""

import pandas as pd
import yfinance as yf

# ponytail: pandas resample aliases used directly as the rebalance-frequency
# API ("M"/"Q"/"A"/"none") instead of inventing our own enum.
_REBALANCE_ALIASES = {"M": "ME", "Q": "QE", "A": "YE"}


def simulate_rebalanced_portfolio(
    prices: pd.DataFrame, weights: dict[str, float], rebalance: str, initial_capital: float
) -> pd.Series:
    symbols = list(prices.columns)
    shares = pd.Series({s: initial_capital * weights[s] / prices[s].iloc[0] for s in symbols})

    rebalance_dates: set = set()
    if rebalance != "none":
        freq = _REBALANCE_ALIASES.get(rebalance, rebalance)
        rebalance_dates = set(prices.resample(freq).first().index)

    values = []
    for date, row in prices.iterrows():
        port_value = float((shares * row).sum())
        values.append(port_value)
        if date in rebalance_dates:
            shares = pd.Series({s: port_value * weights[s] / row[s] for s in symbols})
    return pd.Series(values, index=prices.index)


def max_drawdown(series: pd.Series) -> float:
    running_max = series.cummax()
    return float((series / running_max - 1).min())


def run_backtest(
    weights: dict[str, float],
    start: str,
    end: str,
    rebalance: str = "M",
    initial_capital: float = 10000,
    benchmark: str = "SPY",
) -> dict:
    symbols = list(weights.keys())
    data = yf.download(
        symbols + [benchmark], start=start, end=end, auto_adjust=True, progress=False
    )["Close"]
    data = data.dropna(how="all").ffill().dropna()

    portfolio = simulate_rebalanced_portfolio(data[symbols], weights, rebalance, initial_capital)
    bench_shares = initial_capital / data[benchmark].iloc[0]
    benchmark_series = data[benchmark] * bench_shares

    return {
        "dates": data.index.strftime("%Y-%m-%d").tolist(),
        "portfolio_value": [round(v, 2) for v in portfolio.tolist()],
        "benchmark_value": [round(v, 2) for v in benchmark_series.tolist()],
        "total_return": portfolio.iloc[-1] / initial_capital - 1,
        "benchmark_return": benchmark_series.iloc[-1] / initial_capital - 1,
        "max_drawdown": max_drawdown(portfolio),
    }
