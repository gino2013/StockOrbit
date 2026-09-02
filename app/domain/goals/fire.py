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


def build_fire_progress(
    current_value: float, annual_expenses: float, swr: float, current_annual_return: float | None, as_of: date
) -> dict:
    target = fire_number(annual_expenses, swr)
    progress_pct = min(1.0, current_value / target) if target else None
    proj_date = projected_achievement_date(current_value, target, current_annual_return, as_of)
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
    }
