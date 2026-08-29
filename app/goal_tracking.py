"""Progress toward a single long-term target amount/date: how far along,
and what annualized return from here would be needed to hit it on time,
compared against the portfolio's actual XIRR (app/xirr.py) so far.
"""

from datetime import date


def required_annual_return(current_value: float, target_amount: float, target_date: date, as_of: date) -> float | None:
    years = (target_date - as_of).days / 365.25
    if years <= 0 or current_value <= 0:
        return None
    return (target_amount / current_value) ** (1 / years) - 1


def build_goal_progress(
    current_value: float, target_amount: float, target_date: date, current_annual_return: float | None, as_of: date
) -> dict:
    progress_pct = min(1.0, current_value / target_amount) if target_amount else None
    required_rate = required_annual_return(current_value, target_amount, target_date, as_of)
    on_track = (
        current_annual_return >= required_rate
        if required_rate is not None and current_annual_return is not None
        else None
    )
    return {
        "current_value": current_value,
        "target_amount": target_amount,
        "target_date": target_date.isoformat(),
        "progress_pct": progress_pct,
        "remaining_amount": max(0.0, target_amount - current_value),
        "required_annual_return": required_rate,
        "current_annual_return": current_annual_return,
        "already_past_target_date": (target_date - as_of).days <= 0,
        "on_track": on_track,
    }
