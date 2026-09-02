import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.goals.fire import build_fire_progress, fire_number


def demo():
    as_of = date(2026, 1, 1)

    # 4% rule: FIRE number is expenses x25.
    assert abs(fire_number(annual_expenses=800000, swr=0.04) - 20000000) < 1e-6
    # a higher (more aggressive) SWR needs a smaller nest egg.
    assert fire_number(800000, 0.05) < fire_number(800000, 0.04)

    result = build_fire_progress(
        current_value=10000000, annual_expenses=800000, swr=0.04, current_annual_return=0.08, as_of=as_of,
    )
    assert abs(result["fire_number"] - 20000000) < 1e-6
    assert abs(result["progress_pct"] - 0.5) < 1e-9
    assert abs(result["remaining_amount"] - 10000000) < 1e-6
    assert result["already_fire"] is False
    assert result["projected_achievement_date"] is not None  # +8%/yr does get there eventually

    # progress caps at 1.0 and flags already_fire once past the number.
    already_there = build_fire_progress(25000000, 800000, 0.04, 0.05, as_of)
    assert already_there["progress_pct"] == 1.0
    assert already_there["remaining_amount"] == 0.0
    assert already_there["already_fire"] is True
    assert already_there["projected_achievement_date"] == as_of.isoformat()

    # no return / zero return -> can't project a date, not a fabricated one.
    no_return = build_fire_progress(10000000, 800000, 0.04, None, as_of)
    assert no_return["projected_achievement_date"] is None
    zero_return = build_fire_progress(10000000, 800000, 0.04, 0.0, as_of)
    assert zero_return["projected_achievement_date"] is None


if __name__ == "__main__":
    demo()
    print("OK")
