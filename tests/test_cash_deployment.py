import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cash_deployment import suggest_cash_deployment


def demo():
    # Not enough cash to close every gap: AAPL is already at/above target
    # (post-cash), MSFT is underweight -> all $1000 goes to MSFT, nothing
    # to AAPL, nothing sold.
    snapshots = [
        {"symbol": "AAPL", "market_value": 6000},
        {"symbol": "MSFT", "market_value": 4000},
    ]
    plan = suggest_cash_deployment(snapshots, {"AAPL": 0.5, "MSFT": 0.5}, cash_amount=1000)
    by_symbol = {p["symbol"]: p for p in plan}
    assert "AAPL" not in by_symbol
    assert abs(by_symbol["MSFT"]["buy_amount"] - 1000) < 1e-6

    # Exactly enough cash to close every gap, no leftover.
    even_snapshots = [
        {"symbol": "AAPL", "market_value": 3000},
        {"symbol": "MSFT", "market_value": 3000},
        {"symbol": "PLTR", "market_value": 0},
    ]
    even_targets = {"AAPL": 1 / 3, "MSFT": 1 / 3, "PLTR": 1 / 3}
    plan2 = suggest_cash_deployment(even_snapshots, even_targets, cash_amount=6000)
    by_symbol2 = {p["symbol"]: p for p in plan2}
    assert abs(by_symbol2["AAPL"]["buy_amount"] - 1000) < 1e-6
    assert abs(by_symbol2["MSFT"]["buy_amount"] - 1000) < 1e-6
    assert abs(by_symbol2["PLTR"]["buy_amount"] - 4000) < 1e-6
    assert abs(sum(p["buy_amount"] for p in plan2) - 6000) < 1e-6

    # More cash than needed: gaps close exactly, remainder splits by target
    # weight (equal weights here -> equal $1000 top-up each).
    plan3 = suggest_cash_deployment(even_snapshots, even_targets, cash_amount=9000)
    by_symbol3 = {p["symbol"]: p for p in plan3}
    assert abs(by_symbol3["AAPL"]["buy_amount"] - 2000) < 1e-6
    assert abs(by_symbol3["MSFT"]["buy_amount"] - 2000) < 1e-6
    assert abs(by_symbol3["PLTR"]["buy_amount"] - 5000) < 1e-6
    assert abs(sum(p["buy_amount"] for p in plan3) - 9000) < 1e-6

    # Never suggests a negative (sell) amount, and $0 / no targets -> empty.
    assert all(p["buy_amount"] > 0 for p in plan3)
    assert suggest_cash_deployment(snapshots, {"AAPL": 0.5}, cash_amount=0) == []
    assert suggest_cash_deployment(snapshots, {}, cash_amount=1000) == []


if __name__ == "__main__":
    demo()
    print("OK")
