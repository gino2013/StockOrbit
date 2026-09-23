import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.notifications.price_alerts import alerts_to_trigger


def demo():
    alerts = [
        {"id": "1", "symbol": "AAPL", "target_price": 200.0, "direction": "above", "triggered": False},
        {"id": "2", "symbol": "AAPL", "target_price": 150.0, "direction": "below", "triggered": False},
        {"id": "3", "symbol": "MSFT", "target_price": 400.0, "direction": "above", "triggered": False},
        {"id": "4", "symbol": "NVDA", "target_price": 100.0, "direction": "above", "triggered": True},  # already fired
        {"id": "5", "symbol": "QQQ", "target_price": 500.0, "direction": "above", "triggered": False},  # no price data
    ]
    prices = {"AAPL": 205.0, "MSFT": 380.0, "NVDA": 999.0}  # QQQ missing entirely

    triggered = alerts_to_trigger(alerts, prices)
    ids = {a["id"] for a in triggered}

    assert ids == {"1"}, ids  # only AAPL's "above 200" crossed (205 >= 200)
    # AAPL "below 150" hasn't crossed (205 > 150), MSFT hasn't crossed (380 < 400),
    # NVDA already triggered (skipped regardless of price), QQQ has no price data.

    # exactly-at-threshold counts as crossed (>=, <=), not just strictly past it.
    at_threshold = alerts_to_trigger(
        [{"id": "x", "symbol": "AAPL", "target_price": 200.0, "direction": "above", "triggered": False}],
        {"AAPL": 200.0},
    )
    assert len(at_threshold) == 1

    assert alerts_to_trigger([], {}) == []


if __name__ == "__main__":
    demo()
    print("OK")
