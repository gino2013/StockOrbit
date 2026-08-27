"""Historical risk/volatility metrics for held symbols.

This is deliberately NOT a price forecast. Predicting whether a black-swan
event will happen is not something a rule-based tool can honestly do —
instead this surfaces objective, backward-looking risk data (volatility,
drawdown, beta vs a benchmark) plus a known upcoming event (next earnings
date) that historically tends to coincide with bigger moves, so the user can
judge risk for themselves.
"""

from datetime import date, datetime

import pandas as pd
import yfinance as yf

from app.backtest import max_drawdown_details

TRADING_DAYS_PER_YEAR = 252


def annualized_volatility(returns: pd.Series, window: int) -> float | None:
    recent = returns.tail(window)
    if len(recent) < 2:
        return None
    return float(recent.std() * (TRADING_DAYS_PER_YEAR**0.5))


def beta_vs_benchmark(returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 30:
        return None
    variance = aligned.iloc[:, 1].var()
    if not variance:
        return None
    return float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]) / variance)


def _next_earnings_date(symbol: str) -> date | None:
    try:
        calendar = yf.Ticker(symbol).calendar
        dates = calendar.get("Earnings Date") if calendar else None
    except Exception:
        dates = None
    if not dates:
        return None
    return min(d for d in dates if isinstance(d, date))


def compute_risk_metrics(
    symbols: list[str], benchmark: str = "SPY", earnings_window_days: int = 14
) -> list[dict]:
    if not symbols:
        return []
    tickers = list(dict.fromkeys(symbols + [benchmark]))
    prices = yf.download(tickers, period="1y", auto_adjust=True, progress=False)["Close"]
    prices = prices.dropna(how="all").ffill()
    returns = prices.pct_change()

    benchmark_returns = returns[benchmark].dropna() if benchmark in returns else None
    today = datetime.now().date()
    results = []
    for symbol in symbols:
        if symbol not in prices:
            continue
        series = prices[symbol].dropna()
        symbol_returns = returns[symbol].dropna() if symbol in returns else pd.Series(dtype=float)
        max_dd = max_drawdown_details(series)[0] if len(series) >= 2 else None
        beta = (
            beta_vs_benchmark(symbol_returns, benchmark_returns)
            if benchmark_returns is not None
            else None
        )
        next_earnings = _next_earnings_date(symbol)
        days_to_earnings = (next_earnings - today).days if next_earnings else None
        results.append(
            {
                "symbol": symbol,
                "volatility_30d": annualized_volatility(symbol_returns, 30),
                "volatility_90d": annualized_volatility(symbol_returns, 90),
                "max_drawdown_1y": max_dd,
                "beta": beta,
                "next_earnings_date": next_earnings.isoformat() if next_earnings else None,
                "earnings_soon": days_to_earnings is not None
                and 0 <= days_to_earnings <= earnings_window_days,
            }
        )
    return results
