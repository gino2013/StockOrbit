"""Standard fixed-payment loan amortization (issue #326) - a personal loan
(信貸) used to fund investing, not tied to any brokerage. Payments are
assumed monthly, due on the same day-of-month as `start_date`, first
payment one month after that. Shared by every liability feature (net
worth, leverage-vs-return, amortization table, net-worth history) so
there's exactly one place doing this math, not four slightly different
copies.

If `monthly_payment` doesn't even cover the current month's interest
(negative amortization), the balance grows instead of shrinking -
`remaining_balance`'s closed form naturally reflects that (it's a real,
useful signal: "this loan is upside down"), and `amortization_schedule`
stops and flags it rather than iterating forever.
"""

from calendar import monthrange
from datetime import date


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def _months_elapsed(start_date: date, as_of: date) -> int:
    months = (as_of.year - start_date.year) * 12 + (as_of.month - start_date.month)
    if as_of.day < start_date.day:
        months -= 1
    return max(0, months)


def remaining_balance(principal: float, annual_rate: float, monthly_payment: float, start_date: date, as_of: date) -> float:
    """Closed-form balance after every full monthly payment due on or
    before `as_of`. Clamped to >= 0 - once paid off, a loan stays at 0,
    it doesn't go negative from an overpayment in this model."""
    n = _months_elapsed(start_date, as_of)
    if n <= 0 or principal <= 0:
        return max(0.0, principal)
    r = annual_rate / 12
    if r == 0:
        balance = principal - monthly_payment * n
    else:
        growth = (1 + r) ** n
        balance = principal * growth - monthly_payment * (growth - 1) / r
    return max(0.0, balance)


def amortization_schedule(
    principal: float, annual_rate: float, monthly_payment: float, start_date: date, max_months: int = 600
) -> list[dict]:
    """Month-by-month [{month, date, payment, interest, principal, balance}]
    from the first payment until the balance hits 0 (or `max_months` as a
    safety cap for a loan that will never amortize). The final real payment
    is trimmed to whatever's left, so it isn't overstated."""
    r = annual_rate / 12
    balance = principal
    schedule = []
    for i in range(1, max_months + 1):
        if balance <= 0:
            break
        interest = balance * r
        principal_portion = monthly_payment - interest
        if principal_portion <= 0:
            schedule.append(
                {
                    "month": i,
                    "date": _add_months(start_date, i).isoformat(),
                    "payment": monthly_payment,
                    "interest": interest,
                    "principal": 0.0,
                    "balance": balance,
                    "warning": "月付款不夠付當期利息，本金不會減少",
                }
            )
            break
        principal_portion = min(principal_portion, balance)
        balance -= principal_portion
        schedule.append(
            {
                "month": i,
                "date": _add_months(start_date, i).isoformat(),
                "payment": interest + principal_portion,
                "interest": interest,
                "principal": principal_portion,
                "balance": balance,
            }
        )
    return schedule
