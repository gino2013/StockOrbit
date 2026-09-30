import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.liabilities.amortization import amortization_schedule, remaining_balance


def demo():
    # --- zero-interest loan: pure linear paydown, hand-checkable. ---
    start = date(2025, 1, 15)
    assert remaining_balance(12000, 0.0, 1000, start, date(2025, 1, 15)) == 12000  # no payment made yet
    assert remaining_balance(12000, 0.0, 1000, start, date(2025, 2, 15)) == 11000  # 1 payment made
    assert remaining_balance(12000, 0.0, 1000, start, date(2025, 6, 15)) == 7000  # 5 payments made
    assert remaining_balance(12000, 0.0, 1000, start, date(2026, 1, 15)) == 0  # fully paid off, clamped at 0

    # a day before the due date doesn't count as a payment made yet.
    assert remaining_balance(12000, 0.0, 1000, start, date(2025, 2, 14)) == 12000

    # --- with real interest: remaining_balance (closed form) must agree
    # with amortization_schedule (iterative) at every checkpoint - the
    # whole point of sharing this module across features is that they
    # can't silently disagree with each other. ---
    principal, rate, payment = 500000.0, 0.03, 5000.0
    schedule = amortization_schedule(principal, rate, payment, start, max_months=200)
    assert schedule[0]["month"] == 1
    assert abs(schedule[0]["interest"] - principal * rate / 12) < 1e-6
    assert abs(schedule[0]["principal"] + schedule[0]["interest"] - schedule[0]["payment"]) < 1e-6

    for entry in [schedule[0], schedule[5], schedule[-1]]:
        n = entry["month"]
        as_of = date.fromisoformat(entry["date"])
        assert abs(remaining_balance(principal, rate, payment, start, as_of) - entry["balance"]) < 1e-6, n

    # loan reaches exactly 0 (not negative) and schedule stops there.
    assert schedule[-1]["balance"] == 0.0
    assert all(e["balance"] >= 0 for e in schedule)

    # --- negative amortization: payment doesn't cover interest -> balance
    # never shrinks, schedule flags it and stops instead of looping
    # forever (would otherwise run to max_months). ---
    bad_schedule = amortization_schedule(100000, 0.24, 100, start, max_months=600)
    assert bad_schedule[-1].get("warning")
    assert len(bad_schedule) == 1  # stops immediately, doesn't run out the full 600

    # remaining_balance still returns a (growing) real number for the same
    # scenario, not a crash - useful as its own signal.
    later = remaining_balance(100000, 0.24, 100, start, date(2027, 1, 15))
    assert later > 100000

    # --- fully paid off loan stays at 0 far past its term. ---
    assert remaining_balance(12000, 0.0, 1000, start, date(2030, 1, 1)) == 0

    # --- non-positive principal is a no-op, not a crash. ---
    assert remaining_balance(0, 0.05, 100, start, date(2026, 1, 1)) == 0


if __name__ == "__main__":
    demo()
    print("OK")
