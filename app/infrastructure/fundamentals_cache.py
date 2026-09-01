"""Read/write for FundamentalsCache - see app.db.FundamentalsCache for why
this exists (Render can't reach Yahoo's quoteSummary API directly).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.infrastructure.db import FundamentalsCache
from app.infrastructure.fundamentals import FIELDS

_TAIPEI = ZoneInfo("Asia/Taipei")


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
        # fetched_at is stored as UTC but comes back tz-naive (SQLite/Postgres
        # both drop tzinfo on a plain DateTime column) - convert to Taipei
        # before formatting so the "(快取 YYYY-MM-DD)" badge shown to the
        # user reflects their actual calendar date, not the UTC one.
        fetched_at = row.fetched_at.replace(tzinfo=timezone.utc).astimezone(_TAIPEI) if row.fetched_at else None
        result[row.symbol] = {
            **{field: getattr(row, field) for field in FIELDS},
            "next_earnings_date": row.next_earnings_date,
            "fetched_at": fetched_at.isoformat() if fetched_at else None,
        }
    return result
