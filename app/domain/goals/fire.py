"""FIRE (financial independence, retire early) progress: the 4%-rule FIRE
number, and how far the current portfolio is from it.

Unlike goal_tracking (a target amount *and* date), FIRE has no deadline -
just "when do I get there at the current pace" - so this reuses
goal_tracking.projected_achievement_date directly instead of the full
build_goal_progress (which needs a target_date to compute a required rate).
"""

from datetime import date

from app.domain.goals.goal_tracking import projected_achievement_date


def fire_number(annual_expenses: float, swr: float) -> float:
    """Portfolio size that supports annual_expenses in perpetuity at the
    given safe withdrawal rate (0.04 = the 4% rule -> expenses x25)."""
    return annual_expenses / swr


def coast_fire_number(target: float, years: float, expected_real_return: float) -> float:
    """Portfolio size needed *today* to compound - with no further
    contributions - to `target` in `years` years at `expected_real_return`.
    Below this, more contributions are still needed; at or above it, the
    current portfolio can "coast" to FIRE on growth alone."""
    return target / (1 + expected_real_return) ** years


def build_coast_fire(
    current_value: float, target: float, retirement_date: date, expected_real_return: float, as_of: date
) -> dict | None:
    """None when there's no time left to compound (retirement_date already
    here or past) - coasting isn't a meaningful question at that point."""
    years = (retirement_date - as_of).days / 365.25
    if years <= 0:
        return None
    coast_number = coast_fire_number(target, years, expected_real_return)
    projected_at_retirement = current_value * (1 + expected_real_return) ** years
    return {
        "retirement_date": retirement_date.isoformat(),
        "expected_real_return": expected_real_return,
        "coast_fire_number": coast_number,
        "already_coasting": current_value >= coast_number,
        "remaining_to_coast": max(0.0, coast_number - current_value),
        "projected_value_at_retirement": projected_at_retirement,
    }


def build_dividend_coverage(ttm_dividends: float, annual_expenses: float, current_value: float) -> dict:
    """How much of annual_expenses the trailing-12-month dividend income
    already covers (the "Barista/Dividend FIRE" angle), plus - at the
    current overall yield - roughly how much principal full coverage would
    take. Not a projection: today's yield, held constant."""
    overall_yield = (ttm_dividends / current_value) if current_value else None
    return {
        "ttm_dividends": ttm_dividends,
        "coverage_pct": (ttm_dividends / annual_expenses) if annual_expenses else None,
        "overall_yield": overall_yield,
        "principal_for_full_coverage": (annual_expenses / overall_yield) if overall_yield else None,
    }


def build_fire_progress(
    current_value: float, annual_expenses: float, swr: float, current_annual_return: float | None, as_of: date,
    retirement_date: date | None = None, expected_real_return: float | None = None,
    ttm_dividends: float | None = None,
) -> dict:
    target = fire_number(annual_expenses, swr)
    progress_pct = min(1.0, current_value / target) if target else None
    proj_date = projected_achievement_date(current_value, target, current_annual_return, as_of)
    coast = (
        build_coast_fire(current_value, target, retirement_date, expected_real_return, as_of)
        if retirement_date and expected_real_return is not None
        else None
    )
    dividend_coverage = (
        build_dividend_coverage(ttm_dividends, annual_expenses, current_value)
        if ttm_dividends is not None
        else None
    )
    return {
        "annual_expenses": annual_expenses,
        "swr": swr,
        "fire_number": target,
        "current_value": current_value,
        "progress_pct": progress_pct,
        "remaining_amount": max(0.0, target - current_value),
        "already_fire": current_value >= target,
        "current_annual_return": current_annual_return,
        "projected_achievement_date": proj_date,
        "coast_fire": coast,
        "dividend_coverage": dividend_coverage,
    }
