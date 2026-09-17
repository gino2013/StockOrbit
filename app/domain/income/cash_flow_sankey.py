"""Cash-flow Sankey: where money that ever went INTO the account (deposits
+ dividends) ended up - withdrawn, or still sitting in the account (as cash
or invested). NOT the same as "current market value" - that also includes
unrealized capital gains/losses on top of what was actually deposited/
earned, and there's no "flow" to draw for a value change nobody moved.

Cash is fungible once pooled in the account, so a withdrawal can't be
traced back to a specific dollar. This uses a simplifying, documented
convention: withdrawals are drawn from dividends first, then from deposits
- the common "spend the profit, keep the principal" mental model, not a
claim about which literal dollars left the account. Whatever convention is
used, the totals must still add up exactly (issue #299's own acceptance
bar): every dollar counted as deposited or earned ends up in exactly one
of "withdrawn" or "still in the account".
"""

from app.domain.analytics.xirr import EXTERNAL_CASH_IN_TYPES, EXTERNAL_CASH_OUT_TYPES

DEPOSITS = "總入金"
DIVIDENDS = "累計配息"
WITHDRAWN = "已提領"
REMAINING = "留在帳戶（現金＋投資）"


def build_cash_flow_sankey(transactions: list[dict]) -> dict:
    total_deposits = sum(abs(t["amount"]) for t in transactions if t["trans_type"] in EXTERNAL_CASH_IN_TYPES)
    total_withdrawals = sum(abs(t["amount"]) for t in transactions if t["trans_type"] in EXTERNAL_CASH_OUT_TYPES)
    total_dividends = sum(t["amount"] for t in transactions if t["trans_type"] == "DIV")

    dividends_withdrawn = min(total_dividends, total_withdrawals)
    deposits_withdrawn = total_withdrawals - dividends_withdrawn
    dividends_remaining = total_dividends - dividends_withdrawn
    deposits_remaining = total_deposits - deposits_withdrawn

    flows = []
    if deposits_withdrawn > 1e-9:
        flows.append({"from": DEPOSITS, "to": WITHDRAWN, "flow": deposits_withdrawn})
    if deposits_remaining > 1e-9:
        flows.append({"from": DEPOSITS, "to": REMAINING, "flow": deposits_remaining})
    if dividends_withdrawn > 1e-9:
        flows.append({"from": DIVIDENDS, "to": WITHDRAWN, "flow": dividends_withdrawn})
    if dividends_remaining > 1e-9:
        flows.append({"from": DIVIDENDS, "to": REMAINING, "flow": dividends_remaining})

    return {
        "flows": flows,
        "total_deposits": total_deposits,
        "total_dividends": total_dividends,
        "total_withdrawals": total_withdrawals,
    }
