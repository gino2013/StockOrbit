import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "ft_creds_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "w" * 40
os.environ.pop("OWNER_EMAIL", None)
os.environ.pop("OWNER_INITIAL_PASSWORD", None)

from app.infrastructure.db import (  # noqa: E402
    Base,
    FirestradeCredential,
    InvestmentGoal,
    PositionNote,
    PositionSnapshot,
    SessionLocal,
    TargetAllocation,
    Transaction,
    TransactionNote,
    User,
    engine,
)
from app.infrastructure.repositories import Repositories  # noqa: E402
import app.infrastructure.firstrade_client as fc  # noqa: E402


def _seed_full_account(user_id: str) -> None:
    """One row in every user-owned table, so delete_account has something
    real to wipe (rather than trivially passing on empty tables)."""
    now_kwargs = dict(user_id=user_id)
    db = SessionLocal()
    db.add_all([
        PositionSnapshot(snapshot_at=__import__("datetime").datetime.now(), symbol="AAA",
                          account_number="A1", quantity=1, cost_basis=1, market_value=1,
                          price=1, raw_json="{}", **now_kwargs),
        Transaction(id=f"{user_id}-t1", fetched_at=__import__("datetime").datetime.now(),
                    account_number="A1", symbol="AAA", trans_type="BOUGHT",
                    report_date=date(2026, 1, 1), quantity=1, trade_price=1, amount=-1,
                    description="buy", raw_json="{}", **now_kwargs),
        TargetAllocation(symbol="AAA", target_weight=1.0, **now_kwargs),
        PositionNote(symbol="AAA", note="n", **now_kwargs),
        TransactionNote(transaction_id=f"{user_id}-t1", note="n", **now_kwargs),
        InvestmentGoal(target_amount=1, target_date=date(2030, 1, 1), **now_kwargs),
        FirestradeCredential(user_id=user_id, username_enc="u", password_enc="p", mfa_secret_enc=""),
    ])
    db.commit()
    db.close()


def demo():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add_all([
        User(id="uA", email="a@x.com", password_hash="h"),
        User(id="uB", email="b@x.com", password_hash="h"),
        User(id="uC", email="c@x.com", password_hash="h"),  # never connects Firstrade
    ])
    db.commit()
    db.close()
    _seed_full_account("uA")
    _seed_full_account("uB")

    # --- record_sync ---
    with Repositories("uA") as repo:
        assert repo.firstrade_credential().last_sync_at is None
        repo.record_sync(ok=True, error=None)
        row = repo.firstrade_credential()
        assert row.last_sync_at is not None and row.last_sync_error is None
        repo.record_sync(ok=False, error="boom")
        assert repo.firstrade_credential().last_sync_error == "boom"

    # record_sync on a user with no stored creds is a no-op, not a crash
    with Repositories("uC") as repo:
        repo.record_sync(ok=True, error=None)  # must not raise
        assert repo.firstrade_credential() is None

    # --- delete_account wipes every table for that user, leaves others alone ---
    with Repositories("uA") as repo:
        repo.delete_account()

    db = SessionLocal()
    assert db.query(User).filter(User.id == "uA").first() is None
    for model in (PositionSnapshot, Transaction, TargetAllocation, PositionNote,
                  TransactionNote, InvestmentGoal, FirestradeCredential):
        assert db.query(model).filter(model.user_id == "uA").count() == 0, model
        assert db.query(model).filter(model.user_id == "uB").count() == 1, model  # untouched
    assert db.query(User).filter(User.id == "uB").first() is not None
    db.close()

    # --- firstrade_client._login: explicit creds win over env, missing creds error ---
    class _FakeSession:
        def __init__(self, username, password, mfa_secret, save_session):
            self.username, self.password, self.mfa_secret = username, password, mfa_secret

        def login(self):
            return False  # falsy == success, matches the real firstrade lib's convention

    class _FakeAccountModule:
        FTSession = _FakeSession

    real_account = fc.account
    fc.account = _FakeAccountModule
    try:
        s = fc._login(fc.FtCreds(username="u1", password="p1", mfa_secret="m1"))
        assert (s.username, s.password, s.mfa_secret) == ("u1", "p1", "m1")

        os.environ["FT_USERNAME"] = "envu"
        os.environ["FT_PASSWORD"] = "envp"
        os.environ.pop("FT_MFA_SECRET", None)
        s2 = fc._login(None)
        assert (s2.username, s2.password, s2.mfa_secret) == ("envu", "envp", "")

        os.environ.pop("FT_USERNAME", None)
        os.environ.pop("FT_PASSWORD", None)
        try:
            fc._login(None)
            assert False, "expected RuntimeError with no creds and no env vars"
        except RuntimeError:
            pass
    finally:
        fc.account = real_account


if __name__ == "__main__":
    demo()
    print("OK")
