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


def register_symbol(db, symbol: str) -> bool:
    """Note that someone looked this symbol up, so the scheduled refresh
    job (scripts/refresh_fundamentals_cache.py, unaffected by Render's
    Yahoo block) picks it up even though nobody holds it. Returns True the
    first time (so the caller can also poke the job to run right away
    instead of waiting for its next schedule) and False on every repeat
    lookup - no-op, never overwrite real cached data with an empty
    placeholder. The placeholder's every field but `fetched_at` stays null
    (harmless: every reader already guards on the field it actually wants,
    e.g. fundamentals.html's cache badge checks `f.sector` first) -
    fighting the column's default to null `fetched_at` too isn't worth it."""
    if db.get(FundamentalsCache, symbol) is not None:
        return False
    db.add(FundamentalsCache(symbol=symbol))
    return True


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
