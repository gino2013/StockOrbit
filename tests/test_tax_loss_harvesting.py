import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.income.tax_loss_harvesting import (
    EXEMPTION_TWD,
    TAX_RATE_ON_EXCESS,
    estimate_tax_savings,
    find_loss_candidates,
    is_wash_sale,
)


def demo():
    snapshots = [
        {"symbol": "WINNER", "market_value": 1500, "cost_basis": 1000},  # up -> not a candidate
        {"symbol": "LOSER1", "market_value": 800, "cost_basis": 1000},  # -200 loss
        {"symbol": "LOSER2", "market_value": 500, "cost_basis": 1200},  # -700 loss, worse
        {"symbol": "CASH", "market_value": 300, "cost_basis": 300},
    ]
    candidates = find_loss_candidates(snapshots)
    assert [c["symbol"] for c in candidates] == ["LOSER2", "LOSER1"]  # worst loss first
    assert candidates[0]["unrealized_loss"] == -700

    rate = 31.5
    # income comfortably above the exemption threshold -> full loss offsettable.
    income_over = EXEMPTION_TWD + 1_000_000
    result = estimate_tax_savings(candidates, income_over, rate)
    assert result["total_unrealized_loss_usd"] == 900  # 700 + 200
    assert abs(result["offsettable_amount_twd"] - 900 * rate) < 1e-6
    assert abs(result["estimated_tax_savings_twd"] - 900 * rate * TAX_RATE_ON_EXCESS) < 1e-6

    # income below the exemption threshold -> no tax owed yet, so no savings
    # from harvesting either, regardless of how big the losses are.
    result_below = estimate_tax_savings(candidates, EXEMPTION_TWD - 1, rate)
    assert result_below["estimated_tax_savings_twd"] == 0

    # income only slightly over the threshold -> savings capped at the
    # actual taxable excess, not the full loss amount.
    small_excess = 1000.0
    result_capped = estimate_tax_savings(candidates, EXEMPTION_TWD + small_excess, rate)
    assert abs(result_capped["offsettable_amount_twd"] - small_excess) < 1e-6
    assert abs(result_capped["estimated_tax_savings_twd"] - small_excess * TAX_RATE_ON_EXCESS) < 1e-6

    # no losing positions -> empty candidate list, zero savings, no crash.
    assert find_loss_candidates([snapshots[0]]) == []
    result_none = estimate_tax_savings([], income_over, rate)
    assert result_none["estimated_tax_savings_twd"] == 0

    # --- wash sale detection (issue #294) ---
    as_of = date(2026, 6, 15)
    # bought 10 days before "today" -> selling today for a loss is a wash
    # sale (backward half of the 61-day window: 30 days before the sale).
    assert is_wash_sale(as_of, [date(2026, 6, 5)]) is True
    # bought 31 days before -> outside the window, not a wash sale.
    assert is_wash_sale(as_of, [date(2026, 5, 15)]) is False
    # bought exactly 30 days before -> boundary is inclusive.
    assert is_wash_sale(as_of, [date(2026, 5, 16)]) is True
    # no buys at all for that symbol -> not a wash sale.
    assert is_wash_sale(as_of, []) is False

    # not passing transactions/as_of -> wash_sale_risk stays None (not
    # computed), same as every caller that predates this feature.
    no_txns = find_loss_candidates(snapshots)
    assert all(c["wash_sale_risk"] is None for c in no_txns)

    # LOSER1 was bought 10 days ago (wash sale risk); LOSER2 wasn't bought
    # recently at all -> not at risk.
    transactions = [
        {"trans_type": "BOUGHT", "report_date": date(2026, 6, 5), "symbol": "LOSER1", "amount": -800},
        {"trans_type": "BOUGHT", "report_date": date(2025, 1, 1), "symbol": "LOSER2", "amount": -1200},
        {"trans_type": "SOLD", "report_date": date(2026, 6, 10), "symbol": "LOSER1", "amount": 100},  # not a BUY, ignored
    ]
    flagged = find_loss_candidates(snapshots, transactions, as_of)
    by_symbol = {c["symbol"]: c for c in flagged}
    assert by_symbol["LOSER1"]["wash_sale_risk"] is True
    assert by_symbol["LOSER2"]["wash_sale_risk"] is False

    # estimate_tax_savings excludes wash-sale-risk candidates from the
    # deductible total - only LOSER2's -700 counts, not LOSER1's -200.
    savings_with_wash_sale = estimate_tax_savings(flagged, income_over, rate)
    assert savings_with_wash_sale["total_unrealized_loss_usd"] == 700


if __name__ == "__main__":
    demo()
    print("OK")
