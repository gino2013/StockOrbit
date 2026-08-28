"""On-demand check for held symbols: recent price swings (rule-based,
objective) and news headlines with a lightweight keyword-based sentiment tag.

The sentiment tag is a simple keyword count on the headline text, not real
NLP/LLM judgment — it exists to make an obviously-bullish or obviously-
bearish headline easier to spot at a glance, not as a reliable signal.
Mixed/unclear headlines are left neutral (no color) rather than guessed at.
"""

import re
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

# ponytail: same reasoning as app/fundamentals.py's pool — Ticker.news is a
# per-symbol blocking HTTP call with no batch equivalent, so a small thread
# pool overlaps the network wait instead of doing one symbol at a time.
_MAX_WORKERS = 8

SWING_1D_THRESHOLD = 0.05
SWING_5D_THRESHOLD = 0.10

_BULLISH_WORDS = [
    "beat", "beats", "tops", "topping", "exceed", "exceeds", "surge", "surges",
    "surging", "rally", "rallies", "soar", "soars", "soaring", "jump", "jumps",
    "gain", "gains", "rise", "rises", "rising", "upgrade", "upgrades",
    "upgraded", "outperform", "strong", "robust", "record", "growth", "boom",
    "bullish", "raises guidance", "raises forecast", "better-than-expected",
    "beats expectations", "momentum", "impressive", "strengthens",
]
_BEARISH_WORDS = [
    "miss", "misses", "missed", "falls", "fall", "drop", "drops", "dropping",
    "plunge", "plunges", "plunging", "decline", "declines", "declining",
    "downgrade", "downgrades", "downgraded", "weak", "weakness", "cut", "cuts",
    "lawsuit", "recall", "investigation", "probe", "bearish", "warns",
    "warning", "slump", "slumps", "tumble", "tumbles", "layoffs",
    "bankruptcy", "loss", "losses", "underperform", "disappointing",
    "slashes", "sinks", "sink",
]
_BULLISH_PATTERN = re.compile(r"\b(" + "|".join(_BULLISH_WORDS) + r")\b", re.IGNORECASE)
_BEARISH_PATTERN = re.compile(r"\b(" + "|".join(_BEARISH_WORDS) + r")\b", re.IGNORECASE)


def classify_sentiment(title: str) -> str:
    bullish_hits = len(_BULLISH_PATTERN.findall(title))
    bearish_hits = len(_BEARISH_PATTERN.findall(title))
    if bullish_hits > bearish_hits:
        return "bullish"
    if bearish_hits > bullish_hits:
        return "bearish"
    return "neutral"


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


def _fetch_headlines(symbol: str, limit_per_symbol: int) -> tuple[str, list[dict]]:
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
        headlines.append({
            "title": title,
            "url": url,
            "publisher": publisher,
            "sentiment": classify_sentiment(title),
        })
    return symbol, headlines


def recent_news(symbols: list[str], limit_per_symbol: int = 2) -> dict[str, list[dict]]:
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(symbols))) as pool:
        results = pool.map(lambda s: _fetch_headlines(s, limit_per_symbol), symbols)
    return {symbol: headlines for symbol, headlines in results if headlines}
