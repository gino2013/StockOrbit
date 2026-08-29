"""Progress toward a single long-term target amount/date: how far along,
and what annualized return from here would be needed to hit it on time,
compared against the portfolio's actual XIRR (app/xirr.py) so far, plus a
"stay at the current pace" value projection out to the target date.
"""

import math
from datetime import date, timedelta

_DAYS_PER_MONTH = 30.4375
_MAX_PROJECTION_DAYS = 365 * 40  # don't project a near-zero return for centuries
_MAX_PROJECTION_POINTS = 120  # enough for a smooth line; keeps the payload small


def required_annual_return(current_value: float, target_amount: float, target_date: date, as_of: date) -> float | None:
    years = (target_date - as_of).days / 365.25
    if years <= 0 or current_value <= 0:
        return None
    return (target_amount / current_value) ** (1 / years) - 1


def projected_achievement_date(
    current_value: float, target_amount: float, annual_return: float | None, as_of: date
) -> str | None:
    """When the target is hit if the portfolio keeps compounding at
    `annual_return` from here. None if it never gets there (no/zero/negative
    return), `as_of` itself if already at or past the target."""
    if current_value >= target_amount:
        return as_of.isoformat()
    if annual_return is None or annual_return <= 0 or current_value <= 0:
        return None
    years = math.log(target_amount / current_value) / math.log(1 + annual_return)
    return (as_of + timedelta(days=years * 365.25)).isoformat()


def _projection(current_value: float, annual_return: float | None, as_of: date, until: date) -> list[dict]:
    """Monthly [{date, value}] from `as_of` to `until`, compounding at
    `annual_return`. Empty when there's no return figure to extrapolate."""
    if annual_return is None or current_value <= 0:
        return []
    months = max(1, round((until - as_of).days / _DAYS_PER_MONTH))
    monthly_rate = (1 + annual_return) ** (1 / 12) - 1
    step = max(1, -(-months // _MAX_PROJECTION_POINTS))  # thin out long horizons
    marks = list(range(0, months + 1, step))
    if marks[-1] != months:
        marks.append(months)
    return [
        {
            "date": (as_of + timedelta(days=round(_DAYS_PER_MONTH * m))).isoformat(),
            "value": current_value * (1 + monthly_rate) ** m,
        }
        for m in marks
    ]


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

    proj_date = projected_achievement_date(current_value, target_amount, current_annual_return, as_of)
    # Extend the chart past the target date when the current pace hits the
    # target later than that, so the crossing point is actually visible.
    until = target_date
    if proj_date and proj_date != as_of.isoformat():
        until = max(target_date, date.fromisoformat(proj_date))
    until = min(until, as_of + timedelta(days=_MAX_PROJECTION_DAYS))

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
        "projected_achievement_date": proj_date,
        "projection": _projection(current_value, current_annual_return, as_of, until),
    }
