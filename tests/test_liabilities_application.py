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


if __name__ == "__main__":
    demo()
    print("OK")
