import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.income.realized_gains import compute_realized_gains, summarize_realized_gains


def demo():
    transactions = [
        {"trans_type": "BOUGHT", "symbol": "AAPL", "report_date": date(2025, 1, 10), "quantity": 10, "trade_price": 100},
        {"trans_type": "BOUGHT", "symbol": "AAPL", "report_date": date(2025, 6, 1), "quantity": 10, "trade_price": 150},
        # sells 15 shares: FIFO takes all 10 @ $100 lot + 5 of the $150 lot.
        {"trans_type": "SOLD", "symbol": "AAPL", "report_date": date(2026, 1, 5), "quantity": 15, "trade_price": 200},
        # unrelated symbol/noise rows should be ignored.
        {"trans_type": "DIV", "symbol": "AAPL", "report_date": date(2025, 3, 1), "quantity": 0, "trade_price": 0},
    ]
    realized = compute_realized_gains(transactions)
    assert len(realized) == 1
    row = realized[0]
    expected_cost = 10 * 100 + 5 * 150
    expected_proceeds = 15 * 200
    assert abs(row["cost_basis"] - expected_cost) < 1e-6
    assert abs(row["proceeds"] - expected_proceeds) < 1e-6
    assert abs(row["gain"] - (expected_proceeds - expected_cost)) < 1e-6
    assert row["unmatched_quantity"] == 0

    summary_all = summarize_realized_gains(realized)
    assert abs(summary_all["total_gain"] - (expected_proceeds - expected_cost)) < 1e-6
    assert summary_all["trade_count"] == 1
    assert summary_all["has_unmatched"] is False

    summary_2025 = summarize_realized_gains(realized, year=2025)
    assert summary_2025["trade_count"] == 0  # the sale happened in 2026

    # selling more than we have BOUGHT history for -> partial cost basis,
    # flagged via unmatched_quantity rather than assumed to be zero cost.
    # Proceeds are scaled to the *matched* 5 shares too, so `gain` is a
    # like-for-like figure (5*320 - 5*300 = 100), not full proceeds
    # (8*320) against the partial 5-share cost.
    short_sale_history = [
        {"trans_type": "BOUGHT", "symbol": "MSFT", "report_date": date(2026, 1, 1), "quantity": 5, "trade_price": 300},
        {"trans_type": "SOLD", "symbol": "MSFT", "report_date": date(2026, 2, 1), "quantity": 8, "trade_price": 320},
    ]
    realized2 = compute_realized_gains(short_sale_history)
    assert abs(realized2[0]["unmatched_quantity"] - 3) < 1e-6
    assert abs(realized2[0]["cost_basis"] - 5 * 300) < 1e-6
    assert abs(realized2[0]["proceeds"] - 5 * 320) < 1e-6
    assert abs(realized2[0]["gain"] - (5 * 320 - 5 * 300)) < 1e-6

    # same-day round trip: SOLD row listed before its BOUGHT row. The
    # secondary sort key (BOUGHT before SOLD on equal dates) makes the sell
    # match that day's purchase rather than going unmatched at zero cost.
    same_day = [
        {"trans_type": "SOLD", "symbol": "NVDA", "report_date": date(2026, 3, 4), "quantity": 10, "trade_price": 130},
        {"trans_type": "BOUGHT", "symbol": "NVDA", "report_date": date(2026, 3, 4), "quantity": 10, "trade_price": 120},
    ]
    r3 = compute_realized_gains(same_day)
    assert r3[0]["unmatched_quantity"] == 0
    assert abs(r3[0]["cost_basis"] - 10 * 120) < 1e-6
    assert abs(r3[0]["gain"] - (10 * 130 - 10 * 120)) < 1e-6


if __name__ == "__main__":
    demo()
    print("OK")
