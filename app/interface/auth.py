"""Password hashing and stateless signed-cookie sessions.

Not wired into any route yet - that happens when `/` and `/api/*` move
behind `Depends(current_user)`. Kept in the interface layer because it is
purely an HTTP concern (cookies, request objects).

Env:
  APP_SECRET_KEY   required, >= 32 chars - signs session/verification tokens
"""

import base64
import contextvars
import hashlib
import logging
import os

import bcrypt
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.infrastructure.db import SessionLocal, User

logger = logging.getLogger(__name__)

COOKIE_NAME = "so_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # seconds
_BCRYPT_ROUNDS = 12

# The signed-in user's id for the current request. Set by an app-level
# dependency (see http._bind_request_user) so `Repositories()` with no
# argument scopes to the caller without threading a user through 40 routes.
_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_id", default=None
)


def bind_current_user(user: "User | None") -> None:
    _current_user_id.set(user.id if user is not None else None)


def current_user_id() -> str | None:
    return _current_user_id.get()


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


def check_app_secret_key() -> None:
    """Called once at startup so a missing/short APP_SECRET_KEY is a clear
    line in the deploy log, not a generic 500 on the first login attempt."""
    _secret()


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


# --- owner bootstrap ------------------------------------------------------

_DEV_OWNER_EMAIL = "owner@localhost"
_DEV_OWNER_PASSWORD = "owner"  # local dev only - never used when OWNER_EMAIL is set


def ensure_owner() -> str:
    """Make sure the single `is_owner` account exists and return its id.

    Prod: `OWNER_EMAIL` (+ `OWNER_INITIAL_PASSWORD`) name the owner. Local
    dev with neither set falls back to owner@localhost / "owner" with a
    warning. Called from app startup and from the step-2 data migration;
    also the fallback target for `Repositories(user_id=None)`.
    """
    email = (os.environ.get("OWNER_EMAIL") or "").strip().lower()
    if email:
        password = os.environ.get("OWNER_INITIAL_PASSWORD")
        if not password:
            raise RuntimeError("OWNER_EMAIL is set but OWNER_INITIAL_PASSWORD is not")
    else:
        email, password = _DEV_OWNER_EMAIL, _DEV_OWNER_PASSWORD
        logger.warning("OWNER_EMAIL not set - using the local dev owner %s / %r", email, password)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            existing_owner = db.query(User).filter(User.is_owner.is_(True)).first()
            if existing_owner is not None and existing_owner.email == _DEV_OWNER_EMAIL:
                # The very first deploy ran before OWNER_EMAIL/OWNER_INITIAL_PASSWORD
                # were configured on the host, so this placeholder dev-owner row
                # got created and persisted as the real is_owner account. Now that
                # real values are set, adopt them onto that same row (same id, so
                # nothing it already owns needs re-backfilling). Only fires while
                # the stored email is still literally the placeholder - once
                # reconciled, the email-match lookup above succeeds directly and
                # this branch is never reached again, so a later password change
                # is never clobbered.
                logger.warning(
                    "Reconciling placeholder owner account (%s) to configured "
                    "OWNER_EMAIL - this should only happen once.", _DEV_OWNER_EMAIL
                )
                existing_owner.email = email
                existing_owner.password_hash = hash_password(password)
                user = existing_owner
            elif existing_owner is not None:
                logger.warning(
                    "OWNER_EMAIL=%s matches no existing user, but an owner account "
                    "already exists as %s - leaving it as-is. Set OWNER_EMAIL back "
                    "to that address, or reassign ownership manually.",
                    email, existing_owner.email,
                )
                user = existing_owner
            else:
                user = User(
                    email=email,
                    password_hash=hash_password(password),
                    email_verified=True,
                    is_owner=True,
                )
                db.add(user)
        user.is_owner = True
        db.commit()
        return user.id
    finally:
        db.close()

