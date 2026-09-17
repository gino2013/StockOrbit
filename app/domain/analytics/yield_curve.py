"""US Treasury yield curve - the classic short-rate-vs-long-rate macro
reference, most commonly watched for inversions (a short maturity yielding
more than a long one - historically, though not always, a recession
signal). Pure information display, not a forecast or investment advice.

Yahoo/yfinance quotes these Treasury yield indices directly in percent
(e.g. 4.86 means 4.86%), not multiplied by 10 or as a decimal fraction -
verified against live data before writing this, not assumed.
"""

import pandas as pd

from app.infrastructure import market_data

# (display label, years to maturity, yfinance symbol)
MATURITIES = [
    ("13 週", 0.25, "^IRX"),
    ("5 年", 5, "^FVX"),
    ("10 年", 10, "^TNX"),
    ("30 年", 30, "^TYX"),
]


def _curve_from_row(row: pd.Series) -> list[dict]:
    """A maturity Yahoo has no data for on this row is skipped, not
    zero-filled - a gap is honest, a fabricated 0% yield would look like a
    real (and wildly abnormal) data point."""
    return [
        {"label": label, "years": years, "yield_pct": float(row[sym])}
        for label, years, sym in MATURITIES
        if sym in row.index and not pd.isna(row[sym])
    ]


def is_inverted(curve: list[dict]) -> bool | None:
    """True if the shortest maturity yields more than the longest -
    None (not False) when there aren't at least 2 points to compare."""
    if len(curve) < 2:
        return None
    by_years = sorted(curve, key=lambda p: p["years"])
    return by_years[0]["yield_pct"] > by_years[-1]["yield_pct"]


def build_yield_curve(compare_months_ago: int | None = None) -> dict:
    """Today's (most recent trading day's) yield curve, optionally with a
    second curve from `compare_months_ago` months back for an eyeball
    comparison of how the curve's shape has changed."""
    symbols = [sym for _, _, sym in MATURITIES]
    prices = market_data.download_close(symbols, period="2y")
    prices = prices.dropna(how="all").ffill().dropna(how="all")
    if prices.empty:
        return {"as_of": None, "current": [], "compare": None, "inverted": None}

    current = _curve_from_row(prices.iloc[-1])

    compare = None
    if compare_months_ago:
        target_date = prices.index[-1] - pd.DateOffset(months=compare_months_ago)
        past_rows = prices[prices.index <= target_date]
        if not past_rows.empty:
            compare = {
                "as_of": past_rows.index[-1].date().isoformat(),
                "values": _curve_from_row(past_rows.iloc[-1]),
            }

    return {
        "as_of": prices.index[-1].date().isoformat(),
        "current": current,
        "compare": compare,
        "inverted": is_inverted(current),
    }
