import jwt


def load_jwks_pubkey(jwks_url: str) -> str:
    # Fetch the Clerk signing key. Isolated here so tests monkeypatch it with a
    # local public key instead of hitting the network.
    from jwt import PyJWKClient

    return PyJWKClient(jwks_url).get_signing_keys()[0].key


def verify_token(token: str, jwks_pubkey, issuer: str) -> dict:
    try:
        return jwt.decode(
            token,
            jwks_pubkey,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        raise ValueError(str(exc)) from exc
