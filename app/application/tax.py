"""Overseas-income and tax-loss-harvesting use cases. Both combine realized
capital gains + dividend income for a year, converted to TWD, then estimate
reporting-threshold / tax-saving figures. Pure orchestration."""

from app.domain.income.overseas_income import (
    dividend_income_for_year,
    estimate_overseas_income,
    realized_gains_for_year,
)
from app.domain.income.realized_gains import compute_realized_gains
from app.domain.income.tax_loss_harvesting import estimate_tax_savings, find_loss_candidates


def _income_for_year(transactions: list[dict], year: int, rate: float | None) -> dict:
    realized = compute_realized_gains(transactions)
    capital_gains = realized_gains_for_year(realized, year)
    dividends = dividend_income_for_year(transactions, year)
    return estimate_overseas_income(capital_gains, dividends, rate)


def overseas_income_report(transactions: list[dict], year: int, rate: float | None) -> dict:
    return {**_income_for_year(transactions, year, rate), "year": year}


def tax_loss_report(
    snapshots: list[dict], transactions: list[dict], year: int, rate: float
) -> dict:
    candidates = find_loss_candidates(snapshots)
    income = _income_for_year(transactions, year, rate)
    savings = estimate_tax_savings(candidates, income["total_twd"], rate)
    return {"year": year, "candidates": candidates, "income": income, **savings}
