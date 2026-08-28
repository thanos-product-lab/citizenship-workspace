"""The signed upload token: how a storage key survives a round trip to the client.

The upload is two HTTP calls with a direct-to-storage PUT between them, and the storage
key has to reach the second call. Three ways to do that, two of them wrong:

- **Let the client send the key back.** A client-supplied key is a client-supplied
  storage path, which threat model §12 forbids outright.
- **Persist a reservation row and look the key up.** Safe, but it writes case-scoped
  state before anything has happened, which either leaves orphan rows behind every
  abandoned upload or forces a domain event for a non-event. `UnitOfWork` exists to make
  "state written with no event emitted" impossible, and working around it for the first
  new aggregate in five milestones is the wrong direction.
- **Hand the client a token the server signed.** The key travels through the client but
  the client cannot change it: any edit invalidates the HMAC. Nothing is persisted until
  the bytes actually exist, so an abandoned upload leaves exactly nothing.

The third is what this is. The token binds the key to the case that authorised it, to
the media type baked into the presigned PUT's own signature, and to an expiry — so a
token cannot be replayed into a different case, cannot be re-pointed at another object,
and cannot outlive the URL it accompanies.

It is not a capability: presenting a valid token still proves nothing about ownership.
Completion re-runs `require_case_access` like every other route, and the token's case id
must match the case in the path. It carries integrity, not authority.
"""

import base64
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from hashlib import sha256

import structlog

from app.core.config import LOCAL_ENVIRONMENTS, get_settings
from app.shared.errors import InvalidUploadGrant

_log = structlog.get_logger()

# Regenerated per process when nothing is configured. Fine for a single local API;
# with more than one replica an unset secret means a token signed by one instance is
# rejected by another, so `check_upload_secret` warns at boot exactly as the superuser
# login role does.
_FALLBACK_SECRET = secrets.token_bytes(32)

#: A configured key shorter than this is weaker than the fallback it replaces.
_MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class UploadGrant:
    case_id: uuid.UUID
    storage_key: str
    media_type: str
    expires_at: int


def _now() -> int:
    """The current time, as one named seam. Exists so a test can move the clock without
    reaching into this module's imports or sleeping through a real TTL."""
    return int(time.time())


def _secret() -> bytes:
    configured = get_settings().upload_token_secret
    return configured.encode() if configured else _FALLBACK_SECRET


def check_upload_secret() -> None:
    """Refuse to boot without a signing key anywhere it matters.

    A per-process key is fine for one local API. Deployed across replicas it is not:
    a token signed by one instance is rejected by another, and the symptom is
    intermittent 422s that look exactly like tampering. That is a bad thing to discover
    from a support conversation, so it fails at boot instead of warning into a log.
    """
    settings = get_settings()
    if settings.upload_token_secret:
        if len(settings.upload_token_secret) < _MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"UPLOAD_TOKEN_SECRET must be at least {_MIN_SECRET_LENGTH} characters"
            )
        return
    if settings.environment not in LOCAL_ENVIRONMENTS:
        # Name what was actually observed. A bare "must be set" cannot distinguish
        # "never set it" from "set it on the wrong service", "set it as a shared
        # variable the service does not reference", or "set it and did not redeploy" —
        # and those are the four ways this goes wrong on a platform. Presence is not a
        # secret; the value is never logged or raised.
        raise RuntimeError(
            "UPLOAD_TOKEN_SECRET must be set outside local development: upload tokens "
            "signed with a per-process key do not verify across API replicas. "
            f"Observed ENVIRONMENT={settings.environment!r}; UPLOAD_TOKEN_SECRET was "
            "absent or empty in this process's environment. Set it on the API service "
            "itself (a project-level shared variable must still be referenced by the "
            "service) and redeploy."
        )
    _log.warning(
        "storage.upload_secret_unset",
        detail=(
            "UPLOAD_TOKEN_SECRET is unset; upload tokens are signed with a "
            "per-process key and will not verify across API replicas"
        ),
    )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue(*, case_id: uuid.UUID, storage_key: str, media_type: str, ttl_seconds: int) -> str:
    body = _b64(
        json.dumps(
            {
                "case_id": str(case_id),
                "storage_key": storage_key,
                "media_type": media_type,
                "exp": _now() + ttl_seconds,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    signature = _b64(hmac.new(_secret(), body.encode(), sha256).digest())
    return f"{body}.{signature}"


def verify(token: str, *, case_id: uuid.UUID) -> UploadGrant:
    """Return the grant this token carries, or raise.

    The signature is checked with `compare_digest` before the payload is parsed, so a
    forged token cannot reach the JSON decoder and timing does not leak how much of a
    guess was right.
    """
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise InvalidUploadGrant("malformed upload token") from exc

    expected = _b64(hmac.new(_secret(), body.encode(), sha256).digest())
    if not hmac.compare_digest(expected, signature):
        raise InvalidUploadGrant("upload token signature does not verify")

    try:
        claims = json.loads(_unb64(body))
        grant = UploadGrant(
            case_id=uuid.UUID(claims["case_id"]),
            storage_key=claims["storage_key"],
            media_type=claims["media_type"],
            expires_at=int(claims["exp"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidUploadGrant("malformed upload token") from exc

    if grant.expires_at < _now():
        raise InvalidUploadGrant("the upload token has expired")
    if grant.case_id != case_id:
        # A token minted for one case, presented against another. Ownership is already
        # settled by `require_case_access`; this stops a user replaying their own token
        # across their own cases and filing a document against the wrong one.
        raise InvalidUploadGrant("the upload token is for a different case")
    return grant
