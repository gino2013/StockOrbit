"""resample_rate_series: bucket a USD/TWD close series to the chart's
granularity, taking each bucket's last close. See app/domain/analytics/fx_history.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.domain.analytics.fx_history import resample_rate_series


def demo():
    # ~14 months of business days so W/M/Q/H/A all have >1 bucket.
    idx = pd.bdate_range("2025-01-01", "2026-03-01")
    series = pd.Series([30.0 + i * 0.01 for i in range(len(idx))], index=idx)

    daily = resample_rate_series(series, "D")
    assert len(daily) == len(series)
    assert daily[0] == {"date": "2025-01-01", "rate": 30.0}
    # last close carried through, rounded to 4dp
    assert daily[-1]["rate"] == round(series.iloc[-1], 4)

    # coarser granularities have strictly fewer points, still last-in-bucket.
    weekly = resample_rate_series(series, "W")
    monthly = resample_rate_series(series, "M")
    quarterly = resample_rate_series(series, "Q")
    half = resample_rate_series(series, "H")
    yearly = resample_rate_series(series, "A")
    assert len(daily) > len(weekly) > len(monthly) > len(quarterly) >= len(half) >= len(yearly) >= 1

    # first monthly point is Jan 2025's last trading day's rate
    jan_2025 = series[(series.index.year == 2025) & (series.index.month == 1)]
    assert monthly[0] == {"date": "2025-01-31", "rate": round(float(jan_2025.iloc[-1]), 4)}

    # half-year spacing: Q1-25, Q3-25, Q1-26 -> 3 points
    assert len(half) == 3
    # 2025 + 2026 partial -> 2 yearly buckets
    assert len(yearly) == 2

    # unknown granularity falls back to daily rather than raising.
    assert resample_rate_series(series, "ZZZ") == daily


if __name__ == "__main__":
    demo()
    print("OK")
