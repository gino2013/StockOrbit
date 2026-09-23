import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import attribution


def _fake_prices():
    # AAPL: 100 -> 120 (+20%), MSFT: 100 -> 90 (-10%)
    return pd.DataFrame({"AAPL": [100.0, 120.0], "MSFT": [100.0, 90.0]})


def demo():
    snapshots = [
        {"symbol": "AAPL", "market_value": 8000.0},  # current weight 80%
        {"symbol": "MSFT", "market_value": 2000.0},  # current weight 20%
        {"symbol": "CASH", "market_value": 500.0},  # excluded from weighting
    ]
    targets = {"AAPL": 0.5, "MSFT": 0.5}  # target weight 50/50

    with patch.object(attribution, "close_prices", return_value=_fake_prices()):
        result = attribution.compute_attribution(snapshots, targets, "2026-01-01", "2026-02-01")

    by_symbol = {i["symbol"]: i for i in result["items"]}
    assert abs(by_symbol["AAPL"]["current_weight"] - 0.8) < 1e-9
    assert abs(by_symbol["AAPL"]["target_weight"] - 0.5) < 1e-9
    assert abs(by_symbol["AAPL"]["return"] - 0.2) < 1e-9
    assert abs(by_symbol["MSFT"]["return"] - (-0.1)) < 1e-9

    # overweight the +20% winner (AAPL, 80% vs 50% target) and underweight
    # the -10% loser (MSFT, 20% vs 50% target) - both should be positive
    # contributions (deviating from target helped, on both legs).
    assert by_symbol["AAPL"]["allocation_contribution"] > 0
    assert by_symbol["MSFT"]["allocation_contribution"] > 0

    # Selection/Interaction are identically zero by construction (same
    # symbol universe on both sides - see module docstring), and the whole
    # gap collapses into Allocation effect.
    assert result["selection_effect"] == 0.0
    assert result["interaction_effect"] == 0.0
    assert result["total_effect"] == result["allocation_effect"]
    expected = (0.8 - 0.5) * 0.2 + (0.2 - 0.5) * -0.1
    assert abs(result["allocation_effect"] - expected) < 1e-9

    # acceptance criterion: current weights == target weights -> Allocation
    # effect is exactly 0, regardless of what the returns were.
    with patch.object(attribution, "close_prices", return_value=_fake_prices()):
        matched = attribution.compute_attribution(
            [{"symbol": "AAPL", "market_value": 5000.0}, {"symbol": "MSFT", "market_value": 5000.0}],
            {"AAPL": 0.5, "MSFT": 0.5},
            "2026-01-01",
            "2026-02-01",
        )
    assert matched["allocation_effect"] == 0.0

    assert attribution.compute_attribution([], {}, "2026-01-01", "2026-02-01") == {
        "items": [],
        "allocation_effect": 0.0,
        "selection_effect": 0.0,
        "interaction_effect": 0.0,
        "total_effect": 0.0,
    }


if __name__ == "__main__":
    demo()
    print("OK")
