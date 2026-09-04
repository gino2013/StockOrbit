"""Flex mode = "I bought my current position on FLEX_RETURN_SINCE (or a
symbol's first trading day if it listed later) and never touched it".
Covers apply_flex_since (cost-basis rewrite) and flex_cashflows_since
(the XIRR cashflows). See app/application/dashboard.py.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.application.dashboard import apply_flex_since, flex_cashflows_since


def _snap(symbol, price, quantity, cost_basis, market_value=None):
    return {
        "symbol": symbol,
        "price": price,
        "quantity": quantity,
        "cost_basis": cost_basis,
        "market_value": market_value if market_value is not None else price * quantity,
    }


def demo():
    # AAA: hold 10 shares now (real cost $3000, real value 10*500=5000).
    # 2017 basis price 100 -> flex cost = 10*100 = 1000, value stays 5000.
    # BBB: hold 20, real cost $900, value 20*60=1200; 2017 price 50 ->
    # flex cost = 20*50 = 1000.
    snaps = [_snap("AAA", 500, 10, 3000), _snap("BBB", 60, 20, 900)]
    basis = {"AAA": 100.0, "BBB": 50.0}

    flexed = apply_flex_since(snaps, basis)
    by = {s["symbol"]: s for s in flexed}
    assert by["AAA"]["cost_basis"] == 1000.0
    assert by["BBB"]["cost_basis"] == 1000.0
    # market value / quantity / price untouched - you hold the same shares.
    assert by["AAA"]["market_value"] == 5000.0 and by["AAA"]["quantity"] == 10
    assert by["BBB"]["market_value"] == 1200.0

    # -> portfolio: total_value 6200, flex cost 2000, gain 4200, +210%
    total_value = sum(s["market_value"] for s in flexed)
    total_cost = sum(s["cost_basis"] for s in flexed)
    assert total_value == 6200.0 and total_cost == 2000.0
    assert abs((total_value - total_cost) / total_cost - 2.1) < 1e-9

    # CASH keeps its real cost basis (no price history to rebase from).
    with_cash = snaps + [_snap("CASH", 1.0, 1, 5000, market_value=5000)]
    fc = {s["symbol"]: s for s in apply_flex_since(with_cash, basis)}
    assert fc["CASH"]["cost_basis"] == 5000.0

    # a symbol with no basis price keeps its real cost basis (not zeroed).
    missing = snaps + [_snap("NEW", 200, 5, 800)]
    fm = {s["symbol"]: s for s in apply_flex_since(missing, basis)}  # basis has no "NEW"
    assert fm["NEW"]["cost_basis"] == 800.0
    # basis price present but <= 0 also falls back.
    fz = {s["symbol"]: s for s in apply_flex_since(missing, {**basis, "NEW": 0.0})}
    assert fz["NEW"]["cost_basis"] == 800.0

    # --- flex_cashflows_since: one buy per symbol at its basis date, then
    # the whole non-cash position marked to today. ---
    as_of = date(2026, 1, 1)
    basis_dated = {
        "AAA": (date(2017, 1, 3), 100.0),   # listed pre-2017
        "BBB": (date(2023, 9, 14), 50.0),   # a later IPO - buy sits at listing
    }
    flows = flex_cashflows_since(flexed, basis_dated, as_of)
    assert flows[0] == (date(2017, 1, 3), -1000.0)   # 10 * 100
    assert flows[1] == (date(2023, 9, 14), -1000.0)  # 20 * 50, at the IPO date
    assert flows[-1] == (as_of, 6200.0)              # terminal = sum of non-cash market value

    # CASH contributes neither a buy nor to the terminal value.
    flows_cash = flex_cashflows_since(
        apply_flex_since(with_cash, basis), basis_dated, as_of
    )
    assert flows_cash[-1] == (as_of, 6200.0)  # still 6200, CASH's 5000 excluded

    # nothing with a usable basis -> no cashflows at all (caller gets no XIRR).
    assert flex_cashflows_since(flexed, {}, as_of) == []


if __name__ == "__main__":
    demo()
    print("OK")
