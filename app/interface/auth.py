"""Password hashing and stateless signed-cookie sessions.

Not wired into any route yet - that happens when `/` and `/api/*` move
behind `Depends(current_user)`. Kept in the interface layer because it is
purely an HTTP concern (cookies, request objects).

Env:
  APP_SECRET_KEY   required, >= 32 chars - signs session/verification tokens
"""

import base64
import hashlib
import os

import bcrypt
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.infrastructure.db import SessionLocal, User

COOKIE_NAME = "so_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # seconds
_BCRYPT_ROUNDS = 12


# --- passwords ---------------------------------------------------------------

def _prehash(password: str) -> bytes:
    """bcrypt silently truncates at 72 bytes; sha256 -> base64 first so the
    whole password always contributes and stays within the limit."""
    return base64.b64encode(hashlib.sha256(password.encode()).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode())
    except ValueError:
        return False


# --- signed tokens ---------------------------------------------------------

def _secret() -> str:
    key = os.environ.get("APP_SECRET_KEY")
    if not key or len(key) < 32:
        raise RuntimeError("APP_SECRET_KEY must be set and at least 32 characters")
    return key


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret(), salt=salt)


def make_session_cookie(user: User) -> str:
    return _serializer("session").dumps({"uid": user.id, "sv": user.session_version})


def read_session_cookie(raw: str, max_age: int = SESSION_MAX_AGE) -> dict | None:
    try:
        return _serializer("session").loads(raw, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def make_email_token(purpose: str, email: str) -> str:
    """Short-lived token for email verification / password reset. `purpose`
    keeps a verification link from being replayed as a reset link."""
    return _serializer(f"email:{purpose}").dumps(email.lower())


def read_email_token(purpose: str, raw: str, max_age: int = 900) -> str | None:
    try:
        return _serializer(f"email:{purpose}").loads(raw, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


# --- FastAPI dependencies -------------------------------------------------

def _load_user(request: Request) -> User | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    payload = read_session_cookie(raw)
    if not payload:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, payload.get("uid"))
        if user is None or user.session_version != payload.get("sv"):
            return None
        db.expunge(user)
        return user
    finally:
        db.close()


def current_user(request: Request) -> User:
    """API dependency: 401 when not signed in."""
    user = _load_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


def current_user_html(request: Request) -> User:
    """Page dependency: redirect to /login when not signed in."""
    user = _load_user(request)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_owner(request: Request) -> User:
    user = current_user(request)
    if not user.is_owner:
        raise HTTPException(status_code=403, detail="owner only")
    return user
