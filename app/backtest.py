"""Rebalanced-portfolio backtest against a benchmark, using yfinance price
history. No fees/taxes/slippage modeled - a research approximation, not a
trading simulator.
"""

import pandas as pd
import yfinance as yf

from app.holdings_history import notable_moves, weighted_return_series

# to_period codes (not the "ME"/"QE"/"YE" *anchored offset* aliases) so we can
# group the real trading-day index and take actual observed dates as
# rebalance dates - resample(...).first() instead returns synthetic
# period-end labels (e.g. "2026-07-31") that silently never match a real
# trading day whenever that calendar date falls on a weekend/holiday,
# meaning a whole month's rebalance would get skipped without any error.
_PERIOD_CODES = {"M": "M", "Q": "Q", "A": "Y"}


def rebalance_dates(index: pd.DatetimeIndex, rebalance: str) -> list:
    if rebalance == "none" or rebalance not in _PERIOD_CODES:
        return []
    periods = index.to_period(_PERIOD_CODES[rebalance])
    first_per_period = pd.Series(index, index=periods).groupby(level=0).first()
    return sorted(first_per_period.tolist())[1:]  # skip day 1 - nothing to rebalance yet


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


def run_benchmarks_only(
    benchmarks: list[tuple[str, dict[str, float]]], start: str, end: str, initial_capital: float = 10000
) -> dict:
    """Like run_backtest but skips the user's own portfolio entirely - lets
    benchmark tickers show their full history instead of being truncated to
    whatever date range the portfolio's own (possibly recently-listed)
    holdings support."""
    series = {label: weighted_return_series(bw, start, end) for label, bw in benchmarks}
    aligned = pd.DataFrame(series).dropna()
    if aligned.empty:
        raise ValueError("所選期間沒有足夠的歷史股價資料（例如日期落在未來，或區間內沒有交易日）")

    benchmark_results = []
    for label, _ in benchmarks:
        b = aligned[label] / aligned[label].iloc[0] * initial_capital
        b_dd, _, _ = max_drawdown_details(b)
        b_vol = b.pct_change().std() * 252**0.5
        benchmark_results.append({
            "label": label,
            "value": [round(v, 2) for v in b.tolist()],
            "return": b.iloc[-1] / b.iloc[0] - 1,
            "max_drawdown": b_dd,
            "volatility": None if pd.isna(b_vol) else b_vol,
        })
    return {
        "dates": aligned.index.strftime("%Y-%m-%d").tolist(),
        "benchmarks": benchmark_results,
        "portfolio_excluded": True,
    }


def run_backtest(
    weights: dict[str, float],
    start: str,
    end: str,
    rebalance: str = "M",
    initial_capital: float = 10000,
    benchmarks: list[tuple[str, dict[str, float]]] | None = None,
) -> dict:
    symbols = list(weights.keys())
    data = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    data = data.dropna(how="all").ffill().dropna()
    if len(data) < 2:
        raise ValueError("所選期間沒有足夠的歷史股價資料（例如日期落在未來，或區間內沒有交易日）")
    portfolio = simulate_rebalanced_portfolio(data[symbols], weights, rebalance, initial_capital)
    # Always compute the no-rebalance curve too (when a rebalance frequency
    # was actually chosen) so the chart can show what rebalancing itself
    # bought you, not just the portfolio vs. the benchmark(s).
    no_rebalance = (
        simulate_rebalanced_portfolio(data[symbols], weights, "none", initial_capital)
        if rebalance != "none"
        else None
    )

    benchmarks = benchmarks or [("SPY 100%", {"SPY": 1.0})]
    benchmark_series = {label: weighted_return_series(bw, start, end) for label, bw in benchmarks}
    series = {"portfolio": portfolio, **benchmark_series}
    if no_rebalance is not None:
        series["no_rebalance"] = no_rebalance
    aligned = pd.DataFrame(series).dropna()
    portfolio_aligned = aligned["portfolio"]

    drawdown, peak_date, trough_date = max_drawdown_details(portfolio_aligned)
    portfolio_vol = aligned["portfolio"].pct_change().std() * 252**0.5

    benchmark_results = []
    for label, _ in benchmarks:
        b = aligned[label] / aligned[label].iloc[0] * initial_capital
        b_dd, _, _ = max_drawdown_details(b)
        b_vol = b.pct_change().std() * 252**0.5
        benchmark_results.append({
            "label": label,
            "value": [round(v, 2) for v in b.tolist()],
            "return": b.iloc[-1] / b.iloc[0] - 1,
            "max_drawdown": b_dd,
            "volatility": None if pd.isna(b_vol) else b_vol,
        })

    result = {
        "dates": aligned.index.strftime("%Y-%m-%d").tolist(),
        "portfolio_value": [round(v, 2) for v in portfolio_aligned.tolist()],
        "benchmarks": benchmark_results,
        "total_return": portfolio_aligned.iloc[-1] / portfolio_aligned.iloc[0] - 1,
        "max_drawdown": drawdown,
        "volatility": None if pd.isna(portfolio_vol) else portfolio_vol,
        "drawdown_peak_date": peak_date.strftime("%Y-%m-%d"),
        "drawdown_trough_date": trough_date.strftime("%Y-%m-%d"),
        "rebalance_dates": [
            d.strftime("%Y-%m-%d") for d in rebalance_dates(portfolio_aligned.index, rebalance)
        ],
        "notable_moves": [
            {"date": m["date"].strftime("%Y-%m-%d"), "change": m["change"]}
            for m in notable_moves(portfolio_aligned)
        ],
    }
    if no_rebalance is not None:
        no_rebalance_aligned = aligned["no_rebalance"]
        result["no_rebalance_value"] = [round(v, 2) for v in no_rebalance_aligned.tolist()]
        result["no_rebalance_return"] = (
            no_rebalance_aligned.iloc[-1] / no_rebalance_aligned.iloc[0] - 1
        )
    return result
