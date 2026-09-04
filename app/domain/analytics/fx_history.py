"""Resample a USD/TWD close series for the exchange-rate history chart.

Source is yfinance USDTWD=X (an interbank *mid* rate - the same series the
dashboard's "參考匯率" already uses). No retail bank publishes a free
historical buy/sell feed, so there's one line, not two.
"""

import pandas as pd

# pandas offset aliases; "D" (daily) means "no resampling".
_FREQ = {"D": None, "W": "W", "M": "ME", "Q": "QE", "H": "2QE", "A": "YE"}


def resample_rate_series(series: "pd.Series", granularity: str) -> list[dict]:
    """[{date, rate}] at the requested granularity, taking the last close in
    each bucket. Unknown granularity falls back to daily."""
    freq = _FREQ.get(granularity, None)
    s = series if freq is None else series.resample(freq).last().dropna()
    return [{"date": d.strftime("%Y-%m-%d"), "rate": round(float(v), 4)} for d, v in s.items()]
