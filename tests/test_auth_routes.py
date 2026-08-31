import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "auth_routes.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "z" * 40
os.environ.pop("OWNER_EMAIL", None)

from fastapi import BackgroundTasks  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.infrastructure.db import SessionLocal, User  # noqa: E402
from app.interface import auth, http  # noqa: E402


def _req(path="/x"):
    return Request({"type": "http", "method": "POST", "path": path,
                    "headers": [], "query_string": b"", "app": http.app})


def _register(**kw):
    return http.register(_req(), BackgroundTasks(), **kw)


def _set_cookie_names(resp):
    return [h.decode().split("=", 1)[0] for k, h in resp.raw_headers if k == b"set-cookie"]


def demo():
    # --- register ---
    r = _register(email="New@Test.co", password="password123")
    assert r.status_code == 303 and auth.COOKIE_NAME in _set_cookie_names(r)
    db = SessionLocal()
    u = db.query(User).filter(User.email == "new@test.co").first()
    assert u is not None and u.is_owner is False and u.email_verified is False
    db.close()

    # duplicate / bad email / short password -> 400, no new row
    assert _register(email="new@test.co", password="password123").status_code == 400
    assert _register(email="nope", password="password123").status_code == 400
    assert _register(email="ok@test.co", password="short").status_code == 400
    db = SessionLocal()
    assert db.query(User).filter(User.is_owner.is_(False)).count() == 1  # only "new@test.co"
    db.close()

    # --- login ---
    ok = http.login(_req(), email="new@test.co", password="password123", next="/")
    assert ok.status_code == 303 and auth.COOKIE_NAME in _set_cookie_names(ok)
    bad = http.login(_req(), email="new@test.co", password="WRONG", next="/")
    assert bad.status_code == 401
    # open redirect guard: external next is ignored
    ext = http.login(_req(), email="new@test.co", password="password123", next="https://evil.example")
    assert ext.headers["location"] == "/"

    # --- logout clears the cookie ---
    out = http.logout()
    assert out.status_code == 303
    assert any(b"so_session=" in h and (b"Max-Age=0" in h or b'""' in h)
               for k, h in out.raw_headers if k == b"set-cookie")

    # --- middleware allow-list ---
    pub = http._PUBLIC_PREFIXES
    assert any("/login".startswith(p) for p in pub)
    assert any("/register".startswith(p) for p in pub)
    assert not any("/".startswith(p) and p != "" for p in pub if p not in ("",))
    assert not any("/api/goal".startswith(p) for p in pub)


if __name__ == "__main__":
    demo()
    print("OK")
