"""Clerk JWKS access.

`PyJWKClient` handles fetching the JSON Web Key Set, caching it, and refetching
when a token presents an unknown `kid` (key rotation). The client is a lazily
created singleton so importing the app never performs network I/O.
"""

from functools import lru_cache
from typing import Any

import jwt

from app.core.config import get_settings


@lru_cache
def get_jwk_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().resolved_jwks_url)


def get_signing_key(token: str) -> Any:
    """Return the public signing key for `token`, selected by its `kid`.

    Raises `jwt.PyJWKClientError` if the key set can't be fetched or the `kid`
    is unknown. Kept as a module function so tests can substitute it.
    """
    return get_jwk_client().get_signing_key_from_jwt(token).key
