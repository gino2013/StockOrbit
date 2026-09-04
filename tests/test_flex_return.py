"""flex_return_pct: flex-mode 報酬率 = current-market-value-weighted blend
of each holding's price return since its FLEX_RETURN_SINCE (or first-listed)
price. See app/application/dashboard.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.application.dashboard import flex_return_pct


def _snap(symbol, price, market_value):
    return {"symbol": symbol, "price": price, "market_value": market_value, "quantity": 1, "cost_basis": 0}


def demo():
    # AAA: bought-basis 100, now 500 -> +400%. BBB: basis 50, now 60 -> +20%.
    # weights by *current* market value: AAA 8000, BBB 2000 (total 10000).
    # blend = 0.8 * 4.0 + 0.2 * 0.2 = 3.2 + 0.04 = 3.24  (i.e. +324%)
    snaps = [_snap("AAA", 500, 8000), _snap("BBB", 60, 2000)]
    basis = {"AAA": 100.0, "BBB": 50.0}
    r = flex_return_pct(snaps, basis)
    assert abs(r - 3.24) < 1e-9, r

    # CASH is skipped entirely - no price history to measure against.
    with_cash = snaps + [_snap("CASH", 1.0, 5000)]
    assert abs(flex_return_pct(with_cash, basis) - 3.24) < 1e-9

    # a holding that only listed later still counts: `basis` already carries
    # its first-available price (e.g. a 2024 IPO), so it's measured from
    # then, not skipped. NEW: basis 200 -> now 260 = +30%.
    later = snaps + [_snap("NEW", 260, 10000)]  # equal weight-ish, total 20000
    basis_with_later = {**basis, "NEW": 200.0}
    r2 = flex_return_pct(later, basis_with_later)
    # 8000*4.0 + 2000*0.2 + 10000*0.3 = 32000 + 400 + 3000 = 35400; / 20000
    assert abs(r2 - 1.77) < 1e-9, r2

    # a symbol with no usable basis (bad ticker, fully delisted) drops out
    # of *both* the weighted sum and the denominator - not counted as 0%.
    missing = snaps + [_snap("GONE", 10, 90000)]  # huge weight, but no basis
    assert abs(flex_return_pct(missing, basis) - 3.24) < 1e-9  # unchanged from AAA/BBB only
    assert abs(flex_return_pct(missing, {**basis, "GONE": 0.0}) - 3.24) < 1e-9  # basis <= 0 also drops

    # nothing left to weight -> None, so the caller keeps the plain figure.
    assert flex_return_pct([_snap("CASH", 1.0, 1000)], {}) is None
    assert flex_return_pct(snaps, {}) is None


if __name__ == "__main__":
    demo()
    print("OK")
