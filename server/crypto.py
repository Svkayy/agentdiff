from cryptography.fernet import Fernet
from server.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().secret_encryption_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
