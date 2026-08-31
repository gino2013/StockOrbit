import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "settings_routes.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "y" * 40
os.environ.pop("OWNER_EMAIL", None)
os.environ.pop("OWNER_INITIAL_PASSWORD", None)
os.environ.pop("FT_CREDENTIAL_KEY", None)
os.environ.pop("FT_USERNAME", None)
os.environ.pop("FT_PASSWORD", None)

from cryptography.fernet import Fernet  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.infrastructure import crypto  # noqa: E402
from app.infrastructure.db import SessionLocal, User  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402
from app.interface import auth, http  # noqa: E402


def _req(path="/settings"):
    return Request({"type": "http", "method": "POST", "path": path,
                    "headers": [], "query_string": b"", "app": http.app})


def _make_user(email, verified):
    db = SessionLocal()
    u = User(email=email, password_hash=auth.hash_password("pw"), email_verified=verified)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    db.close()
    return u


def demo():
    verified = _make_user("verified@test.co", verified=True)
    unverified = _make_user("unverified@test.co", verified=False)

    # --- FT connect blocked while FT_CREDENTIAL_KEY is unset ---
    req = _req(); req.state.user = verified
    resp = http.save_firstrade(req, ft_username="u", ft_password="p", ft_mfa_secret="")
    assert resp.status_code == 400

    os.environ["FT_CREDENTIAL_KEY"] = Fernet.generate_key().decode()

    # --- FT connect blocked for an unverified email, even with the feature on ---
    req = _req(); req.state.user = unverified
    resp = http.save_firstrade(req, ft_username="u", ft_password="p", ft_mfa_secret="")
    assert resp.status_code == 403
    with Repositories(unverified.id) as repo:
        assert repo.firstrade_credential() is None

    # --- FT connect succeeds for a verified user, stored encrypted ---
    req = _req(); req.state.user = verified
    resp = http.save_firstrade(req, ft_username="myuser", ft_password="mypass", ft_mfa_secret="totp123")
    assert resp.status_code == 200
    with Repositories(verified.id) as repo:
        row = repo.firstrade_credential()
        assert row is not None
        assert row.username_enc != "myuser"  # not plaintext
        assert crypto.decrypt(row.username_enc) == "myuser"
        assert crypto.decrypt(row.password_enc) == "mypass"
        assert crypto.decrypt(row.mfa_secret_enc) == "totp123"

    # --- remove FT connection ---
    req = _req(); req.state.user = verified
    resp = http.delete_firstrade(req)
    assert resp.status_code == 200
    with Repositories(verified.id) as repo:
        assert repo.firstrade_credential() is None

    # --- change password: wrong current password rejected ---
    req = _req(); req.state.user = verified
    resp = http.change_password(req, current_password="WRONG", new_password="newpassword123")
    assert resp.status_code == 400

    # --- change password: success bumps session_version, reissues cookie ---
    db = SessionLocal()
    sv_before = db.query(User.session_version).filter(User.id == verified.id).first()[0]
    db.close()
    req = _req(); req.state.user = verified
    resp = http.change_password(req, current_password="pw", new_password="newpassword123")
    assert resp.status_code == 200
    assert any(k == b"set-cookie" for k, _ in resp.raw_headers)
    db = SessionLocal()
    updated = db.query(User).filter(User.id == verified.id).first()
    assert updated.session_version == sv_before + 1
    assert auth.verify_password("newpassword123", updated.password_hash)
    db.close()

    # --- delete account: wrong confirm email is rejected, nothing deleted ---
    req = _req(); req.state.user = verified
    resp = http.delete_account(req, confirm_email="wrong@test.co")
    assert resp.status_code == 400
    db = SessionLocal()
    assert db.query(User).filter(User.id == verified.id).first() is not None
    db.close()

    # --- delete account: correct confirmation wipes the user ---
    req = _req(); req.state.user = verified
    resp = http.delete_account(req, confirm_email=verified.email.upper())  # case-insensitive
    assert resp.status_code == 303
    db = SessionLocal()
    assert db.query(User).filter(User.id == verified.id).first() is None
    db.close()

    # unrelated user untouched throughout
    db = SessionLocal()
    assert db.query(User).filter(User.id == unverified.id).first() is not None
    db.close()


if __name__ == "__main__":
    demo()
    print("OK")
