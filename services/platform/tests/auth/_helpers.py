"""Shared test helpers: a local RSA keypair and a token minter.

Signing tokens with our own key lets the full verification matrix run without a
live Clerk instance.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, generate_private_key

ISSUER = "https://test.clerk"


def generate_keypair() -> RSAPrivateKey:
    return generate_private_key(public_exponent=65537, key_size=2048)


def make_token(private_key: RSAPrivateKey, *, kid: str = "test-kid", **overrides: Any) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": "user_123",
        "sid": "sess_1",
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
