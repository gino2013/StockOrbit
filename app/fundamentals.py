"""On-demand fundamental data for held symbols - objective yfinance metrics
shown as reference data. No buy/sell interpretation added.

Known limitation: on Render, Yahoo Finance rejects the crumb-authenticated
quoteSummary API this relies on (401 Invalid Crumb) - an IP-reputation block
on their side that neither retrying nor switching yfinance's cookie strategy
('basic' vs 'csrf') gets around. Works fine locally, and from GitHub Actions
runners (unaffected - see the scheduled cache-refresh workflow), so callers
should fall back to `FundamentalsCache` (app/db.py) when `_fetch_ok` is
False. `debug=1` additionally surfaces the raw error per symbol.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

logger = logging.getLogger(__name__)

FIELDS = [
    "quoteType",
    "sector",
    "industry",
    "marketCap",
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

# ponytail: get_info() is a slow, blocking HTTP round-trip per symbol with
# no batch equivalent in yfinance - fetching a typical 10-15 symbol
# portfolio sequentially took ~7.5s locally. Since this is pure network
# wait (not CPU work), a small thread pool gets all of them in flight at
# once instead of one-at-a-time; upgrade to asyncio only if this stops
# being enough.
_MAX_WORKERS = 8


def _fetch_one(symbol: str, debug: bool) -> tuple[str, dict]:
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
    # {"trailingPegRatio": ...} - none of our FIELDS. So "did this work"
    # means at least one of our fields actually got populated.
    fetch_ok = any(v is not None for v in fields.values())
    if not fetch_ok:
        error = error or "no fields populated (Yahoo likely rejected the auth crumb)"
    fields["_fetch_ok"] = fetch_ok
    if debug:
        fields["_error"] = error
    return symbol, fields


def fetch_fundamentals(symbols: list[str], debug: bool = False) -> dict[str, dict]:
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(symbols))) as pool:
        results = pool.map(lambda s: _fetch_one(s, debug), symbols)
    return dict(results)
