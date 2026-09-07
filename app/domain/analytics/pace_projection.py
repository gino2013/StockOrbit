"""Project the portfolio's current total market value forward to a handful
of standard checkpoints (1 month, 1 quarter, 6 months, 1 year), compounding
at its current XIRR - "if this pace holds, here's roughly where you'd be."
Same compounding assumption as goal_tracking's projection curve, just fixed
checkpoints and no goal/target required.
"""

_CHECKPOINTS = [
    ("1 個月後", 1 / 12, False),
    ("1 季後", 3 / 12, False),
    ("半年後", 6 / 12, False),
    ("1 年後", 1.0, False),
    ("3 年後", 3.0, True),
    ("5 年後", 5.0, True),
    ("10 年後", 10.0, True),
    ("20 年後", 20.0, True),
]

# Above this cumulative change, compounding a short-window annualized rate
# this far out produces a number too extreme to take at face value (e.g.
# a portfolio tracked for only a few months naturally has a noisy, inflated
# XIRR - annualizing it and then compounding for years amplifies that noise
# rather than cancelling it out). Flagged, not hidden - still the honest
# answer to "if this pace holds," just one worth a second look.
EXTREME_CHANGE_PCT = 10.0  # +1000%


def project_at_pace(current_value: float, annual_return: float, annual_contribution: float = 0.0) -> list[dict]:
    """`annual_contribution` (see xirr.estimate_annual_contribution) is added
    as a monthly annuity on top of the compounding lump sum, so the pace
    reflects "if this return *and* my deposit habit both hold"."""
    if current_value <= 0:
        return []
    monthly_rate = (1 + annual_return) ** (1 / 12) - 1
    monthly_contribution = annual_contribution / 12
    results = []
    for label, years, long_term in _CHECKPOINTS:
        months = years * 12
        projected_value = current_value * (1 + monthly_rate) ** months
        if monthly_contribution:
            if monthly_rate:
                projected_value += monthly_contribution * ((1 + monthly_rate) ** months - 1) / monthly_rate
            else:
                projected_value += monthly_contribution * months
        change_pct = (projected_value / current_value) - 1
        results.append(
            {
                "label": label,
                "long_term": long_term,
                "projected_value": projected_value,
                "change": projected_value - current_value,
                "change_pct": change_pct,
                "extreme": abs(change_pct) >= EXTREME_CHANGE_PCT,
            }
        )
    return results
