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

FLEX_RETURN_SINCE = "2017-01-01"


# --- flex mode -------------------------------------------------------------
# Flex mode reframes the whole dashboard as "I bought my *current* position
# (the exact share counts I hold now) back on FLEX_RETURN_SINCE - or on a
# symbol's first trading day if it listed later - and never touched it
# since". Market value / quantity / price stay real (same shares); cost
# basis, unrealized P/L, return %, XIRR, the pace projection, and dividend
# income are all recomputed off that hypothetical 2017 entry. Realized P/L
# is zero (nothing was ever sold). Triggered by typing "flex"; the
# flex_basis / flex_div_per_share inputs are fetched by the route only when
# the cookie is set, and any fetch failure -> flex_basis None -> the
# ordinary figures, page unaffected.


def apply_flex_since(snapshots: list[dict], basis_prices: dict[str, float]) -> list[dict]:
    """Rewrite each holding's cost_basis to `current quantity x basis price`
    (what those shares would have cost at their FLEX_RETURN_SINCE / first-
    listed price). market_value / quantity / price are left real. CASH and
    any symbol with no usable basis keep their real cost_basis so they don't
    distort the totals."""
    out = []
    for s in snapshots:
        b = basis_prices.get(s["symbol"])
        if s["symbol"] == "CASH" or not b or b <= 0:
            out.append(s)
        else:
            out.append({**s, "cost_basis": round(s["quantity"] * b, 2)})
    return out


def flex_cashflows_since(snapshots: list[dict], basis: dict[str, tuple], as_of: date) -> list[tuple]:
    """XIRR cashflows for flex mode: one buy per non-cash symbol at its
    basis *date* for (current quantity x basis price), then the whole
    non-cash position marked to today's market value. A symbol that only
    listed after FLEX_RETURN_SINCE gets its buy at the listing date, so the
    annualized rate reflects the real holding period, not a fake 9 years."""
    flows: list[tuple] = []
    terminal = 0.0
    for s in snapshots:
        if s["symbol"] == "CASH":
            continue
        entry = basis.get(s["symbol"])
        if not entry or entry[1] <= 0:
            continue
        basis_date, basis_price = entry
        flows.append((basis_date, -(s["quantity"] * basis_price)))
        terminal += s["market_value"]
    if flows:
        flows.append((as_of, terminal))
    return flows


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
    flex_basis: dict[str, tuple] | None = None,
    flex_div_per_share: dict[str, float] | None = None,
    as_of: date,
) -> dict:
    sector_allocation = compute_sector_allocation(snapshots, fundamentals_meta) if snapshots else {}
    symbol_sector_buckets = symbol_buckets(snapshots, fundamentals_meta) if snapshots else {}

    daily_allocation_history = allocation_history(snapshot_points) if snapshot_points else None
    allocation_chart_data = chart_series(daily_allocation_history) if daily_allocation_history else None
    concentration_chart_data = concentration_series(daily_allocation_history) if daily_allocation_history else None

    # `flex_active` needs both the toggle AND resolved basis prices - a fetch
    # failure leaves flex_basis None and the dashboard shows the ordinary
    # figures. Once active, "held since 2017" replaces cost basis, XIRR,
    # dividends and realized P/L wholesale (see the flex-mode note above).
    flex_active = flex_mode and bool(flex_basis)
    if flex_active:
        basis_price = {sym: p for sym, (_, p) in flex_basis.items()}
        snapshots = apply_flex_since(snapshots, basis_price)

    # Never sold under "held since 2017" -> no realized gains.
    realized = compute_realized_gains([] if flex_active else transactions)
    realized_summary = {
        "all_time": summarize_realized_gains(realized),
        "this_year": summarize_realized_gains(realized, year=as_of.year),
    }

    advice = build_advice(snapshots, targets, sector_allocation=sector_allocation) if snapshots else None
    rebalance_plan = build_rebalance_plan(snapshots, targets) if snapshots and targets else None
    target_weight_sum = sum(targets.values()) if targets else 0

    total_value = sum(s["market_value"] for s in snapshots)
    total_cost = sum(s["cost_basis"] for s in snapshots)
    total_gain = total_value - total_cost
    total_gain_pct = (total_gain / total_cost) if total_cost else 0

    if flex_active:
        annualized_return = xirr(flex_cashflows_since(snapshots, flex_basis, as_of))
    else:
        # non-flex: nothing scaled `total_value`, so it's the real terminal value.
        annualized_return = xirr(portfolio_cashflows(transactions, total_value, as_of))

    market_value_by_symbol = {s["symbol"]: s["market_value"] for s in snapshots}
    if flex_active and flex_div_per_share is not None:
        # "what my current position would have yielded in the last 12
        # months" - per-symbol TTM dividend-per-share x current quantity.
        ttm_rows = [
            {"symbol": s["symbol"], "ttm_dividends": s["quantity"] * flex_div_per_share.get(s["symbol"], 0.0)}
            for s in snapshots
            if s["symbol"] != "CASH" and flex_div_per_share.get(s["symbol"], 0.0) > 0
        ]
    else:
        ttm_rows = trailing_twelve_month_dividends(transactions, as_of)
    dividend_rows = with_yield(ttm_rows, market_value_by_symbol)

    real_ttm_total = sum(r["ttm_dividends"] for r in trailing_twelve_month_dividends(transactions, as_of))
    flex_ttm_total = sum(r["ttm_dividends"] for r in ttm_rows)
    div_scale = (flex_ttm_total / real_ttm_total) if (flex_active and real_ttm_total) else 1.0
    dividend_calendar = [
        {
            "year": year,
            "month": month,
            "entries": [
                {**e, "estimated_amount": e["estimated_amount"] * div_scale} for e in entries
            ],
        }
        for (year, month), entries in groupby(
            forecast_dividend_calendar(transactions, as_of), key=lambda f: (f["year"], f["month"])
        )
    ]

    stats = {
        "total_value": total_value,
        "total_gain": total_gain,
        "total_gain_pct": total_gain_pct,
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
