import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.analytics.xirr import portfolio_cashflows, xirr


def demo():
    # invest $1000, get back exactly $1100 one year (365 days) later -> 10% flat.
    rate = xirr([(date(2025, 1, 1), -1000), (date(2026, 1, 1), 1100)])
    assert abs(rate - 0.10) < 1e-6

    # invest $1000, get back $1050 after 180 days -> rate solves
    # 1050 / (1+r)^(180/365) = 1000, i.e. r = 1.05**(365/180) - 1.
    expected = 1.05 ** (365 / 180) - 1
    rate2 = xirr([(date(2026, 1, 1), -1000), (date(2026, 6, 30), 1050)])
    assert abs(rate2 - expected) < 1e-4

    # no sign change -> undefined, must not crash or return a bogus number.
    assert xirr([(date(2026, 1, 1), -1000), (date(2026, 6, 1), -500)]) is None
    assert xirr([(date(2026, 1, 1), 1000)]) is None

    # portfolio_cashflows: only DEPOSIT/WITHDRAWAL count as external flows;
    # trades and dividends are already reflected in current_value.
    transactions = [
        {"trans_type": "DEPOSIT", "report_date": date(2026, 1, 1), "amount": 1000},
        {"trans_type": "BOUGHT", "report_date": date(2026, 1, 2), "amount": -1000},
        {"trans_type": "DIV", "report_date": date(2026, 3, 1), "amount": 5},
    ]
    flows = portfolio_cashflows(transactions, current_value=1100, as_of=date(2026, 6, 1))
    assert flows == [(date(2026, 1, 1), -1000), (date(2026, 6, 1), 1100)]

    # no external cash movements at all -> nothing to compute (not even the
    # terminal value, since XIRR needs at least one prior investment date).
    assert portfolio_cashflows([], current_value=1100, as_of=date(2026, 6, 1)) == []


if __name__ == "__main__":
    demo()
    print("OK")
