"""Clerk JWKS access.

`PyJWKClient` handles fetching the JSON Web Key Set, caching it, and refetching
when a token presents an unknown `kid` (key rotation). The client is a lazily
created singleton so importing the app never performs network I/O.
"""

import ssl
from functools import lru_cache
from typing import Any

import certifi
import jwt

from app.core.config import get_settings


@lru_cache
def get_jwk_client() -> jwt.PyJWKClient:
    # Verify TLS against certifi's CA bundle so JWKS fetches work on any platform.
    # (macOS Python — including uv-managed builds — often can't reach the system
    # root certificates, which fails the HTTPS fetch to Clerk's JWKS endpoint.)
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return jwt.PyJWKClient(get_settings().resolved_jwks_url, ssl_context=ssl_context)


def get_signing_key(token: str) -> Any:
    """Return the public signing key for `token`, selected by its `kid`.

    Raises `jwt.PyJWKClientError` if the key set can't be fetched or the `kid`
    is unknown. Kept as a module function so tests can substitute it.
    """
    return get_jwk_client().get_signing_key_from_jwt(token).key
