"""Single-symbol quote detail page - price history chart + the same snapshot
stats Google Finance's per-stock page shows. Objective data, no advice.

Three sources, layered by how resilient they need to be to Render's Yahoo
quoteSummary block (see app/infrastructure/fundamentals.py):

- open/day-high/day-low/price come from `today_ohlc()` - a plain
  `ticker_history(period="1d")` bar. That's the *unblocked* endpoint, so
  these never need a fallback and are never shown stale.
- market cap (or totalAssets for ETFs, which have no marketCap) / trailing
  PE / 52-week range / name / exchange / currency / dividend all come from
  the caller's fetch_fundamentals() (with its usual repo.fundamentals_cache()
  fallback) - these move slowly enough that a few-day-old cached value is
  still honest, and that cache is what actually survives Render's block.
- `fetch_quote()` (a raw, uncached quoteSummary call) only fills in when
  fundamentals has nothing at all - e.g. a symbol nobody holds, so the
  scheduled cache-refresh job (which only covers held symbols) never
  populated it. No fallback of its own: if Yahoo blocks it too, these
  just show "-"/the bare symbol rather than something misleading.
"""

from app.infrastructure import market_data

PERIODS = {
    "1d": dict(period="1d", interval="5m"),
    "5d": dict(period="5d", interval="15m"),
    "1mo": dict(period="1mo", interval="1d"),
    "6mo": dict(period="6mo", interval="1d"),
    "ytd": dict(period="ytd", interval="1d"),
    "1y": dict(period="1y", interval="1d"),
    "5y": dict(period="5y", interval="1wk"),
    "max": dict(period="max", interval="1mo"),
}

def price_history(symbol: str, period: str) -> list[dict]:
    if period not in PERIODS:
        raise ValueError(f"未知的區間: {period}")
    hist = market_data.ticker_history(symbol, **PERIODS[period]).dropna(subset=["Close"])
    return [{"t": ts.isoformat(), "close": round(float(c), 4)} for ts, c in hist["Close"].items()]


def today_ohlc(symbol: str) -> dict:
    try:
        hist = market_data.ticker_history(symbol, period="1d").dropna(subset=["Close"])
    except Exception:
        return {}
    if hist.empty:
        return {}
    row = hist.iloc[-1]
    return {
        "open": float(row["Open"]), "day_high": float(row["High"]),
        "day_low": float(row["Low"]), "price": float(row["Close"]),
    }


def fetch_quote(symbol: str) -> dict:
    try:
        return market_data.ticker_info(symbol)
    except Exception:
        return {}


def build_stock_detail(symbol: str, fundamentals: dict, quote: dict, ohlc: dict, history: list[dict]) -> dict:
    price = ohlc.get("price")
    if price is None:
        price = quote.get("currentPrice") or quote.get("regularMarketPrice")
    if price is None and history:
        price = history[-1]["close"]

    start_price = history[0]["close"] if history else None
    change_abs = change_pct = None
    if price is not None and start_price:
        change_abs = price - start_price
        change_pct = change_abs / start_price

    dividend_rate = fundamentals.get("dividendRate")
    if dividend_rate is None:
        dividend_rate = quote.get("dividendRate")
    return {
        "symbol": symbol,
        "name": fundamentals.get("longName") or quote.get("longName") or quote.get("shortName") or symbol,
        "exchange": fundamentals.get("exchange") or quote.get("exchange"),
        "currency": fundamentals.get("currency") or quote.get("currency"),
        "price": price,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "open": ohlc.get("open") if ohlc.get("open") is not None else (quote.get("open") or quote.get("regularMarketOpen")),
        "day_high": ohlc.get("day_high") if ohlc.get("day_high") is not None else (quote.get("dayHigh") or quote.get("regularMarketDayHigh")),
        "day_low": ohlc.get("day_low") if ohlc.get("day_low") is not None else (quote.get("dayLow") or quote.get("regularMarketDayLow")),
        "market_cap": fundamentals.get("marketCap") or fundamentals.get("totalAssets") or quote.get("marketCap") or quote.get("totalAssets"),
        "trailing_pe": fundamentals.get("trailingPE") or quote.get("trailingPE"),
        "dividend_rate": dividend_rate,
        "dividend_quarterly": (dividend_rate / 4) if dividend_rate else None,
        "fifty_two_week_high": fundamentals.get("fiftyTwoWeekHigh") or quote.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": fundamentals.get("fiftyTwoWeekLow") or quote.get("fiftyTwoWeekLow"),
        "history": history,
    }


def demo() -> None:
    history = [{"t": "2026-01-01", "close": 100.0}, {"t": "2026-01-02", "close": 110.0}]
    fundamentals = {"marketCap": 5000.0, "trailingPE": 20.0, "fiftyTwoWeekHigh": 120.0, "fiftyTwoWeekLow": 90.0}
    quote = {"longName": "Test Corp", "dividendRate": 4.0}
    ohlc = {"open": 108.0, "day_high": 111.0, "day_low": 107.0, "price": 110.0}

    result = build_stock_detail("TEST", fundamentals, quote, ohlc, history)
    assert result["price"] == 110.0
    assert result["change_abs"] == 10.0
    assert abs(result["change_pct"] - 0.1) < 1e-9
    assert result["dividend_quarterly"] == 1.0
    assert result["market_cap"] == 5000.0
    assert result["open"] == 108.0

    # Yahoo blocks quoteSummary (the Render issue) but the unblocked history
    # endpoint still works -> price/open/day-range survive from ohlc alone,
    # only the quoteSummary-only fields (name/PE/market cap/dividend) go blank.
    blocked = build_stock_detail("TEST", {}, {}, ohlc, history)
    assert blocked["price"] == 110.0
    assert blocked["open"] == 108.0
    assert blocked["name"] == "TEST"
    assert blocked["market_cap"] is None
    assert blocked["dividend_quarterly"] is None

    # everything blocked, not even a history bar (bad symbol) -> no crash.
    empty = build_stock_detail("BAD", {}, {}, {}, [])
    assert empty["price"] is None
    assert empty["change_pct"] is None

    # a symbol nobody holds (so the scheduled cache-refresh job never wrote
    # a fundamentals_cache row) but the live quoteSummary call still worked
    # -> fetch_quote() fills the gap.
    uncached = build_stock_detail("TEST", {}, {"marketCap": 999.0, "dividendRate": 2.0}, ohlc, history)
    assert uncached["market_cap"] == 999.0
    assert uncached["dividend_quarterly"] == 0.5

    # an ETF: no marketCap anywhere, only totalAssets (its AUM).
    etf = build_stock_detail("QQQ", {"totalAssets": 12345.0}, {}, ohlc, history)
    assert etf["market_cap"] == 12345.0

    from unittest.mock import patch
    with patch.object(market_data, "ticker_info", side_effect=RuntimeError("blocked")):
        assert fetch_quote("TEST") == {}
    with patch.object(market_data, "ticker_history", side_effect=RuntimeError("blocked")):
        assert today_ohlc("TEST") == {}


if __name__ == "__main__":
    demo()
    print("ok")
