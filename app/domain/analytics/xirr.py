"""XIRR (money-weighted annualized return) - accounts for *when* cash was
put in, unlike the simple (value - cost) / cost figure already shown
elsewhere, which treats every dollar as if it had been invested on day one.
"""

from datetime import date

EXTERNAL_CASH_IN_TYPES = {"DEPOSIT"}
EXTERNAL_CASH_OUT_TYPES = {"WITHDRAWAL", "WITHDRAW"}


def portfolio_cashflows(transactions: list[dict], current_value: float, as_of: date) -> list[tuple[date, float]]:
    """External cash movements only - deposits (negative, money the investor
    put in) and withdrawals (positive, money taken out). Trades and
    dividends aren't external flows, they just move value around inside the
    account, already reflected in current_value.
    """
    flows = []
    for t in transactions:
        if t["trans_type"] in EXTERNAL_CASH_IN_TYPES:
            flows.append((t["report_date"], -abs(t["amount"])))
        elif t["trans_type"] in EXTERNAL_CASH_OUT_TYPES:
            flows.append((t["report_date"], abs(t["amount"])))
    if flows:
        flows.append((as_of, current_value))
    return flows


def xirr(cashflows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    """Newton's method with a bisection fallback. Returns None if there's no
    sign change in the cashflows (no real solution) or it doesn't converge.
    """
    if len(cashflows) < 2:
        return None
    amounts = [a for _, a in cashflows]
    if all(a <= 0 for a in amounts) or all(a >= 0 for a in amounts):
        return None

    t0 = min(d for d, _ in cashflows)
    years = [(d - t0).days / 365 for d, _ in cashflows]

    def npv(rate: float) -> float:
        return sum(a / (1 + rate) ** y for (_, a), y in zip(cashflows, years))

    def dnpv(rate: float) -> float:
        return sum(-y * a / (1 + rate) ** (y + 1) for (_, a), y in zip(cashflows, years))

    rate = guess
    for _ in range(100):
        try:
            f, fprime = npv(rate), dnpv(rate)
        except (ZeroDivisionError, OverflowError):
            break
        if abs(fprime) < 1e-12:
            break
        new_rate = rate - f / fprime
        if new_rate <= -1:  # would make (1+rate) <= 0, undefined for non-integer exponents
            break
        if abs(new_rate - rate) < 1e-9:
            # Step stalled - only trust it if it's actually a root. In a
            # flat NPV region the step can shrink below the threshold while
            # NPV is still far from zero; fall through to bisection then.
            return new_rate if abs(npv(new_rate)) < 1e-6 else _xirr_bisection(npv)
        rate = new_rate

    return _xirr_bisection(npv)


def _xirr_bisection(npv, low: float = -0.99, high: float = 10.0) -> float | None:
    f_low, f_high = npv(low), npv(high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if (f_low > 0) == (f_high > 0):
        return None  # no sign change in this range either -> give up
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-6:
            return mid
        if (f_mid > 0) == (f_low > 0):
            low, f_low = mid, f_mid
        else:
            high = mid
    return (low + high) / 2
