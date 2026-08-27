"""On-demand fundamental data for held symbols — objective yfinance metrics
shown as reference data. No buy/sell interpretation added.

Known limitation: on Render, Yahoo Finance rejects the crumb-authenticated
quoteSummary API this relies on (401 Invalid Crumb) — an IP-reputation block
on their side that neither retrying nor switching yfinance's cookie strategy
('basic' vs 'csrf') gets around. Works fine locally, and from GitHub Actions
runners (unaffected — see the scheduled cache-refresh workflow), so callers
should fall back to `FundamentalsCache` (app/db.py) when `_fetch_ok` is
False. `debug=1` additionally surfaces the raw error per symbol.
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
            error = error or "empty response (Yahoo likely rejected the auth crumb)"
        result[symbol] = {field: info.get(field) for field in FIELDS}
        result[symbol]["_fetch_ok"] = bool(info)
        if debug:
            result[symbol]["_error"] = error
    return result
