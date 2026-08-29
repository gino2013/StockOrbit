import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tax_loss_harvesting import EXEMPTION_TWD, TAX_RATE_ON_EXCESS, estimate_tax_savings, find_loss_candidates


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


if __name__ == "__main__":
    demo()
    print("OK")
