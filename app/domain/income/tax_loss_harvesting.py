"""Rule-based tax-loss-harvesting candidate list: which currently-unrealized
losses could offset this year's already-realized gains + dividends, and
roughly how much basic-income tax (see app/overseas_income.py) that might
save.

NOT tax advice. The fact that 基本稅額 (AMT) is actually the *higher* of
this flat calculation vs regular income tax is out of scope - check an
accountant before acting on this. Wash-sale-style rules ARE checked (issue
#294) since they're an objective, rule-based date comparison, not a tax
judgment call.
"""

from datetime import date, timedelta

from app.domain.income.overseas_income import EXEMPTION_TWD

# 個人基本稅額條例：基本所得額超過免稅額的部分，稅率 20% - this ignores the
# real rule that you pay whichever is higher of this AMT calculation or
# ordinary income tax, so it's a rough estimate, not a filing number.
TAX_RATE_ON_EXCESS = 0.20

WASH_SALE_WINDOW_DAYS = 30  # each side - a 61-day window total (30 before + sale day + 30 after)


def is_wash_sale(sell_date: date, buy_dates: list[date], window_days: int = WASH_SALE_WINDOW_DAYS) -> bool:
    """True if any BUY of the same symbol falls within `window_days` before
    or after `sell_date`. Only checks buys that already happened (or are
    being asked about hypothetically as `sell_date`) - a rebuy the user
    hasn't made yet obviously can't be detected from transaction history,
    which is why find_loss_candidates() below can only warn about it, not
    detect it."""
    window_start = sell_date - timedelta(days=window_days)
    window_end = sell_date + timedelta(days=window_days)
    return any(window_start <= d <= window_end for d in buy_dates)


def find_loss_candidates(
    snapshots: list[dict], transactions: list[dict] | None = None, as_of: date | None = None
) -> list[dict]:
    """Currently-held symbols with unrealized_gain < 0, worst first.

    `wash_sale_risk` (only computed when `transactions`/`as_of` are given)
    is True when selling *today* would already be a wash sale because of a
    BUY of the same symbol in the last `WASH_SALE_WINDOW_DAYS` days - that
    portion of the loss wouldn't actually be deductible this year. It's
    still returned (not filtered out) so the UI can show *why* it's
    excluded from the tax-savings estimate, and it's None (not False) when
    transactions/as_of weren't supplied, to distinguish "checked, no
    recent buy" from "not checked"."""
    buy_dates_by_symbol: dict[str, list[date]] = {}
    if transactions is not None:
        for t in transactions:
            if t["trans_type"] == "BOUGHT" and t.get("symbol"):
                buy_dates_by_symbol.setdefault(t["symbol"], []).append(t["report_date"])

    candidates = []
    for s in snapshots:
        if s["symbol"] == "CASH" or s["market_value"] >= s["cost_basis"]:
            continue
        wash_sale_risk = (
            is_wash_sale(as_of, buy_dates_by_symbol.get(s["symbol"], []))
            if transactions is not None and as_of is not None
            else None
        )
        candidates.append(
            {
                "symbol": s["symbol"],
                "market_value": s["market_value"],
                "cost_basis": s["cost_basis"],
                "unrealized_loss": s["market_value"] - s["cost_basis"],
                "wash_sale_risk": wash_sale_risk,
            }
        )
    return sorted(candidates, key=lambda c: c["unrealized_loss"])


def estimate_tax_savings(candidates: list[dict], income_this_year_twd: float, usdtwd_rate: float) -> dict:
    """income_this_year_twd is this year's realized gains + dividends
    already converted to TWD (app.overseas_income.estimate_overseas_income's
    total_twd), *before* any additional loss-harvesting sale. Candidates'
    unrealized_loss is in USD (Firstrade's own currency), converted here.

    A candidate flagged wash_sale_risk=True is excluded from the total -
    selling it today wouldn't actually produce a deductible loss, so
    counting it would overstate the estimated tax savings."""
    taxable_excess_before = max(0.0, income_this_year_twd - EXEMPTION_TWD)
    total_loss_usd = sum(-c["unrealized_loss"] for c in candidates if not c.get("wash_sale_risk"))
    total_loss_twd = total_loss_usd * usdtwd_rate
    offsettable_twd = min(taxable_excess_before, total_loss_twd)
    return {
        "taxable_excess_before_twd": taxable_excess_before,
        "total_unrealized_loss_usd": total_loss_usd,
        "offsettable_amount_twd": offsettable_twd,
        "estimated_tax_savings_twd": offsettable_twd * TAX_RATE_ON_EXCESS,
    }
