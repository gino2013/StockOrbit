"""Rough estimate of a Taiwan tax resident's overseas income from US-broker
capital gains + dividends, for a heads-up on whether this year's numbers are
worth mentioning to an accountant.

NOT tax advice. Real thresholds/rules and the exact aggregation method
change over time - check 財政部 (Ministry of Finance) guidance or an
accountant before relying on this for an actual filing.
"""

AGGREGATION_THRESHOLD_TWD = 1_000_000  # 個人基本稅額條例：達此金額才需申報海外所得
EXEMPTION_TWD = 6_700_000  # 基本所得額超過此金額的部分才可能要繳稅（已扣除免稅額後的概念，僅供參考）


def realized_gains_for_year(realized_gains: list[dict], year: int) -> float:
    return sum(r["gain"] for r in realized_gains if r["report_date"].year == year)


def dividend_income_for_year(transactions: list[dict], year: int) -> float:
    return sum(
        t["amount"] for t in transactions if t["trans_type"] == "DIV" and t["report_date"].year == year
    )


def estimate_overseas_income(capital_gains_usd: float, dividend_usd: float, rate: float | None) -> dict:
    total_usd = capital_gains_usd + dividend_usd
    total_twd = (total_usd * rate) if rate is not None else None
    return {
        "capital_gains_usd": capital_gains_usd,
        "dividend_usd": dividend_usd,
        "total_usd": total_usd,
        "usdtwd_rate": rate,
        "total_twd": total_twd,
        "over_aggregation_threshold": (total_twd is not None and total_twd >= AGGREGATION_THRESHOLD_TWD),
    }
