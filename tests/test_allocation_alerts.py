import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.notifications.allocation_alerts import alerts_to_check


def demo():
    current = {"AAPL": 0.30, "VOO": 0.20, "QQQ": 0.05}
    targets = {"AAPL": 0.20, "VOO": 0.20, "QQQ": 0.20}

    alerts = [
        # AAPL: drift +10pp, threshold 5pp -> should trigger (not yet triggered).
        {"id": "1", "symbol": "AAPL", "threshold": 0.05, "triggered": False},
        # VOO: drift 0, well under any threshold -> nothing happens either way.
        {"id": "2", "symbol": "VOO", "threshold": 0.05, "triggered": False},
        # QQQ: drift -15pp, already triggered previously, still over threshold
        # -> stays triggered, must NOT trigger again (no duplicate).
        {"id": "3", "symbol": "QQQ", "threshold": 0.05, "triggered": True},
        # AAPL again but already triggered and still over threshold -> no-op.
        {"id": "4", "symbol": "AAPL", "threshold": 0.05, "triggered": True},
    ]

    to_trigger, to_reset = alerts_to_check(alerts, current, targets)
    trigger_ids = {a["id"] for a in to_trigger}
    reset_ids = {a["id"] for a in to_reset}

    assert trigger_ids == {"1"}, trigger_ids
    assert reset_ids == set(), reset_ids

    triggered_aapl = next(a for a in to_trigger if a["id"] == "1")
    assert abs(triggered_aapl["drift"] - 0.10) < 1e-9
    assert abs(triggered_aapl["current_weight"] - 0.30) < 1e-9
    assert abs(triggered_aapl["target_weight"] - 0.20) < 1e-9

    # --- recovery: an alert that was triggered, but drift is now back
    # under threshold -> reset (silently), not re-triggered. ---
    recovered = [{"id": "5", "symbol": "VOO", "threshold": 0.05, "triggered": True}]  # VOO drift is 0
    to_trigger, to_reset = alerts_to_check(recovered, current, targets)
    assert to_trigger == []
    assert {a["id"] for a in to_reset} == {"5"}

    # --- a symbol with no target at all is treated as target 0 (matches
    # advice.py's own "untargeted = full weight is drift" convention). ---
    untargeted = [{"id": "6", "symbol": "NVDA", "threshold": 0.05, "triggered": False}]
    to_trigger, _ = alerts_to_check(untargeted, {"NVDA": 0.10}, {})
    assert {a["id"] for a in to_trigger} == {"6"}

    assert alerts_to_check([], {}, {}) == ([], [])


if __name__ == "__main__":
    demo()
    print("OK")
