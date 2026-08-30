import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import drawdown_periods as dp


def demo():
    # peak 100 -> deep drawdown that never climbs back to 100.
    dates = pd.date_range("2024-01-01", periods=12, freq="30D")
    prices = [100, 90, 70, 80, 85, 90, 92, 94, 96, 98, 99, 99.5]
    fake_data = pd.DataFrame({"AAA": pd.Series(prices, index=dates, dtype=float)})

    with patch.object(dp.yf, "download", return_value={"Close": fake_data}):
        result = dp.find_drawdown_periods("AAA", min_duration_days=30)

    assert result["symbol"] == "AAA"
    assert result["dates"] == [d.strftime("%Y-%m-%d") for d in dates]
    assert result["prices"] == prices
    episodes = result["episodes"]
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep["peak_date"] == dates[0].strftime("%Y-%m-%d")
    assert ep["peak_price"] == 100.0
    assert ep["trough_price"] == 70.0
    assert abs(ep["max_drawdown_pct"] - (-0.30)) < 1e-9
    assert ep["recovered"] is False
    assert ep["recovery_date"] is None
    assert ep["duration_days"] == (dates[-1] - dates[0]).days

    # a series that fully recovers should mark recovered=True with a date
    dates2 = pd.bdate_range("2020-01-01", periods=5)
    dates2 = dates2.append(pd.bdate_range("2021-06-01", periods=1))
    prices2 = [100, 60, 60, 60, 60, 100]
    fake_data2 = pd.DataFrame({"BBB": pd.Series(prices2, index=dates2, dtype=float)})
    with patch.object(dp.yf, "download", return_value={"Close": fake_data2}):
        result2 = dp.find_drawdown_periods("BBB", min_duration_days=30)
    ep2 = result2["episodes"][0]
    assert ep2["recovered"] is True
    assert ep2["recovery_date"] == dates2[-1].strftime("%Y-%m-%d")

    # a dip that recovers well within min_duration_days is normal
    # volatility, not the "months to years" risk this feature is about -
    # should be filtered out entirely.
    dates3 = pd.bdate_range("2023-01-01", periods=5)
    prices3 = [100, 95, 90, 98, 101]
    fake_data3 = pd.DataFrame({"CCC": pd.Series(prices3, index=dates3, dtype=float)})
    with patch.object(dp.yf, "download", return_value={"Close": fake_data3}):
        result3 = dp.find_drawdown_periods("CCC", min_duration_days=30)
    assert result3["episodes"] == []

    # too little history -> raises, doesn't crash silently
    try:
        with patch.object(dp.yf, "download", return_value={"Close": pd.DataFrame({"DDD": [100.0]})}):
            dp.find_drawdown_periods("DDD")
        assert False, "expected ValueError"
    except ValueError:
        pass


if __name__ == "__main__":
    demo()
    print("OK")
