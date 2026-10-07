import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'liab_edit.db'}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402


def demo():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add_all([
        User(id="uA", email="a@x.com", password_hash="h", is_owner=True),
        User(id="uB", email="b@x.com", password_hash="h"),
    ])
    db.commit()
    db.close()

    with Repositories("uA") as a:
        a.add_liability("樂天", 730000.0, 0.0288, 7009.0, date(2026, 3, 13), "TWD")
        loan_id = a.liabilities()[0]["id"]
        assert a.update_liability(loan_id, "樂天1", 800000.0, 0.03, 7500.0, date(2026, 4, 1), "TWD")
        rows = a.liabilities()
        assert len(rows) == 1  # updated in place, not a second row
        assert rows[0]["name"] == "樂天1" and rows[0]["principal"] == 800000.0 and rows[0]["start_date"] == "2026-04-01"
        assert a.update_liability(loan_id, "樂天1", 800000.0, 0.03, 7500.0, date(2026, 4, 1), "TWD", 84)
        assert a.liabilities()[0]["term_months"] == 84
        assert not a.update_liability("nope", "x", 1.0, 0.0, 1.0, date(2026, 1, 1), "USD")

    # Tenancy: another user can't edit my loan by guessing its id.
    with Repositories("uB") as b:
        assert not b.update_liability(loan_id, "hacked", 1.0, 0.0, 1.0, date(2026, 1, 1), "USD")
    with Repositories("uA") as a:
        assert a.liabilities()[0]["name"] == "樂天1"


if __name__ == "__main__":
    demo()
    print("OK")
