import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "fundamentals_cache_tz_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, SessionLocal, engine  # noqa: E402
from app.infrastructure.fundamentals_cache import load_fundamentals, save_fundamentals  # noqa: E402


def demo():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        save_fundamentals(db, "AAPL", {}, None)
        db.commit()

        # Row's actual stored value is UTC (see save_fundamentals) but comes
        # back tz-naive - force a known UTC instant just past midnight to
        # catch a bug where the raw UTC value leaked through unconverted.
        from app.infrastructure.db import FundamentalsCache
        row = db.get(FundamentalsCache, "AAPL")
        row.fetched_at = datetime(2026, 9, 2, 0, 30, tzinfo=timezone.utc).replace(tzinfo=None)
        db.commit()

        result = load_fundamentals(db, ["AAPL"])
        fetched_at = result["AAPL"]["fetched_at"]
        # 2026-09-02 00:30 UTC -> 2026-09-02 08:30 Taipei (+8), same calendar
        # day here, but the hour must reflect the +8 shift, not raw UTC.
        assert fetched_at.startswith("2026-09-02T08:30"), fetched_at
        assert fetched_at.endswith("+08:00"), fetched_at
    finally:
        db.close()


if __name__ == "__main__":
    demo()
    print("OK")
