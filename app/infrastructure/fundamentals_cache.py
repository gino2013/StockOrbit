"""Read/write for FundamentalsCache - see app.db.FundamentalsCache for why
this exists (Render can't reach Yahoo's quoteSummary API directly).
"""

from datetime import datetime, timezone

from app.infrastructure.db import FundamentalsCache
from app.infrastructure.fundamentals import FIELDS


def save_fundamentals(db, symbol: str, fields: dict, next_earnings_date: str | None) -> None:
    row = db.get(FundamentalsCache, symbol)
    if row is None:
        row = FundamentalsCache(symbol=symbol)
        db.add(row)
    for field in FIELDS:
        setattr(row, field, fields.get(field))
    row.next_earnings_date = next_earnings_date
    row.fetched_at = datetime.now(timezone.utc)


def load_fundamentals(db, symbols: list[str]) -> dict[str, dict]:
    rows = db.query(FundamentalsCache).filter(FundamentalsCache.symbol.in_(symbols)).all()
    result = {}
    for row in rows:
        result[row.symbol] = {
            **{field: getattr(row, field) for field in FIELDS},
            "next_earnings_date": row.next_earnings_date,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }
    return result
