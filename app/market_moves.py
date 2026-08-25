"""On-demand check for held symbols: recent price swings (rule-based,
objective) and raw news headlines (shown as-is — no bullish/bearish
sentiment classification, that would need an LLM to read and judge each
story, which is a separate feature).
"""

import yfinance as yf

SWING_1D_THRESHOLD = 0.05
SWING_5D_THRESHOLD = 0.10


def price_swings(symbols: list[str]) -> list[dict]:
    if not symbols:
        return []
    data = yf.download(symbols, period="10d", auto_adjust=True, progress=False)["Close"]
    data = data.dropna(how="all").ffill().dropna()
    if len(data) < 2:
        return []

    swings = []
    for symbol in symbols:
        series = data[symbol]
        change_1d = series.iloc[-1] / series.iloc[-2] - 1
        change_5d = series.iloc[-1] / series.iloc[max(0, len(series) - 6)] - 1
        notes = []
        if abs(change_1d) >= SWING_1D_THRESHOLD:
            notes.append(f"單日{'大漲' if change_1d > 0 else '大跌'} {abs(change_1d):.1%}")
        if abs(change_5d) >= SWING_5D_THRESHOLD:
            notes.append(f"近 5 個交易日{'累計上漲' if change_5d > 0 else '累計下跌'} {abs(change_5d):.1%}")
        if notes:
            swings.append({"symbol": symbol, "notes": notes})
    return swings


def recent_news(symbols: list[str], limit_per_symbol: int = 2) -> dict[str, list[dict]]:
    result = {}
    for symbol in symbols:
        try:
            items = yf.Ticker(symbol).news or []
        except Exception:
            items = []
        headlines = []
        for item in items[:limit_per_symbol]:
            content = item.get("content", {})
            title = content.get("title")
            if not title:
                continue
            url = (content.get("canonicalUrl") or {}).get("url") or (
                content.get("clickThroughUrl") or {}
            ).get("url")
            publisher = (content.get("provider") or {}).get("displayName", "")
            headlines.append({"title": title, "url": url, "publisher": publisher})
        if headlines:
            result[symbol] = headlines
    return result
