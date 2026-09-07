"""Progress toward a single long-term target amount/date: how far along,
and what annualized return from here would be needed to hit it on time,
compared against the portfolio's actual XIRR (app/xirr.py) so far, plus a
"stay at the current pace" value projection out to the target date.

The projection compounds the current value at XIRR *and* adds the
investor's historical rate of fresh deposits (`annual_contribution`) - see
xirr.estimate_annual_contribution - so someone who reliably adds cash each
year isn't told they'll fall short on investment return alone.
"""

import math
from datetime import date, timedelta

_DAYS_PER_MONTH = 30.4375
_MAX_PROJECTION_DAYS = 365 * 40  # don't project a near-zero return for centuries
_MAX_PROJECTION_POINTS = 120  # enough for a smooth line; keeps the payload small
_MAX_PROJECTION_MONTHS = round(_MAX_PROJECTION_DAYS / _DAYS_PER_MONTH)


def required_annual_return(current_value: float, target_amount: float, target_date: date, as_of: date) -> float | None:
    years = (target_date - as_of).days / 365.25
    if years <= 0 or current_value <= 0:
        return None
    return (target_amount / current_value) ** (1 / years) - 1


def _monthly_rate(annual_return: float) -> float:
    return (1 + annual_return) ** (1 / 12) - 1


def _value_after_months(current_value: float, monthly_rate: float, monthly_contribution: float, m: int) -> float:
    """Future value of a lump sum plus an ordinary monthly annuity."""
    grown = current_value * (1 + monthly_rate) ** m
    if monthly_contribution:
        if monthly_rate:
            grown += monthly_contribution * ((1 + monthly_rate) ** m - 1) / monthly_rate
        else:
            grown += monthly_contribution * m
    return grown


def projected_achievement_date(
    current_value: float, target_amount: float, annual_return: float | None, as_of: date,
    annual_contribution: float = 0.0,
) -> str | None:
    """When the target is hit if the portfolio keeps compounding at
    `annual_return` *and* the investor keeps adding `annual_contribution`
    per year. None if it never gets there, `as_of` itself if already at or
    past the target.

    With no contributions and a positive return this is the old closed
    form; with contributions there's no clean inverse, so it steps month by
    month (capped at _MAX_PROJECTION_MONTHS). Contributions also mean a
    zero/negative return can still reach the target eventually - the
    deposits alone get there - so that case is no longer short-circuited to
    None when `annual_contribution > 0`."""
    if current_value >= target_amount:
        return as_of.isoformat()
    if annual_return is None or current_value <= 0:
        return None

    if annual_contribution <= 0:
        if annual_return <= 0:
            return None
        years = math.log(target_amount / current_value) / math.log(1 + annual_return)
        return (as_of + timedelta(days=years * 365.25)).isoformat()

    monthly_rate = _monthly_rate(annual_return)
    monthly_contribution = annual_contribution / 12
    for m in range(1, _MAX_PROJECTION_MONTHS + 1):
        if _value_after_months(current_value, monthly_rate, monthly_contribution, m) >= target_amount:
            return (as_of + timedelta(days=round(_DAYS_PER_MONTH * m))).isoformat()
    return None


def _projection(
    current_value: float, annual_return: float | None, as_of: date, until: date,
    annual_contribution: float = 0.0,
) -> list[dict]:
    """Monthly [{date, value}] from `as_of` to `until`, compounding at
    `annual_return` and adding `annual_contribution / 12` each month. Empty
    when there's no return figure to extrapolate."""
    if annual_return is None or current_value <= 0:
        return []
    months = max(1, round((until - as_of).days / _DAYS_PER_MONTH))
    monthly_rate = _monthly_rate(annual_return)
    monthly_contribution = annual_contribution / 12
    step = max(1, -(-months // _MAX_PROJECTION_POINTS))  # thin out long horizons
    marks = list(range(0, months + 1, step))
    if marks[-1] != months:
        marks.append(months)
    return [
        {
            "date": (as_of + timedelta(days=round(_DAYS_PER_MONTH * m))).isoformat(),
            "value": _value_after_months(current_value, monthly_rate, monthly_contribution, m),
        }
        for m in marks
    ]


def build_goal_progress(
    current_value: float, target_amount: float, target_date: date, current_annual_return: float | None, as_of: date,
    annual_contribution: float = 0.0,
) -> dict:
    progress_pct = min(1.0, current_value / target_amount) if target_amount else None
    required_rate = required_annual_return(current_value, target_amount, target_date, as_of)
    on_track = (
        current_annual_return >= required_rate
        if required_rate is not None and current_annual_return is not None
        else None
    )

    proj_date = projected_achievement_date(
        current_value, target_amount, current_annual_return, as_of, annual_contribution
    )
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
        "annual_contribution": annual_contribution,
        "already_past_target_date": (target_date - as_of).days <= 0,
        "on_track": on_track,
        "projected_achievement_date": proj_date,
        "projection": _projection(
            current_value, current_annual_return, as_of, until, annual_contribution
        ),
    }
