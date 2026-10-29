"""Entry check for one symbol right before buying: where today's price sits
inside several lookback windows (1M / 3M / 1Y / 5Y), RSI, and how the
stock historically did over the next 3 months on days whose distance from
the 200-day MA looked like today's. Rule-based facts, not a prediction or
investment advice.
"""

import pandas as pd

from app.domain.analytics.technical_indicators import RSI_OVERBOUGHT, RSI_OVERSOLD, compute_rsi
from app.infrastructure import market_data

WINDOWS = [("1 個月", 21), ("3 個月", 63), ("1 年", 252), ("5 年", 1260)]
HIGH_ZONE = 0.8  # top 20% of the window's range
LOW_ZONE = 0.2
FORWARD_DAYS = 63  # ~3 months
SIMILAR_BAND = 0.05  # +/-5pp around today's distance from the 200-day MA
MA_DAYS = 200


def _zone(position: float) -> str:
    if position >= HIGH_ZONE:
        return "high"
    if position <= LOW_ZONE:
        return "low"
    return "mid"


def window_stats(closes: pd.Series, days: int) -> dict:
    window = closes.iloc[-days:]
    price = float(closes.iloc[-1])
    high, low = float(window.max()), float(window.min())
    position = 0.5 if high == low else (price - low) / (high - low)
    return {
        "days": len(window),
        "high": high,
        "low": low,
        "position": position,
        "zone": _zone(position),
        "from_high": price / high - 1,
        "vs_average": price / float(window.mean()) - 1,
    }


def similar_setups(closes: pd.Series) -> dict | None:
    """Forward 3-month returns on past days whose gap to the 200-day MA was
    within SIMILAR_BAND of today's gap, vs. all days as a baseline."""
    gap = closes / closes.rolling(MA_DAYS).mean() - 1
    forward = closes.shift(-FORWARD_DAYS) / closes - 1
    frame = pd.DataFrame({"gap": gap, "fwd": forward}).dropna()
    today_gap = gap.iloc[-1]
    if frame.empty or pd.isna(today_gap):
        return None
    similar = frame[(frame["gap"] - today_gap).abs() <= SIMILAR_BAND]["fwd"]
    if len(similar) < 20:  # too few samples to say anything
        return None
    return {
        "today_gap": float(today_gap),
        "sample_days": len(similar),
        "median_return": float(similar.median()),
        "win_rate": float((similar > 0).mean()),
        "baseline_median_return": float(frame["fwd"].median()),
        "baseline_win_rate": float((frame["fwd"] > 0).mean()),
    }


def verdict(windows: list[dict], rsi: float | None) -> str:
    # ponytail: simple vote over 1M/3M/1Y zones + RSI; 5Y left out because
    # long uptrends sit near the 5Y high most of the time.
    zones = [w["zone"] for w in windows[:3]]
    if zones.count("high") >= 2 or (rsi is not None and rsi >= RSI_OVERBOUGHT):
        return "high"
    if zones.count("low") >= 2 or (rsi is not None and rsi <= RSI_OVERSOLD):
        return "low"
    return "mid"


def check_entry(symbol: str) -> dict:
    # Ticker.history's last row is today's live bar during market hours.
    history = market_data.ticker_history(symbol, period="10y")
    closes = history["Close"].dropna() if "Close" in history else pd.Series(dtype=float)
    if len(closes) < WINDOWS[0][1]:
        raise ValueError("沒有足夠的歷史股價資料")

    windows = [
        {"label": label, **window_stats(closes, days)}
        for label, days in WINDOWS
        if len(closes) >= days
    ]
    latest_rsi = compute_rsi(closes).iloc[-1]
    rsi = None if pd.isna(latest_rsi) else float(latest_rsi)
    return {
        "symbol": symbol,
        "price": float(closes.iloc[-1]),
        "as_of": closes.index[-1].strftime("%Y-%m-%d"),
        "rsi": rsi,
        "windows": windows,
        "similar": similar_setups(closes),
        "verdict": verdict(windows, rsi),
    }
