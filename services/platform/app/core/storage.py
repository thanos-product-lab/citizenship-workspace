"""Private object storage for evidence files.

Two implementations behind one protocol.

`S3Storage` is the real one: an S3-compatible private bucket (MinIO locally, any S3
in deployment), reached only through short-lived presigned URLs that the server issues
after an ownership check.

`InMemoryStorage` is a fake, and its limits are the point. It exists so that
`just seed` and every test that is *not* about storage can run without MinIO. It
asserts behaviour — a key round-trips, a missing key raises, presign returns a URL —
and it can assert nothing about privacy, expiry, or deletion, because those are
properties of the storage service rather than of this code. **No test using the fake
may claim a security property.** Those live in `tests/evidence/test_storage_minio.py`,
which runs against a real MinIO and is guarded by a test that fails if it silently
collected nothing.

Two invariants hold in both implementations:

- **Storage keys are generated here, never derived from a filename.** Threat model §12:
  "Original filenames are metadata only and never determine storage paths."
- **A storage key is not a permission** (Domain §52). `build_key` puts the case id in
  the path for operational legibility only; nothing anywhere may read authorisation out
  of a key.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings


class StorageError(RuntimeError):
    """The store could not be reached or refused an operation."""


@dataclass(frozen=True)
class PresignedUpload:
    """A presigned POST: the URL to send to, and the fields that must accompany the file.

    A presigned **POST** rather than a presigned PUT, because only POST can carry a
    policy — and the policy is what puts the size ceiling on the *store* rather than on
    a promise. `declared_size_bytes` is a client's claim; a PUT signed from it accepts a
    40 MB body just as happily as a 10 byte one, and the oversize is then already
    written to a private bucket with no row naming it. With `content-length-range` in
    the policy the store refuses the body itself.
    """

    url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class StoredObject:
    """What the store reports about an object that exists."""

    size_bytes: int
    etag: str


def build_key(*, case_id: uuid.UUID) -> str:
    """A server-generated, non-semantic storage key.

    The random component is what makes the key unguessable; the case id makes an object
    traceable to a case when someone is staring at a bucket listing during an incident.
    Neither is a credential — Domain §52, and every read path re-checks ownership.

    There is deliberately no evidence-item id in the path. The key is minted *before*
    any row exists (ADR-0019), so an item id here could only be a throwaway that never
    becomes the item's real id — a segment that looks traceable and is not, which is
    worse than one that does not pretend.
    """
    return f"cases/{case_id}/evidence/{secrets.token_urlsafe(24)}"


class StorageAdapter(Protocol):
    def ensure_bucket(self) -> None: ...

    def presigned_upload(
        self, key: str, *, media_type: str, ttl_seconds: int, max_bytes: int
    ) -> PresignedUpload: ...

    def presigned_get_url(
        self, key: str, *, ttl_seconds: int, download_filename: str | None = None
    ) -> str: ...

    def head(self, key: str) -> StoredObject | None: ...

    def read_prefix(self, key: str, *, length: int) -> bytes: ...

    def read(self, key: str, *, max_bytes: int) -> bytes: ...

    def delete(self, key: str) -> None: ...


# --- Content-Disposition -----------------------------------------------------------
#
# `original_filename` is untrusted user input reaching an HTTP header. A filename
# containing CR or LF splits the header (CWE-93 / CWE-113); one containing a quote
# breaks out of the quoted-string. React escapes it in the library view, but a header
# has no such protection, so it is encoded here, once, at the boundary.

_ASCII_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. ()[]")
_FALLBACK_FILENAME = "document"
_MAX_FILENAME = 120


def content_disposition(filename: str | None) -> str:
    """An `attachment` Content-Disposition for a user-supplied filename, per RFC 6266.

    Emits both forms: a conservative ASCII `filename=` that every client understands,
    and `filename*=UTF-8''…` percent-encoded for the ones that read it. The result is
    always a single line — that is the property the CRLF test pins.
    """
    raw = (filename or "").strip()[:_MAX_FILENAME]
    # Truncate at the first control character rather than filtering them out. Filtering
    # keeps the injected *payload* while dropping only the delimiter - "a.pdf\r\nSet-Cookie:
    # x" becomes "a.pdfSet-Cookie x", which cannot split the header but does put an
    # attacker's text in front of the user as their own filename. Anything after a control
    # character is hostile or broken; keeping the prefix is the honest reading.
    for index, char in enumerate(raw):
        if ord(char) < 32 or ord(char) == 127:
            raw = raw[:index]
            break
    ascii_name = "".join(c for c in raw if c in _ASCII_SAFE).strip() or _FALLBACK_FILENAME
    encoded = quote(raw.strip() or _FALLBACK_FILENAME, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


# --- S3 ----------------------------------------------------------------------------


class S3Storage:
    """An S3-compatible private bucket."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.storage_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url or None,
            aws_access_key_id=settings.storage_access_key or None,
            aws_secret_access_key=settings.storage_secret_key or None,
            region_name=settings.storage_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        # A second client, used *only* to sign URLs the browser will follow.
        #
        # The server and the browser do not always reach the store at the same address.
        # In local compose the API talks to `http://minio:9000` over the docker network,
        # a hostname that does not resolve on the developer's machine — so every URL
        # signed for the browser named a host it could not reach, and the upload failed
        # with a bare "That document was not uploaded". Nothing was wrong with the
        # signature, the policy, or the store.
        #
        # Rewriting the host afterwards is not an option: a presigned **GET** signs the
        # host as part of SigV4, so a rewritten URL is an invalid one. The address has to
        # be correct at signing time, which is why this is a second client rather than a
        # string replacement.
        #
        # Deployed, `storage_public_endpoint_url` is unset and this *is* `_client` — the
        # API and the browser both reach real S3 at the same address, and there is no
        # second endpoint to get wrong.
        self._signing_client = self._client
        if settings.storage_public_endpoint_url:
            self._signing_client = boto3.client(
                "s3",
                endpoint_url=settings.storage_public_endpoint_url,
                aws_access_key_id=settings.storage_access_key or None,
                aws_secret_access_key=settings.storage_secret_key or None,
                region_name=settings.storage_region,
                config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
            )

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def endpoint_url(self) -> str:
        """The store's base URL. Exposed so the storage security tests can address an
        object *without* a signature, which is the only way to prove it is refused."""
        return str(self._client.meta.endpoint_url).rstrip("/")

    def ensure_bucket(self) -> None:
        """Create the bucket if absent. It is private: no bucket policy is applied and
        no ACL is set, so the S3 default of owner-only access stands. That the bucket
        is genuinely unreadable is asserted in the MinIO-marked tests, not here."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except ClientError as exc:  # pragma: no cover - depends on live storage
                raise StorageError("could not create the evidence bucket") from exc

    def presigned_upload(
        self, key: str, *, media_type: str, ttl_seconds: int, max_bytes: int
    ) -> PresignedUpload:
        """Authorise one upload: this key, this media type, at most this many bytes.

        All three are inside the signed policy, so none of them is a request the client
        can restate. An oversized or mistyped body is refused by the store with a 400
        and nothing is written — which is what makes "the size limit" a control rather
        than a check that runs after the damage.
        """
        signed = self._signing_client.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": media_type},
            Conditions=[
                {"Content-Type": media_type},
                ["content-length-range", 1, max_bytes],
                # A zero-byte file is not a document; the ceiling is the real bound.
            ],
            ExpiresIn=ttl_seconds,
        )
        return PresignedUpload(
            url=str(signed["url"]),
            fields={str(k): str(v) for k, v in signed["fields"].items()},
        )

    def presigned_get_url(
        self, key: str, *, ttl_seconds: int, download_filename: str | None = None
    ) -> str:
        params: dict[str, str] = {"Bucket": self._bucket, "Key": key}
        if download_filename is not None:
            params["ResponseContentDisposition"] = content_disposition(download_filename)
        return str(
            self._signing_client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=ttl_seconds
            )
        )

    def head(self, key: str) -> StoredObject | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise StorageError("could not read object metadata") from exc
        return StoredObject(
            size_bytes=int(response["ContentLength"]),
            etag=str(response["ETag"]).strip('"'),
        )

    def read_prefix(self, key: str, *, length: int) -> bytes:
        """The object's first bytes, as a ranged GET.

        A range rather than a download: the caller is deciding whether these bytes are
        what they claim to be, and pulling twenty megabytes of an attacker-controlled
        file into memory to look at its first eight is the wrong order to do that in.
        """
        try:
            response = self._client.get_object(
                Bucket=self._bucket, Key=key, Range=f"bytes=0-{max(length - 1, 0)}"
            )
            return bytes(response["Body"].read())
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return b""
            raise StorageError("could not read object content") from exc

    def read(self, key: str, *, max_bytes: int) -> bytes:
        """The whole object, up to a ceiling.

        `max_bytes` is not belt-and-braces over the upload limit: the upload policy
        bounds what a *client* can put there, and this bounds what the worker will pull
        into memory regardless of how the object came to be that size. A ranged GET means
        the ceiling is enforced by the store rather than by us remembering to stop
        reading.
        """
        try:
            response = self._client.get_object(
                Bucket=self._bucket, Key=key, Range=f"bytes=0-{max(max_bytes - 1, 0)}"
            )
            return bytes(response["Body"].read())
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return b""
            raise StorageError("could not read object content") from exc

    def delete(self, key: str) -> None:
        """Idempotent: S3 does not distinguish deleting an absent key from a present
        one, which is what Domain §51.1 needs — deletion must be safe to redeliver."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise StorageError("could not delete object") from exc


# --- In-memory fake ----------------------------------------------------------------


class InMemoryStorage:
    """A behaviour-only fake. See the module docstring for what it may not be used for."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def ensure_bucket(self) -> None:
        return None

    def presigned_upload(
        self, key: str, *, media_type: str, ttl_seconds: int, max_bytes: int
    ) -> PresignedUpload:
        return PresignedUpload(
            url=f"memory://put/{key}",
            fields={
                "key": key,
                "Content-Type": media_type,
                "x-cw-expires": str(ttl_seconds),
                "x-cw-max-bytes": str(max_bytes),
            },
        )

    def presigned_get_url(
        self, key: str, *, ttl_seconds: int, download_filename: str | None = None
    ) -> str:
        return f"memory://get/{key}?expires={ttl_seconds}"

    def head(self, key: str) -> StoredObject | None:
        body = self.objects.get(key)
        if body is None:
            return None
        return StoredObject(size_bytes=len(body), etag=hashlib.md5(body).hexdigest())

    def read_prefix(self, key: str, *, length: int) -> bytes:
        return self.objects.get(key, b"")[:length]

    def read(self, key: str, *, max_bytes: int) -> bytes:
        return self.objects.get(key, b"")[:max_bytes]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    # Test affordance: the fake has no HTTP endpoint, so a test that needs an object
    # to exist puts it here directly.
    def put(self, key: str, body: bytes) -> None:
        self.objects[key] = body


_storage: StorageAdapter | None = None


def get_storage() -> StorageAdapter:
    global _storage
    if _storage is None:
        settings = get_settings()
        if settings.storage_backend == "memory":
            _storage = InMemoryStorage()
        else:
            _storage = S3Storage(settings)
    return _storage


def reset_storage() -> None:
    """Drop the cached adapter. For tests that switch backends."""
    global _storage
    _storage = None
