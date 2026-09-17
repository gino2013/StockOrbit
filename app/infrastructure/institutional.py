"""Institutional holders + insider transactions for a symbol - objective
reference data, no buy/sell interpretation added.

Same known limitation as fundamentals.py: on Render, Yahoo rejects the
crumb-authenticated quoteSummary API this relies on. Unlike fundamentals.py
this is NOT wired into the scheduled cache-refresh job - it's a live-only,
best-effort reference card (same convention as market_moves.py /
stock_detail.fetch_quote()), since an ETF genuinely having no institutional
data looks identical to a blocked call (both come back as empty frames, no
exception raised), so there's no reliable "did this actually fail" signal
worth caching around, unlike fundamentals.py's get_info() which still
returns *some* fields even when partially blocked.
"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

_MAX_INSIDER_ROWS = 10  # most recent N is plenty for a reference card, not a full filing archive


def fetch_institutional_data(symbol: str) -> dict:
    empty = {
        "institutional_holders": [],
        "insider_transactions": [],
        "insiders_pct_held": None,
        "institutions_pct_held": None,
    }
    try:
        ticker = yf.Ticker(symbol)
        institutional = ticker.institutional_holders
        major = ticker.major_holders
        insiders = ticker.insider_transactions
    except Exception as e:
        logger.warning("institutional data fetch failed for %s: %s: %s", symbol, type(e).__name__, e)
        return empty

    holders = (
        [
            {
                "holder": row.get("Holder"),
                "pct_held": row.get("pctHeld"),
                "shares": row.get("Shares"),
                "value": row.get("Value"),
                "date_reported": _isoformat(row.get("Date Reported")),
            }
            for row in institutional.to_dict("records")
        ]
        if institutional is not None and not institutional.empty
        else []
    )
    insider_rows = (
        [
            {
                "insider": row.get("Insider"),
                "position": row.get("Position"),
                "text": row.get("Text"),
                "shares": row.get("Shares"),
                "start_date": _isoformat(row.get("Start Date")),
            }
            for row in insiders.to_dict("records")
        ]
        if insiders is not None and not insiders.empty
        else []
    )
    major_dict = major["Value"].to_dict() if major is not None and not major.empty else {}

    return {
        "institutional_holders": holders,
        "insider_transactions": insider_rows[:_MAX_INSIDER_ROWS],
        "insiders_pct_held": major_dict.get("insidersPercentHeld"),
        "institutions_pct_held": major_dict.get("institutionsPercentHeld"),
    }


def _isoformat(value) -> str | None:
    return value.date().isoformat() if value is not None and hasattr(value, "date") else None
