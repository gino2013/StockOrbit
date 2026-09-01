import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Must be set before importing app.interface.http: that module runs
# run_pending_migrations()/ensure_owner() etc. at import time, and without
# an explicit override here it would silently fall through to .env's real
# DATABASE_URL and touch the production database - see test_repositories_
# tenancy.py for the same convention.
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'to_taipei_test.db'}"
os.environ["APP_SECRET_KEY"] = "x" * 40
os.environ.pop("OWNER_EMAIL", None)

from app.interface.http import _to_taipei  # noqa: E402


def demo():
    # naive datetime (how DB timestamps actually come back) is treated as UTC
    naive = datetime(2026, 9, 2, 0, 30)
    converted = _to_taipei(naive)
    assert converted.isoformat() == "2026-09-02T08:30:00+08:00", converted.isoformat()

    # tz-aware UTC input converts the same way
    aware = datetime(2026, 9, 2, 0, 30, tzinfo=timezone.utc)
    assert _to_taipei(aware).isoformat() == "2026-09-02T08:30:00+08:00"

    # a UTC instant just before midnight lands on the *next* calendar day
    # in Taipei - the case that actually matters for a date-only display.
    late_utc = datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc)
    assert _to_taipei(late_utc).date().isoformat() == "2026-09-02"

    assert _to_taipei(None) is None


if __name__ == "__main__":
    demo()
    print("OK")
