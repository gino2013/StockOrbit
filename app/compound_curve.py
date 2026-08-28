"""Actual compound-growth curve vs smooth constant-rate curves, using the
geometric mean (CAGR) — not the arithmetic mean — because the geometric mean
is the only "average annual rate" whose compounding reproduces the real
total return. The arithmetic mean of a series of returns systematically
overstates the true compounded result whenever returns vary year to year,
and the overstatement grows with volatility. Both smooth curves are shown
side by side (geometric = correct, arithmetic = cautionary contrast) and
extended past the historical range as a projection, so the gap between
"what actually happened" and "what a naive average implies" stays visible
into the future too — not investment advice, just what the math says if the
past rate (however computed) continued.
"""

import yfinance as yf


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

    return {
        "historical_periods": historical_periods,
        "future_periods": future_periods,
        "geometric_mean": geometric_mean,
        "arithmetic_mean": arithmetic_mean,
        # Real path only covers the historical range — there's no "actual"
        # data for the future, that's the entire point of the projection.
        "real_path": compound_path(returns, initial_value),
        # Both smooth paths span historical+future in one continuous curve:
        # over the historical range this shows how each average compares to
        # what really happened; past that point it's a projection.
        "geometric_path": smooth_path(geometric_mean, total_periods, initial_value),
        "arithmetic_path": smooth_path(arithmetic_mean, total_periods, initial_value),
    }


def fetch_annual_returns(symbol: str, start_year: int, end_year: int) -> list[float]:
    """One return per calendar year from start_year to end_year: the first
    trading day of start_year is the baseline, each year's last trading day
    is that year's closing value.
    """
    history = yf.download(
        symbol,
        start=f"{start_year}-01-01",
        end=f"{end_year + 1}-01-01",
        auto_adjust=True,
        progress=False,
    )["Close"]
    if hasattr(history, "columns"):
        history = history.iloc[:, 0]
    history = history.dropna()
    if history.empty:
        return []
    yearly_last = history.groupby(history.index.year).last()
    prices = [float(history.iloc[0])] + [float(v) for v in yearly_last]
    return [prices[i + 1] / prices[i] - 1 for i in range(len(prices) - 1)]
