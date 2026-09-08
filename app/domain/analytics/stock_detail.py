"""Single-symbol quote detail page - price history chart + the same snapshot
stats Google Finance's per-stock page shows. Objective data, no advice.

The quote fields (open/day range/market cap/PE/dividend) come from a direct
`market_data.ticker_info()` call rather than fetch_fundamentals(), on
purpose: that function's FIELDS whitelist is tied to FundamentalsCache's DB
columns (the Render Yahoo-quoteSummary-block fallback), and open/day-high/
day-low are inherently "as of today" - showing them from a multi-day-old
cache would be quietly wrong, not just stale. So on Render this page's
quote stats degrade to "-" instead of lying; the price chart is unaffected
since ticker_history() hits a different, unblocked endpoint.
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

PERIOD_LABELS = {
    "1d": "1天", "5d": "5天", "1mo": "1個月", "6mo": "6個月",
    "ytd": "本年迄今", "1y": "1年", "5y": "5年", "max": "最久",
}


def price_history(symbol: str, period: str) -> list[dict]:
    if period not in PERIODS:
        raise ValueError(f"未知的區間: {period}")
    hist = market_data.ticker_history(symbol, **PERIODS[period]).dropna(subset=["Close"])
    return [{"t": ts.isoformat(), "close": round(float(c), 4)} for ts, c in hist["Close"].items()]


def fetch_quote(symbol: str) -> dict:
    try:
        return market_data.ticker_info(symbol)
    except Exception:
        return {}


def build_stock_detail(symbol: str, fundamentals: dict, history: list[dict]) -> dict:
    price = fundamentals.get("currentPrice") or fundamentals.get("regularMarketPrice")
    if price is None and history:
        price = history[-1]["close"]
    start_price = history[0]["close"] if history else None
    change_abs = change_pct = None
    if price is not None and start_price:
        change_abs = price - start_price
        change_pct = change_abs / start_price
    dividend_rate = fundamentals.get("dividendRate")
    return {
        "symbol": symbol,
        "name": fundamentals.get("longName") or fundamentals.get("shortName") or symbol,
        "exchange": fundamentals.get("exchange"),
        "currency": fundamentals.get("currency"),
        "price": price,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "open": fundamentals.get("open") or fundamentals.get("regularMarketOpen"),
        "day_high": fundamentals.get("dayHigh") or fundamentals.get("regularMarketDayHigh"),
        "day_low": fundamentals.get("dayLow") or fundamentals.get("regularMarketDayLow"),
        "market_cap": fundamentals.get("marketCap"),
        "trailing_pe": fundamentals.get("trailingPE"),
        "dividend_rate": dividend_rate,
        "dividend_quarterly": (dividend_rate / 4) if dividend_rate else None,
        "fifty_two_week_high": fundamentals.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": fundamentals.get("fiftyTwoWeekLow"),
        "history": history,
    }


def demo() -> None:
    history = [{"t": "2026-01-01", "close": 100.0}, {"t": "2026-01-02", "close": 110.0}]
    result = build_stock_detail("TEST", {"currentPrice": 110.0, "dividendRate": 4.0}, history)
    assert result["change_abs"] == 10.0
    assert abs(result["change_pct"] - 0.1) < 1e-9
    assert result["dividend_quarterly"] == 1.0

    empty = build_stock_detail("TEST", {}, [])
    assert empty["price"] is None
    assert empty["change_pct"] is None
    assert empty["dividend_quarterly"] is None

    from unittest.mock import patch
    with patch.object(market_data, "ticker_info", side_effect=RuntimeError("blocked")):
        assert fetch_quote("TEST") == {}


if __name__ == "__main__":
    demo()
    print("ok")
