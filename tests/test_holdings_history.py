import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.domain.analytics.holdings_history import parse_weights, resample_for_display


def demo():
    series = pd.Series(
        range(1, 91), index=pd.date_range("2026-01-01", periods=90, freq="D"), dtype=float
    )

    daily = resample_for_display(series, "D")
    assert len(daily) == 90

    monthly = resample_for_display(series, "M")
    assert len(monthly) == 3
    assert monthly.iloc[-1] == series.iloc[-1]

    assert parse_weights("QQQ") == {"QQQ": 1.0}
    assert parse_weights("QQQ:0.6,VOO:0.4") == {"QQQ": 0.6, "VOO": 0.4}
    assert parse_weights(" qqq : 0.6 , voo : 0.4 ") == {"QQQ": 0.6, "VOO": 0.4}
    assert parse_weights("") == {}


if __name__ == "__main__":
    demo()
    print("OK")
