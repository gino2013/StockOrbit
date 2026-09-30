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
from app.domain.liabilities.amortization import remaining_balance
from app.domain.liabilities.leverage import leverage_spread, weighted_average_rate


def liability_summary(
    *, liabilities: list[dict], snapshots: list[dict], transactions: list[dict], as_of: date,
) -> dict:
    rows = []
    for liability in liabilities:
        balance = remaining_balance(
            liability["principal"], liability["annual_rate"], liability["monthly_payment"],
            date.fromisoformat(liability["start_date"]), as_of,
        )
        rows.append({**liability, "remaining_balance": balance})

    total_value = sum(s["market_value"] for s in snapshots)
    portfolio_return = xirr(portfolio_cashflows(transactions, total_value, as_of)) if snapshots else None
    weighted_rate = weighted_average_rate([(r["remaining_balance"], r["annual_rate"]) for r in rows])

    return {
        "liabilities": rows,
        "portfolio_return": portfolio_return,
        "weighted_average_rate": weighted_rate,
        "leverage_spread": leverage_spread(portfolio_return, weighted_rate),
    }
