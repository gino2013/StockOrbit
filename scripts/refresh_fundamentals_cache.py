"""Scheduled cache refresh — see .github/workflows/refresh-fundamentals-cache.yml.

Render's outbound IP gets a 401 Invalid Crumb from Yahoo's quoteSummary API
(issue #9), so it can never fetch fundamentals/earnings-dates itself. GitHub
Actions runners aren't blocked, so this runs there on a schedule and writes
results to the shared Neon DB; the dashboard reads this as a fallback
whenever a live fetch comes back empty.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import desc

from app.db import PositionSnapshot, SessionLocal, init_db
from app.fundamentals import fetch_fundamentals
from app.fundamentals_cache import save_fundamentals
from app.risk import fetch_next_earnings_date


def held_symbols(db) -> list[str]:
    latest = db.query(PositionSnapshot.snapshot_at).order_by(desc(PositionSnapshot.snapshot_at)).first()
    if not latest:
        return []
    rows = (
        db.query(PositionSnapshot.symbol)
        .filter(PositionSnapshot.snapshot_at == latest[0])
        .distinct()
        .all()
    )
    return [r[0] for r in rows if r[0] != "CASH"]


def main():
    init_db()
    db = SessionLocal()
    try:
        symbols = held_symbols(db)
        if not symbols:
            print("No held symbols found, nothing to refresh.")
            return
        fundamentals = fetch_fundamentals(symbols)
        for symbol in symbols:
            fields = dict(fundamentals.get(symbol, {}))
            fundamentals_ok = fields.pop("_fetch_ok", False)
            next_earnings, earnings_ok = fetch_next_earnings_date(symbol)
            if not fundamentals_ok and not earnings_ok:
                print(f"{symbol}: both fetches failed, leaving old cache untouched")
                continue
            save_fundamentals(db, symbol, fields, next_earnings.isoformat() if next_earnings else None)
            print(f"{symbol}: cached (fundamentals_ok={fundamentals_ok}, earnings_ok={earnings_ok})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
