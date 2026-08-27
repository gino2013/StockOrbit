"""On-demand fundamental data for held symbols — objective yfinance metrics
shown as reference data. No buy/sell interpretation added.
"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

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


def fetch_fundamentals(symbols: list[str], debug: bool = False) -> dict[str, dict]:
    result = {}
    for symbol in symbols:
        error = None
        try:
            info = yf.Ticker(symbol).get_info()
        except Exception as e:
            logger.warning("get_info(%s) failed: %s: %s", symbol, type(e).__name__, e)
            info = {}
            error = f"{type(e).__name__}: {e}"
        if not info:
            logger.warning("get_info(%s) returned empty — likely blocked/rate-limited by Yahoo", symbol)
            error = error or "empty response"
        result[symbol] = {field: info.get(field) for field in FIELDS}
        if debug:
            result[symbol]["_error"] = error
    return result
