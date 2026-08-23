"""Storage **security** properties, against a real MinIO.

This is the only file permitted to assert that a bucket is private, that a presigned
URL expires, or that a deleted object is gone. Those are properties of the storage
service; the in-process fake has no bucket policy to be wrong about and no clock to run
out, so a test of it could only ever assert something about itself.

Marked `minio`. Where `CW_EXPECT_MINIO=1` (CI), an unreachable store fails the run
rather than skipping it — see `conftest.py`.
"""

import time
import uuid

import httpx
import pytest

from app.core.storage import PresignedUpload, S3Storage, build_key

pytestmark = pytest.mark.minio

_BODY = b"%PDF-1.7 hello"
_MAX_BYTES = 1024


def _key() -> str:
    return build_key(case_id=uuid.uuid4())


def _post(signed: PresignedUpload, body: bytes, media_type: str) -> int:
    """Send a multipart POST exactly as a browser would: signed fields, then the file."""
    return httpx.post(
        signed.url,
        data=signed.fields,
        files={"file": ("document", body, media_type)},
    ).status_code


def _upload(storage: S3Storage, *, key: str | None = None) -> str:
    """Put one object there through the presigned path a real client would use."""
    key = key or _key()
    signed = storage.presigned_upload(
        key, media_type="application/pdf", ttl_seconds=60, max_bytes=_MAX_BYTES
    )
    assert _post(signed, _BODY, "application/pdf") in {200, 204}
    return key


def test_an_object_is_not_readable_without_a_signature(minio_storage: S3Storage) -> None:
    """The property the whole milestone rests on: MVP §8.9, "Documents are not publicly
    accessible." An unsigned GET at the object's own address must be refused."""
    key = _upload(minio_storage)

    unsigned = f"{minio_storage.endpoint_url}/{minio_storage.bucket}/{key}"
    assert httpx.get(unsigned).status_code in {401, 403}


def test_a_presigned_url_stops_working_when_it_expires(minio_storage: S3Storage) -> None:
    """MVP §8.9: "Upload URLs expire." A presigned URL cannot be revoked (ADR-0018), so
    its TTL is the entire bound on its life — which makes the TTL actually elapsing the
    only thing standing between an issued URL and an indefinite one."""
    key = _upload(minio_storage)

    url = minio_storage.presigned_get_url(key, ttl_seconds=1)
    assert httpx.get(url).status_code == 200
    time.sleep(2)
    assert httpx.get(url).status_code == 403


def test_an_old_signed_url_cannot_reach_a_deleted_object(minio_storage: S3Storage) -> None:
    """MVP §8.9: "Old signed URLs cannot access deleted files." Not because the URL is
    revoked — it is not — but because there is nothing behind it once the purge runs.
    This is the assertion that makes Domain §51.1 step 3 mean something."""
    key = _upload(minio_storage)

    url = minio_storage.presigned_get_url(key, ttl_seconds=300)
    assert httpx.get(url).status_code == 200

    minio_storage.delete(key)
    assert httpx.get(url).status_code == 404
    assert minio_storage.head(key) is None


def test_an_upload_cannot_declare_a_different_content_type_than_the_one_signed(
    minio_storage: S3Storage,
) -> None:
    """The content type is inside the signed policy, so the media type the server
    authorised is the only one that can be uploaded. This is the first half of
    "unsupported file types are rejected before processing" — the magic-byte check in
    the worker is the second, because a client controls the bytes even when it cannot
    control the label."""
    key = _key()
    signed = minio_storage.presigned_upload(
        key, media_type="application/pdf", ttl_seconds=60, max_bytes=_MAX_BYTES
    )
    # The policy constrains the `Content-Type` *form field*, so that is what has to be
    # tampered with. The first version of this test varied the multipart part header
    # instead and got a 204 — the upload succeeded, because the signed field still said
    # application/pdf. The condition was doing its job; the test was aiming past it.
    tampered = PresignedUpload(
        url=signed.url,
        fields={**signed.fields, "Content-Type": "application/x-msdownload"},
    )
    assert _post(tampered, b"MZ\x90\x00", "application/x-msdownload") == 403
    assert minio_storage.head(key) is None


def test_an_oversized_body_is_refused_by_the_store_and_nothing_is_written(
    minio_storage: S3Storage,
) -> None:
    """The size ceiling is a control, not a check that runs afterwards.

    A presigned PUT signs only the key and the type, so a client that declared ten bytes
    could upload forty megabytes and the object would already be sitting in a private
    bucket before anything looked at it. A presigned POST carries `content-length-range`
    in the signed policy, so the store refuses the body itself — and the assertion that
    matters is the second one: nothing was written.
    """
    key = _key()
    signed = minio_storage.presigned_upload(
        key, media_type="application/pdf", ttl_seconds=60, max_bytes=_MAX_BYTES
    )
    assert _post(signed, b"%PDF-1.7" + b"x" * (_MAX_BYTES * 4), "application/pdf") == 400
    assert minio_storage.head(key) is None


def test_an_empty_body_is_refused(minio_storage: S3Storage) -> None:
    """A zero-byte file is not a document, and the policy's lower bound says so."""
    key = _key()
    signed = minio_storage.presigned_upload(
        key, media_type="application/pdf", ttl_seconds=60, max_bytes=_MAX_BYTES
    )
    assert _post(signed, b"", "application/pdf") == 400
    assert minio_storage.head(key) is None


def test_the_download_disposition_reaches_the_response(minio_storage: S3Storage) -> None:
    key = _upload(minio_storage)

    url = minio_storage.presigned_get_url(key, ttl_seconds=60, download_filename="a\r\nb.pdf")
    disposition = httpx.get(url).headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
