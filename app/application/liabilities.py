"""Liability summary use case: remaining balances + whether borrowing to
invest is beating its own cost (issue #330). Pure orchestration; the route
supplies the raw liability/snapshot/transaction rows.

Computes its own XIRR from `transactions` rather than reusing the
dashboard's already-computed one - same independent-computation pattern
app/application/goals.py already uses for its own progress tracking, not a
new inconsistency this module introduces.
"""

from datetime import date

from app.domain.analytics.xirr import portfolio_cashflows, xirr
from app.domain.liabilities.amortization import _months_elapsed, balance_in_usd, loan_term_months, remaining_balance
from app.domain.liabilities.leverage import leverage_spread, weighted_average_rate


def liability_summary(
    *, liabilities: list[dict], snapshots: list[dict], transactions: list[dict], as_of: date,
    usd_twd_rate: float | None = None,
) -> dict:
    rows = []
    for liability in liabilities:
        # remaining_balance is in the loan's own currency (what the table
        # shows); *_usd is converted at the current rate for net worth and
        # the weighted-rate/spread comparison.
        balance = remaining_balance(
            liability["principal"], liability["annual_rate"], liability["monthly_payment"],
            date.fromisoformat(liability["start_date"]), as_of,
        )
        term = liability.get("term_months") or loan_term_months(
            liability["principal"], liability["annual_rate"], liability["monthly_payment"]
        )
        elapsed = _months_elapsed(date.fromisoformat(liability["start_date"]), as_of)
        # Everything is *displayed* in NT$ (issue #382): a TWD loan as is, a
        # USD-stored one at the current rate (None without a rate).
        def twd(x: float, _c=liability.get("currency", "USD")) -> float | None:
            return x if _c == "TWD" else (x * usd_twd_rate if usd_twd_rate else None)

        rows.append({
            **liability,
            "principal_twd": twd(liability["principal"]),
            "monthly_payment_twd": twd(liability["monthly_payment"]),
            "remaining_balance_twd": twd(balance),
            "remaining_balance": balance,
            "remaining_balance_usd": balance_in_usd(liability, as_of, usd_twd_rate),
            "term_months": term,
            "remaining_months": max(0, term - elapsed) if term else None,
        })

    total_value = sum(s["market_value"] for s in snapshots)
    portfolio_return = xirr(portfolio_cashflows(transactions, total_value, as_of)) if snapshots else None
    weighted_rate = weighted_average_rate([(r["remaining_balance_usd"], r["annual_rate"]) for r in rows])

    return {
        "liabilities": rows,
        "portfolio_return": portfolio_return,
        "weighted_average_rate": weighted_rate,
        "leverage_spread": leverage_spread(portfolio_return, weighted_rate),
    }
