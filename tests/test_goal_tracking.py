import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.goal_tracking import build_goal_progress, required_annual_return


def demo():
    as_of = date(2026, 1, 1)

    # doubling in exactly 1 year requires exactly +100% annualized.
    rate = required_annual_return(current_value=10000, target_amount=20000, target_date=date(2027, 1, 1), as_of=as_of)
    assert abs(rate - 1.0) < 1e-3

    # already past the target date -> no meaningful required rate.
    assert required_annual_return(10000, 20000, date(2025, 1, 1), as_of) is None
    # zero/negative current value -> can't compute a growth rate from it.
    assert required_annual_return(0, 20000, date(2027, 1, 1), as_of) is None

    result = build_goal_progress(
        current_value=15000, target_amount=20000, target_date=date(2027, 1, 1),
        current_annual_return=0.30, as_of=as_of,
    )
    assert abs(result["progress_pct"] - 0.75) < 1e-9
    assert abs(result["remaining_amount"] - 5000) < 1e-9
    # required rate for 15000 -> 20000 in 1 year is 20000/15000 - 1 ≈ 33.3%
    assert abs(result["required_annual_return"] - (20000 / 15000 - 1)) < 1e-3
    # 30% actual < ~33.3% required -> not on track
    assert result["on_track"] is False

    # progress_pct caps at 1.0 even if current value already exceeds target.
    over_target = build_goal_progress(25000, 20000, date(2027, 1, 1), 0.10, as_of)
    assert over_target["progress_pct"] == 1.0
    assert over_target["remaining_amount"] == 0.0

    # past the target date -> flagged, and no required-rate number to show.
    past_due = build_goal_progress(15000, 20000, date(2025, 1, 1), 0.10, as_of)
    assert past_due["already_past_target_date"] is True
    assert past_due["required_annual_return"] is None
    assert past_due["on_track"] is None  # nothing to compare against


if __name__ == "__main__":
    demo()
    print("OK")
