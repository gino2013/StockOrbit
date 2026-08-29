import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import health_dashboard as hd


def demo():
    snapshots = [
        {"symbol": "AAA", "market_value": 6000},
        {"symbol": "BBB", "market_value": 3000},
        {"symbol": "CASH", "market_value": 1000},
    ]

    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    daily_returns = pd.Series([0.01 if i % 2 == 0 else -0.005 for i in range(60)], index=dates)
    aaa = 100 * (1 + daily_returns).cumprod()
    bbb = aaa * 2  # scaling doesn't change returns -> perfectly correlated with AAA
    spy = 100 * (1 + daily_returns * 0.5).cumprod()  # half the swing -> not perfectly correlated
    prices = pd.DataFrame({"AAA": aaa, "BBB": bbb, "SPY": spy})

    with patch.object(hd.yf, "download", return_value={"Close": prices}), \
         patch.object(hd, "beta_vs_benchmark", side_effect=[1.2, 0.6]):
        result = hd.build_health_overview(snapshots)

    assert result["position_count"] == 2  # CASH excluded
    assert abs(result["max_concentration"] - 0.6) < 1e-9  # AAA: 6000/10000
    assert abs(result["avg_correlation"] - 1.0) < 1e-6  # AAA/BBB perfectly correlated by construction
    # weighted beta: AAA 60% * 1.2 + BBB 30% * 0.6 = 0.72 + 0.18 = 0.90
    assert abs(result["portfolio_beta"] - 0.90) < 1e-9

    # fewer than 2 non-cash symbols -> no correlation to average, no crash.
    single_prices = pd.DataFrame({"AAA": aaa, "SPY": spy})
    with patch.object(hd.yf, "download", return_value={"Close": single_prices}), \
         patch.object(hd, "beta_vs_benchmark", return_value=1.0):
        result_one = hd.build_health_overview([{"symbol": "AAA", "market_value": 100}])
    assert result_one["avg_correlation"] is None
    assert result_one["position_count"] == 1

    # missing beta for a symbol -> excluded from the weighted average, not treated as 0.
    with patch.object(hd.yf, "download", return_value={"Close": prices}), \
         patch.object(hd, "beta_vs_benchmark", side_effect=[None, 0.6]):
        result_missing = hd.build_health_overview(snapshots)
    assert abs(result_missing["portfolio_beta"] - 0.30 * 0.6) < 1e-9  # only BBB's term counted

    # no holdings at all -> no crash, everything comes back empty/None.
    result_empty = hd.build_health_overview([{"symbol": "CASH", "market_value": 100}])
    assert result_empty["position_count"] == 0
    assert result_empty["avg_correlation"] is None
    assert result_empty["portfolio_beta"] is None


if __name__ == "__main__":
    demo()
    print("OK")
