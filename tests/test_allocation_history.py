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

    # Multiple refreshes on the same calendar day (the 30-minute
    # staleness-triggered auto-refresh can easily produce several) collapse
    # to just that day's latest snapshot, not one point per refresh.
    same_day_a = datetime(2026, 3, 1, 8, 0)
    same_day_b = datetime(2026, 3, 1, 14, 30)
    next_day = datetime(2026, 3, 2, 9, 0)
    same_day_rows = [
        {"snapshot_at": same_day_a, "symbol": "AAPL", "market_value": 500},
        {"snapshot_at": same_day_a, "symbol": "MSFT", "market_value": 500},
        {"snapshot_at": same_day_b, "symbol": "AAPL", "market_value": 700},
        {"snapshot_at": same_day_b, "symbol": "MSFT", "market_value": 300},
        {"snapshot_at": next_day, "symbol": "AAPL", "market_value": 800},
        {"snapshot_at": next_day, "symbol": "MSFT", "market_value": 200},
    ]
    daily = allocation_history(same_day_rows)
    assert len(daily) == 2  # 2026-03-01 and 2026-03-02, not 3 raw snapshots
    assert daily[0]["snapshot_at"] == same_day_b  # the LATER of the two same-day snapshots
    assert abs(daily[0]["weights"]["AAPL"] - 0.7) < 1e-9  # from same_day_b (700/1000), not same_day_a
    assert daily[1]["snapshot_at"] == next_day

    # daily=False opts back into the old one-point-per-raw-snapshot behavior.
    raw = allocation_history(same_day_rows, daily=False)
    assert len(raw) == 3


if __name__ == "__main__":
    demo()
    print("OK")
