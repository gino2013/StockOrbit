import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.advice import build_advice, compute_allocation


def demo():
    snapshots = [
        {"symbol": "AAPL", "market_value": 6000},
        {"symbol": "MSFT", "market_value": 4000},
    ]
    allocation = compute_allocation(snapshots)
    assert abs(allocation["AAPL"] - 0.6) < 1e-9
    assert abs(allocation["MSFT"] - 0.4) < 1e-9

    result = build_advice(
        snapshots, targets={"AAPL": 0.5, "MSFT": 0.5},
        concentration_threshold=0.55, drift_threshold=0.05,
    )
    assert any("AAPL" in note for note in result["advice"])

    no_issues = build_advice(snapshots, targets={}, concentration_threshold=0.9)
    assert "沒有明顯建議" in no_issues["advice"][0]


if __name__ == "__main__":
    demo()
    print("OK")
