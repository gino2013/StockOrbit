import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.allocation_history import allocation_history, chart_series


def demo():
    t1 = datetime(2026, 1, 1)
    t2 = datetime(2026, 2, 1)
    rows = [
        {"snapshot_at": t1, "symbol": "AAPL", "market_value": 600},
        {"snapshot_at": t1, "symbol": "MSFT", "market_value": 400},
        # a new position shows up at t2, AAPL's weight shifts.
        {"snapshot_at": t2, "symbol": "AAPL", "market_value": 500},
        {"snapshot_at": t2, "symbol": "MSFT", "market_value": 300},
        {"snapshot_at": t2, "symbol": "GOOG", "market_value": 200},
    ]
    history = allocation_history(rows)
    assert len(history) == 2
    assert history[0]["snapshot_at"] == t1
    assert abs(history[0]["weights"]["AAPL"] - 0.6) < 1e-9
    assert abs(history[1]["weights"]["GOOG"] - 0.2) < 1e-9

    series = chart_series(history)
    assert series["labels"] == [t1.isoformat(), t2.isoformat()]
    # GOOG wasn't held at t1 -> fills in 0 rather than skipping the point.
    assert series["series"]["GOOG"][0] == 0
    assert abs(series["series"]["GOOG"][1] - 20.0) < 1e-9
    assert abs(series["series"]["AAPL"][0] - 60.0) < 1e-9
    assert abs(series["series"]["AAPL"][1] - 50.0) < 1e-9


if __name__ == "__main__":
    demo()
    print("OK")
