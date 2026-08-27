import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.overseas_income import (
    dividend_income_for_year,
    estimate_overseas_income,
    realized_gains_for_year,
)


def demo():
    realized = [
        {"report_date": date(2025, 6, 1), "gain": 500},
        {"report_date": date(2026, 3, 1), "gain": 1000},
        {"report_date": date(2026, 8, 1), "gain": -200},
    ]
    assert realized_gains_for_year(realized, 2026) == 800
    assert realized_gains_for_year(realized, 2025) == 500
    assert realized_gains_for_year(realized, 2027) == 0

    transactions = [
        {"trans_type": "DIV", "report_date": date(2026, 7, 10), "amount": 7.76},
        {"trans_type": "DIV", "report_date": date(2025, 7, 10), "amount": 5.0},
        {"trans_type": "INTEREST", "report_date": date(2026, 8, 17), "amount": 0.01},
    ]
    assert abs(dividend_income_for_year(transactions, 2026) - 7.76) < 1e-9

    result = estimate_overseas_income(capital_gains_usd=800, dividend_usd=7.76, rate=31.5)
    assert abs(result["total_usd"] - 807.76) < 1e-6
    assert abs(result["total_twd"] - 807.76 * 31.5) < 1e-6
    assert result["over_aggregation_threshold"] is False  # well under NT$1M

    no_rate = estimate_overseas_income(capital_gains_usd=800, dividend_usd=0, rate=None)
    assert no_rate["total_twd"] is None
    assert no_rate["over_aggregation_threshold"] is False


if __name__ == "__main__":
    demo()
    print("OK")
