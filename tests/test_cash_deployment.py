import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.portfolio.cash_deployment import suggest_cash_deployment


def demo():
    # Not enough cash to close every gap: AAPL is already at/above target
    # (post-cash), MSFT is underweight -> all $1000 goes to MSFT, nothing
    # to AAPL, nothing sold. Both symbols are still reported, so the caller
    # can see AAPL's weight didn't move it further from target and MSFT's
    # new_weight is closer to (but not necessarily at) its target.
    snapshots = [
        {"symbol": "AAPL", "market_value": 6000},
        {"symbol": "MSFT", "market_value": 4000},
    ]
    plan = suggest_cash_deployment(snapshots, {"AAPL": 0.5, "MSFT": 0.5}, cash_amount=1000)
    by_symbol = {p["symbol"]: p for p in plan}
    assert abs(by_symbol["AAPL"]["buy_amount"]) < 1e-9
    assert abs(by_symbol["MSFT"]["buy_amount"] - 1000) < 1e-6
    # total post-cash = 11000; AAPL stays at 6000/11000, MSFT becomes 5000/11000.
    assert abs(by_symbol["AAPL"]["new_weight"] - 6000 / 11000) < 1e-6
    assert abs(by_symbol["MSFT"]["new_weight"] - 5000 / 11000) < 1e-6
    # neither hits its 50% target exactly -> new_weight != target_weight here,
    # which is exactly the "did this actually reach target" signal callers need.
    assert by_symbol["MSFT"]["new_weight"] < by_symbol["MSFT"]["target_weight"]

    # Exactly enough cash to close every gap -> new_weight == target_weight.
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
    for p in plan2:
        assert abs(p["new_weight"] - p["target_weight"]) < 1e-9
    assert abs(sum(p["buy_amount"] for p in plan2) - 6000) < 1e-6

    # More cash than needed: still lands exactly on target for every symbol.
    plan3 = suggest_cash_deployment(even_snapshots, even_targets, cash_amount=9000)
    for p in plan3:
        assert abs(p["new_weight"] - p["target_weight"]) < 1e-9
    assert abs(sum(p["buy_amount"] for p in plan3) - 9000) < 1e-6

    # Never suggests a negative (sell) amount for a symbol with a positive
    # target, and $0 / no targets -> empty.
    assert all(p["buy_amount"] >= 0 for p in plan3)
    assert suggest_cash_deployment(snapshots, {"AAPL": 0.5}, cash_amount=0) == []
    assert suggest_cash_deployment(snapshots, {}, cash_amount=1000) == []

    # A target of exactly 0 means "sell this entirely" (issue #336
    # followup) - VT is fully sold, and its $3000 proceeds fold into the
    # $1000 of new cash so QQQ (the only positive-weight target) gets $4000
    # total, landing exactly on its 100% target of the resulting $9000.
    sell_snapshots = [
        {"symbol": "QQQ", "market_value": 5000},
        {"symbol": "VT", "market_value": 3000},
    ]
    plan4 = suggest_cash_deployment(sell_snapshots, {"QQQ": 1.0, "VT": 0.0}, cash_amount=1000)
    by_symbol4 = {p["symbol"]: p for p in plan4}
    assert abs(by_symbol4["VT"]["buy_amount"] - (-3000)) < 1e-6
    assert abs(by_symbol4["VT"]["new_value"]) < 1e-6
    assert abs(by_symbol4["VT"]["new_weight"]) < 1e-9
    assert abs(by_symbol4["QQQ"]["buy_amount"] - 4000) < 1e-6
    assert abs(by_symbol4["QQQ"]["new_weight"] - 1.0) < 1e-9
    # current_value/current_weight still reflect real (pre-sell) holdings.
    assert by_symbol4["VT"]["current_value"] == 3000


if __name__ == "__main__":
    demo()
    print("OK")
