import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

from app import health_dashboard as hd


def demo():
    snapshots = [
        {"symbol": "AAA", "market_value": 6000},
        {"symbol": "BBB", "market_value": 3000},
        {"symbol": "CASH", "market_value": 1000},
    ]
    fake_corr = {"symbols": ["AAA", "BBB"], "matrix": [[1.0, 0.4], [0.4, 1.0]]}
    fake_risk = [
        {"symbol": "AAA", "beta": 1.2},
        {"symbol": "BBB", "beta": 0.6},
    ]
    with patch.object(hd, "compute_correlation_matrix", return_value=fake_corr), \
         patch.object(hd, "compute_risk_metrics", return_value=fake_risk):
        result = hd.build_health_overview(snapshots)

    assert result["position_count"] == 2  # CASH excluded
    assert abs(result["max_concentration"] - 0.6) < 1e-9  # AAA: 6000/10000
    assert abs(result["avg_correlation"] - 0.4) < 1e-9  # only off-diagonal entries averaged
    # weighted beta: AAA 60% * 1.2 + BBB 30% * 0.6 = 0.72 + 0.18 = 0.90
    assert abs(result["portfolio_beta"] - 0.90) < 1e-9

    # fewer than 2 non-cash symbols -> no correlation to average, no crash.
    with patch.object(hd, "compute_correlation_matrix", return_value={"symbols": [], "matrix": []}), \
         patch.object(hd, "compute_risk_metrics", return_value=[{"symbol": "AAA", "beta": 1.0}]):
        result_one = hd.build_health_overview([{"symbol": "AAA", "market_value": 100}])
    assert result_one["avg_correlation"] is None
    assert result_one["position_count"] == 1

    # missing beta for a symbol -> excluded from the weighted average, not treated as 0.
    with patch.object(hd, "compute_correlation_matrix", return_value=fake_corr), \
         patch.object(hd, "compute_risk_metrics", return_value=[{"symbol": "AAA", "beta": None}, {"symbol": "BBB", "beta": 0.6}]):
        result_missing = hd.build_health_overview(snapshots)
    assert abs(result_missing["portfolio_beta"] - 0.30 * 0.6) < 1e-9  # only BBB's term counted


if __name__ == "__main__":
    demo()
    print("OK")
