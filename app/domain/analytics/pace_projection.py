"""Project the portfolio's current total market value forward to a handful
of standard checkpoints (1 month, 1 quarter, 6 months, 1 year), compounding
at its current XIRR - "if this pace holds, here's roughly where you'd be."
Same compounding assumption as goal_tracking's projection curve, just fixed
checkpoints and no goal/target required.
"""

_CHECKPOINTS = [
    ("1 個月後", 1 / 12),
    ("1 季後", 3 / 12),
    ("半年後", 6 / 12),
    ("1 年後", 1.0),
]


def project_at_pace(current_value: float, annual_return: float) -> list[dict]:
    if current_value <= 0:
        return []
    results = []
    for label, years in _CHECKPOINTS:
        projected_value = current_value * (1 + annual_return) ** years
        results.append(
            {
                "label": label,
                "projected_value": projected_value,
                "change": projected_value - current_value,
                "change_pct": (projected_value / current_value) - 1,
            }
        )
    return results
