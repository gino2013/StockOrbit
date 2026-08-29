"""Actual compound-growth curve vs smooth constant-rate curves, using the
geometric mean (CAGR) - not the arithmetic mean - because the geometric mean
is the only "average annual rate" whose compounding reproduces the real
total return. The arithmetic mean of a series of returns systematically
overstates the true compounded result whenever returns vary year to year,
and the overstatement grows with volatility. Both smooth curves are shown
side by side (geometric = correct, arithmetic = cautionary contrast) and
extended past the historical range as a projection, so the gap between
"what actually happened" and "what a naive average implies" stays visible
into the future too - not investment advice, just what the math says if the
past rate (however computed) continued.
"""

import yfinance as yf

from app.holdings_history import weighted_return_series


def geometric_mean_return(returns: list[float]) -> float:
    """The constant annual rate r such that (1+r)^n == prod(1+returns)."""
    product = 1.0
    for r in returns:
        product *= 1 + r
    return product ** (1 / len(returns)) - 1


def arithmetic_mean_return(returns: list[float]) -> float:
    return sum(returns) / len(returns)


def compound_path(returns: list[float], initial_value: float = 100.0) -> list[float]:
    """Cumulative value after each period. len(result) == len(returns) + 1."""
    path = [initial_value]
    for r in returns:
        path.append(path[-1] * (1 + r))
    return path


def smooth_path(rate: float, periods: int, initial_value: float = 100.0) -> list[float]:
    return [initial_value * (1 + rate) ** t for t in range(periods + 1)]


def build_compound_curve(returns: list[float], future_periods: int, initial_value: float = 100.0) -> dict:
    if not returns:
        raise ValueError("returns must not be empty")
    historical_periods = len(returns)
    total_periods = historical_periods + future_periods

    geometric_mean = geometric_mean_return(returns)
    arithmetic_mean = arithmetic_mean_return(returns)
    geometric_path = smooth_path(geometric_mean, total_periods, initial_value)
    arithmetic_path = smooth_path(arithmetic_mean, total_periods, initial_value)

    return {
        "historical_periods": historical_periods,
        "future_periods": future_periods,
        "geometric_mean": geometric_mean,
        "arithmetic_mean": arithmetic_mean,
        # Real path only covers the historical range - there's no "actual"
        # data for the future, that's the entire point of the projection.
        "real_path": compound_path(returns, initial_value),
        # Both smooth paths span historical+future in one continuous curve:
        # over the historical range this shows how each average compares to
        # what really happened; past that point it's a projection.
        "geometric_path": geometric_path,
        "arithmetic_path": arithmetic_path,
        # The cumulative % implied by compounding each average all the way
        # through the future projection - "累積數字", not just the annual
        # rate - so the user can see e.g. "+1143%" rather than having to
        # mentally compound 18.3%/year themselves.
        "geometric_cumulative_return": geometric_path[-1] / initial_value - 1,
        "arithmetic_cumulative_return": arithmetic_path[-1] / initial_value - 1,
    }


def _annual_returns_from_daily(series, start_year: int, end_year: int) -> list[float]:
    """Shared by fetch_annual_returns() and fetch_portfolio_annual_returns():
    one return per calendar year, first trading day of start_year as the
    baseline, each year's last trading day as that year's close.
    """
    series = series.dropna()
    series = series[(series.index.year >= start_year) & (series.index.year <= end_year)]
    if series.empty:
        return []
    yearly_last = series.groupby(series.index.year).last()
    prices = [float(series.iloc[0])] + [float(v) for v in yearly_last]
    return [prices[i + 1] / prices[i] - 1 for i in range(len(prices) - 1)]


def fetch_annual_returns(symbol: str, start_year: int, end_year: int) -> list[float]:
    history = yf.download(
        symbol,
        start=f"{start_year}-01-01",
        end=f"{end_year + 1}-01-01",
        auto_adjust=True,
        progress=False,
    )["Close"]
    if hasattr(history, "columns"):
        history = history.iloc[:, 0]
    return _annual_returns_from_daily(history, start_year, end_year)


def fetch_portfolio_annual_returns(
    weights: dict[str, float], start_year: int, end_year: int
) -> tuple[list[float], int]:
    """Same idea as fetch_annual_returns() but for a weighted basket (the
    user's target allocation) instead of a single symbol - reuses the
    existing buy-and-hold simulator from the 再平衡策略回測 feature rather
    than duplicating basket-return math here.

    weighted_return_series() inner-joins every symbol's trading history, so
    if any holding IPO'd after start_year (common - a target list mixing
    decade-old ETFs with a 2021 IPO is normal), the usable range silently
    starts wherever the *youngest* holding's history begins, not
    start_year. Returns (returns, actual_start_year) so the caller can be
    upfront about that truncation instead of mislabeling a short recent
    window as if it covered the full requested range.
    """
    series = weighted_return_series(weights, start=f"{start_year}-01-01", end=f"{end_year + 1}-01-01")
    if series.empty:
        return [], start_year
    actual_start_year = max(start_year, series.index.min().year)
    return _annual_returns_from_daily(series, actual_start_year, end_year), actual_start_year


def build_portfolio_compound_curve(
    weights: dict[str, float], start_year: int, end_year: int, future_periods: int, initial_value: float = 100.0
) -> dict | None:
    """None means there's no usable history at all for this basket in the
    requested range (e.g. every holding IPO'd after end_year) - the caller
    should just omit the portfolio line rather than show a broken one.
    """
    returns, actual_start_year = fetch_portfolio_annual_returns(weights, start_year, end_year)
    if not returns:
        return None
    result = build_compound_curve(returns, future_periods, initial_value)
    result["actual_start_year"] = actual_start_year
    result["truncated"] = actual_start_year > start_year
    return result
