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
        fields = {field: info.get(field) for field in FIELDS}
        # info can be non-empty yet still useless: the "complementary" PEG
        # fetch (a different, unauthenticated endpoint) succeeds even when
        # the main quoteSummary call was blocked, leaving a dict with only
        # {"trailingPegRatio": ...} — none of our FIELDS. So "did this work"
        # means at least one of our fields actually got populated.
        fetch_ok = any(v is not None for v in fields.values())
        if not fetch_ok:
            error = error or "no fields populated (Yahoo likely rejected the auth crumb)"
        result[symbol] = fields
        result[symbol]["_fetch_ok"] = fetch_ok
        if debug:
            result[symbol]["_error"] = error
    return result
