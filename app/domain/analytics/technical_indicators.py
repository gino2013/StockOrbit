"""Objective technical indicators per held symbol: moving-average cross
state (50/200 day) and RSI (14 day). Pure backward-looking price-pattern
facts, not a buy/sell signal or prediction of future price movement.
"""

import pandas as pd
from app.infrastructure import market_data

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
SHORT_MA = 50
LONG_MA = 200


def compute_rsi(closes: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ma_cross_state(short_ma: float, long_ma: float, prev_short_ma: float, prev_long_ma: float) -> str:
    if short_ma > long_ma:
        return "golden_cross" if prev_short_ma <= prev_long_ma else "above"
    return "death_cross" if prev_short_ma >= prev_long_ma else "below"


def compute_technical_indicators(symbols: list[str]) -> list[dict]:
    if not symbols:
        return []
    # LONG_MA + RSI_PERIOD trading days of buffer, converted to roughly
    # calendar days (252 trading days/year) so the 200-day MA has enough
    # history to actually compute on the first row we care about.
    period = f"{int((LONG_MA + RSI_PERIOD) * 365 / 252) + 30}d"
    data = market_data.download_close(symbols, period=period)
    if isinstance(data, pd.Series):
        data = data.to_frame(symbols[0])
    data = data.ffill()

    results = []
    for symbol in symbols:
        if symbol not in data:
            continue
        closes = data[symbol].dropna()
        if len(closes) < LONG_MA + 2:
            results.append({"symbol": symbol, "insufficient_history": True})
            continue

        short_ma = closes.rolling(SHORT_MA).mean()
        long_ma = closes.rolling(LONG_MA).mean()
        rsi = compute_rsi(closes)

        cross_state = _ma_cross_state(
            short_ma.iloc[-1], long_ma.iloc[-1], short_ma.iloc[-2], long_ma.iloc[-2]
        )
        latest_rsi = rsi.iloc[-1]
        rsi_value = None if pd.isna(latest_rsi) else float(latest_rsi)
        results.append(
            {
                "symbol": symbol,
                "current_price": float(closes.iloc[-1]),
                "ma_short": float(short_ma.iloc[-1]),
                "ma_long": float(long_ma.iloc[-1]),
                "ma_cross_state": cross_state,
                "rsi": rsi_value,
                "rsi_overbought": rsi_value is not None and rsi_value >= RSI_OVERBOUGHT,
                "rsi_oversold": rsi_value is not None and rsi_value <= RSI_OVERSOLD,
            }
        )
    return results
