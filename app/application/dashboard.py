"""Assemble the home dashboard's template context from already-fetched
persistence data. Pure orchestration over domain functions - no I/O, no
HTTP, no session. The route just fetches via Repositories, decides flex
mode from the cookie, and hands the raw data here.
"""

from datetime import date
from itertools import groupby

from app.domain.portfolio.advice import build_advice, build_rebalance_plan
from app.domain.portfolio.allocation_history import allocation_history, chart_series, concentration_series
from app.domain.portfolio.sector_allocation import compute_sector_allocation, symbol_buckets
from app.domain.income.dividends import forecast_dividend_calendar, trailing_twelve_month_dividends, with_yield
from app.domain.income.realized_gains import compute_realized_gains, summarize_realized_gains
from app.domain.analytics.pace_projection import project_at_pace
from app.domain.analytics.xirr import portfolio_cashflows, xirr

FLEX_MODE_MULTIPLIER = 10.1


def apply_flex_mode(snapshots: list[dict]) -> list[dict]:
    """Cosmetic display multiplier (see the hidden toggle in the header).
    Never persisted - a purely presentational scaling of the snapshot dicts.
    round() avoids float artifacts leaking into the un-formatted template."""
    return [
        {
            **s,
            "quantity": round(s["quantity"] * FLEX_MODE_MULTIPLIER, 6),
            "cost_basis": round(s["cost_basis"] * FLEX_MODE_MULTIPLIER, 2),
            "market_value": round(s["market_value"] * FLEX_MODE_MULTIPLIER, 2),
        }
        for s in snapshots
    ]


def build_dashboard_context(
    *,
    snapshots: list[dict],
    targets: dict[str, float],
    transactions: list[dict],
    fundamentals_meta: dict[str, dict],
    snapshot_points: list[dict],
    notes: dict[str, str],
    note_history: dict[str, list[dict]],
    usd_twd_rate: float | None,
    flex_mode: bool,
    as_of: date,
) -> dict:
    sector_allocation = compute_sector_allocation(snapshots, fundamentals_meta) if snapshots else {}
    symbol_sector_buckets = symbol_buckets(snapshots, fundamentals_meta) if snapshots else {}

    daily_allocation_history = allocation_history(snapshot_points) if snapshot_points else None
    allocation_chart_data = chart_series(daily_allocation_history) if daily_allocation_history else None
    concentration_chart_data = concentration_series(daily_allocation_history) if daily_allocation_history else None

    realized = compute_realized_gains(transactions)
    realized_summary = {
        "all_time": summarize_realized_gains(realized),
        "this_year": summarize_realized_gains(realized, year=as_of.year),
    }

    # XIRR's terminal cashflow must be the *real* total value: comparing real
    # deposit history against a flex-inflated ending value blows the rate up
    # into nonsense (seen: 20078% vs the real ~45%). Capture it before flex
    # scaling. total_gain_pct is fine under flex because both its inputs scale.
    real_total_value = sum(s["market_value"] for s in snapshots)
    if flex_mode:
        snapshots = apply_flex_mode(snapshots)

    advice = build_advice(snapshots, targets, sector_allocation=sector_allocation) if snapshots else None
    rebalance_plan = build_rebalance_plan(snapshots, targets) if snapshots and targets else None
    target_weight_sum = sum(targets.values()) if targets else 0

    total_value = sum(s["market_value"] for s in snapshots)
    total_cost = sum(s["cost_basis"] for s in snapshots)
    total_gain = total_value - total_cost
    annualized_return = xirr(portfolio_cashflows(transactions, real_total_value, as_of))

    market_value_by_symbol = {s["symbol"]: s["market_value"] for s in snapshots}
    dividend_rows = with_yield(trailing_twelve_month_dividends(transactions, as_of), market_value_by_symbol)
    dividend_calendar = [
        {"year": year, "month": month, "entries": list(entries)}
        for (year, month), entries in groupby(
            forecast_dividend_calendar(transactions, as_of), key=lambda f: (f["year"], f["month"])
        )
    ]

    stats = {
        "total_value": total_value,
        "total_gain": total_gain,
        "total_gain_pct": (total_gain / total_cost) if total_cost else 0,
        "annualized_return": annualized_return,
        "position_count": sum(1 for s in snapshots if s["symbol"] != "CASH"),
        "usd_twd_rate": usd_twd_rate,
        "total_value_twd": (total_value * usd_twd_rate) if usd_twd_rate else None,
        "total_gain_twd": (total_gain * usd_twd_rate) if usd_twd_rate else None,
    }
    pace_projection = project_at_pace(total_value, annualized_return) if annualized_return is not None else []

    return {
        "snapshots": snapshots,
        "advice": advice,
        "targets": targets,
        "stats": stats,
        "pace_projection": pace_projection,
        "rebalance_plan": rebalance_plan,
        "target_weight_sum": target_weight_sum,
        "realized_summary": realized_summary,
        "realized_trades": sorted(realized, key=lambda r: r["report_date"], reverse=True),
        "dividend_rows": dividend_rows,
        "dividend_calendar": dividend_calendar,
        "sector_allocation": sector_allocation,
        "symbol_sector_buckets": symbol_sector_buckets,
        "allocation_chart_data": allocation_chart_data,
        "concentration_chart_data": concentration_chart_data,
        "notes_by_symbol": notes,
        "note_history_by_symbol": note_history,
        "current_year": as_of.year,
        "total_ttm_dividends": sum(r["ttm_dividends"] for r in dividend_rows),
    }
