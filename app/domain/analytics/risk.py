"""Historical risk/volatility metrics for held symbols.

This is deliberately NOT a price forecast. Predicting whether a black-swan
event will happen is not something a rule-based tool can honestly do -
instead this surfaces objective, backward-looking risk data (volatility,
drawdown, beta vs a benchmark) plus a known upcoming event (next earnings
date) that historically tends to coincide with bigger moves, so the user can
judge risk for themselves.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pandas as pd
from app.infrastructure import market_data

logger = logging.getLogger(__name__)

from app.domain.analytics.backtest import max_drawdown_details

TRADING_DAYS_PER_YEAR = 252
# ponytail: same reasoning as app/fundamentals.py's pool - Ticker.calendar is
# a per-symbol blocking HTTP call with no batch equivalent, so a small
# thread pool overlaps the network wait instead of doing one at a time.
_MAX_WORKERS = 8


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


def fetch_next_earnings_date(symbol: str) -> tuple[date | None, bool]:
    """Returns (date, fetch_ok). fetch_ok=False means the calendar call itself
    failed/came back empty (Yahoo blocked us) - as opposed to succeeding with
    a genuine "no upcoming earnings" answer - so callers know when it's worth
    falling back to a cached value instead of trusting this "None"."""
    try:
        calendar = market_data.earnings_calendar(symbol)
    except Exception as e:
        logger.warning("calendar(%s) failed: %s: %s", symbol, type(e).__name__, e)
        return None, False
    if not calendar:
        logger.warning("calendar(%s) returned empty - likely blocked/rate-limited by Yahoo", symbol)
        return None, False
    dates = calendar.get("Earnings Date")
    if not dates:
        return None, True
    # Yahoo's calendar routinely includes the *last reported* earnings date
    # alongside the next estimated one, so a plain min() often returns a
    # date in the past. Keep only today-or-later before picking the soonest.
    today = date.today()
    upcoming = [d for d in dates if isinstance(d, date) and d >= today]
    return (min(upcoming), True) if upcoming else (None, True)


def compute_risk_metrics(
    symbols: list[str], benchmark: str = "SPY", earnings_window_days: int = 14
) -> list[dict]:
    if not symbols:
        return []
    tickers = list(dict.fromkeys(symbols + [benchmark]))
    prices = market_data.download_close(tickers, period="1y")
    prices = prices.dropna(how="all").ffill()
    returns = prices.pct_change()

    benchmark_returns = returns[benchmark].dropna() if benchmark in returns else None
    today = datetime.now().date()

    # fetch_next_earnings_date() is a per-symbol blocking HTTP call with no
    # batch equivalent - fetch all of them concurrently up front rather than
    # interleaving one call per loop iteration with the (fast, CPU-only)
    # pandas math below, which would otherwise sit idle waiting on the
    # network the whole time.
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(symbols))) as pool:
        earnings_by_symbol = dict(zip(symbols, pool.map(fetch_next_earnings_date, symbols)))

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
        next_earnings, earnings_fetch_ok = earnings_by_symbol[symbol]
        days_to_earnings = (next_earnings - today).days if next_earnings else None
        results.append(
            {
                "symbol": symbol,
                "volatility_30d": annualized_volatility(symbol_returns, 30),
                "volatility_90d": annualized_volatility(symbol_returns, 90),
                "max_drawdown_1y": max_dd,
                "beta": beta,
                "next_earnings_date": next_earnings.isoformat() if next_earnings else None,
                "earnings_fetch_ok": earnings_fetch_ok,
                "earnings_soon": days_to_earnings is not None
                and 0 <= days_to_earnings <= earnings_window_days,
            }
        )
    return results
