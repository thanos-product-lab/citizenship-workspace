"""Clerk JWT verification and the `get_current_user` FastAPI dependency.

The security-sensitive rules live in `decode_clerk_jwt`:

- `algorithms=["RS256"]` — the whitelist is what rejects `alg:none` and HS* tokens.
- issuer is verified against the configured Clerk instance.
- `exp` and `iat` are required and verified (rejects expired / undated tokens).
- audience is verified only when configured (Clerk's default session token has
  no `aud`); otherwise we anchor on issuer + signature + expiry.
- `azp` (authorized party) is checked against an allow-list when configured.
"""

from typing import Annotated, Any

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import jwks
from app.auth.schemas import CurrentUser
from app.core.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)
_log = structlog.get_logger()

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing authentication",
    headers={"WWW-Authenticate": "Bearer"},
)


def decode_clerk_jwt(token: str, signing_key: Any, settings: Settings) -> dict[str, Any]:
    """Verify and decode a Clerk session JWT. Raises `jwt.PyJWTError` on failure."""
    claims: dict[str, Any] = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=settings.clerk_issuer or None,
        audience=settings.clerk_audience,
        options={
            "require": ["exp", "iat"],
            "verify_iss": bool(settings.clerk_issuer),
            "verify_aud": settings.clerk_audience is not None,
        },
    )
    parties = {p.strip() for p in settings.clerk_authorized_parties.split(",") if p.strip()}
    if parties and claims.get("azp") not in parties:
        raise jwt.InvalidTokenError("azp not in authorized parties")
    return claims


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    # Fail closed, explicitly: without a configured issuer we cannot verify the
    # `iss` claim, so refuse all tokens rather than accept unverified ones.
    if not settings.clerk_issuer:
        _log.warning("auth.rejected", reason="clerk_issuer_unset")
        raise _UNAUTHORIZED
    if credentials is None or not credentials.credentials:
        _log.info("auth.rejected", reason="missing_bearer")
        raise _UNAUTHORIZED
    token = credentials.credentials
    try:
        signing_key = jwks.get_signing_key(token)
        claims = decode_clerk_jwt(token, signing_key, settings)
    except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
        # reason/detail describe the failure type only — never the token or PII.
        _log.info("auth.rejected", reason=exc.__class__.__name__, detail=str(exc))
        raise _UNAUTHORIZED from exc

    sub = claims.get("sub")
    if not isinstance(sub, str):
        _log.info("auth.rejected", reason="missing_subject")
        raise _UNAUTHORIZED
    sid = claims.get("sid")
    email = claims.get("email")
    return CurrentUser(
        user_id=sub,
        session_id=sid if isinstance(sid, str) else None,
        email=email if isinstance(email, str) else None,
    )
