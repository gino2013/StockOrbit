import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "email_flows.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "v" * 40
os.environ.pop("OWNER_EMAIL", None)
os.environ.pop("SMTP_HOST", None)  # mailer just logs; tasks are harmless to run

from fastapi import BackgroundTasks  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.infrastructure.db import SessionLocal, User  # noqa: E402
from app.interface import auth, http  # noqa: E402


def _req(path="/x", client_host="1.2.3.4"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [],
                    "query_string": b"", "app": http.app, "client": (client_host, 12345),
                    "scheme": "http", "server": ("testserver", 80)})


def _verified(email):
    db = SessionLocal()
    row = db.query(User).filter(User.email == email).first()
    v = row.email_verified
    db.close()
    return v


def demo():
    # --- rate limiter unit behaviour ---
    for _ in range(3):
        assert http._rate_limited("k", limit=3, window_seconds=100) is False
    assert http._rate_limited("k", limit=3, window_seconds=100) is True

    # --- register queues a verification email ---
    bt = BackgroundTasks()
    r = http.register(_req(), bt, email="alice@test.co", password="password123")
    assert r.status_code == 303
    assert not _verified("alice@test.co")
    assert len(bt.tasks) == 1
    assert "alice@test.co" in bt.tasks[0].args  # (to, subject, body)

    # --- /verify: bad token leaves the user unverified ---
    assert http.verify_email(_req(), token="garbage").status_code == 400
    assert not _verified("alice@test.co")

    # --- /verify: good token flips email_verified and redirects to /settings ---
    token = auth.make_email_token("verify", "alice@test.co")
    resp = http.verify_email(_req(), token=token)
    assert resp.status_code == 303 and resp.headers["location"] == "/settings"
    assert _verified("alice@test.co")

    # --- resend-verification: already-verified is a no-op message, not an email ---
    db = SessionLocal()
    alice = db.query(User).filter(User.email == "alice@test.co").first()
    db.expunge(alice)
    db.close()
    req = _req(); req.state.user = alice
    bt = BackgroundTasks()
    http.resend_verification(req, bt)
    assert len(bt.tasks) == 0

    # --- /forgot: SMTP not configured -> honest message, nothing queued ---
    os.environ.pop("SMTP_HOST", None)
    bt = BackgroundTasks()
    resp = http.forgot(_req(), bt, email="alice@test.co")
    assert resp.status_code == 200 and len(bt.tasks) == 0

    os.environ["SMTP_HOST"] = "smtp.example.test"  # mailer.is_enabled() -> True

    # --- /forgot: unknown email -> same generic response, no email, no crash ---
    bt = BackgroundTasks()
    resp = http.forgot(_req(), bt, email="nobody@test.co")
    assert resp.status_code == 200 and len(bt.tasks) == 0

    # --- /forgot: known email -> queues a reset email ---
    bt = BackgroundTasks()
    resp = http.forgot(_req(), bt, email="alice@test.co")
    assert resp.status_code == 200 and len(bt.tasks) == 1

    # --- /reset: bad token / short password rejected ---
    assert http.reset_password(_req(), token="garbage", new_password="password123").status_code == 400
    good = auth.make_email_token("reset", "alice@test.co")
    assert http.reset_password(_req(), token=good, new_password="short").status_code == 400

    # --- /reset: good token sets the new password and bumps session_version ---
    db = SessionLocal()
    sv_before = db.query(User.session_version).filter(User.email == "alice@test.co").first()[0]
    old_hash = db.query(User.password_hash).filter(User.email == "alice@test.co").first()[0]
    db.close()
    resp = http.reset_password(_req(), token=good, new_password="brandnewpass1")
    assert resp.status_code == 303
    assert any(k == b"set-cookie" for k, _ in resp.raw_headers)
    db = SessionLocal()
    row = db.query(User).filter(User.email == "alice@test.co").first()
    assert row.session_version == sv_before + 1
    assert row.password_hash != old_hash
    assert auth.verify_password("brandnewpass1", row.password_hash)
    db.close()

    # --- a verify token can't be replayed as a reset token (purpose salt) ---
    v = auth.make_email_token("verify", "alice@test.co")
    assert auth.read_email_token("reset", v) is None

    # --- /login rate limit kicks in after 20 tries from one IP ---
    for _ in range(20):
        http.login(_req(path="/login", client_host="9.9.9.9"), email="x@y.co", password="nope", next="/")
    limited = http.login(_req(path="/login", client_host="9.9.9.9"), email="x@y.co", password="nope", next="/")
    assert limited.status_code == 429


if __name__ == "__main__":
    demo()
    print("OK")
