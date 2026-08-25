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
    quantities = pd.Series(holdings)
    return (data[symbols] * quantities).sum(axis=1)


def resample_for_display(series: pd.Series, granularity: str) -> pd.Series:
    freq = _RESAMPLE_FREQ.get(granularity)
    return series.resample(freq).last().dropna() if freq else series
