"""Rule-based tax-loss-harvesting candidate list: which currently-unrealized
losses could offset this year's already-realized gains + dividends, and
roughly how much basic-income tax (see app/overseas_income.py) that might
save.

NOT tax advice. wash-sale-style rules, and the fact that 基本稅額 (AMT) is
actually the *higher* of this flat calculation vs regular income tax, are
both out of scope - check an accountant before acting on this.
"""

from app.domain.income.overseas_income import EXEMPTION_TWD

# 個人基本稅額條例：基本所得額超過免稅額的部分，稅率 20% - this ignores the
# real rule that you pay whichever is higher of this AMT calculation or
# ordinary income tax, so it's a rough estimate, not a filing number.
TAX_RATE_ON_EXCESS = 0.20


def find_loss_candidates(snapshots: list[dict]) -> list[dict]:
    """Currently-held symbols with unrealized_gain < 0, worst first."""
    candidates = [
        {
            "symbol": s["symbol"],
            "market_value": s["market_value"],
            "cost_basis": s["cost_basis"],
            "unrealized_loss": s["market_value"] - s["cost_basis"],
        }
        for s in snapshots
        if s["symbol"] != "CASH" and s["market_value"] < s["cost_basis"]
    ]
    return sorted(candidates, key=lambda c: c["unrealized_loss"])


def estimate_tax_savings(candidates: list[dict], income_this_year_twd: float, usdtwd_rate: float) -> dict:
    """income_this_year_twd is this year's realized gains + dividends
    already converted to TWD (app.overseas_income.estimate_overseas_income's
    total_twd), *before* any additional loss-harvesting sale. Candidates'
    unrealized_loss is in USD (Firstrade's own currency), converted here."""
    taxable_excess_before = max(0.0, income_this_year_twd - EXEMPTION_TWD)
    total_loss_usd = sum(-c["unrealized_loss"] for c in candidates)
    total_loss_twd = total_loss_usd * usdtwd_rate
    offsettable_twd = min(taxable_excess_before, total_loss_twd)
    return {
        "taxable_excess_before_twd": taxable_excess_before,
        "total_unrealized_loss_usd": total_loss_usd,
        "offsettable_amount_twd": offsettable_twd,
        "estimated_tax_savings_twd": offsettable_twd * TAX_RATE_ON_EXCESS,
    }
