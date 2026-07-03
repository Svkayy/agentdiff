import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def generate_api_key() -> tuple[str, str, str]:
    body = secrets.token_urlsafe(32)
    full = f"adk_{body}"
    prefix = full[:12]
    return full, prefix, _ph.hash(full)


def verify_api_key(full_key: str, key_hash: str) -> bool:
    try:
        return _ph.verify(key_hash, full_key)
    except VerifyMismatchError:
        return False
    except Exception:
        return False
