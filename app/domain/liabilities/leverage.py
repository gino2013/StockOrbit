"""Is borrowing to invest actually paying off (issue #330)? Compares the
portfolio's money-weighted return (XIRR, already computed elsewhere - see
app/application/liabilities.py) against the liabilities' balance-weighted
interest rate. Purely a spread calculation - not investment advice, and it
says nothing about *future* risk (a positive spread today doesn't mean the
borrowed money will keep outperforming its cost).
"""


def weighted_average_rate(balances_and_rates: list[tuple[float, float]]) -> float | None:
    """balances_and_rates: [(remaining_balance, annual_rate), ...]. Weighted
    by remaining balance - a paid-off loan (balance 0) no longer costs
    anything and drops out entirely, rather than dragging the average with
    its original rate. None when there's nothing left owed."""
    total = sum(b for b, _ in balances_and_rates if b > 0)
    if not total:
        return None
    return sum(b * r for b, r in balances_and_rates if b > 0) / total


def leverage_spread(portfolio_return: float | None, weighted_rate: float | None) -> float | None:
    if portfolio_return is None or weighted_rate is None:
        return None
    return portfolio_return - weighted_rate
