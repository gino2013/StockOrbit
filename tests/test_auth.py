import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# a real file DB (SessionLocal opens fresh connections; :memory: would be empty)
_DB = Path(tempfile.mkdtemp()) / "auth_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.interface import auth  # noqa: E402


def demo():
    Base.metadata.create_all(engine)

    # --- passwords ---
    h = auth.hash_password("hunter2")
    assert h != "hunter2"
    assert auth.verify_password("hunter2", h) is True
    assert auth.verify_password("Hunter2", h) is False
    assert auth.verify_password("nope", "not-a-hash") is False

    # >72 bytes: two passwords sharing the first 72 bytes must still differ
    base = "A" * 72
    ha, hb = auth.hash_password(base + "one"), auth.hash_password(base + "two")
    assert auth.verify_password(base + "one", ha) and not auth.verify_password(base + "two", ha)
    assert auth.verify_password(base + "two", hb)

    # --- session cookie ---
    db = SessionLocal()
    db.add(User(id="u1", email="a@example.com", password_hash=h, session_version=1))
    db.commit()
    db.close()

    db = SessionLocal()
    user = db.get(User, "u1")
    db.expunge(user)  # detached but fully loaded, like auth._load_user returns
    db.close()

    cookie = auth.make_session_cookie(user)
    assert auth.read_session_cookie(cookie) == {"uid": "u1", "sv": 1}
    assert auth.read_session_cookie(cookie + "x") is None          # tampered
    assert auth.read_session_cookie(cookie, max_age=-1) is None    # expired

    class Req:
        def __init__(self, cookies):
            self.cookies = cookies

    assert auth._load_user(Req({})) is None
    assert auth._load_user(Req({auth.COOKIE_NAME: "garbage"})) is None
    loaded = auth._load_user(Req({auth.COOKIE_NAME: cookie}))
    assert loaded is not None and loaded.id == "u1"

    # session_version bump invalidates every existing cookie
    db = SessionLocal()
    db.get(User, "u1").session_version = 2
    db.commit()
    db.close()
    assert auth._load_user(Req({auth.COOKIE_NAME: cookie})) is None

    # current_user raises 401, current_user_html redirects
    from fastapi import HTTPException

    for dep, code in ((auth.current_user, 401), (auth.current_user_html, 303)):
        try:
            dep(Req({}))
            assert False, "expected HTTPException"
        except HTTPException as e:
            assert e.status_code == code

    # --- email tokens ---
    tok = auth.make_email_token("verify", "A@Example.com")
    assert auth.read_email_token("verify", tok) == "a@example.com"
    assert auth.read_email_token("reset", tok) is None       # purpose mismatch
    assert auth.read_email_token("verify", tok, max_age=-1) is None

    # --- APP_SECRET_KEY guard ---
    os.environ["APP_SECRET_KEY"] = "short"
    try:
        auth.make_session_cookie(user)
        assert False, "expected RuntimeError for a short APP_SECRET_KEY"
    except RuntimeError:
        pass
    os.environ["APP_SECRET_KEY"] = "x" * 40


if __name__ == "__main__":
    demo()
    print("OK")
