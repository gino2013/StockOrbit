import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from unittest.mock import patch

from app.domain.analytics import holdings_history
from app.domain.analytics.holdings_history import parse_weights, resample_for_display


def late_listing():
    # BBB has no price for the first 3 days (listed mid-window).
    idx = pd.date_range("2026-03-02", periods=6, freq="B")
    prices = pd.DataFrame({
        "AAA": [100, 110, 121, 121, 121, 121],
        "BBB": [None, None, None, 50, 55, 50],
    }, index=idx, dtype=float)
    with patch.object(holdings_history.market_data, "download_close", return_value=prices):
        v = holdings_history.portfolio_value_history({"AAA": 2, "BBB": 4}, "2026-03-02", "2026-03-09")
    # Not truncated to BBB's first day.
    assert len(v) == 6 and v.index[0] == idx[0]
    # Once both are priced, equals shares x close exactly.
    assert abs(v.iloc[3] - (2 * 121 + 4 * 50)) < 1e-9
    assert abs(v.iloc[-1] - (2 * 121 + 4 * 50)) < 1e-9
    # BBB joining adds no jump: day 3->4 return is AAA's own (flat).
    assert abs(v.iloc[3] / v.iloc[2] - 1) < 1e-9
    # Before BBB exists, the curve moves with AAA only (+10%/day).
    assert abs(v.iloc[1] / v.iloc[0] - 1.10) < 1e-9


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
    late_listing()
    print("OK")
