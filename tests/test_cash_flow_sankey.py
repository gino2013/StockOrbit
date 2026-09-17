import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.income.cash_flow_sankey import (
    DEPOSITS,
    DIVIDENDS,
    REMAINING,
    WITHDRAWN,
    build_cash_flow_sankey,
)


def _flow_amount(flows, from_node, to_node):
    for f in flows:
        if f["from"] == from_node and f["to"] == to_node:
            return f["flow"]
    return 0.0


def demo():
    # $10,000 deposited, $1,000 in dividends, $500 withdrawn - less than
    # total dividends, so under the "spend profit first" convention the
    # whole withdrawal comes out of dividends, deposits are untouched.
    small_withdrawal = [
        {"trans_type": "DEPOSIT", "report_date": date(2024, 1, 1), "amount": 10000},
        {"trans_type": "DIV", "report_date": date(2024, 6, 1), "amount": 1000},
        {"trans_type": "WITHDRAWAL", "report_date": date(2025, 1, 1), "amount": 500},
        {"trans_type": "BOUGHT", "report_date": date(2024, 1, 2), "amount": -10000},  # not a cash-flow node
    ]
    result = build_cash_flow_sankey(small_withdrawal)
    assert result["total_deposits"] == 10000
    assert result["total_dividends"] == 1000
    assert result["total_withdrawals"] == 500
    assert _flow_amount(result["flows"], DIVIDENDS, WITHDRAWN) == 500
    assert _flow_amount(result["flows"], DIVIDENDS, REMAINING) == 500
    assert _flow_amount(result["flows"], DEPOSITS, WITHDRAWN) == 0  # deposits untouched
    assert _flow_amount(result["flows"], DEPOSITS, REMAINING) == 10000

    # conservation: every dollar in ends up in exactly one sink.
    total_in = result["total_deposits"] + result["total_dividends"]
    total_out = sum(f["flow"] for f in result["flows"])
    assert abs(total_in - total_out) < 1e-9
    total_withdrawn_flows = _flow_amount(result["flows"], DEPOSITS, WITHDRAWN) + _flow_amount(result["flows"], DIVIDENDS, WITHDRAWN)
    assert abs(total_withdrawn_flows - result["total_withdrawals"]) < 1e-9

    # withdrawal bigger than total dividends -> dividends fully consumed
    # first, the *excess* comes out of deposits (the convention's point).
    big_withdrawal = [
        {"trans_type": "DEPOSIT", "report_date": date(2024, 1, 1), "amount": 10000},
        {"trans_type": "DIV", "report_date": date(2024, 6, 1), "amount": 1000},
        {"trans_type": "WITHDRAWAL", "report_date": date(2025, 1, 1), "amount": 3000},
    ]
    result2 = build_cash_flow_sankey(big_withdrawal)
    assert _flow_amount(result2["flows"], DIVIDENDS, WITHDRAWN) == 1000  # all dividends used up
    assert _flow_amount(result2["flows"], DIVIDENDS, REMAINING) == 0  # nothing left of dividends
    assert _flow_amount(result2["flows"], DEPOSITS, WITHDRAWN) == 2000  # the excess 3000-1000
    assert _flow_amount(result2["flows"], DEPOSITS, REMAINING) == 8000
    total_in2 = result2["total_deposits"] + result2["total_dividends"]
    assert abs(sum(f["flow"] for f in result2["flows"]) - total_in2) < 1e-9

    # no withdrawals at all -> everything just flows straight to "remaining",
    # nothing in the withdrawn sink, no zero-amount flow rows cluttering it.
    no_withdrawals = [
        {"trans_type": "DEPOSIT", "report_date": date(2024, 1, 1), "amount": 5000},
        {"trans_type": "DIV", "report_date": date(2024, 6, 1), "amount": 200},
    ]
    result3 = build_cash_flow_sankey(no_withdrawals)
    assert all(f["to"] != WITHDRAWN for f in result3["flows"])
    assert len(result3["flows"]) == 2  # just the two "-> remaining" flows

    # no transactions at all -> empty flows, not a crash.
    empty = build_cash_flow_sankey([])
    assert empty["flows"] == []
    assert empty["total_deposits"] == 0


if __name__ == "__main__":
    demo()
    print("OK")
