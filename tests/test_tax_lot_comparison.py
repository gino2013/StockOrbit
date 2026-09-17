import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.income.tax_lot_comparison import compare_lot_selection


def demo():
    # two lots, oldest first (as open_lots_by_symbol() would hand them
    # over): an old cheap lot and a recent expensive one.
    lots = [
        {"buy_date": date(2023, 1, 1), "quantity": 10, "price": 100},  # cheap, old
        {"buy_date": date(2026, 1, 1), "quantity": 10, "price": 180},  # expensive, recent
    ]
    sale_price = 200

    # selling 10 shares: FIFO takes the old $100 lot (biggest gain, worst
    # for realized-gains-this-year); HIFO takes the $180 lot (smallest
    # gain) - the whole point of the feature.
    result = compare_lot_selection(lots, quantity=10, sale_price=sale_price)
    assert abs(result["fifo"]["cost_basis"] - 10 * 100) < 1e-9
    assert abs(result["fifo"]["gain"] - (10 * 200 - 10 * 100)) < 1e-9
    assert abs(result["hifo"]["cost_basis"] - 10 * 180) < 1e-9
    assert abs(result["hifo"]["gain"] - (10 * 200 - 10 * 180)) < 1e-9
    # HIFO realizes less gain than FIFO here -> gain_difference is negative.
    assert result["gain_difference"] < 0
    assert abs(result["gain_difference"] - (result["hifo"]["gain"] - result["fifo"]["gain"])) < 1e-9
    assert result["fifo"]["unmatched_quantity"] == 0
    assert result["hifo"]["unmatched_quantity"] == 0

    # selling across both lots (15 shares): FIFO takes all 10 of the old
    # lot + 5 of the new; HIFO takes all 10 of the expensive lot + 5 of the
    # cheap one - same total shares, different cost basis split.
    across = compare_lot_selection(lots, quantity=15, sale_price=sale_price)
    assert abs(across["fifo"]["cost_basis"] - (10 * 100 + 5 * 180)) < 1e-9
    assert abs(across["hifo"]["cost_basis"] - (10 * 180 + 5 * 100)) < 1e-9
    assert across["fifo"]["matched_quantity"] == 15
    assert across["hifo"]["matched_quantity"] == 15

    # requesting more shares than held -> both sides report the same
    # unmatched remainder, not a crash or a fabricated cost.
    too_many = compare_lot_selection(lots, quantity=25, sale_price=sale_price)
    assert too_many["fifo"]["matched_quantity"] == 20
    assert too_many["fifo"]["unmatched_quantity"] == 5
    assert too_many["hifo"]["matched_quantity"] == 20
    assert too_many["hifo"]["unmatched_quantity"] == 5

    # a single lot -> FIFO and HIFO are trivially identical (nothing to
    # choose between), gain_difference is exactly 0.
    one_lot = [{"buy_date": date(2025, 1, 1), "quantity": 10, "price": 150}]
    same = compare_lot_selection(one_lot, quantity=5, sale_price=200)
    assert same["gain_difference"] == 0
    assert same["fifo"]["gain"] == same["hifo"]["gain"]


if __name__ == "__main__":
    demo()
    print("OK")
