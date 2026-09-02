import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.goals.fire import build_coast_fire, build_fire_progress, coast_fire_number, fire_number


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

    # no retirement_date/expected_real_return -> coast_fire is None, not crash.
    assert result["coast_fire"] is None

    # --- Coast FIRE ---
    # ~10 years @ 5% real return: coast number = target / 1.05^years, using
    # the same days/365.25 year-count build_coast_fire computes internally.
    target = 20000000
    retirement = date(2036, 1, 1)  # ~10 years out
    years = (retirement - as_of).days / 365.25
    coast_num = coast_fire_number(target, years=years, expected_real_return=0.05)
    assert abs(coast_num - target / 1.05**years) < 1e-6
    assert coast_num < target  # compounding for a decade needs less than the raw target today

    coast = build_coast_fire(current_value=coast_num, target=target, retirement_date=retirement,
                              expected_real_return=0.05, as_of=as_of)
    assert coast is not None
    assert coast["already_coasting"] is True  # exactly at the coast number
    assert coast["remaining_to_coast"] == 0.0
    assert abs(coast["projected_value_at_retirement"] - target) < 1e-3

    # short of the coast number -> not coasting yet, still a gap.
    short = build_coast_fire(current_value=coast_num * 0.5, target=target, retirement_date=retirement,
                              expected_real_return=0.05, as_of=as_of)
    assert short["already_coasting"] is False
    assert short["remaining_to_coast"] > 0

    # retirement date already past -> nothing meaningful to coast toward.
    assert build_coast_fire(coast_num, target, date(2025, 1, 1), 0.05, as_of) is None
    assert build_coast_fire(coast_num, target, as_of, 0.05, as_of) is None  # "today" -> zero years left

    # build_fire_progress wires coast_fire through end to end.
    with_coast = build_fire_progress(
        current_value=coast_num, annual_expenses=800000, swr=0.04, current_annual_return=0.08, as_of=as_of,
        retirement_date=retirement, expected_real_return=0.05,
    )
    assert with_coast["coast_fire"]["already_coasting"] is True


if __name__ == "__main__":
    demo()
    print("OK")
