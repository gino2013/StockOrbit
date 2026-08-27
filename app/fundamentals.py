"""On-demand fundamental data for held symbols — objective yfinance metrics
shown as reference data. No buy/sell interpretation added.
"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def _dependency_versions() -> dict[str, str]:
    versions = {"yfinance": yf.__version__}
    try:
        import curl_cffi

        versions["curl_cffi"] = curl_cffi.__version__
    except Exception as e:
        versions["curl_cffi"] = f"unavailable: {e}"
    return versions


def _try_fetch(symbol: str) -> str | None:
    from yfinance.config import YfConfig

    previous = YfConfig.debug.hide_exceptions
    YfConfig.debug.hide_exceptions = False
    try:
        yf.Ticker(symbol)._quote._fetch(modules=["summaryDetail"])
        return None
    except Exception as e:
        body = getattr(getattr(e, "response", None), "text", "")
        return f"{type(e).__name__}: {e} | body[:300]={body[:300]!r}"
    finally:
        YfConfig.debug.hide_exceptions = previous


def _raw_quote_summary_error(symbol: str) -> dict:
    """yfinance silently swallows the HTTPError from the quoteSummary call
    (YfConfig.debug.hide_exceptions defaults True) and returns None, which is
    why get_info() can come back near-empty with no exception on our side.
    Force it to raise so we can see the real status/body for diagnosis, and
    try forcing the 'csrf' cookie strategy to see if that avoids the error
    some cloud hosts hit with the default 'basic' strategy.
    """
    from yfinance.data import YfData

    basic_error = _try_fetch(symbol)
    YfData()._set_cookie_strategy("csrf")
    csrf_error = _try_fetch(symbol)
    return {"basic": basic_error, "csrf": csrf_error}

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
    if debug:
        result["_versions"] = _dependency_versions()
        result["_raw_quote_summary_error"] = _raw_quote_summary_error(symbols[0]) if symbols else None
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
            result[symbol]["_key_count"] = len(info)
            result[symbol]["_sample_keys"] = sorted(info.keys())[:15]
    return result
