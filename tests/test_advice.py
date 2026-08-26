import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.advice import build_advice, build_rebalance_plan, compute_allocation


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

    # total_value = 6000 + 4000 + 500 (CASH) = 10500.
    # AAPL target 5250 vs held 6000 -> sell 750. MSFT target 3150 vs held
    # 4000 -> sell 850. PLTR target 2100 vs held 0 -> buy 2100 from scratch.
    # CASH must never appear (it's not a rebalance-able position).
    cash_snapshots = snapshots + [{"symbol": "CASH", "market_value": 500}]
    plan = build_rebalance_plan(
        cash_snapshots, targets={"AAPL": 0.5, "MSFT": 0.3, "PLTR": 0.2}
    )
    by_symbol = {p["symbol"]: p for p in plan}
    assert "CASH" not in by_symbol
    assert abs(by_symbol["AAPL"]["diff"] - -750) < 1e-6
    assert abs(by_symbol["MSFT"]["diff"] - -850) < 1e-6
    assert abs(by_symbol["PLTR"]["diff"] - 2100) < 1e-6

    # A held symbol with no target is treated as target 0% (full sell).
    plan2 = build_rebalance_plan(snapshots, targets={"AAPL": 1.0})
    by_symbol2 = {p["symbol"]: p for p in plan2}
    assert abs(by_symbol2["MSFT"]["diff"] - -4000) < 1e-6


if __name__ == "__main__":
    demo()
    print("OK")
