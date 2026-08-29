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


def project_at_pace(current_value: float, annual_return: float) -> list[dict]:
    if current_value <= 0:
        return []
    results = []
    for label, years, long_term in _CHECKPOINTS:
        projected_value = current_value * (1 + annual_return) ** years
        results.append(
            {
                "label": label,
                "long_term": long_term,
                "projected_value": projected_value,
                "change": projected_value - current_value,
                "change_pct": (projected_value / current_value) - 1,
            }
        )
    return results
