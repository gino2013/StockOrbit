"""Rebalanced-portfolio backtest against a benchmark, using yfinance price
history. No fees/taxes/slippage modeled — a research approximation, not a
trading simulator.
"""

import pandas as pd
import yfinance as yf

# to_period codes (not the "ME"/"QE"/"YE" *anchored offset* aliases) so we can
# group the real trading-day index and take actual observed dates as
# rebalance dates — resample(...).first() instead returns synthetic
# period-end labels (e.g. "2026-07-31") that silently never match a real
# trading day whenever that calendar date falls on a weekend/holiday,
# meaning a whole month's rebalance would get skipped without any error.
_PERIOD_CODES = {"M": "M", "Q": "Q", "A": "Y"}


def rebalance_dates(index: pd.DatetimeIndex, rebalance: str) -> list:
    if rebalance == "none" or rebalance not in _PERIOD_CODES:
        return []
    periods = index.to_period(_PERIOD_CODES[rebalance])
    first_per_period = pd.Series(index, index=periods).groupby(level=0).first()
    return sorted(first_per_period.tolist())[1:]  # skip day 1 — nothing to rebalance yet


def simulate_rebalanced_portfolio(
    prices: pd.DataFrame, weights: dict[str, float], rebalance: str, initial_capital: float
) -> pd.Series:
    symbols = list(prices.columns)
    shares = pd.Series({s: initial_capital * weights[s] / prices[s].iloc[0] for s in symbols})
    dates_to_rebalance = set(rebalance_dates(prices.index, rebalance))

    values = []
    for date, row in prices.iterrows():
        port_value = float((shares * row).sum())
        values.append(port_value)
        if date in dates_to_rebalance:
            shares = pd.Series({s: port_value * weights[s] / row[s] for s in symbols})
    return pd.Series(values, index=prices.index)


def max_drawdown_details(series: pd.Series) -> tuple[float, object, object]:
    running_max = series.cummax()
    drawdown = series / running_max - 1
    trough_date = drawdown.idxmin()
    peak_date = series.loc[:trough_date].idxmax()
    return float(drawdown.loc[trough_date]), peak_date, trough_date


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
    drawdown, peak_date, trough_date = max_drawdown_details(portfolio)

    return {
        "dates": data.index.strftime("%Y-%m-%d").tolist(),
        "portfolio_value": [round(v, 2) for v in portfolio.tolist()],
        "benchmark_value": [round(v, 2) for v in benchmark_series.tolist()],
        "total_return": portfolio.iloc[-1] / initial_capital - 1,
        "benchmark_return": benchmark_series.iloc[-1] / initial_capital - 1,
        "max_drawdown": drawdown,
        "drawdown_peak_date": peak_date.strftime("%Y-%m-%d"),
        "drawdown_trough_date": trough_date.strftime("%Y-%m-%d"),
        "rebalance_dates": [d.strftime("%Y-%m-%d") for d in rebalance_dates(data.index, rebalance)],
    }
