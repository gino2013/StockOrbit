import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "tenancy_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402


def _pos(sym, mv):
    return {"account_number": "A1", "symbol": sym, "quantity": 1.0,
            "cost_basis": mv, "market_value": mv, "price": mv, "raw_json": "{}"}


def _txn(sym, amount):
    return {"account_number": "A1", "symbol": sym, "trans_type": "BOUGHT",
            "report_date": date(2026, 1, 5), "quantity": 1.0, "trade_price": amount,
            "amount": -amount, "description": f"buy {sym}", "raw_json": "{}"}


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
        a.upsert_target("AAA", 0.5)
        a.upsert_note("AAA", "note-a")
        a.upsert_goal(1000.0, date(2030, 1, 1))
        a.save_refresh([_pos("AAA", 100.0)], [_txn("AAA", 100.0)], rate=31.0)
        tid = next(iter(a.all_transactions()))["id"]
        a.upsert_transaction_note(tid, "tn-a")

    with Repositories("uB") as b:
        b.upsert_target("BBB", 0.7)
        b.upsert_note("BBB", "note-b")
        b.upsert_goal(2000.0, date(2031, 1, 1))

    # B sees only its own rows
    with Repositories("uB") as b:
        assert b.targets() == {"BBB": 0.7}
        assert b.notes() == {"BBB": "note-b"}
        assert b.goal().target_amount == 2000.0
        assert b.latest_snapshots() == []
        assert b.all_transactions() == []
        assert b.transaction_notes([tid]) == {}
        assert b.transaction_exists(tid) is False

    # A still has all of its own rows
    with Repositories("uA") as a:
        assert a.targets() == {"AAA": 0.5}
        assert a.notes() == {"AAA": "note-a"}
        assert a.goal().target_amount == 1000.0
        snaps = a.latest_snapshots()
        assert len(snaps) == 1 and snaps[0]["symbol"] == "AAA"
        assert len(a.all_transactions()) == 1
        assert a.transaction_notes([tid]) == {tid: "tn-a"}
        assert a.transaction_exists(tid) is True

    # cross-user delete is a no-op
    with Repositories("uB") as b:
        b.delete_target("AAA")
        b.delete_goal()
    with Repositories("uA") as a:
        assert a.targets() == {"AAA": 0.5}
        assert a.goal() is not None

    # exchange rate is global - written by A's save_refresh, visible to B
    with Repositories("uB") as b:
        assert b.usd_twd_rate() == 31.0

    # user_id=None resolves to the is_owner account (uA)
    with Repositories() as owner:
        assert owner.targets() == {"AAA": 0.5}

    # composite PK (user_id, symbol/transaction_id/id): two users can hold
    # the exact same natural key without colliding - this is the whole
    # point of migration 0004 folding user_id into the primary key.
    with Repositories("uA") as a, Repositories("uB") as b:
        a.upsert_target("SPY", 0.5)
        b.upsert_target("SPY", 0.9)  # would raise IntegrityError pre-0004
        a.upsert_note("SPY", "a's spy note")
        b.upsert_note("SPY", "b's spy note")
    with Repositories("uA") as a, Repositories("uB") as b:
        assert a.targets()["SPY"] == 0.5 and b.targets()["SPY"] == 0.9
        assert a.notes()["SPY"] == "a's spy note" and b.notes()["SPY"] == "b's spy note"

    # goal PK is user_id alone now (no more "default" singleton) - both
    # users already have one from earlier in this test; each is independent.
    with Repositories("uA") as a, Repositories("uB") as b:
        assert a.goal().target_amount == 1000.0
        assert b.goal() is None  # uB's goal was deleted above


if __name__ == "__main__":
    demo()
    print("OK")
