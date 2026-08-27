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

    # No issues: 3+ positions (clears min_positions), every symbol targeted
    # with zero drift, no cash, concentration threshold wide open.
    balanced_snapshots = [
        {"symbol": "AAPL", "market_value": 3000},
        {"symbol": "MSFT", "market_value": 3000},
        {"symbol": "GOOG", "market_value": 3000},
    ]
    no_issues = build_advice(
        balanced_snapshots,
        targets={"AAPL": 1 / 3, "MSFT": 1 / 3, "GOOG": 1 / 3},
        concentration_threshold=0.9,
    )
    assert "沒有明顯建議" in no_issues["advice"][0]

    # Held but never given a target at all (not just target 0%).
    untargeted = build_advice(balanced_snapshots, targets={"AAPL": 1 / 3}, concentration_threshold=0.9)
    assert any("MSFT" in note and "GOOG" in note and "沒有設定目標配置" in note for note in untargeted["advice"])

    # Cash sitting idle above the threshold.
    cash_heavy = balanced_snapshots + [{"symbol": "CASH", "market_value": 5000}]
    cash_advice = build_advice(cash_heavy, targets={"AAPL": 1 / 3, "MSFT": 1 / 3, "GOOG": 1 / 3}, concentration_threshold=0.9, cash_threshold=0.15)
    assert any("現金佔投資組合" in note for note in cash_advice["advice"])

    # Too few positions.
    too_few = build_advice([{"symbol": "AAPL", "market_value": 1000}], targets={"AAPL": 1.0}, concentration_threshold=0.9, min_positions=3)
    assert any("只有 1 檔持股" in note for note in too_few["advice"])

    # Too many positions.
    many_snapshots = [{"symbol": f"S{i}", "market_value": 100} for i in range(35)]
    many_targets = {f"S{i}": 1 / 35 for i in range(35)}
    too_many = build_advice(many_snapshots, targets=many_targets, concentration_threshold=0.9, max_positions=30)
    assert any("數量偏多" in note for note in too_many["advice"])

    # Sector concentration.
    sector_advice = build_advice(
        balanced_snapshots, targets={"AAPL": 1 / 3, "MSFT": 1 / 3, "GOOG": 1 / 3}, concentration_threshold=0.9,
        sector_allocation={"Technology": 8000, "Healthcare": 1000},
    )
    assert any("Technology 類股" in note for note in sector_advice["advice"])
    # "CASH"/"ETF" buckets from compute_sector_allocation() are never flagged.
    no_sector_flag = build_advice(
        balanced_snapshots, targets={"AAPL": 1 / 3, "MSFT": 1 / 3, "GOOG": 1 / 3}, concentration_threshold=0.9,
        sector_allocation={"CASH": 8000, "ETF": 1000},
    )
    assert "沒有明顯建議" in no_sector_flag["advice"][0]

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
