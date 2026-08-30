"""app.interface.auth.ensure_owner() - the owner-account bootstrap.

Covers the real incident this fixed: an early deploy ran before
OWNER_EMAIL/OWNER_INITIAL_PASSWORD were configured, so the placeholder dev
owner (owner@localhost) got created and persisted as the is_owner account.
A later deploy with the real env vars set must adopt them onto that same
row - not leave the placeholder credentials in place, and not create a
second, duplicate owner row.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "ensure_owner.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "y" * 40
os.environ.pop("OWNER_EMAIL", None)
os.environ.pop("OWNER_INITIAL_PASSWORD", None)

from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.interface import auth  # noqa: E402


def demo():
    Base.metadata.create_all(engine)

    # boot 1: no OWNER_EMAIL configured -> creates the placeholder dev owner
    id1 = auth.ensure_owner()
    db = SessionLocal()
    u = db.get(User, id1)
    assert u.email == auth._DEV_OWNER_EMAIL and u.is_owner is True
    db.close()

    # boot 2: OWNER_EMAIL/OWNER_INITIAL_PASSWORD now set -> reconciles the
    # SAME row (same id) rather than creating a second owner
    os.environ["OWNER_EMAIL"] = "real-owner@example.com"
    os.environ["OWNER_INITIAL_PASSWORD"] = "real-password-123"
    id2 = auth.ensure_owner()
    assert id2 == id1, "must reuse the existing row, not create a duplicate"

    db = SessionLocal()
    assert db.query(User).count() == 1
    u = db.get(User, id1)
    assert u.email == "real-owner@example.com"
    assert auth.verify_password("real-password-123", u.password_hash)
    assert not auth.verify_password(auth._DEV_OWNER_PASSWORD, u.password_hash)  # old creds dead
    db.close()

    # boot 3: idempotent - reconciliation already happened, must not run
    # again (a later real password change must never be clobbered back to
    # OWNER_INITIAL_PASSWORD)
    db = SessionLocal()
    db.get(User, id1).password_hash = auth.hash_password("user-changed-this")
    db.commit()
    db.close()

    id3 = auth.ensure_owner()
    assert id3 == id1
    db = SessionLocal()
    assert db.query(User).count() == 1
    u = db.get(User, id1)
    assert u.email == "real-owner@example.com"
    assert auth.verify_password("user-changed-this", u.password_hash), (
        "a later password change must survive - ensure_owner() must not "
        "re-apply OWNER_INITIAL_PASSWORD once already reconciled"
    )
    db.close()

    # a second, unrelated user with a different email is left completely
    # alone - only the flagged owner row is ever touched
    os.environ.pop("OWNER_EMAIL", None)
    os.environ.pop("OWNER_INITIAL_PASSWORD", None)


if __name__ == "__main__":
    demo()
    print("OK")
