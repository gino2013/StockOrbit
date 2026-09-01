import asyncio
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "verify_toggle.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "t" * 40
os.environ.pop("OWNER_EMAIL", None)
os.environ.pop("SMTP_HOST", None)
os.environ.pop("REQUIRE_EMAIL_VERIFICATION", None)

from cryptography.fernet import Fernet  # noqa: E402
from starlette.datastructures import UploadFile  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.infrastructure import crypto  # noqa: E402
from app.infrastructure.db import SessionLocal, User  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402
from app.interface import auth, http  # noqa: E402


def _req(path="/settings"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [],
                    "query_string": b"", "app": http.app, "client": ("1.2.3.4", 1),
                    "scheme": "http", "server": ("testserver", 80)})


def _unverified_user(email):
    db = SessionLocal()
    u = User(email=email, password_hash=auth.hash_password("pw"), email_verified=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    db.close()
    return u


def _csv_upload(text):
    return UploadFile(io.BytesIO(text.encode()), filename="x.csv")


def demo():
    # --- _email_verification_required() parsing ---
    for val, expected in [
        (None, True), ("true", True), ("1", True), ("yes", True), ("anything", True),
        ("false", False), ("False", False), ("FALSE", False), ("0", False), ("no", False), (" false ", False),
    ]:
        if val is None:
            os.environ.pop("REQUIRE_EMAIL_VERIFICATION", None)
        else:
            os.environ["REQUIRE_EMAIL_VERIFICATION"] = val
        assert http._email_verification_required() is expected, (val, expected)

    os.environ["FT_CREDENTIAL_KEY"] = Fernet.generate_key().decode()
    u = _unverified_user("gate@test.co")

    # --- gate ON (default): unverified user is blocked from the FT form ---
    os.environ.pop("REQUIRE_EMAIL_VERIFICATION", None)
    req = _req(); req.state.user = u
    resp = http.save_firstrade(req, ft_username="a", ft_password="b", ft_mfa_secret="")
    assert resp.status_code == 403
    with Repositories(u.id) as repo:
        assert repo.firstrade_credential() is None

    # --- gate OFF: same unverified user can now store credentials ---
    os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"
    req = _req(); req.state.user = u
    resp = http.save_firstrade(req, ft_username="myuser", ft_password="mypass", ft_mfa_secret="tot")
    assert resp.status_code == 200
    with Repositories(u.id) as repo:
        row = repo.firstrade_credential()
        assert row is not None and crypto.decrypt(row.username_enc) == "myuser"

    # --- CSV import follows the same gate ---
    os.environ.pop("REQUIRE_EMAIL_VERIFICATION", None)  # gate ON
    req = _req(); req.state.user = u
    resp = asyncio.run(http._handle_import(req, _csv_upload("symbol,quantity\nVOO,3\n"), "positions"))
    assert resp.status_code == 403

    os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"  # gate OFF
    req = _req(); req.state.user = u
    resp = asyncio.run(http._handle_import(req, _csv_upload("symbol,quantity\nVOO,3\n"), "positions"))
    assert resp.status_code == 200
    with Repositories(u.id) as repo:
        assert [s["symbol"] for s in repo.latest_snapshots()] == ["VOO"]

    # --- resend-verification messaging ---
    from fastapi import BackgroundTasks

    os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"
    req = _req(); req.state.user = u
    bt = BackgroundTasks()
    resp = http.resend_verification(req, bt)
    assert resp.status_code == 200 and len(bt.tasks) == 0  # nothing to do, no email

    os.environ.pop("REQUIRE_EMAIL_VERIFICATION", None)  # gate ON, but no SMTP
    req = _req(); req.state.user = u
    bt = BackgroundTasks()
    resp = http.resend_verification(req, bt)
    assert resp.status_code == 503 and len(bt.tasks) == 0  # honest: can't send

    os.environ["SMTP_HOST"] = "smtp.example.test"
    req = _req(); req.state.user = u
    bt = BackgroundTasks()
    resp = http.resend_verification(req, bt)
    assert resp.status_code == 200 and len(bt.tasks) == 1  # now it actually queues one


if __name__ == "__main__":
    demo()
    print("OK")
