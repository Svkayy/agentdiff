import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from server import clerk
from server.deps import get_user_ctx


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub


def test_verify_token_ok():
    priv, pub = _keypair()
    token = jwt.encode(
        {"sub": "user_1", "org_id": "org_1", "iss": "https://clerk.test"},
        priv,
        algorithm="RS256",
    )
    claims = clerk.verify_token(token, jwks_pubkey=pub, issuer="https://clerk.test")
    assert claims["sub"] == "user_1"


def test_verify_token_bad_issuer():
    priv, pub = _keypair()
    token = jwt.encode({"sub": "u", "iss": "https://evil"}, priv, algorithm="RS256")
    with pytest.raises(ValueError):
        clerk.verify_token(token, jwks_pubkey=pub, issuer="https://clerk.test")


@pytest.mark.asyncio(loop_scope="session")
async def test_get_user_ctx_missing_header_raises_401(session):
    # No Authorization header (None) must raise 401.
    with pytest.raises(HTTPException) as exc_info:
        await get_user_ctx(None, session)
    assert exc_info.value.status_code == 401

    # A non-Bearer value must also raise 401.
    with pytest.raises(HTTPException) as exc_info:
        await get_user_ctx("garbage", session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_get_user_ctx_upserts(session, monkeypatch):
    priv, pub = _keypair()
    token = jwt.encode(
        {"sub": "user_9", "org_id": "org_9", "email": "a@b.co", "iss": "https://clerk.test"},
        priv,
        algorithm="RS256",
    )
    monkeypatch.setattr(clerk, "load_jwks_pubkey", lambda url: pub)
    user, org = await get_user_ctx(f"Bearer {token}", session)
    assert user.clerk_user_id == "user_9"
    assert org.clerk_org_id == "org_9"

    # Second call — must not create duplicate rows (idempotent upsert)
    user2, org2 = await get_user_ctx(f"Bearer {token}", session)
    assert user2.clerk_user_id == "user_9"
    assert org2.clerk_org_id == "org_9"
