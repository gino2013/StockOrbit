import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'dedup_test.db'}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.domain.income.realized_gains import compute_realized_gains  # noqa: E402
from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402


def _t(trans_type, qty, amount, desc, day=date(2026, 10, 6)):
    return {"account_number": "A1", "symbol": "PLTR", "trans_type": trans_type, "report_date": day,
            "quantity": qty, "trade_price": 192.1758, "amount": amount, "description": desc, "raw_json": "{}"}


def demo():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(id="u", email="a@x.com", password_hash="h", is_owner=True))
    db.commit()
    db.close()

    buy = _t("BOUGHT", 3.76738, -580.61, "buy", date(2026, 1, 5))
    sold_pending = _t("SOLD", -3.76738, 723.9893, "Palantir Technologies Inc.")
    sold_settled = _t("SOLD", -3.76738, 723.98, "PALANTIR ... S/D: 10/07/2026")
    with Repositories("u") as repo:
        repo.save_refresh([], [buy, sold_pending], None)
        repo.save_refresh([], [buy, sold_settled], None)  # next day's sync
        txns = repo.all_transactions()
    # Same fill under two hashes -> stored once, realized gain counted once.
    assert sum(1 for t in txns if t["trans_type"] == "SOLD") == 1
    assert len(compute_realized_gains(txns)) == 1
    # A genuinely different fill (other day) is still recorded.
    with Repositories("u") as repo:
        repo.save_refresh([], [_t("SOLD", -3.76738, 723.98, "x", date(2026, 10, 7))], None)
        assert sum(1 for t in repo.all_transactions() if t["trans_type"] == "SOLD") == 2


if __name__ == "__main__":
    demo()
    print("OK")
