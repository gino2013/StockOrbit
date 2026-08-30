import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet


def demo():
    from app.infrastructure import crypto

    # disabled when the key is absent
    os.environ.pop("FT_CREDENTIAL_KEY", None)
    assert crypto.is_enabled() is False
    try:
        crypto.encrypt("x")
        assert False, "expected RuntimeError with no key"
    except RuntimeError:
        pass

    key = Fernet.generate_key().decode()
    os.environ["FT_CREDENTIAL_KEY"] = key
    assert crypto.is_enabled() is True

    secret = "s3cr3t-totp-ABCDEFGH 中文"
    token = crypto.encrypt(secret)
    assert token != secret
    assert crypto.decrypt(token) == secret

    # a different key cannot read it
    os.environ["FT_CREDENTIAL_KEY"] = Fernet.generate_key().decode()
    try:
        crypto.decrypt(token)
        assert False, "expected ValueError decrypting with the wrong key"
    except ValueError:
        pass


if __name__ == "__main__":
    demo()
    print("OK")
