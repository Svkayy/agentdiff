from cryptography.fernet import Fernet, MultiFernet
from server.config import get_settings


def _fernet(key_string: str | None = None) -> MultiFernet | Fernet:
    """Build a Fernet (or MultiFernet for rotation) from a comma-separated key string.

    The first key is used for encryption; all keys are tried for decryption.
    Accepts an explicit key_string for testing; defaults to settings value.
    """
    raw = key_string if key_string is not None else get_settings().secret_encryption_key
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise ValueError("AGENTDIFF_SECRET_ENCRYPTION_KEY must be set")
    if len(keys) == 1:
        return Fernet(keys[0].encode())
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
