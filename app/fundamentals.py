"""On-demand fundamental data for held symbols — objective yfinance metrics
shown as reference data. No buy/sell interpretation added.
"""

import yfinance as yf

FIELDS = [
    "sector",
    "industry",
    "trailingPE",
    "forwardPE",
    "pegRatio",
    "returnOnEquity",
    "profitMargins",
    "revenueGrowth",
    "earningsGrowth",
    "debtToEquity",
    "beta",
    "fiftyTwoWeekLow",
    "fiftyTwoWeekHigh",
    "targetMeanPrice",
    "recommendationKey",
]


def fetch_fundamentals(symbols: list[str]) -> dict[str, dict]:
    result = {}
    for symbol in symbols:
        try:
            info = yf.Ticker(symbol).get_info()
        except Exception:
            info = {}
        result[symbol] = {field: info.get(field) for field in FIELDS}
    return result
