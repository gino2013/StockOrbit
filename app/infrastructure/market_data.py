"""The single gateway for yfinance access.

Domain modules import from here instead of `import yfinance` directly, so
every default (`auto_adjust=True`, `progress=False`), every network quirk,
and every "what shape does this actually return" lives in one file. Nothing
here interprets the data - callers still do the cleaning (`ffill`, `dropna`)
and the maths.
"""

import yfinance as yf


def _window(start, end, period) -> dict:
    kw = {}
    if period:
        kw["period"] = period
    if start:
        kw["start"] = start
    if end:
        kw["end"] = end
    return kw


def download_close(symbols, *, start=None, end=None, period=None):
    """`yf.download(...)["Close"]` - the call ~10 modules make. `symbols` may
    be one str or a list; the return matches yfinance (Series for one symbol
    in some versions, DataFrame otherwise) so callers keep their own guards."""
    return yf.download(symbols, auto_adjust=True, progress=False, **_window(start, end, period))["Close"]


def ticker_history(symbol: str, *, start=None, end=None, period=None, auto_adjust: bool = True):
    """Full OHLCV(+Dividends) frame for one symbol - used where the caller
    needs more than the close column (e.g. DRIP needs per-share dividends)."""
    return yf.Ticker(symbol).history(auto_adjust=auto_adjust, **_window(start, end, period))


def earnings_calendar(symbol: str):
    """`yf.Ticker(symbol).calendar` - may raise or return empty when Yahoo
    blocks the request; the caller decides what that means."""
    return yf.Ticker(symbol).calendar


def ticker_news(symbol: str) -> list:
    try:
        return yf.Ticker(symbol).news or []
    except Exception:
        return []


def search_symbols(query: str, max_results: int = 8) -> list:
    return yf.Search(query, max_results=max_results).quotes


def screen(screener: str, count: int = 10) -> list:
    return yf.screen(screener, count=count).get("quotes", [])
