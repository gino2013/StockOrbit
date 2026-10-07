import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.application.liabilities import liability_summary


def demo():
    liabilities = [
        {"id": "1", "name": "信貸-A", "principal": 500000.0, "annual_rate": 0.03, "monthly_payment": 5000.0, "start_date": "2025-01-01"},
    ]
    snapshots = [{"symbol": "AAPL", "market_value": 20000.0}]
    transactions = [
        {"trans_type": "DEPOSIT", "symbol": None, "report_date": date(2025, 1, 1), "quantity": 0, "trade_price": 0, "amount": -15000.0},
    ]
    as_of = date(2026, 1, 1)

    result = liability_summary(liabilities=liabilities, snapshots=snapshots, transactions=transactions, as_of=as_of)

    # remaining_balance shows up per-row, matching app.domain.liabilities.amortization directly.
    assert len(result["liabilities"]) == 1
    assert result["liabilities"][0]["remaining_balance"] < 500000.0  # a year of $5000/mo payments has paid some down
    assert result["liabilities"][0]["name"] == "信貸-A"  # original fields pass through untouched

    # portfolio grew from a $15000 deposit to $20000 over ~1 year -> a real, positive XIRR.
    assert result["portfolio_return"] is not None
    assert result["portfolio_return"] > 0

    assert result["weighted_average_rate"] == 0.03  # single loan, matches its own rate
    assert result["leverage_spread"] == result["portfolio_return"] - 0.03

    # --- no liabilities at all -> weighted rate/spread are None, not 0. ---
    empty = liability_summary(liabilities=[], snapshots=snapshots, transactions=transactions, as_of=as_of)
    assert empty["liabilities"] == []
    assert empty["weighted_average_rate"] is None
    assert empty["leverage_spread"] is None
    assert empty["portfolio_return"] is not None  # portfolio return still computable without any debt

    # --- no holdings at all -> portfolio_return None, spread None (nothing
    # to compare the loan rate against), not a crash. ---
    no_holdings = liability_summary(liabilities=liabilities, snapshots=[], transactions=[], as_of=as_of)
    assert no_holdings["portfolio_return"] is None
    assert no_holdings["leverage_spread"] is None
    assert no_holdings["weighted_average_rate"] == 0.03  # still computable - doesn't need portfolio data

    # --- TWD loans (issue #382): stored in NT$, converted at the CURRENT rate.
    twd_loan = {"id": "2", "name": "樂天", "principal": 730000.0, "annual_rate": 0.0288, "monthly_payment": 7009.0,
                "start_date": "2025-01-01", "currency": "TWD"}
    at_32 = liability_summary(liabilities=[twd_loan], snapshots=snapshots, transactions=transactions, as_of=as_of, usd_twd_rate=32.0)
    at_30 = liability_summary(liabilities=[twd_loan], snapshots=snapshots, transactions=transactions, as_of=as_of, usd_twd_rate=30.0)
    r32, r30 = at_32["liabilities"][0], at_30["liabilities"][0]
    assert r32["remaining_balance_twd"] == r32["remaining_balance"] == r30["remaining_balance_twd"]  # NT$ side never moves
    assert abs(r32["remaining_balance_usd"] - r32["remaining_balance"] / 32.0) < 1e-6
    assert r30["remaining_balance_usd"] > r32["remaining_balance_usd"]  # weaker NT$ -> bigger USD debt
    assert r32["principal_twd"] == 730000.0
    # term: 730000 @2.88% paid 7009/mo -> roughly 120 payments (10 years), 12 elapsed.
    assert 115 <= r32["term_months"] <= 125 and r32["remaining_months"] == r32["term_months"] - 12
    # USD-stored loan shown in NT$ at the current rate; no rate -> None, not a crash.
    usd_row = liability_summary(liabilities=liabilities, snapshots=snapshots, transactions=transactions, as_of=as_of, usd_twd_rate=32.0)["liabilities"][0]
    assert abs(usd_row["principal_twd"] - 500000.0 * 32.0) < 1e-6
    assert liability_summary(liabilities=liabilities, snapshots=snapshots, transactions=transactions, as_of=as_of)["liabilities"][0]["principal_twd"] is None
    # payment below monthly interest never amortizes -> no term.
    never = {**twd_loan, "monthly_payment": 100.0}
    assert liability_summary(liabilities=[never], snapshots=[], transactions=[], as_of=as_of, usd_twd_rate=32.0)["liabilities"][0]["term_months"] is None

    # --- entered term (issue #388): overrides the payment-derived count, and
    # payment_for_term inverts remaining_balance (balance hits ~0 at the term).
    from app.domain.liabilities.amortization import payment_for_term, remaining_balance

    pay = payment_for_term(730000.0, 0.0288, 84)
    assert abs(remaining_balance(730000.0, 0.0288, pay, date(2020, 1, 1), date(2027, 1, 1))) < 1.0
    assert payment_for_term(1200.0, 0.0, 12) == 100.0
    termed = {**twd_loan, "monthly_payment": pay, "term_months": 84}
    row = liability_summary(liabilities=[termed], snapshots=[], transactions=[], as_of=as_of, usd_twd_rate=32.0)["liabilities"][0]
    assert row["term_months"] == 84 and row["remaining_months"] == 84 - 12


if __name__ == "__main__":
    demo()
    print("OK")
