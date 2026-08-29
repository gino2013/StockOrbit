import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

from app import risk_parity


def demo():
    snapshots = [
        {"symbol": "CALM", "market_value": 5000},
        {"symbol": "WILD", "market_value": 5000},
        {"symbol": "CASH", "market_value": 2000},
    ]
    fake_risk_items = [
        {"symbol": "CALM", "volatility_90d": 0.10},
        {"symbol": "WILD", "volatility_90d": 0.40},  # 4x more volatile than CALM
    ]
    with patch.object(risk_parity, "compute_risk_metrics", return_value=fake_risk_items):
        result = risk_parity.suggest_risk_parity(snapshots)

    by_symbol = {r["symbol"]: r for r in result}
    assert "CASH" not in by_symbol  # cash has no volatility to weight by

    # current weights: CALM 5000/12000, WILD 5000/12000 -> equal.
    assert abs(by_symbol["CALM"]["current_weight"] - 5000 / 12000) < 1e-9

    # 1/vol weighting: CALM (vol 0.10) should get a much bigger suggested
    # share than WILD (vol 0.40) - the whole point of risk parity.
    assert by_symbol["CALM"]["suggested_weight"] > by_symbol["WILD"]["suggested_weight"]

    # non-cash suggested weights must sum to (1 - cash_weight), i.e. CASH's
    # 2000/12000 share is left untouched rather than being redistributed too.
    cash_weight = 2000 / 12000
    total_suggested = by_symbol["CALM"]["suggested_weight"] + by_symbol["WILD"]["suggested_weight"]
    assert abs(total_suggested - (1 - cash_weight)) < 1e-9

    # missing volatility data -> suggested_weight is None, not a crash or a bogus number.
    with patch.object(risk_parity, "compute_risk_metrics", return_value=[]):
        result = risk_parity.suggest_risk_parity(snapshots)
    assert all(r["suggested_weight"] is None for r in result)


if __name__ == "__main__":
    demo()
    print("OK")
