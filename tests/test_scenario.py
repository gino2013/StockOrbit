import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

from app.domain.analytics import scenario


def demo():
    snapshots = [
        {"symbol": "HIBETA", "market_value": 6000},
        {"symbol": "LOBETA", "market_value": 3000},
        {"symbol": "CASH", "market_value": 1000},
    ]
    fake_risk_items = [
        {"symbol": "HIBETA", "beta": 2.0},
        {"symbol": "LOBETA", "beta": 0.5},
    ]
    with patch.object(scenario, "compute_risk_metrics", return_value=fake_risk_items):
        result = scenario.simulate_market_drop(snapshots, -0.10)

    by_symbol = {r["symbol"]: r for r in result["items"]}
    assert abs(by_symbol["HIBETA"]["estimated_change"] - (-0.20)) < 1e-9  # 2.0 * -10%
    assert abs(by_symbol["LOBETA"]["estimated_change"] - (-0.05)) < 1e-9  # 0.5 * -10%
    assert by_symbol["CASH"]["estimated_change"] == 0.0  # cash assumed beta 0, unaffected

    # portfolio change = weighted average of per-symbol dollar changes / total value
    expected_value_change = 6000 * -0.20 + 3000 * -0.05 + 1000 * 0.0
    assert abs(result["portfolio_value_change"] - expected_value_change) < 1e-6
    assert abs(result["portfolio_change"] - expected_value_change / 10000) < 1e-9

    # missing beta -> None estimate, not a crash or a bogus 0.
    with patch.object(scenario, "compute_risk_metrics", return_value=[]):
        result = scenario.simulate_market_drop(snapshots, -0.10)
    by_symbol = {r["symbol"]: r for r in result["items"]}
    assert by_symbol["HIBETA"]["estimated_change"] is None


if __name__ == "__main__":
    demo()
    print("OK")
