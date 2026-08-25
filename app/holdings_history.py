"""Historical value of the *current* holdings — current quantities priced
at past dates via yfinance. Assumes today's share counts were held
throughout the window (no buy/sell history), so it's an approximation for
older positions, not an exact reconstruction.
"""

import pandas as pd
import yfinance as yf

_RESAMPLE_FREQ = {"M": "ME", "Q": "QE", "A": "YE"}  # "D" (daily) needs no resampling


def portfolio_value_history(holdings: dict[str, float], start: str, end: str) -> pd.Series:
    symbols = list(holdings.keys())
    data = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    data = data.dropna(how="all").ffill().dropna()
    if len(data) < 2:
        raise ValueError("所選期間沒有足夠的歷史股價資料（例如日期落在未來，或區間內沒有交易日）")
    quantities = pd.Series(holdings)
    return (data[symbols] * quantities).sum(axis=1)


def resample_for_display(series: pd.Series, granularity: str) -> pd.Series:
    freq = _RESAMPLE_FREQ.get(granularity)
    return series.resample(freq).last().dropna() if freq else series


def weighted_return_series(weights: dict[str, float], start: str, end: str) -> pd.Series:
    """Normalized (starts at 1.0) buy-and-hold value curve for an arbitrary
    weighted basket — for comparing "what if I'd bought X% this / Y% that"
    against the actual portfolio, not for dollar amounts.
    """
    symbols = list(weights.keys())
    data = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    data = data.dropna(how="all").ffill().dropna()
    if len(data) < 2:
        raise ValueError("所選期間沒有足夠的歷史股價資料（例如日期落在未來，或區間內沒有交易日）")
    normalized = data[symbols] / data[symbols].iloc[0]
    return (normalized * pd.Series(weights)).sum(axis=1)


def parse_weights(raw: str) -> dict[str, float]:
    """Parse "QQQ:0.6,VOO:0.4" (or a bare "QQQ", implying 100%) into a
    {symbol: weight} dict. Raises ValueError on a malformed weight."""
    weights: dict[str, float] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            symbol, weight = part.split(":", 1)
            weights[symbol.strip().upper()] = float(weight.strip())
        else:
            weights[part.upper()] = 1.0
    return weights
