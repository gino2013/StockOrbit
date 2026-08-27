"""Market-wide trending tickers via yfinance's predefined screeners, with
recent news headlines attached as context. Objective market data — no
"buy this" framing, this isn't personalized investment advice.
"""

import yfinance as yf

from app.market_moves import recent_news

SCREENERS = {
    "day_gainers": "漲幅最大",
    "day_losers": "跌幅最大",
    "most_actives": "成交量最大",
}


def trending_tickers(screener: str, count: int = 10) -> list[dict]:
    if screener not in SCREENERS:
        raise ValueError(f"未知的篩選器: {screener}")
    quotes = yf.screen(screener, count=count).get("quotes", [])
    symbols = [q["symbol"] for q in quotes if q.get("symbol")]
    news = recent_news(symbols, limit_per_symbol=2)
    return [
        {
            "symbol": q.get("symbol"),
            "name": q.get("shortName"),
            "change_pct": q.get("regularMarketChangePercent"),
            "price": q.get("regularMarketPrice"),
            "sector": q.get("sector"),
            "news": news.get(q.get("symbol"), []),
        }
        for q in quotes
    ]
