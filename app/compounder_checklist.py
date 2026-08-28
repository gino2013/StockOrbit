"""Rule-based, objective checklist for whether a stock's own history
actually supports "buy and hold this specific company for a decade to
compound" — not whether it's a good buy, not a price target. Every check
is shown with its real number; there's deliberately no overall score or
pass/fail verdict computed anywhere in this module — the user weighs
whether the combination of facts is enough to trust a long hold themselves.

Two things have to both hold for individual-stock compounding to work:
survivability (won't the company still exist and be growing in 10 years?)
and whether its real history has actually shown compounding rather than
just being volatile (high volatility erodes the geometric mean toward zero
even when the arithmetic average return looks fine — see app/compound_curve.py).
"""

from datetime import datetime

from app.compound_curve import arithmetic_mean_return, fetch_annual_returns, geometric_mean_return
from app.risk import compute_risk_metrics

MIN_MARKET_CAP = 2_000_000_000  # below this, "micro-cap" delisting/survival risk rises sharply
MAX_DEBT_TO_EQUITY = 100  # same threshold the fundamentals table already color-codes green at
MIN_HISTORY_YEARS = 5
VOLATILITY_EROSION_THRESHOLD = 0.40  # annualized volatility
EROSION_GAP_THRESHOLD = 0.05  # arithmetic-vs-geometric mean gap that counts as "real" erosion


def build_compounder_checklist(symbol: str, fundamentals: dict, min_years: int = MIN_HISTORY_YEARS) -> dict:
    """fundamentals is one symbol's field dict, e.g. from fetch_fundamentals()
    (already merged with FundamentalsCache fallback by the caller — see
    /api/fundamentals for why that merge can't happen in here on Render)."""
    symbol = symbol.upper()
    risk_items = compute_risk_metrics([symbol])
    risk = risk_items[0] if risk_items else {}

    current_year = datetime.now().year
    returns = fetch_annual_returns(symbol, current_year - min_years, current_year)
    years_available = len(returns)
    geometric_mean = geometric_mean_return(returns) if returns else None
    arithmetic_mean = arithmetic_mean_return(returns) if returns else None

    profit_margin = fundamentals.get("profitMargins")
    debt_to_equity = fundamentals.get("debtToEquity")
    revenue_growth = fundamentals.get("revenueGrowth")
    earnings_growth = fundamentals.get("earningsGrowth")
    market_cap = fundamentals.get("marketCap")
    volatility_90d = risk.get("volatility_90d")

    erosion = (
        volatility_90d is not None
        and volatility_90d > VOLATILITY_EROSION_THRESHOLD
        and arithmetic_mean is not None
        and geometric_mean is not None
        and (arithmetic_mean - geometric_mean) > EROSION_GAP_THRESHOLD
    )
    erosion_value = (
        f"年化波動度 {volatility_90d:.1%}，算術/幾何平均差距 {(arithmetic_mean - geometric_mean):.1%}"
        if volatility_90d is not None and arithmetic_mean is not None and geometric_mean is not None
        else "無資料"
    )

    checks = [
        {
            "label": "獲利能力：毛利率為正",
            "passed": profit_margin is not None and profit_margin > 0,
            "value": f"{profit_margin:.1%}" if profit_margin is not None else "無資料",
        },
        {
            "label": f"財務體質：負債權益比 < {MAX_DEBT_TO_EQUITY}",
            "passed": debt_to_equity is not None and debt_to_equity < MAX_DEBT_TO_EQUITY,
            "value": f"{debt_to_equity:.0f}" if debt_to_equity is not None else "無資料",
        },
        {
            "label": "持續成長：營收成長率為正",
            "passed": revenue_growth is not None and revenue_growth > 0,
            "value": f"{revenue_growth:.1%}" if revenue_growth is not None else "無資料",
        },
        {
            "label": "持續成長：EPS 成長率為正",
            "passed": earnings_growth is not None and earnings_growth > 0,
            "value": f"{earnings_growth:.1%}" if earnings_growth is not None else "無資料",
        },
        {
            "label": f"公司規模：市值 ≥ ${MIN_MARKET_CAP / 1e9:.0f}B（非微型股，存活力較高）",
            "passed": market_cap is not None and market_cap >= MIN_MARKET_CAP,
            "value": f"${market_cap / 1e9:.1f}B" if market_cap is not None else "無資料",
        },
        {
            "label": f"歷史夠長：至少 {min_years} 年股價歷史可供判斷",
            "passed": years_available >= min_years,
            "value": f"{years_available} 年",
        },
        {
            "label": "歷史複利是否成立：幾何平均年化報酬率（CAGR）為正",
            "passed": geometric_mean is not None and geometric_mean > 0,
            "value": f"{geometric_mean:.1%}" if geometric_mean is not None else "無資料",
        },
        {
            "label": "歷史複利是否成立：波動沒有嚴重侵蝕複利效果",
            "passed": not erosion,
            "value": erosion_value,
        },
    ]

    return {"symbol": symbol, "checks": checks}
