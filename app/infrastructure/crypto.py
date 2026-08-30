"""Symmetric encryption for stored Firstrade credentials.

`FT_CREDENTIAL_KEY` is a urlsafe-base64 Fernet key, supplied only via the
environment (never committed, never stored in the DB). When it is unset,
per-user Firstrade sync is disabled - `is_enabled()` is False and the
settings UI says so - rather than falling back to storing plaintext.

    FT_CREDENTIAL_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
"""

import os

from cryptography.fernet import Fernet, InvalidToken

_ENV = "FT_CREDENTIAL_KEY"


def is_enabled() -> bool:
    return bool(os.environ.get(_ENV))


def _fernet() -> Fernet:
    key = os.environ.get(_ENV)
    if not key:
        raise RuntimeError(
            f"{_ENV} is not set - per-user Firstrade credential storage is disabled"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:  # wrong key, or corrupted ciphertext
        raise ValueError("could not decrypt - FT_CREDENTIAL_KEY changed or data corrupted") from e
