"""issue #97: per-account filtering. account_numbers() lists the accounts
in the latest snapshot batch; latest_snapshots()/all_transactions()/
all_snapshot_points() accept an optional account_number to restrict to.
"""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "account_filter_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402


def _pos(account, sym, qty, price):
    mv = qty * price
    return {"account_number": account, "symbol": sym, "quantity": qty,
            "cost_basis": mv, "market_value": mv, "price": price, "raw_json": "{}"}


def _txn(account, sym, amount):
    return {"account_number": account, "symbol": sym, "trans_type": "BOUGHT",
            "report_date": date(2026, 1, 5), "quantity": 1.0, "trade_price": amount,
            "amount": -amount, "description": f"buy {sym}", "raw_json": "{}"}


def demo():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(id="u1", email="u1@x.com", password_hash="h", is_owner=True))
    db.commit()
    db.close()

    # --- single account: account_numbers() has exactly one entry, and
    # filtering by it (or not filtering) gives the same result - matches
    # the issue's own acceptance criterion that single-account UX doesn't
    # change ---
    with Repositories("u1") as repo:
        repo.save_refresh(positions=[_pos("A1", "AAPL", 10, 100.0)], transactions=[_txn("A1", "AAPL", 1000)], rate=None)
        assert repo.account_numbers() == ["A1"]
        all_accounts = repo.latest_snapshots()
        one_account = repo.latest_snapshots("A1")
        assert all_accounts == one_account

    # --- two accounts: account_numbers() lists both, sorted ---
    with Repositories("u1") as repo:
        repo.save_refresh(
            positions=[_pos("A2", "AAPL", 10, 100.0), _pos("A1", "VOO", 5, 400.0)],
            transactions=[_txn("A2", "AAPL", 1000), _txn("A1", "VOO", 2000)],
            rate=None,
        )
        assert repo.account_numbers() == ["A1", "A2"]

        # unfiltered: both accounts' symbols show up.
        combined = {s["symbol"] for s in repo.latest_snapshots()}
        assert combined == {"AAPL", "VOO"}

        # filtered to A1: only A1's holdings/transactions/snapshot-points.
        a1_snaps = repo.latest_snapshots("A1")
        assert {s["symbol"] for s in a1_snaps} == {"VOO"}
        # transactions accumulate (unlike snapshots, which only look at the
        # latest batch) - A1 has both its phase-1 AAPL buy and this phase's
        # VOO buy; A2 never bought anything until this phase.
        a1_txns = repo.all_transactions("A1")
        assert {t["symbol"] for t in a1_txns} == {"AAPL", "VOO"}
        # snapshot points span every historical snapshot too, same reasoning.
        a1_points = repo.all_snapshot_points("A1")
        assert {p["symbol"] for p in a1_points} == {"AAPL", "VOO"}

        # filtered to A2: only A2's.
        a2_snaps = repo.latest_snapshots("A2")
        assert {s["symbol"] for s in a2_snaps} == {"AAPL"}
        assert a2_snaps[0]["quantity"] == 10
        assert a2_snaps[0]["market_value"] == 1000.0

        # a symbol not present in the filtered account doesn't leak in.
        assert not any(s["symbol"] == "VOO" for s in a2_snaps)

        # --- resolve_account(): the validation every account-accepting
        # route should share, so a stale/removed value doesn't silently
        # filter one endpoint to zero rows while others (which do
        # validate) show the real all-accounts total (code review finding
        # on #222) ---
        numbers = repo.account_numbers()
        assert Repositories.resolve_account("A1", numbers) == "A1"
        assert Repositories.resolve_account("A2", numbers) == "A2"
        # closed/renamed/nonexistent account -> falls back to "all accounts".
        assert Repositories.resolve_account("GONE", numbers) is None
        assert Repositories.resolve_account(None, numbers) is None
        # single-account list -> filter UI wouldn't even show, so even a
        # technically-valid value is ignored (matches the dashboard route's
        # existing behavior).
        assert Repositories.resolve_account("A1", ["A1"]) is None


if __name__ == "__main__":
    demo()
    print("OK")
